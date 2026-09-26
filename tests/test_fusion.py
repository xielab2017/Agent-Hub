"""One model picker for every source; several picked models answer together and one merges them."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_connections import state  # noqa: E402


def test_sources_list_api_vendors_and_accounts_without_secrets():
    from ali import connections

    with state():
        connections.save("deepseek", {"api_key": "sk-deepseek-aaaaaaaaaaaaaaaa"})
        agents = [{"id": "claude-code", "label": "Claude 订阅（Claude Code）", "label_en": "Claude", "installed": True,
                   "logged_in": True},
                  {"id": "cursor", "label": "Cursor 账号（Cursor Agent）", "label_en": "Cursor", "installed": True,
                   "logged_in": False}]
        rows = connections.model_sources(agents=agents)["sources"]
        ids = {r["id"] for r in rows}
        assert "deepseek::deepseek-chat" in ids or any(i.startswith("deepseek::") for i in ids)
        assert {"claude-code::", "claude-code::opus", "cursor::auto"} <= ids
        assert not next(r for r in rows if r["id"] == "cursor::auto")["ready"]  # not signed in: shown, not ready
        assert "sk-deepseek" not in json.dumps(rows)
        assert not any(r["provider"] == "kimi" for r in rows)  # vendors without a key are not offered


def test_pin_source_routes_to_that_vendor_or_account():
    from ali import connections, routing
    from ali.settings import load_campus_config

    with state():
        connections.save("deepseek", {"api_key": "sk-deepseek-aaaaaaaaaaaaaaaa"})
        cfg = load_campus_config()  # the backend is minimax-cn
        r = routing.pin_source("deepseek::deepseek-reasoner", cfg)
        assert r["provider"] == "deepseek" and r["model"] == "deepseek-reasoner"
        assert r["base_url"] == "https://api.deepseek.com/v1" and r["pinned"] and not r["agent_cli"]
        a = routing.pin_source("claude-code::opus", cfg)
        assert a["agent_cli"] == "claude-code" and a["model"] == "opus" and a["base_url"] == ""
        cfg["data_policy"] = "restricted"
        assert routing.pin_source("cursor::", cfg)["blocked"]


def test_fusion_merges_members_and_survives_a_failed_one():
    from ali import fusion

    def fake_api(member, messages, cfg):
        return f"answer from {member['model']}"

    def fake_agent(member, question, preamble, hub_session, cancelled):
        if member["provider"] == "cursor":
            raise RuntimeError("not signed in")
        return f"agent {member['provider']} says hi"

    seen = {}

    def fake_stream(base, key, *, model, messages, **kw):
        seen["prompt"] = messages[-1]["content"]
        return "<think>hidden</think>Merged: A and B agree."

    syn = {"provider": "deepseek", "model": "deepseek-chat", "base_url": "u", "api_key": "k", "verify_tls": True,
           "label": "deepseek-chat"}
    events = []
    with mock.patch.object(fusion, "_ask_api", fake_api), mock.patch.object(fusion, "_ask_agent", fake_agent), \
            mock.patch.object(fusion, "synthesizer", lambda members, cfg: syn), \
            mock.patch("ali.llm_client.stream_chat", fake_stream):
        r = fusion.run("Q?", ["deepseek::deepseek-chat", "claude-code::opus", "cursor::"], cfg={},
                       on_event=lambda k, d: events.append(k))
    assert r["answer"] == "Merged: A and B agree." and r["synthesizer"] == "deepseek-chat"
    ok = {m["source"]: m["ok"] for m in r["members"]}
    assert ok == {"deepseek::deepseek-chat": True, "claude-code::opus": True, "cursor::": False}
    assert "[A] deepseek-chat" in seen["prompt"] and "[B] Claude 订阅 · opus" in seen["prompt"]
    assert "not signed in" in seen["prompt"]  # the synthesizer is told who failed
    assert events.count("member_start") == 3 and events.count("member_done") == 3 and "token" in events
    with mock.patch.object(fusion, "_ask_api", fake_api), mock.patch.object(fusion, "_ask_agent", fake_agent):
        one = fusion.run("Q?", ["deepseek::x", "cursor::"], cfg={})
    assert one["answer"].startswith("answer from x") and "未能融合" in one["answer"]


def test_synthesizer_never_an_agent_account():
    from ali import fusion

    members = fusion.resolve(["claude-code::opus", "deepseek::deepseek-chat"], {})
    with mock.patch("ali.providers.connection", lambda cfg, pid: {"base_url": "u", "api_key": "k", "verify_tls": True}):
        assert fusion.synthesizer(members, {})["provider"] == "deepseek"


E2E = r"""
import json, sys, time
sys.path.insert(0, sys.argv[1])
stub_a, stub_b = sys.argv[2], sys.argv[3]
from ali import agent_cli, connections, streaming, sessions as store
from ali.settings import load_campus_config, save_campus_config
cfg = load_campus_config()
cfg.setdefault("ali", {})["hub_chat_mode"] = "agent"
cfg["backend"] = {**cfg.get("backend", {}), "type": "campus-openai-compatible", "base_url": stub_a, "model": "stub-model",
                  "verify_tls": False}
save_campus_config(cfg)
connections.save("campus-openai-compatible", {"api_key": "stub-key", "base_url": stub_a, "verify_tls": False})
connections.save("local-ollama", {"base_url": stub_b, "verify_tls": False, "custom_base_url": True})
agent_cli.start_login("claude-code", "api_key", api_key="sk-ant-api03-" + "k" * 40)
s = store.create_session(title="fusion")
out = []
for text, models in (("请比较两种 CRISPR 脱靶检测方法", ["local-ollama::stub-model"]),
                     ("请比较两种 CRISPR 脱靶检测方法", ["campus-openai-compatible::stub-model", "claude-code::opus",
                                                    "cursor::"])):
    before = len([m for m in store.get_session(s.id).messages if m.get("role") == "assistant"])
    res = streaming.start_chat(s.id, text, models=models, web_search=False)
    for _ in range(600):
        msgs = [m for m in store.get_session(s.id).messages if m.get("role") == "assistant"]
        if len(msgs) > before:
            break
        time.sleep(0.1)
    m = msgs[-1]
    out.append({"engine": res["route"].get("chat_engine"), "provider": res["route"].get("provider"),
                "content": m["content"][:300], "fusion": (m.get("route") or {}).get("fusion")})
print(json.dumps(out, ensure_ascii=False))
"""


def _free_port() -> int:
    with socket.socket() as sk:
        sk.bind(("127.0.0.1", 0))
        return sk.getsockname()[1]


def test_picker_end_to_end_one_source_and_a_fused_answer():
    pa, pb = _free_port(), _free_port()
    stubs = [subprocess.Popen([sys.executable, str(ROOT / "scripts" / "stub_llm.py"), "--port", str(p), "--tag", t])
             for p, t in ((pa, "A"), (pb, "B"))]
    try:
        time.sleep(0.8)
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "HERMES_ALI_STATE_DIR": str(Path(tmp) / "state"), "AGENT_CLI_HOME": str(Path(tmp) / "ac"),
                   "HERMES_HOME": str(Path(tmp) / "hermes"), "HOME": tmp,
                   "PATH": f"{ROOT / 'tests' / 'fakes'}{os.pathsep}/usr/bin:/bin"}
            proc = subprocess.run([sys.executable, "-c", E2E, str(ROOT), f"http://127.0.0.1:{pa}/v1",
                                   f"http://127.0.0.1:{pb}/v1"], env=env, capture_output=True, text=True, timeout=240)
            assert proc.returncode == 0, proc.stderr[-2500:]
            single, fused = json.loads(proc.stdout.strip().splitlines()[-1])
    finally:
        for p in stubs:
            p.terminate()
    assert single["provider"] == "local-ollama" and "[B]" in single["content"]  # the second vendor answered
    assert fused["engine"] == "fusion" and fused["content"].startswith("Fused answer from 2 models [A]")
    members = {m["source"]: m for m in fused["fusion"]["members"]}
    assert members["campus-openai-compatible::stub-model"]["ok"] and "[A]" in members[
        "campus-openai-compatible::stub-model"]["answer"]
    assert members["claude-code::opus"]["ok"] and members["claude-code::opus"]["answer"].startswith("Fake Claude")
    assert not members["cursor::"]["ok"]  # not signed in: recorded, the others still fused
    assert fused["fusion"]["synthesizer"] == "stub-model"
