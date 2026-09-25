"""Hub ↔ Hermes integration (no Hermes install needed).

Behaviour pinned here was verified against the real Hermes Agent v0.19.0:
* tool_progress_callback is called ("tool.started", name, preview, args) /
  ("tool.completed", name, None, None, duration=…, is_error=…) / reasoning events;
* AIAgent accepts ephemeral_system_prompt (Hub context must not be sent as the user turn);
* config.yaml must keep user MCP servers and have a single mcp_servers key;
* the CLI prints notices before the answer and "session_id: …" after it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parent.parent


# ── tool events ────────────────────────────────────────────────────────


def test_parse_tool_event_v019_and_legacy():
    from ali.streaming import parse_tool_event as p

    assert p(("tool.started", "read_file", "probe.txt", {"path": "/x/probe.txt"}), {}) == {
        "kind": "started", "name": "read_file", "preview": "probe.txt", "duration": None, "is_error": False}
    done = p(("tool.completed", "read_file", None, None), {"duration": 0.237, "is_error": False, "result": "…"})
    assert done["kind"] == "completed" and done["duration"] == 0.237 and done["is_error"] is False
    assert p(("tool.output_risk", "terminal", None, None), {"risk_metadata": {}})["kind"] == "risk"
    assert p(("reasoning.available", "_thinking", "let me think", None), {}) == {"kind": "reasoning", "name": "", "text": "let me think"}
    assert p(("_thinking", "first line"), {})["text"] == "first line"
    # preview falls back to the args when Hermes gives none
    assert p(("tool.started", "terminal", "", {"command": "ls"}), {})["preview"] == "{'command': 'ls'}"
    # legacy (name, preview) and keyword styles
    assert p(("web_search", "q=tp53"), {}) == {"kind": "started", "name": "web_search", "preview": "q=tp53"}
    assert p((), {"tool_name": "x", "args": "a"})["name"] == "x"


# ── turn input ─────────────────────────────────────────────────────────


def test_hermes_turn_input_uses_ephemeral_system_prompt_when_supported():
    from ali.streaming import hermes_turn_input

    class New:
        def __init__(self, model="", ephemeral_system_prompt=None, **kw):
            pass

    class Old:
        def __init__(self, model="", quiet_mode=False):
            pass

    assert hermes_turn_input(New, "HUB RULES", "question") == ("question", {"ephemeral_system_prompt": "HUB RULES"})
    msg, extra = hermes_turn_input(Old, "HUB RULES", "question")
    assert extra == {} and msg == "[SYSTEM CONTEXT]\nHUB RULES\n\n[USER]\nquestion"
    assert hermes_turn_input(New, "", "question") == ("question", {})


# ── CLI output & history ───────────────────────────────────────────────


def test_clean_cli_output_and_session_id():
    from ali.hermes_cli import clean_hermes_text, hermes_session_id

    raw = "  ⚠  tirith security scanner enabled but not available — pattern matching only\r\nThe answer ⚠ stays.\nsession_id: 20260925_102931_3f61d3\n"
    assert clean_hermes_text(raw) == "The answer ⚠ stays."
    assert hermes_session_id("", "\nsession_id: 20260925_102931_3f61d3\n") == "20260925_102931_3f61d3"
    assert hermes_session_id("nothing here") == ""


def test_recent_history_goes_before_user_marker():
    from ali import streaming
    from ali import sessions as store

    fake = mock.Mock()
    fake.messages = [
        {"role": "user", "content": "第一问"}, {"role": "assistant", "content": "答案一 " + "x" * 900},
        {"role": "assistant", "content": "**Error:** boom", "error": True},
        {"role": "user", "content": "第二问"},
    ]
    with mock.patch.object(store, "get_session", return_value=fake):
        out = streaming._with_recent_history("[SYSTEM CONTEXT]\nrules\n\n[USER]\n第二问", "s")
    head, _, tail = out.rpartition("[USER]\n")
    assert tail == "第二问"
    assert "[CONVERSATION SO FAR]\nuser: 第一问\nassistant: 答案一" in head and "…" in head and "boom" not in head
    with mock.patch.object(store, "get_session", return_value=None):
        assert streaming._with_recent_history("p", "s") == "p"


# ── config.yaml sync ───────────────────────────────────────────────────


def test_mcp_merge_keeps_user_servers_single_key_and_repairs_legacy(tmp_path):
    yaml = pytest.importorskip("yaml")

    from ali.hermes_cli import _MCP_MARKER_BEGIN, _MCP_MARKER_END, merge_mcp_servers_into_config

    cfg = tmp_path / "config.yaml"
    # the broken state older Hubs left behind: plain key + marker block (duplicate key)
    cfg.write_text(
        "model:\n  default: m\nmcp_servers:\n  my-own:\n    command: my-mcp\n"
        f"agent:\n  max_turns: 40\n\n{_MCP_MARKER_BEGIN}\nmcp_servers:\n  old-hub:\n    command: x\n{_MCP_MARKER_END}\n",
        encoding="utf-8",
    )
    merge_mcp_servers_into_config(cfg, {"filesystem": {"command": "npx", "args": ["-y", "fs", "/tmp"]}})
    text = cfg.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert text.count("mcp_servers:") == 1 and _MCP_MARKER_BEGIN not in text
    assert set(data["mcp_servers"]) == {"my-own", "filesystem"}  # old Hub server gone, user's kept
    assert data["mcp_servers"]["filesystem"]["args"] == ["-y", "fs", "/tmp"]
    assert data["agent"]["max_turns"] == 40 and data["model"]["default"] == "m"
    # disabling the Hub server removes only it; repeated syncs are stable
    merge_mcp_servers_into_config(cfg, {})
    merge_mcp_servers_into_config(cfg, {})
    assert set(yaml.safe_load(cfg.read_text(encoding="utf-8"))["mcp_servers"]) == {"my-own"}
    assert json.loads((tmp_path / ".agent-hub-mcp.json").read_text())["servers"] == []


def test_sync_uses_backend_model_before_default(tmp_path):
    from ali import hermes_cli

    cfg = {"backend": {"type": "campus-openai-compatible", "base_url": "http://llm.local/v1", "model": "my-model",
                       "api_key_env": "OPENAI_API_KEY"}, "models": {}, "routing": {}}
    with mock.patch.object(hermes_cli, "hermes_home", return_value=tmp_path), \
            mock.patch.object(hermes_cli, "hermes_config_homes", return_value=[tmp_path]), \
            mock.patch("ali.secrets.resolve_api_key", return_value={"key": "sk-test-0123456789abcdef", "present": True, "env_name": "OPENAI_API_KEY"}), \
            mock.patch("ali.mcp_hub.active_servers_for_hermes", return_value={}):
        res = hermes_cli.sync_hub_to_hermes(cfg)
    assert res["ok"] and res["model"] == "my-model"
    assert "default: my-model" in (tmp_path / "config.yaml").read_text() or 'default: "my-model"' in (tmp_path / "config.yaml").read_text()


# ── skills ─────────────────────────────────────────────────────────────


def test_skill_links_repaired_and_pruned(tmp_path):
    from ali import skills

    hub = tmp_path / "hub"
    claw = tmp_path / "hermes" / "skills"
    (hub / "s1").mkdir(parents=True)
    (hub / "s1" / "SKILL.md").write_text("---\nname: s1\n---\n")
    claw.mkdir(parents=True)
    os.symlink(tmp_path / "gone", claw / "s1")  # dangling link from an old install
    with mock.patch.object(skills, "install_skills_root", return_value=hub), \
            mock.patch("ali.config.hermes_home", return_value=tmp_path / "hermes"), \
            mock.patch.object(skills, "claw_skill_dirs", return_value=[claw]):
        res = skills.sync_skills_to_claw("hermes")
        assert res["written"] == [str(claw / "s1")] and (claw / "s1" / "SKILL.md").is_file()
        import shutil

        shutil.rmtree(hub / "s1")
        assert skills.prune_dangling_claw_links("s1") == [str(claw / "s1")]
        assert not (claw / "s1").is_symlink()


# ── end to end: real Hub code path, fake run_agent on the discovery path ──

FAKE_RUN_AGENT = r'''
import json, os
LOG = os.environ["FAKE_AGENT_LOG"]
class AIAgent:
    def __init__(self, base_url=None, api_key=None, provider=None, model="", quiet_mode=False, session_id=None,
                 platform=None, ephemeral_system_prompt=None, tool_progress_callback=None,
                 stream_delta_callback=None, **kw):
        self.tp, self.sd = tool_progress_callback, stream_delta_callback
        self.init = {"model": model, "provider": provider, "base_url": base_url, "has_key": bool(api_key),
                     "ephemeral": (ephemeral_system_prompt or "")[:200], "platform": platform}
    def run_conversation(self, user_message, conversation_history=None, task_id=None):
        # exactly how Hermes v0.19 reports tools (callback errors are swallowed by Hermes)
        for call in ((("tool.started", "read_file", "probe.txt", {"path": "/tmp/probe.txt"}), {}),
                     (("tool.completed", "read_file", None, None), {"duration": 0.12, "is_error": False, "result": "ok"}),
                     (("reasoning.available", "_thinking", "checking the file", None), {})):
            try:
                self.tp(*call[0], **call[1])
            except Exception as exc:
                self.init["callback_error"] = repr(exc)
        text = "HERMES_OK: " + user_message[-30:]
        for i in range(0, len(text), 6):
            self.sd(text[i:i + 6])
        with open(LOG, "a") as f:
            f.write(json.dumps({"init": self.init, "user_message": user_message,
                                "history": [(m["role"], m["content"][:40]) for m in conversation_history or []]}) + "\n")
        return {"final_response": text}
'''

E2E = r"""
import json, sys, time
sys.path.insert(0, sys.argv[1])
from ali import runtimes, streaming, sessions as store
from ali.settings import load_campus_config, save_campus_config
cfg = load_campus_config()
cfg.setdefault("ali", {})["hub_chat_mode"] = "agent"
save_campus_config(cfg)
runtimes.connect_runtime("hermes")
s = store.create_session(title="hermes fake")
turns = []
for text in ("第一问：TP53 是什么？", "第二问：接着说"):
    before = len([m for m in store.get_session(s.id).messages if m.get("role") == "assistant"])
    res = streaming.start_chat(s.id, text, web_search=False)
    for _ in range(300):
        msgs = [m for m in store.get_session(s.id).messages if m.get("role") == "assistant"]
        if len(msgs) > before:
            break
        time.sleep(0.1)
    m = msgs[-1]
    turns.append({"engine": res["route"].get("chat_engine"), "content": m["content"], "tools": m.get("tools"),
                  "prov_tools": (m.get("provenance") or {}).get("tools")})
print(json.dumps({"status": streaming.agent_status()["chat_engine"], "turns": turns}, ensure_ascii=False))
"""


def test_inprocess_hermes_end_to_end_with_fake_run_agent():
    with tempfile.TemporaryDirectory() as tmp:
        agent_dir = Path(tmp) / "fake-hermes"
        agent_dir.mkdir()
        (agent_dir / "run_agent.py").write_text(FAKE_RUN_AGENT, encoding="utf-8")
        log = Path(tmp) / "agent.jsonl"
        env = dict(os.environ)
        env.update({
            "HERMES_ALI_STATE_DIR": str(Path(tmp) / "state"), "AGENT_CLI_HOME": str(Path(tmp) / "agent-cli"),
            "HERMES_HOME": str(Path(tmp) / "hermes"), "HOME": tmp,
            "HERMES_ALI_AGENT_DIR": str(agent_dir), "FAKE_AGENT_LOG": str(log),
            "PATH": "/usr/bin:/bin",  # no real hermes CLI
        })
        proc = subprocess.run([sys.executable, "-c", E2E, str(ROOT)], env=env, capture_output=True, text=True, timeout=180)
        assert proc.returncode == 0, proc.stderr[-2000:]
        out = json.loads(proc.stdout.strip().splitlines()[-1])
        calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert out["status"] == "hermes"
    t1, t2 = out["turns"]
    assert t1["engine"] == "hermes" and t1["content"].startswith("HERMES_OK:")
    # tool events in Hermes v0.19 style reach the Hub (message + provenance)
    assert t1["tools"] == [{"name": "read_file", "preview": "probe.txt", "ok": True, "duration_ms": 120}]
    assert t1["prov_tools"] == 1
    first, second = calls
    assert "callback_error" not in first["init"]
    # Hub context travels as an ephemeral system prompt; the user turn stays clean
    assert first["init"]["ephemeral"] and "[SYSTEM CONTEXT]" not in first["user_message"]
    assert first["user_message"] == "第一问：TP53 是什么？" and first["init"]["platform"] == "cli"
    # second turn gets the first turn as history
    assert second["history"][:2] == [["user", "第一问：TP53 是什么？"], ["assistant", t1["content"][:40]]]
