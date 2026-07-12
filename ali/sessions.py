"""JSON session store for Hermes-ALI."""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .config import SESSIONS_DIR, ensure_state_dirs

_lock = threading.RLock()


@dataclass
class Session:
    id: str
    title: str
    created_at: float
    updated_at: float
    model: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    pinned: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Session":
        return cls(
            id=data["id"],
            title=data.get("title") or "New chat",
            created_at=float(data.get("created_at") or time.time()),
            updated_at=float(data.get("updated_at") or time.time()),
            model=data.get("model") or "",
            messages=list(data.get("messages") or []),
            pinned=bool(data.get("pinned")),
        )


def _path(session_id: str) -> Path:
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_")
    return SESSIONS_DIR / f"{safe}.json"


def list_sessions() -> list[dict[str, Any]]:
    ensure_state_dirs()
    items: list[dict[str, Any]] = []
    with _lock:
        for path in SESSIONS_DIR.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                s = Session.from_dict(data)
                items.append(
                    {
                        "id": s.id,
                        "title": s.title,
                        "created_at": s.created_at,
                        "updated_at": s.updated_at,
                        "model": s.model,
                        "pinned": s.pinned,
                        "message_count": len(s.messages),
                    }
                )
            except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
    items.sort(key=lambda x: (not x["pinned"], -x["updated_at"]))
    return items


def get_session(session_id: str) -> Session | None:
    path = _path(session_id)
    if not path.is_file():
        return None
    with _lock:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Session.from_dict(data)
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None


def save_session(session: Session) -> None:
    ensure_state_dirs()
    path = _path(session.id)
    with _lock:
        path.write_text(json.dumps(session.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def create_session(title: str = "New chat", model: str = "") -> Session:
    now = time.time()
    session = Session(
        id=str(uuid.uuid4()),
        title=title or "New chat",
        created_at=now,
        updated_at=now,
        model=model or "",
    )
    save_session(session)
    return session


def delete_session(session_id: str) -> bool:
    path = _path(session_id)
    with _lock:
        if path.is_file():
            path.unlink()
            return True
    return False


def update_session(
    session_id: str,
    *,
    title: str | None = None,
    model: str | None = None,
    pinned: bool | None = None,
    messages: list[dict[str, Any]] | None = None,
) -> Session | None:
    session = get_session(session_id)
    if session is None:
        return None
    if title is not None:
        session.title = title.strip() or session.title
    if model is not None:
        session.model = model
    if pinned is not None:
        session.pinned = pinned
    if messages is not None:
        session.messages = messages
    session.updated_at = time.time()
    save_session(session)
    return session


def append_messages(session_id: str, *msgs: dict[str, Any]) -> Session | None:
    session = get_session(session_id)
    if session is None:
        return None
    session.messages.extend(msgs)
    # Auto-title from first user message
    if session.title in ("New chat", "新对话", "") and msgs:
        first = next((m for m in msgs if m.get("role") == "user"), None)
        if first and isinstance(first.get("content"), str):
            text = first["content"].strip().replace("\n", " ")
            session.title = (text[:48] + "…") if len(text) > 48 else text or session.title
    session.updated_at = time.time()
    save_session(session)
    return session
