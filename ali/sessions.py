"""JSON session store for Hermes-ALI."""

from __future__ import annotations

import json
import os
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
    archived: bool = False
    # Ephemeral parallel subagent lanes (hidden from sidebar by default)
    hidden: bool = False
    parent_id: str = ""
    folder_id: str = ""
    summary: str = ""
    facts: list[str] = field(default_factory=list)
    todos: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

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
            archived=bool(data.get("archived")),
            hidden=bool(data.get("hidden")),
           parent_id=str(data.get("parent_id") or ""),
            folder_id=str(data.get("folder_id") or ""),
            summary=str(data.get("summary") or ""),
            facts=[str(x) for x in (data.get("facts") or []) if str(x).strip()],
            todos=[str(x) for x in (data.get("todos") or []) if str(x).strip()],
            tags=[str(x) for x in (data.get("tags") or []) if str(x).strip()],
        )


def _path(session_id: str) -> Path:
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_")
    return SESSIONS_DIR / f"{safe}.json"


def _session_active_job(session_id: str) -> dict[str, Any] | None:
    try:
        from . import streaming

        return streaming.session_job(session_id)
    except Exception:  # noqa: BLE001
        return None


def list_sessions(*, include_archived: bool = False, include_hidden: bool = False) -> list[dict[str, Any]]:
    ensure_state_dirs()
    items: list[dict[str, Any]] = []
    with _lock:
        for path in SESSIONS_DIR.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                s = Session.from_dict(data)
                if s.archived and not include_archived:
                    continue
                if s.hidden and not include_hidden:
                    continue
                items.append(
                    {
                        "id": s.id,
                        "title": s.title,
                        "created_at": s.created_at,
                        "updated_at": s.updated_at,
                        "model": s.model,
                        "pinned": s.pinned,
                        "archived": s.archived,
                        "hidden": s.hidden,
                       "parent_id": s.parent_id,
                        "folder_id": s.folder_id,
                        "summary": s.summary,
                        "facts": s.facts,
                        "todos": s.todos,
                        "tags": s.tags,
                        "message_count": len(s.messages),
                        "active_job": _session_active_job(s.id),
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
        # Replace the complete document atomically so refreshes never parse a
        # partially written session while a task is being finalized.
        tmp = path.with_name(f".{path.name}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(session.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)


def create_session(
    title: str = "New chat",
    model: str = "",
    *,
    hidden: bool = False,
   parent_id: str = "",
    folder_id: str = "",
) -> Session:
    now = time.time()
    session = Session(
        id=str(uuid.uuid4()),
        title=title or "New chat",
        created_at=now,
        updated_at=now,
        model=model or "",
        hidden=bool(hidden),
       parent_id=str(parent_id or "").strip(),
        folder_id=str(folder_id or "").strip(),
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
    archived: bool | None = None,
    folder_id: str | None = None,
    messages: list[dict[str, Any]] | None = None,
) -> Session | None:
    # Keep read-modify-write together; parallel lanes can update one session.
    with _lock:
        session = get_session(session_id)
        if session is None:
            return None
        if title is not None:
            session.title = title.strip() or session.title
        if model is not None:
            session.model = model
        if pinned is not None:
            session.pinned = pinned
        if archived is not None:
            session.archived = archived
        if folder_id is not None:
            session.folder_id = str(folder_id or "").strip()
        if messages is not None:
            session.messages = messages
        session.updated_at = time.time()
        save_session(session)
        return session


def ensure_message_id(msg: dict[str, Any]) -> dict[str, Any]:
    if not msg.get("id"):
        msg = dict(msg)
        msg["id"] = str(uuid.uuid4())
    return msg


def append_messages(session_id: str, *msgs: dict[str, Any]) -> Session | None:
    # Read-modify-write must be one critical section or concurrent task lanes
    # can overwrite each other's messages with stale session snapshots.
    with _lock:
        session = get_session(session_id)
        if session is None:
            return None
        session.messages.extend(ensure_message_id(dict(m)) for m in msgs)
        # Auto-title from first user message
        if session.title in ("New chat", "新对话", "") and msgs:
            first = next((m for m in msgs if m.get("role") == "user"), None)
            if first and isinstance(first.get("content"), str):
                text = first["content"].strip().replace("\n", " ")
                session.title = (text[:48] + "…") if len(text) > 48 else text or session.title
        _refresh_memory(session)
        session.updated_at = time.time()
        save_session(session)
        return session

def _refresh_memory(session: Session) -> None:
    """Keep a compact deterministic memory for cross-session retrieval."""
    import re
    users = [str(m.get("content") or "").strip() for m in session.messages if m.get("role") == "user"]
    assistants = [str(m.get("content") or "").strip() for m in session.messages if m.get("role") == "assistant"]
    if users:
        session.summary = (users[0] + ("；" + assistants[-1][:500] if assistants else ""))[:900]
    text = "\n".join(users[-3:] + assistants[-2:])
    candidates = re.findall(r"[\u4e00-\u9fff]{2,8}|[A-Za-z][A-Za-z0-9_-]{2,24}", text)
    stop = {"请问", "可以", "一下", "进行", "这个", "我们", "需要", "如果", "是否", "with", "from", "that", "this"}
    session.tags = list(dict.fromkeys(x for x in candidates if x.lower() not in stop))[:16]
    session.facts = [x[:240] for x in assistants[-2:] if x][:4]
    session.todos = [line.strip("- *")[:180] for line in text.splitlines() if any(k in line for k in ("待办", "后续", "TODO", "下一步"))][:6]

def folder_context(session_id: str, query: str = "", *, limit: int = 4, max_chars: int = 6000) -> dict[str, Any]:
    current = get_session(session_id)
    if current is None or not current.folder_id:
        return {"ok": True, "folder_id": getattr(current, "folder_id", ""), "items": [], "context": ""}
    terms = set(str(query or "").lower().split())
    results = []
    for item in list_sessions():
        if item.get("id") == session_id or item.get("folder_id") != current.folder_id:
            continue
        hay = " ".join([str(item.get("title") or ""), str(item.get("summary") or ""), " ".join(item.get("tags") or [])]).lower()
        score = sum(1 for term in terms if term and term in hay)
        if terms and score == 0:
            continue
        results.append((score, item))
    results.sort(key=lambda pair: (pair[0], pair[1].get("updated_at", 0)), reverse=True)
    chosen = [x[1] for x in results[:max(1, min(limit, 8))]]
    blocks = []
    for item in chosen:
        title = str(item.get("title") or "未命名")
        block = "- " + title + ": " + str(item.get("summary") or "（暂无摘要）")
        if item.get("facts"):
            block += "；事实：" + " | ".join(item["facts"][:2])
        blocks.append(block)
    return {"ok": True, "folder_id": current.folder_id, "items": chosen, "context": "\n".join(blocks)[:max_chars]}


def backup_session(session_id: str) -> dict[str, Any]:
    """Copy session JSON into ~/.agent-cli/backups/sessions/ and return metadata."""
    from .home import ensure_home

    session = get_session(session_id)
    if session is None:
        raise FileNotFoundError(f"session not found: {session_id}")
    home = ensure_home()
    dest_dir = Path(home["backups"]) / "sessions"
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    safe_title = "".join(c if (c.isalnum() or c in "-_") else "_" for c in (session.title or "session"))[:40]
    dest = dest_dir / f"{stamp}_{safe_title or 'session'}_{session.id[:8]}.json"
    payload = {
        "backed_up_at": time.time(),
        "backed_up_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "session": session.to_dict(),
    }
    with _lock:
        dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "path": str(dest), "session_id": session.id, "title": session.title}
