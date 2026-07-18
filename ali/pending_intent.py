"""Phase 2 mid-turn controls: Queue / Steer / Stop-and-send.

In-memory pending intents per session. Adapted from Hermes-WebUI semantics
without embedding the WebUI.
"""

from __future__ import annotations

import threading
import time
from typing import Any

_lock = threading.RLock()

# session_id -> {queue: str|None, steer: str|None, busy_mode: str, updated_at: float}
_PENDING: dict[str, dict[str, Any]] = {}

# session_id -> list of steer snippets delivered this run (for UI / journal)
_STEER_LOG: dict[str, list[str]] = {}


def get(session_id: str) -> dict[str, Any]:
    sid = (session_id or "").strip()
    with _lock:
        row = dict(_PENDING.get(sid) or {})
        row.setdefault("queue", None)
        row.setdefault("steer", None)
        row.setdefault("busy_mode", "queue")
        row["has_queue"] = bool(row.get("queue"))
        row["has_steer"] = bool(row.get("steer"))
        row["steer_log"] = list(_STEER_LOG.get(sid) or [])
        return row


def set_busy_mode(session_id: str, mode: str) -> dict[str, Any]:
    sid = (session_id or "").strip()
    m = (mode or "queue").strip().lower()
    if m not in ("queue", "steer"):
        m = "queue"
    with _lock:
        row = _PENDING.setdefault(sid, {})
        row["busy_mode"] = m
        row["updated_at"] = time.time()
    return get(sid)


def enqueue(session_id: str, text: str) -> dict[str, Any]:
    sid = (session_id or "").strip()
    msg = (text or "").strip()
    if not sid or not msg:
        return {"ok": False, "error": "session_id and text required"}
    with _lock:
        row = _PENDING.setdefault(sid, {})
        # Replace previous queue (single pending slot, WebUI-style)
        row["queue"] = msg
        row["updated_at"] = time.time()
        row.setdefault("busy_mode", "queue")
    return {"ok": True, "action": "queue", **get(sid)}


def steer(session_id: str, text: str) -> dict[str, Any]:
    sid = (session_id or "").strip()
    msg = (text or "").strip()
    if not sid or not msg:
        return {"ok": False, "error": "session_id and text required"}
    with _lock:
        row = _PENDING.setdefault(sid, {})
        row["steer"] = msg
        row["updated_at"] = time.time()
        log = _STEER_LOG.setdefault(sid, [])
        log.append(msg)
        if len(log) > 20:
            del log[:-20]
    # Notify running stream if any
    try:
        from . import streaming

        streaming.inject_steer(sid, msg)
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "action": "steer", **get(sid)}


def clear_steer(session_id: str) -> None:
    sid = (session_id or "").strip()
    with _lock:
        row = _PENDING.get(sid)
        if row:
            row["steer"] = None


def pop_queue(session_id: str) -> str | None:
    sid = (session_id or "").strip()
    with _lock:
        row = _PENDING.get(sid) or {}
        msg = row.get("queue")
        if row:
            row["queue"] = None
        return str(msg).strip() if msg else None


def clear_run(session_id: str) -> None:
    """Clear steer for a finished run; keep queue for drain."""
    sid = (session_id or "").strip()
    with _lock:
        row = _PENDING.get(sid)
        if row:
            row["steer"] = None
        _STEER_LOG.pop(sid, None)


def consume_steer_for_prompt(session_id: str) -> str | None:
    """Return and clear current steer text for injection into the active turn."""
    sid = (session_id or "").strip()
    with _lock:
        row = _PENDING.get(sid) or {}
        msg = row.get("steer")
        if row:
            row["steer"] = None
        return str(msg).strip() if msg else None
