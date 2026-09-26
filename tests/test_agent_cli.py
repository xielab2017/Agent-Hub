"""Claude Code / Codex agents: streaming, resume, permissions, flag drift, external-link login (fake CLIs)."""

from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parent.parent
FAKES = ROOT / "tests" / "fakes"
sys.path.insert(0, str(ROOT))

from ali import agent_cli  # noqa: E402


@contextlib.contextmanager
def env():
    """Temp HOME / config / secrets; the fake CLIs first on PATH; argv logged to a file."""
    from ali import secrets, settings

    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        (t / "ws").mkdir()
        log = t / "argv.jsonl"
        with mock.patch.dict(os.environ, {"HOME": str(t), "PATH": f"{FAKES}:{os.environ['PATH']}",
                                          "FAKE_AGENT_LOG": str(log), "CODEX_HOME": str(t / ".codex"),
                                          "ANTHROPIC_API_KEY": "sk-shell-should-not-leak",
                                          "ANTHROPIC_BASE_URL": "https://api.minimax.cn/anthropic"}), \
                mock.patch.object(settings, "CAMPUS_CONFIG_FILE", t / "campus.json"), \
                mock.patch.object(settings, "ensure_state_dirs", lambda: None), \
                mock.patch.object(secrets, "SECRETS_FILE", t / "secrets.json"), \
                mock.patch.object(agent_cli, "SESSIONS_FILE", t / "agent-sessions.json"), \
                mock.patch("ali.audit.log_event", lambda *a, **k: None):
            agent_cli._HELP_CACHE.clear()
            yield t, log


def calls(log: Path) -> list[dict]:
    return [json.loads(ln) for ln in log.read_text().splitlines()] if log.exists() else []


def wait(job_id: str, until=lambda j: j["status"] != "running", timeout: float = 15.0) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = agent_cli.login_status(job_id)
        if until(j):
            return j
        time.sleep(0.1)
    raise AssertionError(f"login job stuck: {agent_cli.login_status(job_id)}")


def test_flag_check_catches_cli_drift():
    assert agent_cli.check_flags("claude-code", help_text=agent_cli.cli_help("claude-code", str(FAKES / "claude"))) == []
    assert agent_cli.check_flags("codex", help_text="codex exec\n  --json\n  -s, --sandbox read-only workspace-write") == [
        "--skip-git-repo-check"]
    assert agent_cli.check_flags("codex", help_text="--json --sandbox --skip-git-repo-check read-only") == [
        "--sandbox workspace-write"]
    assert "--permission-mode" in agent_cli.check_flags("claude-code", help_text="-p, --print --output-format")


def test_claude_link_login_stores_token_hidden_and_chat_resumes():
    with env() as (t, log):
        job = agent_cli.start_login("claude-code", "link")
        job = wait(job["id"], lambda j: j["needs_input"] or j["status"] != "running")
        assert job["url"].startswith("https://claude.ai/oauth/authorize")
        agent_cli.login_input(job["id"], "fake-auth-code")
        job = wait(job["id"])
        assert job["status"] == "done" and job.get("token_saved")
        assert "sk-ant-oat01" not in json.dumps(job) and "[token saved in Agent Hub]" in "\n".join(job["lines"])
        st = agent_cli.auth_status("claude-code")
        assert st["logged_in"] and st["mode"] == "oauth" and "sk-ant" not in json.dumps(st)

        events = []
        r1 = agent_cli.run("claude-code", "hello there", hub_session="s1", workspace=str(t / "ws"),
                           on_event=lambda k, d: events.append((k, d)))
        assert r1["text"].startswith("Fake Claude read the workspace") and not r1["error"]
        assert [k for k, _ in events].count("token") > 1  # streamed as deltas
        assert ("tool", {"name": "Read", "preview": '{"file_path": "README.md"}'}) in events
        r2 = agent_cli.run("claude-code", "again", hub_session="s1", workspace=str(t / "ws"))
        assert r2["resumed"] and r2["session_id"] == r1["session_id"]
        c = [x for x in calls(log) if "-p" in x["argv"]]
        assert c[0]["oauth"] and not c[0]["api_key"] and c[0]["base_url"] == ""  # shell ANTHROPIC_* stripped
        argv = c[0]["argv"]
        assert argv[argv.index("--permission-mode") + 1] == "dontAsk"  # read-only default
        assert "Edit" not in argv[argv.index("--allowedTools") + 1]
        assert "bypassPermissions" not in json.dumps(c)
        assert c[1]["argv"][c[1]["argv"].index("--resume") + 1] == r1["session_id"]
        assert c[0]["cwd"] == str(t / "ws")


def test_codex_device_login_status_and_chat_with_workspace_write():
    from ali.settings import load_campus_config, save_campus_config

    with env() as (t, log):
        assert not agent_cli.auth_status("codex")["logged_in"]
        job = agent_cli.start_login("codex", "device")
        job = wait(job["id"])
        assert job["status"] == "done" and job["url"] == "https://auth.openai.com/codex/device"
        assert job["code"] == "ABCD-12345"
        assert agent_cli.auth_status("codex")["logged_in"]
        cfg = load_campus_config()
        cfg.setdefault("ali", {})["agent_permissions"] = "workspace-write"
        save_campus_config(cfg)
        events = []
        r = agent_cli.run("codex", "list files", hub_session="s2", workspace=str(t / "ws"),
                          on_event=lambda k, d: events.append((k, d)))
        assert r["text"].startswith("Fake Codex listed the workspace") and r["session_id"]
        assert ("tool", {"name": "shell", "preview": "ls"}) in events
        r2 = agent_cli.run("codex", "more", hub_session="s2", workspace=str(t / "ws"))
        argv1, argv2 = [x["argv"] for x in calls(log) if x["argv"][:1] == ["exec"] and "--help" not in x["argv"]]
        assert argv1[argv1.index("--sandbox") + 1] == "workspace-write" and argv1[argv1.index("-C") + 1] == str(t / "ws")
        assert "resume" in argv2 and argv2[argv2.index("resume") + 1] == r["session_id"] and r2["resumed"]
        assert agent_cli.logout("codex")["logged_in"] is False


def test_api_key_login_modes():
    from ali.secrets import get_api_key

    with env() as (_t, log):
        agent_cli.start_login("codex", "api_key", api_key="sk-proj-test-key-0000000000")
        assert get_api_key("codex-api-key").startswith("sk-proj") and agent_cli.auth_mode("codex") == "api_key"
        assert agent_cli.build_env("codex")["CODEX_API_KEY"].startswith("sk-proj")
        agent_cli.start_login("claude-code", "api_key", api_key="sk-ant-api03-" + "k" * 40)
        e = agent_cli.build_env("claude-code")
        assert e["ANTHROPIC_API_KEY"].startswith("sk-ant-api03") and "CLAUDE_CODE_OAUTH_TOKEN" not in e
        assert "ANTHROPIC_BASE_URL" not in e
        with pytest.raises(ValueError):
            agent_cli.start_login("claude-code", "device")


def test_missing_cli_and_flag_drift_are_clear_errors():
    with env():
        with mock.patch.object(agent_cli, "find_bin", lambda rid: ""):
            with pytest.raises(RuntimeError, match="not installed"):
                agent_cli.run("codex", "hi")
        with mock.patch.object(agent_cli, "cli_help", lambda rid, b: "Usage: codex exec\n  --json"):
            with pytest.raises(RuntimeError, match="lacks --sandbox"):
                agent_cli.run("codex", "hi")


def test_cursor_flags_match_the_real_cli_help():
    """The saved help is the real Cursor CLI 2026.09 --help (workflow cursor-cli-probe on a GitHub runner)."""
    real = (FAKES / "cursor-agent.help.txt").read_text()
    assert agent_cli.check_flags("cursor", help_text=real) == []
    assert agent_cli.check_flags("cursor", help_text="Usage: agent\n  -p, --print\n  --output-format") != []


def test_cursor_link_login_status_chat_resume_and_read_only_mode():
    from ali.settings import load_campus_config, save_campus_config

    with env() as (t, log):
        with mock.patch.dict(os.environ, {"CURSOR_API_KEY": "shell-key-must-not-leak"}):
            assert not agent_cli.auth_status("cursor")["logged_in"]
            job = wait(agent_cli.start_login("cursor", "link")["id"])
            assert job["status"] == "done" and job["url"].startswith("https://cursor.com/loginDeepControl")
            st = agent_cli.auth_status("cursor")
            assert st["logged_in"] and "user@example.org" in st["detail"]
            events = []
            r = agent_cli.run("cursor", "summarise notes.md", hub_session="c1", workspace=str(t / "ws"),
                              system="HUB CONTEXT", on_event=lambda k, d: events.append((k, d)))
            assert r["text"].startswith("Fake Cursor (ask mode) read notes.md.") and r["session_id"]
            assert r["text"].endswith("summarise notes.md") and r["text"].count("Fake Cursor") == 1
            assert ("tool", {"name": "read", "preview": '{"path": "notes.md"}'}) in events
            assert sum(1 for k, _d in events if k == "token") >= 3  # streamed as deltas, the full repeat dropped
            cfg = load_campus_config()
            cfg.setdefault("ali", {})["agent_permissions"] = "workspace-write"
            save_campus_config(cfg)
            r2 = agent_cli.run("cursor", "edit it", hub_session="c1", workspace=str(t / "ws"))
            assert r2["resumed"] and "(agent mode)" in r2["text"]
        runs = [x for x in calls(log) if "-p" in x["argv"]]
        a1, a2 = runs[0]["argv"], runs[1]["argv"]
        assert a1[a1.index("--mode") + 1] == "ask" and a1[a1.index("--workspace") + 1] == str(t / "ws")
        assert a1[a1.index("-p") + 1].startswith("HUB CONTEXT")  # the Hub context rides in the first prompt
        assert "--mode" not in a2 and a2[a2.index("--resume") + 1] == r["session_id"]
        for a in (a1, a2):  # never run-everything
            assert "--force" not in a and "-f" not in a and "--yolo" not in a
        assert all(not x["cursor_api_key"] for x in runs)  # the shell's key did not override the Hub login
        assert all(x["no_open_browser"] == "1" for x in calls(log) if x["argv"][:1] == ["login"])
        assert agent_cli.logout("cursor")["logged_in"] is False


def test_cursor_api_key_login_and_clear_auth_error():
    with env() as (_t, _log):
        with pytest.raises(ValueError):
            agent_cli.start_login("cursor", "device")
        r = agent_cli.run("cursor", "hi")
        assert "Authentication required" in r["error"] or "exited" in r["error"]
        agent_cli.start_login("cursor", "api_key", api_key="key_cursor_test_000000000000")
        assert agent_cli.auth_mode("cursor") == "api_key" and agent_cli.build_env("cursor")["CURSOR_API_KEY"]
        assert agent_cli.auth_status("cursor")["detail"] == "Cursor API key"
        assert agent_cli.run("cursor", "hi")["text"].startswith("Fake Cursor")
