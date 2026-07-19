"""Configuration and path discovery for Hermes-ALI."""

from __future__ import annotations

import ipaddress
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

VERSION = "5.0.1"
APP_NAME = "Agent Hub"
APP_TAGLINE = "Control UI · claws use native homes (~/.hermes · ~/.openclaw · ~/.nanobot)"

# Default bind: all interfaces so phones / other PCs can connect by IP
DEFAULT_HOST = os.environ.get("HERMES_ALI_HOST", "0.0.0.0")
DEFAULT_PORT = int(os.environ.get("HERMES_ALI_PORT", "8765"))

# Optional shared password for remote access (empty = no auth)
AUTH_PASSWORD = os.environ.get("HERMES_ALI_PASSWORD", "").strip()
AUTH_PASSWORD_SHA256 = os.environ.get("HERMES_ALI_PASSWORD_SHA256", "").strip().lower()

# Optional canonical URL supplied by an HTTPS tunnel or reverse proxy. Public
# address discovery is deliberately explicit because NAT and proxy headers make
# automatic detection unreliable and easy to spoof.
def _public_url() -> str:
    value = os.environ.get("HERMES_ALI_PUBLIC_URL", "").strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    return value


PUBLIC_URL = _public_url()

_PUBLIC_IP_CACHE: dict[str, str | float] = {"value": "", "expires": 0.0}
_PUBLIC_IP_LOCK = threading.Lock()
_PUBLIC_IP_SERVICES = (
    "https://api.ipify.org",
    "https://checkip.amazonaws.com",
    "https://icanhazip.com",
)


def public_ip() -> str:
    """Return the detected public IP with a short failure/success cache."""
    now = time.monotonic()
    if now < float(_PUBLIC_IP_CACHE["expires"]):
        return str(_PUBLIC_IP_CACHE["value"])
    with _PUBLIC_IP_LOCK:
        now = time.monotonic()
        if now < float(_PUBLIC_IP_CACHE["expires"]):
            return str(_PUBLIC_IP_CACHE["value"])
        value = ""
        curl = shutil.which("curl")
        for service in _PUBLIC_IP_SERVICES:
            try:
                if curl:
                    result = subprocess.run(
                        [curl, "--fail", "--silent", "--show-error", "--max-time", "2", service],
                        capture_output=True,
                        check=False,
                        text=True,
                        timeout=2.5,
                    )
                    if result.returncode != 0:
                        continue
                    candidate = result.stdout.strip()
                else:
                    request = Request(service, headers={"User-Agent": f"Agent-Hub/{VERSION}"})
                    with urlopen(request, timeout=1.5) as response:
                        candidate = response.read(80).decode("ascii").strip()
                address = ipaddress.ip_address(candidate)
                if address.is_global:
                    value = str(address)
                    break
            except (OSError, subprocess.SubprocessError, UnicodeError, ValueError):
                continue
        _PUBLIC_IP_CACHE["value"] = value
        _PUBLIC_IP_CACHE["expires"] = now + (600.0 if value else 60.0)
        return value

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
    """Candidate directories that may contain run_agent.py (native ~/.hermes first)."""
    from .home import ensure_home, runtime_dir

    ensure_home()
    home = hermes_home()
    candidates = [
        home / "hermes-agent",
        home,
        Path("/usr/local/lib/hermes-agent"),
        # Legacy Hub parallel cache (read-only fallback)
        runtime_dir("hermes") / "hermes-agent",
        runtime_dir("hermes"),
    ]
    env_dir = os.environ.get("HERMES_ALI_AGENT_DIR", "").strip() or os.environ.get("AGENT_CLI_HERMES_DIR", "").strip()
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
    from .home import ensure_home

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    ensure_home()


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
