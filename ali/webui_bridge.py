"""Lifecycle bridge from Agent Hub → Hermes-WebUI (deep session UI).

Hub remains the control-plane shell. Hermes-WebUI runs as a separate local
process sharing the same ``HERMES_HOME``. See hermes-webui
``docs/agent-hub-bridge.md``.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from . import home
from .config import REPO_ROOT, hermes_home

DEFAULT_WEBUI_PORT = 8787
_PID_FILE_NAME = "hermes-webui.pid"
_STATE_FILE_NAME = "hermes-webui-bridge.json"


def _agent_cli_state_dir() -> Path:
    paths = home.ensure_home()
    state = paths.get("state") or (home.agent_cli_home() / "state")
    state.mkdir(parents=True, exist_ok=True)
    return state


def pid_path() -> Path:
    return _agent_cli_state_dir() / _PID_FILE_NAME


def bridge_state_path() -> Path:
    return _agent_cli_state_dir() / _STATE_FILE_NAME


def resolve_webui_root(cfg: dict[str, Any] | None = None) -> Path | None:
    """Locate the hermes-webui checkout."""
    env = os.environ.get("HERMES_WEBUI_ROOT", "").strip()
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env).expanduser())
    if isinstance(cfg, dict):
        webui_cfg = cfg.get("webui") if isinstance(cfg.get("webui"), dict) else {}
        root = str((webui_cfg or {}).get("root") or "").strip()
        if root:
            candidates.append(Path(root).expanduser())
    # Sibling of Agent-Hub checkout
    candidates.append(REPO_ROOT.parent / "hermes-webui")
    candidates.append(REPO_ROOT.parent / "Hermes-WebUI")
    # Common Windows layout used in this workspace
    candidates.append(Path("D:/hermes-webui"))
    seen: set[Path] = set()
    for raw in candidates:
        try:
            path = raw.resolve()
        except OSError:
            continue
        if path in seen:
            continue
        seen.add(path)
        if (path / "bootstrap.py").is_file() and (path / "server.py").is_file():
            return path
    return None


def webui_port(cfg: dict[str, Any] | None = None) -> int:
    env = os.environ.get("HERMES_WEBUI_PORT", "").strip()
    if env.isdigit():
        return int(env)
    if isinstance(cfg, dict):
        webui_cfg = cfg.get("webui") if isinstance(cfg.get("webui"), dict) else {}
        try:
            port = int((webui_cfg or {}).get("port") or 0)
            if port > 0:
                return port
        except (TypeError, ValueError):
            pass
    return DEFAULT_WEBUI_PORT


def webui_base_url(cfg: dict[str, Any] | None = None) -> str:
    return f"http://127.0.0.1:{webui_port(cfg)}"


def webui_state_dir() -> Path:
    override = os.environ.get("HERMES_WEBUI_STATE_DIR", "").strip()
    if override:
        path = Path(override).expanduser()
    else:
        path = home.agent_cli_home() / "hermes-webui-state"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_pid() -> int | None:
    path = pid_path()
    if not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8").strip()
        pid = int(raw)
        return pid if pid > 0 else None
    except (OSError, ValueError):
        return None


def _write_pid(pid: int) -> None:
    pid_path().write_text(str(int(pid)), encoding="utf-8")


def _clear_pid() -> None:
    try:
        pid_path().unlink(missing_ok=True)
    except OSError:
        pass


def _pid_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        if sys.platform == "win32":
            import ctypes

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if not handle:
                return False
            kernel32.CloseHandle(handle)
            return True
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def health_check(cfg: dict[str, Any] | None = None, timeout: float = 2.0) -> dict[str, Any]:
    base = webui_base_url(cfg)
    for path in ("/api/health", "/health"):
        url = f"{base}{path}"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read(4096)
                ok = 200 <= int(resp.status) < 300
                return {
                    "ok": ok,
                    "url": url,
                    "status": int(resp.status),
                    "body_preview": body[:120].decode("utf-8", errors="replace"),
                }
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            continue
    return {"ok": False, "url": f"{base}/api/health", "status": 0}


def open_url(cfg: dict[str, Any] | None = None, *, embedded: bool = True, profile: str = "") -> str:
    from urllib.parse import quote

    base = webui_base_url(cfg).rstrip("/")
    qs: list[str] = []
    if embedded:
        qs.append("embedded=1")
    if profile:
        qs.append(f"profile={quote(profile)}")
    return f"{base}/{'?' + '&'.join(qs) if qs else ''}"


def status(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    root = resolve_webui_root(cfg)
    port = webui_port(cfg)
    pid = _read_pid()
    healthy = health_check(cfg)
    running = bool(healthy.get("ok")) or _pid_alive(pid)
    if not healthy.get("ok") and not _pid_alive(pid):
        _clear_pid()
        pid = None
    hh = hermes_home()
    return {
        "ok": True,
        "running": running,
        "healthy": bool(healthy.get("ok")),
        "pid": pid if _pid_alive(pid) else None,
        "port": port,
        "base_url": webui_base_url(cfg),
        "open_url": open_url(cfg, embedded=True),
        "root": str(root) if root else "",
        "root_found": bool(root),
        "hermes_home": str(hh),
        "state_dir": str(webui_state_dir()),
        "health": healthy,
        "contract_path": str(route_contract_path()),
    }


def route_contract_path() -> Path:
    """Shared Hub→WebUI routing contract under Hermes home."""
    path = hermes_home() / "webui" / "hub_route_contract.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def export_route_contract(
    cfg: dict[str, Any] | None = None,
    *,
    last_decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write C0–C3 tier matrix for Hermes-WebUI token_optimizer."""
    from . import routing
    from .settings import load_campus_config

    cfg = cfg or load_campus_config()
    backend = cfg.get("backend") or {}
    provider = str((backend.get("type") or "")).strip() or None
    tiers: dict[str, dict[str, Any]] = {}
    for tier in ("C0", "C1", "C2", "C3"):
        info = routing.resolve_route(tier, "", cfg)
        model = str(info.get("model") or "").strip()
        if not model:
            continue
        entry: dict[str, Any] = {"model": model}
        prov = str(info.get("provider") or provider or "").strip()
        if prov and prov not in ("hybrid",):
            entry["provider"] = prov
        base_url = str(info.get("base_url") or "").strip()
        if base_url:
            entry["base_url"] = base_url
        tiers[tier] = entry

    ali = cfg.get("ali") if isinstance(cfg.get("ali"), dict) else {}
    mode = "recommended"
    if isinstance(ali, dict) and ali.get("token_optimizer_mode"):
        mode = str(ali.get("token_optimizer_mode")).strip().lower() or "recommended"
    if mode not in ("disabled", "observe", "recommended"):
        mode = "recommended"

    payload = {
        "version": 1,
        "source": "agent-hub",
        "mode": mode,
        "model_routing": bool(tiers),
        "adaptive_reasoning": True,
        "tool_compression": True,
        "tiers": tiers,
        "updated_at": time.time(),
        "hermes_home": str(hermes_home()),
    }
    if last_decision:
        payload["last_decision"] = {
            "tier": last_decision.get("tier"),
            "model": last_decision.get("model"),
            "provider": last_decision.get("provider"),
            "route_key": last_decision.get("route_key"),
            "auto": last_decision.get("auto"),
        }
    path = route_contract_path()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "path": str(path), "tiers": list(tiers.keys()), "mode": mode}


def _build_child_env(cfg: dict[str, Any] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    hh = str(hermes_home())
    env["HERMES_HOME"] = hh
    env["HERMES_WEBUI_STATE_DIR"] = str(webui_state_dir())
    env["HERMES_WEBUI_HOST"] = "127.0.0.1"
    env["HERMES_WEBUI_PORT"] = str(webui_port(cfg))
    env["HERMES_WEBUI_ALLOW_FRAME"] = "1"
    env["HERMES_WEBUI_PRESERVE_ENV"] = "1"
    env["HERMES_WEBUI_SKIP_ONBOARDING"] = env.get("HERMES_WEBUI_SKIP_ONBOARDING") or "1"
    # Point frame-ancestors allowlist via helpers (see hermes-webui api/helpers.py)
    hub_port = str(os.environ.get("HERMES_ALI_PORT") or "8765")
    env.setdefault(
        "HERMES_WEBUI_FRAME_ANCESTORS",
        f"'self' http://127.0.0.1:{hub_port} http://localhost:{hub_port}",
    )
    return env


def ensure_running(cfg: dict[str, Any] | None = None, *, timeout: float = 45.0) -> dict[str, Any]:
    """Start Hermes-WebUI if needed; always refresh the route contract."""
    from .settings import load_campus_config

    cfg = cfg or load_campus_config()
    try:
        export_route_contract(cfg)
    except Exception as exc:  # noqa: BLE001
        contract_error = str(exc)
    else:
        contract_error = ""

    current = status(cfg)
    if current.get("healthy"):
        current["started"] = False
        current["contract_error"] = contract_error
        return current

    root = resolve_webui_root(cfg)
    if not root:
        return {
            "ok": False,
            "error": "hermes-webui root not found",
            "error_zh": "未找到 hermes-webui 仓库（设置 HERMES_WEBUI_ROOT 或 webui.root）",
            "error_en": "hermes-webui checkout not found; set HERMES_WEBUI_ROOT or webui.root",
            **current,
            "contract_error": contract_error,
        }

    bootstrap = root / "bootstrap.py"
    python = sys.executable
    env = _build_child_env(cfg)
    port = webui_port(cfg)
    log_path = webui_state_dir() / f"hub-bridge-{port}.log"
    cmd = [
        python,
        str(bootstrap),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--no-browser",
    ]
    flags = 0
    if sys.platform == "win32":
        for attr in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP", "CREATE_NO_WINDOW"):
            flags |= getattr(subprocess, attr, 0)
    with log_path.open("ab") as log_file:
        popen_kwargs: dict[str, Any] = {
            "cwd": str(root),
            "env": env,
            "stdin": subprocess.DEVNULL,
            "stdout": log_file,
            "stderr": subprocess.STDOUT,
        }
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = flags
            popen_kwargs["close_fds"] = True
        else:
            popen_kwargs["start_new_session"] = True
        proc = subprocess.Popen(cmd, **popen_kwargs)
    _write_pid(proc.pid)
    bridge_state_path().write_text(
        json.dumps(
            {
                "pid": proc.pid,
                "port": port,
                "root": str(root),
                "log": str(log_path),
                "started_at": time.time(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    deadline = time.time() + max(5.0, float(timeout))
    last_health: dict[str, Any] = {}
    while time.time() < deadline:
        last_health = health_check(cfg, timeout=1.5)
        if last_health.get("ok"):
            out = status(cfg)
            out["started"] = True
            out["log"] = str(log_path)
            out["contract_error"] = contract_error
            return out
        time.sleep(0.5)

    return {
        "ok": False,
        "started": True,
        "error": "webui health timeout",
        "error_zh": f"WebUI 启动超时，请查看日志 {log_path}",
        "error_en": f"WebUI health timeout; see log {log_path}",
        "log": str(log_path),
        "health": last_health,
        **status(cfg),
        "contract_error": contract_error,
    }


def stop(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    pid = _read_pid()
    stopped = False
    if pid and _pid_alive(pid):
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    check=False,
                    capture_output=True,
                )
            else:
                os.kill(pid, signal.SIGTERM)
            stopped = True
        except OSError as exc:
            return {"ok": False, "error": str(exc), "pid": pid}
    _clear_pid()
    try:
        bridge_state_path().unlink(missing_ok=True)
    except OSError:
        pass
    # Best-effort: wait briefly for port to free
    for _ in range(10):
        if not health_check(cfg, timeout=0.5).get("ok"):
            break
        time.sleep(0.2)
    return {"ok": True, "stopped": stopped, "pid": pid, **status(cfg)}


def sync_before_open(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Sync Hub → Hermes assets then ensure WebUI is up (Phase 2 strengthening)."""
    from . import hermes_cli
    from .settings import load_campus_config

    cfg = cfg or load_campus_config()
    results: dict[str, Any] = {}
    try:
        results["hermes_sync"] = hermes_cli.sync_hub_to_hermes(cfg)
    except Exception as exc:  # noqa: BLE001
        results["hermes_sync"] = {"ok": False, "error": str(exc)}
    try:
        results["contract"] = export_route_contract(cfg)
    except Exception as exc:  # noqa: BLE001
        results["contract"] = {"ok": False, "error": str(exc)}
    results["webui"] = ensure_running(cfg)
    results["ok"] = bool(results["webui"].get("healthy") or results["webui"].get("ok"))
    return results
