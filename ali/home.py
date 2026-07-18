"""Agent Hub control-plane home.

Hub owns UI state, digests, backups, and an optional skill *catalog* under
``~/.agent-cli``. Live Claw installs, LLM configs, SOUL, and skills for each
agent live in that claw's **native** home (``~/.hermes``, ``~/.openclaw``,
``~/.nanobot``, …). ``runtimes/`` is legacy cache only — not the operational home.
"""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path
from typing import Any


def agent_cli_home() -> Path:
    override = (
        os.environ.get("AGENT_CLI_HOME", "").strip()
        or os.environ.get("HERMES_ALI_HOME", "").strip()
    )
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return (base / "agent-cli").resolve()
    return (Path.home() / ".agent-cli").resolve()


def os_profile() -> dict[str, Any]:
    system = platform.system().lower()  # darwin | linux | windows
    machine = platform.machine().lower()
    is_wsl = False
    if system == "linux":
        try:
            is_wsl = "microsoft" in Path("/proc/version").read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            is_wsl = False
    kind = "macos" if system == "darwin" else ("windows" if system == "windows" else ("wsl" if is_wsl else "linux"))
    shell = "powershell" if system == "windows" and not is_wsl else "bash"
    return {
        "system": system,
        "kind": kind,
        "machine": machine,
        "shell": shell,
        "is_wsl": is_wsl,
        "platform": platform.platform(),
        "python": sys.version.split()[0],
    }


def layout() -> dict[str, Path]:
    root = agent_cli_home()
    return {
        "root": root,
        "runtimes": root / "runtimes",  # legacy cache; not live claw homes
        "skills": root / "skills",  # Hub catalog; sync into native claw dirs on connect
        "ecosystem": root / "ecosystem",
        "backups": root / "backups",
        "digests": root / "digests",
        "recommend": root / "recommend",
        "logs": root / "logs",
        "state": root / "state",
        "runs": root / "runs",
    }


def ensure_home() -> dict[str, Path]:
    paths = layout()
    for key, p in paths.items():
        if key == "root":
            p.mkdir(parents=True, exist_ok=True)
        else:
            p.mkdir(parents=True, exist_ok=True)
    readme = paths["root"] / "README.md"
    if not readme.is_file():
        readme.write_text(
            "# Agent Hub Home\n\n"
            "Control-plane data for Agent Hub. **Live claws use their native homes.**\n\n"
            "- Hub catalog: `skills/`, `ecosystem/`, `backups/`, `digests/`\n"
            "- Hermes → `~/.hermes` · OpenClaw → `~/.openclaw` · NanoBot → `~/.nanobot`\n"
            "- `runtimes/` — legacy install cache only (not the operational agent home)\n",
            encoding="utf-8",
        )
    return paths


def runtime_dir(runtime_id: str) -> Path:
    """Legacy parallel cache path (do not use as HERMES_HOME / OPENCLAW_STATE_DIR)."""
    return ensure_home()["runtimes"] / runtime_id


def native_claw_home(runtime_id: str) -> Path | None:
    """Canonical native state home for a claw id (None for builtins / unknown)."""
    rid = (runtime_id or "").strip()
    home = Path.home()
    mapping = {
        "hermes": home / ".hermes",
        "openclaw": home / ".openclaw",
        "qqclaw": home / ".openclaw",
        "aliyun_claw": home / ".openclaw",
        "nanobot": home / ".nanobot",
        "nano_claw": home / ".nano-claw",
        "nanoclaw": home / "nanoclaw",
    }
    if rid in mapping:
        return mapping[rid]
    if rid and rid not in ("direct", "auto"):
        return home / f".{rid}"
    return None


def skill_dir(skill_id: str = "") -> Path:
    base = ensure_home()["skills"]
    return base / skill_id if skill_id else base


def ecosystem_dir(name: str = "") -> Path:
    base = ensure_home()["ecosystem"]
    return base / name if name else base


def home_status() -> dict[str, Any]:
    paths = ensure_home()
    counts = {}
    for key in ("runtimes", "skills", "ecosystem", "backups", "digests"):
        p = paths[key]
        try:
            counts[key] = len([x for x in p.iterdir() if not x.name.startswith(".")])
        except OSError:
            counts[key] = 0
    natives = {
        "hermes": str(Path.home() / ".hermes"),
        "openclaw": str(Path.home() / ".openclaw"),
        "nanobot": str(Path.home() / ".nanobot"),
    }
    return {
        "ok": True,
        "home": str(paths["root"]),
        "mode": "native-claws",
        "os": os_profile(),
        "paths": {k: str(v) for k, v in paths.items()},
        "native_homes": natives,
        "counts": counts,
        "note_zh": "Hub 为操作界面；安装 / LLM / Soul / Skills 指向各 Claw 原生目录。",
        "note_en": "Hub is the control UI; install/LLM/soul/skills target each claw’s native home.",
    }
