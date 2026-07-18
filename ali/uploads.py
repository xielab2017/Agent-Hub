"""File / folder uploads into session workspace or ALI uploads dir."""

from __future__ import annotations

import re
import time
import uuid
from pathlib import Path
from typing import Any

from .config import STATE_DIR, ensure_state_dirs
from .settings import load_campus_config

UPLOADS_DIR = STATE_DIR / "uploads"
_SAFE = re.compile(r"[^\w.\u4e00-\u9fff\-_/]+", re.UNICODE)


def uploads_root(session_id: str = "") -> Path:
    ensure_state_dirs()
    base = UPLOADS_DIR
    if session_id:
        safe = "".join(c for c in session_id if c.isalnum() or c in "-_")
        base = base / safe
    base.mkdir(parents=True, exist_ok=True)
    return base


def _safe_rel(rel: str) -> str:
    rel = (rel or "").replace("\\", "/").lstrip("/")
    parts = []
    for p in rel.split("/"):
        if not p or p in (".", ".."):
            continue
        parts.append(_SAFE.sub("_", p)[:120] or "file")
    return "/".join(parts) if parts else f"file-{uuid.uuid4().hex[:8]}"


def save_bytes(
    data: bytes,
    *,
    filename: str,
    session_id: str = "",
    relative_path: str = "",
    into_workspace: bool = False,
) -> dict[str, Any]:
    if into_workspace:
        cfg = load_campus_config()
        ws = (cfg.get("workspace") or "").strip()
        root = Path(ws).expanduser() if ws else uploads_root(session_id)
        root.mkdir(parents=True, exist_ok=True)
    else:
        root = uploads_root(session_id)

    rel = _safe_rel(relative_path or filename or f"upload-{int(time.time())}")
    dest = (root / rel).resolve()
    if not str(dest).startswith(str(root.resolve())):
        raise ValueError("invalid path")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return {
        "ok": True,
        "path": str(dest),
        "relative": rel,
        "size": len(data),
        "root": str(root),
    }


def list_uploads(session_id: str = "") -> dict[str, Any]:
    root = uploads_root(session_id)
    files = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            try:
                files.append(
                    {
                        "relative": str(p.relative_to(root)).replace("\\", "/"),
                        "path": str(p),
                        "size": p.stat().st_size,
                        "mtime": p.stat().st_mtime,
                    }
                )
            except ValueError:
                continue
    return {"ok": True, "root": str(root), "files": files[:200], "count": len(files)}
