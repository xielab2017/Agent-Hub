"""Persistent session folders for the Hub sidebar."""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .home import ensure_home

_lock = threading.RLock()

def _path() -> Path:
    return ensure_home()["state"] / "session_folders.json"

def _load() -> list[dict[str, Any]]:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        return list(data) if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []

def _save(items: list[dict[str, Any]]) -> None:
    p = _path(); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def list_folders() -> list[dict[str, Any]]:
    with _lock:
        return sorted(_load(), key=lambda x: (int(x.get("sort_order") or 0), float(x.get("updated_at") or 0)))

def create_folder(name: str) -> dict[str, Any]:
    label = (name or "新文件夹").strip() or "新文件夹"
    now = time.time()
    item = {"id": str(uuid.uuid4()), "name": label[:80], "created_at": now, "updated_at": now, "sort_order": len(_load()), "archived": False}
    with _lock:
        items = _load(); items.append(item); _save(items)
    return item

def update_folder(folder_id: str, name: str | None = None, sort_order: int | None = None, archived: bool | None = None) -> dict[str, Any] | None:
    with _lock:
        items = _load()
        found = next((x for x in items if x.get("id") == folder_id), None)
        if found is None: return None
        if name is not None: found["name"] = (name.strip() or found.get("name") or "未命名")[:80]
        if sort_order is not None: found["sort_order"] = int(sort_order)
        if archived is not None: found["archived"] = bool(archived)
        found["updated_at"] = time.time(); _save(items); return found

def delete_folder(folder_id: str) -> bool:
    with _lock:
        items = _load(); kept = [x for x in items if x.get("id") != folder_id]
        if len(kept) == len(items): return False
        _save(kept); return True
