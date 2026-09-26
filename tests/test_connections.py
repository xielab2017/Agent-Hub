"""Multi-vendor connections: several keys at once, per-tier vendors with their own endpoint / key / TLS."""

from __future__ import annotations

import contextlib
import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@contextlib.contextmanager
def state():
    """Temp config + secrets files; no OS env keys leak in."""
    from ali import secrets, settings

    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        env = {k: "" for k in ("MINIMAX_API_KEY", "MINIMAX_CN_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY",
                               "MOONSHOT_API_KEY", "KIMI_API_KEY", "DASHSCOPE_API_KEY", "ANTHROPIC_API_KEY")}
        with mock.patch.object(settings, "CAMPUS_CONFIG_FILE", t / "campus.json"), \
                mock.patch.object(settings, "ensure_state_dirs", lambda: None), \
                mock.patch.object(secrets, "SECRETS_FILE", t / "secrets.json"), \
                mock.patch.dict("os.environ", env), \
                mock.patch("ali.audit.log_event", lambda *a, **k: None):
            cfg = settings.load_campus_config()
            cfg["backend"] = {**cfg["backend"], "type": "minimax-cn", "base_url": "https://api.minimax.cn/anthropic"}
            settings.save_campus_config(cfg)
            yield t


def test_saving_several_vendor_keys_never_switches_the_backend():
    from ali import connections, settings
    from ali.secrets import get_api_key

    with state() as t:
        connections.save("deepseek", {"api_key": "sk-deepseek-aaaaaaaaaaaaaaaa"})
        connections.save("kimi", {"api_key": "sk-kimi-bbbbbbbbbbbbbbbbbbbb", "verify_tls": False})
        cfg = settings.load_campus_config()
        assert cfg["backend"]["type"] == "minimax-cn"
        assert get_api_key("deepseek").startswith("sk-deepseek") and get_api_key("kimi").startswith("sk-kimi")
        assert "sk-" not in (t / "campus.json").read_text()  # keys only in the secrets store
        view = {c["provider"]: c for c in connections.view()["connections"]}
        assert view["deepseek"]["enabled"] and view["deepseek"]["key_present"] and "api_key" not in view["deepseek"]
        assert view["deepseek"]["key_masked"].startswith("sk-d") and "aaaaaaaa" not in view["deepseek"]["key_masked"]
        assert view["kimi"]["verify_tls"] is False
        assert view["minimax-cn"]["base_url"] == "https://api.minimax.cn/anthropic"  # the single backend's URL
        connections.save("deepseek", {"clear": True})
        assert get_api_key("deepseek") == ""


def test_base_url_override_rules():
    from ali import connections
    from ali.providers import connection_base_url
    from ali.settings import load_campus_config

    with state():
        connections.save("minimax-cn", {"base_url": "https://evil.example/v1"})
        assert connection_base_url(load_campus_config(), "minimax-cn") == "https://api.minimaxi.com/v1"  # not allowed
        connections.save("minimax-cn", {"base_url": "https://api.minimax.cn/anthropic"})
        assert connection_base_url(load_campus_config(), "minimax-cn") == "https://api.minimax.cn/anthropic"
        connections.save("campus-openai-compatible", {"base_url": "http://10.1.2.3:8000/v1", "custom_base_url": True})
        assert connection_base_url(load_campus_config(), "campus-openai-compatible") == "http://10.1.2.3:8000/v1"


def test_tiers_route_to_each_vendor_with_its_own_endpoint_key_and_tls():
    from ali import connections
    from ali.providers import hub_model
    from ali.settings import load_campus_config

    with state():
        connections.save("minimax-cn", {"api_key": "sk-cp-minimaxkeyxxxxxxxxxxxxxxxx"})
        connections.save("deepseek", {"api_key": "sk-deepseek-aaaaaaaaaaaaaaaa"})
        connections.save("kimi", {"api_key": "sk-kimi-bbbbbbbbbbbbbbbbbbbb", "verify_tls": False})
        connections.set_tier("simple", "deepseek", "deepseek-chat")
        connections.set_tier("office", "minimax-cn", "MiniMax-M3")
        rows = {r["route_key"]: r for r in connections.set_tier("reasoning", "kimi", "kimi-k2-thinking")["routes"]}
        cfg = load_campus_config()
        assert cfg["backend"]["type"] == "hybrid" and cfg["backend"]["previous_type"] == "minimax-cn"
        assert rows["simple"]["provider"] == "deepseek" and rows["simple"]["base_url"] == "https://api.deepseek.com/v1"
        # the old single backend's endpoint (…/anthropic) survives the switch to hybrid
        assert rows["office"]["provider"] == "minimax-cn" and rows["office"]["base_url"].endswith("/anthropic")
        assert rows["reasoning"]["provider"] == "kimi" and all(r["key_present"] for r in rows.values()
                                                              if r["route_key"] != "vision")
        hm = hub_model(cfg, "reasoning")
        assert hm["api_key"].startswith("sk-kimi") and hm["verify_tls"] is False
        assert hub_model(cfg, "vision")["provider"] == "minimax-cn"  # unbound tier → office vendor
        with pytest.raises(ValueError):
            connections.set_tier("office", "no-such-vendor", "x")


def test_hub_llm_works_under_hybrid():
    from ali import connections
    from ali.review_writer import HubLLM

    with state():
        connections.save("deepseek", {"api_key": "sk-deepseek-aaaaaaaaaaaaaaaa"})
        connections.save("minimax-cn", {"api_key": "sk-cp-minimaxkeyxxxxxxxxxxxxxxxx"})
        connections.set_tier("office", "minimax-cn", "MiniMax-M3")
        connections.set_tier("reasoning", "deepseek", "deepseek-reasoner")
        office = HubLLM()
        assert (office.provider, office.model) == ("minimax-cn", "MiniMax-M3")
        assert office.base_url.endswith("/anthropic") and office.api_key.startswith("sk-cp-")
        reasoning = HubLLM(route_key="reasoning")
        assert reasoning.provider == "deepseek" and reasoning.api_key.startswith("sk-deepseek")


def test_connection_test_lists_models_or_falls_back_to_chat():
    from ali import connections
    from ali.settings import load_campus_config

    with state():
        connections.save("deepseek", {"api_key": "sk-deepseek-aaaaaaaaaaaaaaaa"})
        calls = []

        def lister(base, key, timeout, verify_tls):
            calls.append((base, key))
            return {"ok": True, "models": ["deepseek-chat", "deepseek-reasoner"], "count": 2}

        res = connections.test("deepseek", list_fn=lister)
        assert res["ok"] and calls == [("https://api.deepseek.com/v1", "sk-deepseek-aaaaaaaaaaaaaaaa")]
        cfg = load_campus_config()
        assert cfg["available_models"]["deepseek"] == ["deepseek-chat", "deepseek-reasoner"]
        assert cfg["connection_probes"]["deepseek"]["ok"] is True
        res = connections.test("deepseek", list_fn=lambda *a, **k: {"ok": False, "error": "404 not found"},
                               chat_fn=lambda *a, **k: {"ok": True, "models": [], "count": 0})
        assert res["ok"] and res["via"] == "chat"
        assert not connections.test("openai")["ok"]  # no key
        assert json.dumps(res).count("sk-deepseek") == 0
