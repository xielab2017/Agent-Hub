"""Configuration and path discovery for Hermes-ALI."""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

VERSION = "1.1.2"
APP_NAME = "Hermes-ALI"

# Default bind: all interfaces so phones / other PCs can connect by IP
DEFAULT_HOST = os.environ.get("HERMES_ALI_HOST", "0.0.0.0")
DEFAULT_PORT = int(os.environ.get("HERMES_ALI_PORT", "8765"))

# Optional shared password for remote access (empty = no auth)
AUTH_PASSWORD = os.environ.get("HERMES_ALI_PASSWORD", "").strip()

# State directory
def _default_state_dir() -> Path:
    override = os.environ.get("HERMES_ALI_STATE_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "hermes-ali"
    return Path.home() / ".hermes" / "ali"


STATE_DIR = _default_state_dir()
SESSIONS_DIR = STATE_DIR / "sessions"
SETTINGS_FILE = STATE_DIR / "settings.json"

# Hermes Agent home
def hermes_home() -> Path:
    env = os.environ.get("HERMES_HOME", "").strip()
    if env:
        return Path(env).expanduser()
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "hermes"
    return Path.home() / ".hermes"


def discover_agent_dirs() -> list[Path]:
    """Candidate directories that may contain run_agent.py."""
    home = hermes_home()
    candidates = [
        home / "hermes-agent",
        Path("/usr/local/lib/hermes-agent"),
    ]
    env_dir = os.environ.get("HERMES_ALI_AGENT_DIR", "").strip()
    if env_dir:
        candidates.insert(0, Path(env_dir).expanduser())
    for p in (
        Path.home() / "hermes-agent",
        Path.home() / "src" / "hermes-agent",
        Path.home() / "Projects" / "hermes-agent",
    ):
        candidates.append(p)
    out: list[Path] = []
    seen = set()
    for c in candidates:
        try:
            resolved = c.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if (resolved / "run_agent.py").is_file() or (resolved / "run_agent" / "__init__.py").is_file():
            out.append(resolved)
    return out


def ensure_state_dirs() -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def local_ips() -> list[str]:
    """Best-effort LAN IPs for connection hints."""
    ips: list[str] = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127.") and ip not in ips:
            ips.insert(0, ip)
    except OSError:
        pass
    return ips


REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = REPO_ROOT / "static"

# Filled by server.main() at runtime
RUNTIME: dict = {
    "host": DEFAULT_HOST,
    "port": DEFAULT_PORT,
}
