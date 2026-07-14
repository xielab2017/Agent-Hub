"""Invoke connected Claw CLIs (OpenClaw family) from Agent Hub.

Hub is the control UI: install / LLM / soul / skills target **native** homes
(``~/.openclaw``). Chat defaults to fast Direct streaming; this module is for
optional full-agent turns and workspace personality injection.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

OPENCLAW_FAMILY = frozenset({"openclaw", "qqclaw", "aliyun_claw"})

_WORKSPACE_FILES = (
    "SOUL.md",
    "IDENTITY.md",
    "AGENTS.md",
    "USER.md",
    "TOOLS.md",
)


def is_openclaw_family(runtime_id: str) -> bool:
    return str(runtime_id or "").strip() in OPENCLAW_FAMILY


def openclaw_native_home() -> Path:
    return Path.home() / ".openclaw"


def openclaw_workspace() -> Path:
    return openclaw_native_home() / "workspace"


def find_openclaw_bin() -> Path | None:
    """Prefer PATH / native global install."""
    which = shutil.which("openclaw")
    if which:
        return Path(which)
    return None


def openclaw_cli_status() -> dict[str, Any]:
    bin_path = find_openclaw_bin()
    native = openclaw_native_home()
    return {
        "available": bin_path is not None,
        "bin": str(bin_path) if bin_path else "",
        "native_home": str(native),
        "native_present": native.is_dir() and any(native.iterdir()) if native.is_dir() else False,
        "workspace": str(openclaw_workspace()),
        "prefer_native": True,
    }


def parallel_vs_native_note(runtime_id: str) -> dict[str, str]:
    """Short honesty copy for Control Center."""
    rid = str(runtime_id or "").strip()
    if rid == "hermes":
        return {
            "zh": "安装/LLM/Soul/Skills → 原生 `~/.hermes`。Hub 默认 Agent 模式（Hermes 工具/Skill）；快聊见 composer「快聊」。",
            "en": "Install/LLM/soul/skills → native `~/.hermes`. Hub defaults to Agent mode (Hermes tools/skills); use composer Fast chat for Direct.",
        }
    if is_openclaw_family(rid):
        return {
            "zh": "安装/LLM/Soul/Skills → 原生 `~/.openclaw`。Hub Agent 模式调用 `openclaw agent --local`；快聊为 Direct 流式。",
            "en": "Install/LLM/soul/skills → native `~/.openclaw`. Hub Agent mode runs `openclaw agent --local`; Fast chat uses Direct streaming.",
        }
    return {
        "zh": "Hub 是操作界面；各 Claw 使用各自原生目录。聊天优先速度（Direct 流式）。",
        "en": "Hub is the control UI; claws use native homes. Chat prioritizes speed (Direct streaming).",
    }


def load_claw_workspace_context(runtime_id: str = "openclaw", *, max_chars: int = 6000) -> str:
    """Read native OpenClaw workspace personality files for Direct-LLM fallback."""
    if not is_openclaw_family(runtime_id) and runtime_id not in ("", "auto"):
        # Still try openclaw workspace when family aliases are used
        pass
    root = openclaw_workspace()
    if not root.is_dir():
        return ""
    parts: list[str] = [
        "## Connected Claw workspace (OpenClaw)",
        f"Workspace: `{root}`",
        "You are the OpenClaw agent for this workspace. Honor SOUL / IDENTITY / AGENTS / USER / TOOLS below.",
        "Do not pretend to be a generic Hub chatbot; keep claw personality, tone, and tool preferences.",
    ]
    used = 0
    for name in _WORKSPACE_FILES:
        path = root / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if not text:
            continue
        budget = max(800, max_chars - used)
        if len(text) > budget:
            text = text[: budget - 20] + "\n…(truncated)"
        parts.append(f"### {name}\n{text}")
        used += len(text)
        if used >= max_chars:
            break
    return "\n\n".join(parts).strip()


def enrich_preamble_with_claw(preamble: str, runtime_id: str) -> str:
    block = load_claw_workspace_context(runtime_id)
    if not block:
        return preamble or ""
    base = (preamble or "").strip()
    if not base:
        return block
    if "Connected Claw workspace" in base:
        return base
    return f"{base}\n\n{block}".strip()


def _parse_openclaw_json(stdout: str, stderr: str) -> dict[str, Any]:
    raw = (stdout or "").strip()
    if not raw:
        raw = (stderr or "").strip()
    # Prefer last JSON object in output (warnings may precede it)
    candidates: list[str] = []
    if raw.startswith("{") and raw.endswith("}"):
        candidates.append(raw)
    for m in re.finditer(r"\{[\s\S]*\}", raw):
        candidates.append(m.group(0))
    for blob in reversed(candidates):
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return {}


def _extract_reply_text(data: dict[str, Any]) -> str:
    if not data:
        return ""
    for key in ("reply", "text", "message", "output", "result", "content", "final"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, dict):
            nested = _extract_reply_text(val)
            if nested:
                return nested
    payloads = data.get("payloads")
    if isinstance(payloads, list):
        bits = []
        for p in payloads:
            if isinstance(p, dict) and isinstance(p.get("text"), str):
                bits.append(p["text"])
            elif isinstance(p, str):
                bits.append(p)
        if bits:
            return "\n".join(bits).strip()
    return ""


def build_openclaw_env(
    *,
    api_key: str = "",
    env_name: str = "",
    base_url: str = "",
    provider_id: str = "",
) -> dict[str, str]:
    """Subprocess env using native OpenClaw home; inject Hub keys for --local."""
    env = {k: v for k, v in os.environ.items()}
    # Never point OpenClaw at the thin parallel dir — native home has identity/skills.
    native = openclaw_native_home()
    if native.is_dir():
        env["OPENCLAW_STATE_DIR"] = str(native)
        cfg = native / "openclaw.json"
        if cfg.is_file():
            env["OPENCLAW_CONFIG_PATH"] = str(cfg)
    slot = (env_name or "OPENAI_API_KEY").strip()
    if slot and api_key:
        env[slot] = api_key
    if api_key:
        env.setdefault("OPENAI_API_KEY", api_key)
    if base_url:
        env["OPENAI_BASE_URL"] = base_url
        env["OPENAI_API_BASE"] = base_url
    pid = (provider_id or "").strip()
    if pid == "openrouter" and api_key:
        env["OPENROUTER_API_KEY"] = api_key
    if pid == "nvidia-nim" and api_key:
        env["NVIDIA_API_KEY"] = api_key
    if pid == "anthropic" and api_key:
        env["ANTHROPIC_API_KEY"] = api_key
    if pid == "deepseek" and api_key:
        env["DEEPSEEK_API_KEY"] = api_key
    if pid in ("gemini", "google") and api_key:
        env["GOOGLE_API_KEY"] = api_key
        env["GEMINI_API_KEY"] = api_key
    if pid in ("moonshot", "kimi") and api_key:
        env["MOONSHOT_API_KEY"] = api_key
    if pid == "minimax" and api_key:
        env["MINIMAX_API_KEY"] = api_key
    env["NO_COLOR"] = "1"
    return env


def run_openclaw_chat(
    prompt: str,
    *,
    session_id: str = "",
    agent: str = "main",
    api_key: str = "",
    env_name: str = "",
    base_url: str = "",
    provider_id: str = "",
    timeout: float = 180,
) -> dict[str, Any]:
    bin_path = find_openclaw_bin()
    if not bin_path:
        raise FileNotFoundError("openclaw CLI not found — install/connect OpenClaw first")

    sid = (session_id or "").strip() or f"agent-hub-{uuid.uuid4().hex[:12]}"
    agent_id = (agent or "main").strip() or "main"
    env = build_openclaw_env(
        api_key=api_key,
        env_name=env_name,
        base_url=base_url,
        provider_id=provider_id,
    )
    cmd = [
        str(bin_path),
        "agent",
        "--local",
        "--agent",
        agent_id,
        "--session-id",
        sid,
        "--message",
        prompt,
        "--json",
        "--timeout",
        str(max(30, int(timeout))),
    ]
    cwd = str(openclaw_workspace()) if openclaw_workspace().is_dir() else None
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout + 15,
        env=env,
        cwd=cwd,
    )
    out = proc.stdout or ""
    err = proc.stderr or ""
    data = _parse_openclaw_json(out, err)
    text = _extract_reply_text(data)
    if not text and proc.returncode == 0:
        # Non-JSON quiet text
        cleaned = out.strip()
        if cleaned and not cleaned.startswith("{"):
            text = cleaned
    if proc.returncode != 0 and not text:
        tip = (err or out or f"openclaw exited {proc.returncode}").strip()
        tip = re.sub(r"\x1b\[[0-9;]*m", "", tip)
        # Prefer the actionable Error: line over plugin noise / config warnings
        for line in reversed(tip.splitlines()):
            low = line.lower()
            if "error:" in low or "unknown model" in low or "lane task error" in low:
                tip = line.strip()
                break
        raise RuntimeError(tip[-2000:])
    return {
        "ok": bool(text),
        "text": text,
        "bin": str(bin_path),
        "session_id": sid,
        "agent": agent_id,
        "raw": data,
        "returncode": proc.returncode,
        "stderr_tail": (err or "")[-800:],
    }
