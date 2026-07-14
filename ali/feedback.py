"""Message rating / purification self-feedback store."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from .config import STATE_DIR, ensure_state_dirs
from . import sessions as store

FEEDBACK_DIR = STATE_DIR / "feedback"


def _path(session_id: str) -> Any:
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_")
    return FEEDBACK_DIR / f"{safe}.jsonl"


def rate_message(
    session_id: str,
    message_id: str,
    *,
    rating: int,
    note: str = "",
    model: str = "",
    content_preview: str = "",
) -> dict[str, Any]:
    """rating: 1..5 or -1 (bad) / 1 (good) — we accept both scales."""
    ensure_state_dirs()
    if rating not in (-1, 0, 1, 2, 3, 4, 5):
        raise ValueError("rating must be -1..5")
    # Also stamp onto the session message if found
    session = store.get_session(session_id)
    if session:
        changed = False
        for m in session.messages:
            if m.get("id") == message_id:
                m["feedback"] = {
                    "rating": rating,
                    "note": (note or "")[:500],
                    "ts": time.time(),
                }
                changed = True
                break
        if changed:
            store.save_session(session)

    entry = {
        "id": str(uuid.uuid4()),
        "ts": time.time(),
        "session_id": session_id,
        "message_id": message_id,
        "rating": rating,
        "note": (note or "")[:500],
        "model": model or "",
        "content_preview": (content_preview or "")[:400],
    }
    path = _path(session_id)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return {"ok": True, "entry": entry}


def summary(limit: int = 50) -> dict[str, Any]:
    ensure_state_dirs()
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for path in sorted(FEEDBACK_DIR.glob("*.jsonl"), key=lambda p: -p.stat().st_mtime):
        try:
            for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
                rows.append(json.loads(line))
        except (OSError, json.JSONDecodeError):
            continue
    rows.sort(key=lambda r: -float(r.get("ts") or 0))
    rows = rows[:limit]
    # Scales: thumbs -1/1, or stars 1–5 (4–5 good, 1–2 bad)
    thumbs_up = sum(1 for r in rows if int(r.get("rating") or 0) in (1, 4, 5))
    thumbs_down = sum(1 for r in rows if int(r.get("rating") or 0) in (-1, 2))
    return {
        "count": len(rows),
        "thumbs_up": thumbs_up,
        "thumbs_down": thumbs_down,
        "recent": rows[:20],
    }
