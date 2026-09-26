"""Claude Code and OpenAI Codex as Agent Hub agents (runtimes ``claude-code`` / ``codex``).

Chat turns
  ``run(rid, prompt, …)`` spawns the official CLI headless and streams its JSON events:
  Claude Code ``claude -p … --output-format stream-json --verbose --include-partial-messages``;
  Codex ``codex exec --json …``.  Text arrives as ``token`` events, tool use as ``tool`` events; the CLI's own
  session id is kept per Hub session so the next turn resumes it (``--resume`` / ``exec resume``).
  Permissions default to read-only (Claude ``--permission-mode dontAsk`` + read tools; Codex ``--sandbox
  read-only``); ``workspace-write`` allows file edits in the Hub workspace.  The Hub never passes a
  permission-bypass mode.

Login (external link)
  ``start_login(rid, method)`` runs the CLI's own login in a pseudo-terminal and surfaces the authorisation URL
  (and device code) to the UI; a code the CLI asks for can be pasted back (``login_input``).
  Claude Code: ``claude setup-token`` → the printed long-lived token is stored in the Hub secrets store (slot
  ``claude-code-oauth``), removed from all output, and injected as ``CLAUDE_CODE_OAUTH_TOKEN``.
  Codex: ``codex login`` (browser) / ``codex login --device-auth`` (URL + code) / ``--with-api-key`` (stdin);
  the CLI keeps its own credentials in ``~/.codex``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from .config import STATE_DIR

SESSIONS_FILE = STATE_DIR / "agent-sessions.json"
OAUTH_SLOT = "claude-code-oauth"
API_SLOTS = {"claude-code": "claude-code-api-key", "codex": "codex-api-key"}
READ_TOOLS = "Read,Grep,Glob,WebSearch,WebFetch"
WRITE_TOOLS = "Read,Grep,Glob,Edit,Write,MultiEdit,WebSearch,WebFetch"
# flags each adapter needs; any one of the alternatives must appear in the CLI's --help
NEEDED_FLAGS = {
    "claude-code": [("--print", "-p"), ("--output-format",), ("--resume", "-r"), ("--permission-mode",),
                    ("--allowedTools", "--allowed-tools"), ("--verbose",)],
    "codex": [("--json",), ("--sandbox", "-s"), ("--skip-git-repo-check",)],
}
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07|\r")
_URL = re.compile(r"https://[^\s'\"<>\x1b]+")
_DEVICE_CODE = re.compile(r"\b([A-Z0-9]{4}-[A-Z0-9]{4,5})\b")
_TOKEN = re.compile(r"sk-ant-(?:oat|api)\d{2}-[A-Za-z0-9_\-]{20,}")
_LOCK = threading.Lock()


# ── binaries, env, permissions ─────────────────────────────────────────


def bin_name(rid: str) -> str:
    return {"claude-code": "claude", "codex": "codex"}[rid]


def find_bin(rid: str) -> str:
    name = bin_name(rid)
    found = shutil.which(name)
    if found:
        return found
    for cand in (Path.home() / ".local" / "bin" / name, Path.home() / ".claude" / "local" / name,
                 Path.home() / ".npm-global" / "bin" / name):
        if cand.exists():
            return str(cand)
    return ""


def _secret(slot: str) -> str:
    from .secrets import get_api_key

    return (get_api_key(slot) or "").strip()


def auth_mode(rid: str) -> str:
    """oauth (Hub-held token) | api_key | cli (the CLI's own login) | env (the shell's variables)."""
    from .settings import load_campus_config

    mode = str(((load_campus_config().get("ali") or {}).get("agent_auth") or {}).get(rid) or "").strip()
    if mode:
        return mode
    if rid == "claude-code" and _secret(OAUTH_SLOT):
        return "oauth"
    if _secret(API_SLOTS[rid]):
        return "api_key"
    return "cli"


def build_env(rid: str) -> dict[str, str]:
    env = dict(os.environ)
    mode = auth_mode(rid)
    if rid == "claude-code":
        if mode != "env":  # a shell ANTHROPIC_* (e.g. another vendor's gateway) must not override the login
            for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDE_CODE_OAUTH_TOKEN"):
                env.pop(k, None)
        if mode == "oauth" and _secret(OAUTH_SLOT):
            env["CLAUDE_CODE_OAUTH_TOKEN"] = _secret(OAUTH_SLOT)
        elif mode == "api_key" and _secret(API_SLOTS[rid]):
            env["ANTHROPIC_API_KEY"] = _secret(API_SLOTS[rid])
    else:
        if mode != "env":
            for k in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "CODEX_API_KEY"):
                env.pop(k, None)
        if mode == "api_key" and _secret(API_SLOTS[rid]):
            env["CODEX_API_KEY"] = _secret(API_SLOTS[rid])
    env.setdefault("NO_COLOR", "1")
    return env


def permission_level() -> str:
    from .settings import load_campus_config

    level = str((load_campus_config().get("ali") or {}).get("agent_permissions") or "read-only")
    return level if level in ("read-only", "workspace-write") else "read-only"


# ── CLI flag drift check ───────────────────────────────────────────────

_HELP_CACHE: dict[str, tuple[float, str]] = {}


def cli_help(rid: str, binpath: str) -> str:
    key = f"{rid}:{binpath}"
    try:
        mtime = os.path.getmtime(binpath)
    except OSError:
        mtime = 0.0
    hit = _HELP_CACHE.get(key)
    if hit and hit[0] == mtime:
        return hit[1]
    cmd = [binpath, "--help"] if rid == "claude-code" else [binpath, "exec", "--help"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=build_env(rid))
        text = (out.stdout or "") + (out.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as exc:
        text = f"(help failed: {exc})"
    _HELP_CACHE[key] = (mtime, text)
    return text


def check_flags(rid: str, binpath: str = "", help_text: str | None = None) -> list[str]:
    """Flags the adapter needs that this CLI version does not document ([] = compatible)."""
    text = help_text if help_text is not None else cli_help(rid, binpath or find_bin(rid))
    return [alts[0] for alts in NEEDED_FLAGS[rid]
            if not any(re.search(r"(?<![\w-])" + re.escape(a) + r"(?![\w-])", text) for a in alts)]


# ── per-Hub-session CLI session ids ────────────────────────────────────


def _sessions() -> dict[str, Any]:
    try:
        return json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def cli_session(hub_session: str, rid: str) -> str:
    return str((_sessions().get(hub_session) or {}).get(rid) or "")


def remember_session(hub_session: str, rid: str, cli_sid: str) -> None:
    if not (hub_session and cli_sid):
        return
    with _LOCK:
        data = _sessions()
        data.setdefault(hub_session, {})[rid] = cli_sid
        SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SESSIONS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


# ── commands and event parsing ─────────────────────────────────────────


def build_command(rid: str, binpath: str, prompt: str, *, resume: str = "", model: str = "", system: str = "",
                  workspace: str = "", level: str = "read-only") -> list[str]:
    if rid == "claude-code":
        cmd = [binpath, "-p", prompt, "--output-format", "stream-json", "--verbose", "--include-partial-messages"]
        if level == "workspace-write":
            cmd += ["--permission-mode", "acceptEdits", "--allowedTools", WRITE_TOOLS]
        else:
            cmd += ["--permission-mode", "dontAsk", "--allowedTools", READ_TOOLS]
        if resume:
            cmd += ["--resume", resume]
        if model:
            cmd += ["--model", model]
        if system:
            cmd += ["--append-system-prompt", system]
        return cmd
    opts = ["--json", "--skip-git-repo-check", "--sandbox",
            "workspace-write" if level == "workspace-write" else "read-only"]
    if workspace:
        opts += ["-C", workspace]
    if model:
        opts += ["-m", model]
    full = f"{system}\n\n{prompt}" if system and not resume else prompt
    if resume:
        return [binpath, "exec", *opts, "resume", resume, full]
    return [binpath, "exec", *opts, full]


def _preview(obj: Any, n: int = 160) -> str:
    s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + "…"


def parse_claude_event(ev: dict[str, Any], st: dict[str, Any]) -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    t = ev.get("type")
    if t == "system" and ev.get("subtype") == "init":
        st["session_id"] = ev.get("session_id") or st.get("session_id")
        out.append(("meta", {"session_id": st["session_id"], "model": ev.get("model")}))
    elif t == "stream_event":
        inner = ev.get("event") or {}
        delta = inner.get("delta") or {}
        if delta.get("type") == "text_delta" and delta.get("text"):
            st["streamed"] = True
            out.append(("token", delta["text"]))
    elif t == "assistant":
        for block in (ev.get("message") or {}).get("content") or []:
            if block.get("type") == "tool_use":
                out.append(("tool", {"name": block.get("name") or "tool", "preview": _preview(block.get("input") or {})}))
            elif block.get("type") == "text" and block.get("text") and not st.get("streamed"):
                out.append(("token", block["text"]))
    elif t == "result":
        st["session_id"] = ev.get("session_id") or st.get("session_id")
        st["cost"] = ev.get("total_cost_usd")
        if ev.get("is_error"):
            out.append(("error", str(ev.get("result") or ev.get("error") or "Claude Code reported an error")))
        elif ev.get("result") and not st.get("text_seen"):
            out.append(("token", str(ev["result"])))
        out.append(("meta", {"session_id": st.get("session_id"), "cost_usd": st.get("cost")}))
    return out


def parse_codex_event(ev: dict[str, Any], st: dict[str, Any]) -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    t = ev.get("type") or ((ev.get("msg") or {}).get("type") if isinstance(ev.get("msg"), dict) else "")
    if t in ("thread.started", "session.created", "session_configured"):
        sid = ev.get("thread_id") or ev.get("session_id") or (ev.get("msg") or {}).get("session_id")
        if sid:
            st["session_id"] = sid
            out.append(("meta", {"session_id": sid}))
    elif t in ("item.completed", "item.started"):
        item = ev.get("item") or {}
        kind = item.get("type") or item.get("item_type")
        if kind in ("agent_message", "assistant_message") and t == "item.completed":
            text = item.get("text") or ""
            if text:
                out.append(("token", text + ("\n" if not text.endswith("\n") else "")))
        elif kind == "reasoning" and t == "item.completed" and item.get("text"):
            out.append(("think", str(item["text"])[:400]))
        elif kind in ("command_execution", "file_change", "mcp_tool_call", "web_search") and t == "item.started":
            name = {"command_execution": "shell", "file_change": "edit", "web_search": "web_search"}.get(kind, kind)
            out.append(("tool", {"name": name, "preview": _preview(item.get("command") or item.get("query")
                                                                    or item.get("changes") or item)}))
    elif t == "agent_message":  # older event shape
        msg = (ev.get("msg") or {}).get("message") or ""
        if msg:
            out.append(("token", msg))
    elif t in ("turn.failed", "error"):
        err = ev.get("error") or ev.get("message") or {}
        out.append(("error", str(err.get("message") if isinstance(err, dict) else err)))
    elif t == "turn.completed":
        out.append(("meta", {"session_id": st.get("session_id"), "usage": ev.get("usage")}))
    return out


def run(rid: str, prompt: str, *, hub_session: str = "", workspace: str = "", model: str = "", system: str = "",
        on_event: Callable[[str, Any], None] | None = None, cancelled: Callable[[], bool] | None = None,
        timeout: float = 900.0, binpath: str = "") -> dict[str, Any]:
    """One chat turn through the CLI; events go to ``on_event(kind, data)`` as they arrive."""
    binpath = binpath or find_bin(rid)
    if not binpath:
        raise RuntimeError(f"{bin_name(rid)} is not installed")
    missing = check_flags(rid, binpath)
    if missing:
        raise RuntimeError(f"this {bin_name(rid)} version lacks {', '.join(missing)} — upgrade it in Claws")
    resume = cli_session(hub_session, rid) if hub_session else ""
    ws = workspace if workspace and Path(workspace).is_dir() else str(Path.home())
    cmd = build_command(rid, binpath, prompt, resume=resume, model=model, system=system, workspace=ws,
                        level=permission_level())
    proc = subprocess.Popen(cmd, cwd=ws, env=build_env(rid), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", bufsize=1)
    st: dict[str, Any] = {"session_id": resume}
    texts: list[str] = []
    tools: list[dict[str, Any]] = []
    errors: list[str] = []
    stderr_tail: list[str] = []
    killed = {"why": ""}

    def watchdog() -> None:
        t0 = time.time()
        while proc.poll() is None:
            if cancelled and cancelled():
                killed["why"] = "cancelled"
                proc.terminate()
                return
            if time.time() - t0 > timeout:
                killed["why"] = f"timed out after {int(timeout)} s"
                proc.terminate()
                return
            time.sleep(0.5)

    def drain_err() -> None:
        for line in proc.stderr or []:
            stderr_tail.append(line.rstrip())
            del stderr_tail[:-40]

    threading.Thread(target=watchdog, daemon=True).start()
    threading.Thread(target=drain_err, daemon=True).start()
    parse = parse_claude_event if rid == "claude-code" else parse_codex_event
    for line in proc.stdout or []:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        for kind, data in parse(ev, st):
            if kind == "token":
                texts.append(data)
                st["text_seen"] = True
            elif kind == "tool":
                tools.append(data)
            elif kind == "error":
                errors.append(data)
            if on_event:
                on_event(kind, data)
    rc = proc.wait()
    if st.get("session_id"):
        remember_session(hub_session, rid, str(st["session_id"]))
    text = "".join(texts).strip()
    if killed["why"]:
        errors.append(killed["why"])
    if rc != 0 and not text and not errors:
        errors.append(_mask(" ".join(stderr_tail[-6:]))[:600] or f"{bin_name(rid)} exited with {rc}")
    return {"text": text, "session_id": st.get("session_id") or "", "cost_usd": st.get("cost"), "tools": tools,
            "error": "; ".join(errors), "returncode": rc, "resumed": bool(resume)}


# ── login (external link) ──────────────────────────────────────────────

_LOGINS: dict[str, dict[str, Any]] = {}


def _mask(text: str) -> str:
    return _TOKEN.sub("[token saved in Agent Hub]", text or "")


def login_command(rid: str, method: str, binpath: str) -> list[str]:
    if rid == "claude-code":
        if method not in ("link", "oauth"):
            raise ValueError("Claude Code signs in with the browser link (setup-token) or an API key")
        return [binpath, "setup-token"]
    if method == "device":
        return [binpath, "login", "--device-auth"]
    if method == "link":
        return [binpath, "login"]
    raise ValueError(f"unknown login method: {method}")


def start_login(rid: str, method: str = "link", *, api_key: str = "", binpath: str = "") -> dict[str, Any]:
    """Run the CLI's login in a pseudo-terminal; the job exposes the auth URL / device code and final status."""
    from .secrets import set_api_key
    from .settings import load_campus_config, save_campus_config

    binpath = binpath or find_bin(rid)
    job_id = f"login-{rid}-{uuid.uuid4().hex[:6]}"
    job: dict[str, Any] = {"id": job_id, "runtime": rid, "method": method, "status": "running", "url": "",
                           "code": "", "lines": [], "started_at": time.time(), "finished_at": None, "error": "",
                           "needs_input": False}
    _LOGINS[job_id] = job

    def set_mode(mode: str) -> None:
        cfg = load_campus_config()
        cfg.setdefault("ali", {}).setdefault("agent_auth", {})[rid] = mode
        save_campus_config(cfg)

    if method == "api_key":
        key = (api_key or "").strip()
        if not key:
            raise ValueError("api_key required")
        set_api_key(API_SLOTS[rid], key)
        if rid == "codex" and binpath:  # let the CLI store it too, so a plain `codex` works as well
            try:
                out = subprocess.run([binpath, "login", "--with-api-key"], input=key + "\n", capture_output=True,
                                     text=True, timeout=60, env=build_env(rid))
                job["lines"].append(_mask((out.stdout or "") + (out.stderr or "")).strip()[-400:])
            except (OSError, subprocess.TimeoutExpired) as exc:
                job["lines"].append(f"codex login --with-api-key: {exc}")
        set_mode("api_key")
        job.update(status="done", finished_at=time.time())
        return public_job(job)
    if not binpath:
        raise RuntimeError(f"{bin_name(rid)} is not installed — install it in Claws first")
    cmd = login_command(rid, method, binpath)
    env = build_env(rid)
    env.pop("NO_COLOR", None)
    env["BROWSER"] = env.get("BROWSER") or "true"  # the Hub shows the link; the CLI must not need a browser

    try:
        import pty

        master, slave = pty.openpty()
        proc = subprocess.Popen(cmd, stdin=slave, stdout=slave, stderr=slave, env=env, close_fds=True)
        os.close(slave)
        job["_master"] = master
    except (ImportError, OSError):  # Windows: no pty — pipes still show the URL of device-code logins
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                env=env, text=True)
        job["_master"] = None
    job["_proc"] = proc

    def reader() -> None:
        buf = ""
        while True:
            try:
                if job["_master"] is not None:
                    chunk = os.read(job["_master"], 4096).decode("utf-8", "replace")
                else:
                    chunk = proc.stdout.readline() if proc.stdout else ""
            except OSError:
                chunk = ""
            if not chunk:
                if proc.poll() is not None:
                    break
                time.sleep(0.1)
                continue
            buf += _ANSI.sub("", chunk)
            tok = _TOKEN.search(buf)
            if tok and rid == "claude-code":
                set_api_key(OAUTH_SLOT, tok.group(0))
                set_mode("oauth")
                job["token_saved"] = True
            clean = _mask(buf)
            if not job["url"]:
                m = _URL.search(clean)
                if m:
                    job["url"] = m.group(0).rstrip(".,)")
            if not job["code"]:
                m = _DEVICE_CODE.search(clean)
                if m:
                    job["code"] = m.group(1)
            job["needs_input"] = bool(re.search(r"(?i)(paste|enter).{0,40}(code|token)", clean[-300:]))
            job["lines"] = [ln for ln in clean.splitlines() if ln.strip()][-40:]
        rc = proc.wait()
        if job["_master"] is not None:
            try:
                os.close(job["_master"])
            except OSError:
                pass
        ok = rc == 0 and (job.get("token_saved") or rid == "codex")
        if ok and rid == "codex":
            set_mode("cli")
        job.update(status="done" if ok else "failed", finished_at=time.time(),
                   error="" if ok else (f"login exited with {rc}" if rc else "no token received"))

    threading.Thread(target=reader, name=job_id, daemon=True).start()
    return public_job(job)


def public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in job.items() if not k.startswith("_")}


def login_status(job_id: str) -> dict[str, Any]:
    job = _LOGINS.get(job_id)
    if not job:
        raise FileNotFoundError(job_id)
    return public_job(job)


def login_input(job_id: str, text: str) -> dict[str, Any]:
    job = _LOGINS.get(job_id)
    if not job:
        raise FileNotFoundError(job_id)
    data = (text or "").strip() + "\r"
    if job.get("_master") is not None:
        os.write(job["_master"], data.encode())
    elif job.get("_proc") and job["_proc"].stdin:
        job["_proc"].stdin.write(data + "\n")
        job["_proc"].stdin.flush()
    job["needs_input"] = False
    return public_job(job)


def auth_status(rid: str, *, binpath: str = "") -> dict[str, Any]:
    """Whether the agent can run, and how it is signed in (never returns a secret)."""
    binpath = binpath or find_bin(rid)
    mode = auth_mode(rid)
    info: dict[str, Any] = {"runtime": rid, "installed": bool(binpath), "bin": binpath, "mode": mode,
                            "logged_in": False, "detail": ""}
    if rid == "claude-code":
        if mode == "oauth" and _secret(OAUTH_SLOT):
            info.update(logged_in=True, detail="Claude subscription (token held by Agent Hub)")
        elif mode == "api_key" and _secret(API_SLOTS[rid]):
            info.update(logged_in=True, detail="Anthropic API key")
        elif mode == "env" and (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")):
            info.update(logged_in=True, detail="shell environment")
        elif (Path.home() / ".claude" / ".credentials.json").exists():
            info.update(logged_in=True, detail="Claude Code login (~/.claude)")
    else:
        if mode == "api_key" and _secret(API_SLOTS[rid]):
            info.update(logged_in=True, detail="OpenAI API key")
        elif binpath:
            try:
                out = subprocess.run([binpath, "login", "status"], capture_output=True, text=True, timeout=15,
                                     env=build_env(rid))
                text = _mask(((out.stdout or "") + (out.stderr or "")).strip())
                info["detail"] = text.splitlines()[-1][:200] if text else ""
                info["logged_in"] = out.returncode == 0 and "not logged in" not in text.lower()
            except (OSError, subprocess.TimeoutExpired) as exc:
                info["detail"] = str(exc)
        if not info["logged_in"] and (Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "auth.json").exists():
            info.update(logged_in=True, detail=info["detail"] or "Codex login (~/.codex)")
    info["permissions"] = permission_level()
    return info


def logout(rid: str, *, binpath: str = "") -> dict[str, Any]:
    from .secrets import set_api_key
    from .settings import load_campus_config, save_campus_config

    if rid == "claude-code":
        set_api_key(OAUTH_SLOT, "")
    set_api_key(API_SLOTS[rid], "")
    binpath = binpath or find_bin(rid)
    if rid == "codex" and binpath:
        try:
            subprocess.run([binpath, "logout"], capture_output=True, text=True, timeout=30, env=build_env(rid))
        except (OSError, subprocess.TimeoutExpired):
            pass
    cfg = load_campus_config()
    (cfg.setdefault("ali", {}).setdefault("agent_auth", {})).pop(rid, None)
    save_campus_config(cfg)
    return auth_status(rid, binpath=binpath)
