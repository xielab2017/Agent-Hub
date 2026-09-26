"""Agent accounts (Claude Code / Codex / Cursor) as model sources in 多模型 API: several signed in at once, tier
routing to an account, HTTP-only Hub calls never sent to an account."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_connections import state  # noqa: E402


def test_a_tier_can_be_bound_to_an_agent_account():
    from ali import connections
    from ali.routing import resolve_route
    from ali.settings import load_campus_config

    with state():
        connections.save("deepseek", {"api_key": "sk-deepseek-aaaaaaaaaaaaaaaa"})
        connections.set_tier("office", "deepseek", "deepseek-chat")
        connections.set_tier("reasoning", "claude-code", "opus")
        cfg = load_campus_config()
        r = resolve_route("reasoning", "证明这个定理", cfg)
        assert r["provider"] == "claude-code" and r["agent_cli"] == "claude-code" and r["model"] == "opus"
        assert r["base_url"] == "" and not r["blocked"]
        o = resolve_route("office", "写一封会议通知", cfg)
        assert o["provider"] == "deepseek" and o["agent_cli"] == ""
        cfg["data_policy"] = "restricted"
        assert resolve_route("reasoning", "x", cfg)["blocked"]  # an agent account is an external service
        with pytest.raises(ValueError):
            connections.set_tier("office", "no-such-agent", "")


def test_hub_calls_never_go_to_an_agent_account():
    from ali import connections
    from ali.providers import hub_model
    from ali.settings import load_campus_config

    with state():
        connections.save("deepseek", {"api_key": "sk-deepseek-aaaaaaaaaaaaaaaa"})
        connections.set_tier("office", "deepseek", "deepseek-chat")
        connections.set_tier("reasoning", "codex", "")
        hm = hub_model(load_campus_config(), "reasoning")  # e.g. the review skill's reviewers
        assert hm["provider"] == "deepseek" and hm["api_key"].startswith("sk-deepseek")
        for rk in ("simple", "office", "vision"):
            connections.set_tier(rk, "cursor", "")
        cfg = load_campus_config()
        # every tier on an account: the vendor the Hub had before hybrid (minimax-cn) still serves Hub calls
        hm = hub_model(cfg, "office")
        assert hm["provider"] == "minimax-cn" or hm.get("error")


def test_agents_view_lists_every_account_with_its_state():
    from ali import agent_cli, connections

    fakes = ROOT / "tests" / "fakes"
    with state() as t, pytest.MonkeyPatch.context() as mp:
        mp.setenv("PATH", f"{fakes}{os.pathsep}{os.environ['PATH']}")
        mp.setenv("HOME", str(t))
        mp.setenv("CODEX_HOME", str(t / ".codex"))
        mp.setattr(agent_cli, "SESSIONS_FILE", t / "agent-sessions.json")
        agent_cli._HELP_CACHE.clear()
        agent_cli.start_login("cursor", "api_key", api_key="key_cursor_test_000000000000")
        agent_cli.start_login("claude-code", "api_key", api_key="sk-ant-api03-" + "k" * 40)
        connections.set_tier("reasoning", "claude-code", "")
        rows = {a["id"]: a for a in connections.agents_view()["agents"]}
        assert set(rows) == {"claude-code", "codex", "cursor"}
        assert all(r["installed"] for r in rows.values())  # the fakes are on PATH
        assert rows["claude-code"]["logged_in"] and rows["cursor"]["logged_in"]  # two accounts at once
        assert not rows["codex"]["logged_in"] and rows["codex"]["device_login"]
        assert rows["claude-code"]["tiers"] == ["reasoning"]
        dumped = json.dumps(rows)
        assert "key_cursor_test" not in dumped and "sk-ant-api03" not in dumped  # no secrets in the view


E2E = r"""
import json, sys, time
sys.path.insert(0, sys.argv[1])
stub = sys.argv[2]
from ali import agent_cli, connections, streaming, sessions as store
from ali.settings import load_campus_config, save_campus_config
cfg = load_campus_config()
cfg.setdefault("ali", {})["hub_chat_mode"] = "agent"
cfg["backend"] = {**cfg.get("backend", {}), "type": "campus-openai-compatible", "base_url": stub, "model": "stub-model",
                  "verify_tls": False}
save_campus_config(cfg)
connections.save("campus-openai-compatible", {"api_key": "stub-key", "base_url": stub, "verify_tls": False})
connections.set_tier("office", "campus-openai-compatible", "stub-model")
connections.set_tier("reasoning", "claude-code", "opus")
connections.set_tier("simple", "claude-code", "")
agent_cli.start_login("claude-code", "api_key", api_key="sk-ant-api03-" + "k" * 40)
s = store.create_session(title="accounts")
out = []
for text, route in (("证明根号二是无理数", "reasoning"), ("你好", "auto")):
    before = len([m for m in store.get_session(s.id).messages if m.get("role") == "assistant"])
    res = streaming.start_chat(s.id, text, route=route, web_search=False)
    for _ in range(400):
        msgs = [m for m in store.get_session(s.id).messages if m.get("role") == "assistant"]
        if len(msgs) > before:
            break
        time.sleep(0.1)
    m = msgs[-1]
    out.append({"engine": res["route"].get("chat_engine"), "provider": res["route"].get("provider"),
                "content": m["content"][:200]})
print(json.dumps(out, ensure_ascii=False))
"""


def test_chat_on_an_account_tier_runs_that_agent_and_greetings_use_the_api_vendor():
    port = socket.socket()
    port.bind(("127.0.0.1", 0))
    p = port.getsockname()[1]
    port.close()
    stub = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "stub_llm.py"), "--port", str(p)])
    try:
        time.sleep(0.8)
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "argv.jsonl"
            env = {**os.environ, "HERMES_ALI_STATE_DIR": str(Path(tmp) / "state"), "AGENT_CLI_HOME": str(Path(tmp) / "ac"),
                   "HERMES_HOME": str(Path(tmp) / "hermes"), "HOME": tmp, "FAKE_AGENT_LOG": str(log),
                   "PATH": f"{ROOT / 'tests' / 'fakes'}{os.pathsep}/usr/bin:/bin"}
            proc = subprocess.run([sys.executable, "-c", E2E, str(ROOT), f"http://127.0.0.1:{p}/v1"], env=env,
                                  capture_output=True, text=True, timeout=180)
            assert proc.returncode == 0, proc.stderr[-2000:]
            first, greet = json.loads(proc.stdout.strip().splitlines()[-1])
            calls = [json.loads(ln) for ln in log.read_text().splitlines()] if log.exists() else []
    finally:
        stub.terminate()
    assert first["engine"] == "claude-code" and first["content"].startswith("Fake Claude")
    runs = [c["argv"] for c in calls if "-p" in c["argv"]]
    assert runs and runs[0][runs[0].index("--model") + 1] == "opus"  # the tier's model, not the composer's
    assert greet["provider"] == "campus-openai-compatible" and greet["engine"] != "claude-code"
    assert "Stub reply" in greet["content"] or greet["content"]
