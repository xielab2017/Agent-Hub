"""Filesystem helpers for workspace browsing (read-only listing)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _safe_path(raw: str) -> Path:
    p = Path(raw or "").expanduser()
    if not str(raw).strip():
        p = Path.home()
    try:
        return p.resolve()
    except OSError:
        return Path.home()


def list_dir(path: str = "", *, show_hidden: bool = False) -> dict[str, Any]:
    root = _safe_path(path)
    if not root.exists():
        return {"ok": False, "error": f"path not found: {root}", "path": str(root), "entries": []}
    if not root.is_dir():
        return {"ok": False, "error": "not a directory", "path": str(root), "entries": []}

    entries: list[dict[str, Any]] = []
    try:
        for child in root.iterdir():
            name = child.name
            if not show_hidden and name.startswith("."):
                continue
            try:
                is_dir = child.is_dir()
            except OSError:
                continue
            if not is_dir:
                continue  # folders only for workspace picker
            entries.append(
                {
                    "name": name,
                    "path": str(child.resolve()),
                    "is_dir": True,
                }
            )
    except PermissionError:
        return {"ok": False, "error": "permission denied", "path": str(root), "entries": []}

    entries.sort(key=lambda e: e["name"].lower())
    parent = str(root.parent.resolve()) if root != root.parent else None
    homes = []
    home = str(Path.home())
    homes.append({"label": "~", "path": home})
    if os.name == "posix":
        for label, p in (("Documents", Path.home() / "Documents"), ("Desktop", Path.home() / "Desktop")):
            if p.is_dir():
                homes.append({"label": label, "path": str(p)})
    return {
        "ok": True,
        "path": str(root),
        "parent": parent,
        "entries": entries,
        "shortcuts": homes,
    }
