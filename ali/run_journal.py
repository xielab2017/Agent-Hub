"""Append-only run event journal for Hub SSE (Phase 2).

Mirrors in-memory JOBS events to disk JSONL so clients can resume with
``from_seq`` / Last-Event-ID after reconnect, without embedding Hermes-WebUI.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from .home import ensure_home

_lock = threading.RLock()


def _runs_dir() -> Path:
    paths = ensure_home()
    d = paths.get("runs") or (paths["root"] / "runs")
    d.mkdir(parents=True, exist_ok=True)
    return d


def journal_path(stream_id: str) -> Path:
    safe = "".join(c for c in (stream_id or "") if c.isalnum() or c in "-_") or "unknown"
    return _runs_dir() / f"{safe}.jsonl"


def append_event(stream_id: str, seq: int, event: str, data: dict[str, Any] | None = None) -> None:
    """Append one journal line. Best-effort; never raises into the chat path."""
    sid = (stream_id or "").strip()
    if not sid:
        return
    row = {
        "seq": int(seq),
        "event": event,
        "data": data if isinstance(data, dict) else {},
        "ts": time.time(),
    }
    path = journal_path(sid)
    try:
        with _lock:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    except OSError:
        return


def read_events(stream_id: str, *, from_seq: int = 0, limit: int = 5000) -> list[dict[str, Any]]:
    """Load journal events with seq >= from_seq (1-based seq preferred)."""
    path = journal_path(stream_id)
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                seq = int(row.get("seq") or 0)
                if seq < int(from_seq or 0):
                    continue
                out.append(row)
                if len(out) >= limit:
                    break
    except OSError:
        return []
    return out


def status(stream_id: str) -> dict[str, Any]:
    events = read_events(stream_id, from_seq=0, limit=100000)
    last = events[-1] if events else None
    return {
        "ok": True,
        "stream_id": stream_id,
        "path": str(journal_path(stream_id)),
        "event_count": len(events),
        "last_seq": (last or {}).get("seq"),
        "last_event": (last or {}).get("event"),
        "exists": journal_path(stream_id).is_file(),
    }
