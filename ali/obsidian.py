"""Obsidian vault helpers — read status, list allowed notes, write to AI inbox."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from .settings import load_campus_config

_UNSAFE = re.compile(r"[^\w\u4e00-\u9fff\-_. ]+", re.UNICODE)


def vault_root(cfg: dict[str, Any] | None = None) -> Path | None:
    cfg = cfg or load_campus_config()
    path = ((cfg.get("obsidian") or {}).get("vault_path") or "").strip()
    if not path:
        return None
    return Path(path).expanduser()


def vault_status() -> dict[str, Any]:
    cfg = load_campus_config()
    obs = cfg.get("obsidian") or {}
    root = vault_root(cfg)
    exists = bool(root and root.is_dir())
    inbox_rel = (obs.get("ai_inbox") or "00_Inbox/AI_Candidates").replace("\\", "/")
    inbox = (root / inbox_rel) if root else None
    return {
        "configured": bool(obs.get("vault_path")),
        "vault_path": obs.get("vault_path") or "",
        "exists": exists,
        "ai_inbox": inbox_rel,
        "inbox_exists": bool(inbox and inbox.is_dir()),
        "allowed_roots": obs.get("allowed_roots") or [],
        "write_requires_approval": bool(obs.get("write_requires_approval", True)),
        "excluded_globs": obs.get("excluded_globs") or [],
    }


def _is_excluded(rel: str, excluded: list[str]) -> bool:
    rel_n = rel.replace("\\", "/")
    for g in excluded:
        g = g.replace("\\", "/")
        if g.endswith("/**"):
            prefix = g[:-3]
            if rel_n == prefix or rel_n.startswith(prefix + "/"):
                return True
        if "*" in g:
            core = g.strip("*").strip("/")
            if core and core.lower() in rel_n.lower():
                return True
        elif rel_n == g or rel_n.startswith(g + "/"):
            return True
    return False


def list_notes(limit: int = 50, root_filter: str = "") -> dict[str, Any]:
    cfg = load_campus_config()
    obs = cfg.get("obsidian") or {}
    root = vault_root(cfg)
    if not root or not root.is_dir():
        return {"ok": False, "error": "vault not found", "notes": []}

    allowed = [a.replace("\\", "/") for a in (obs.get("allowed_roots") or [])]
    excluded = obs.get("excluded_globs") or []
    notes: list[dict[str, Any]] = []

    if root_filter:
        search_roots = [root / root_filter]
    elif allowed:
        search_roots = [root / a for a in allowed]
    else:
        search_roots = [root]

    for base in search_roots:
        if not base.exists():
            continue
        for path in base.rglob("*.md"):
            try:
                rel = str(path.relative_to(root)).replace("\\", "/")
            except ValueError:
                continue
            if _is_excluded(rel, excluded):
                continue
            notes.append(
                {
                    "path": rel,
                    "name": path.name,
                    "size": path.stat().st_size,
                    "mtime": path.stat().st_mtime,
                }
            )
            if len(notes) >= limit:
                break
        if len(notes) >= limit:
            break

    notes.sort(key=lambda n: -n["mtime"])
    return {"ok": True, "notes": notes, "count": len(notes)}


def read_note(rel_path: str) -> dict[str, Any]:
    cfg = load_campus_config()
    obs = cfg.get("obsidian") or {}
    root = vault_root(cfg)
    if not root or not root.is_dir():
        return {"ok": False, "error": "vault not found"}
    rel = rel_path.replace("\\", "/").lstrip("/")
    if ".." in rel.split("/"):
        return {"ok": False, "error": "invalid path"}
    if _is_excluded(rel, obs.get("excluded_globs") or []):
        return {"ok": False, "error": "path excluded by policy"}
    path = (root / rel).resolve()
    if not str(path).startswith(str(root.resolve())):
        return {"ok": False, "error": "path outside vault"}
    if not path.is_file():
        return {"ok": False, "error": "not found"}
    return {
        "ok": True,
        "path": rel,
        "content": path.read_text(encoding="utf-8", errors="replace"),
    }


def write_candidate(
    title: str,
    content: str,
    *,
    approved: bool = False,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Write ONLY into AI_Candidates inbox."""
    cfg = load_campus_config()
    obs = cfg.get("obsidian") or {}
    root = vault_root(cfg)
    if not root:
        return {"ok": False, "error": "vault_path not configured"}

    if obs.get("write_requires_approval", True) and not approved:
        return {
            "ok": False,
            "needs_approval": True,
            "error": "write_requires_approval — set approved=true after user confirms",
            "preview_title": title,
        }

    inbox_rel = (obs.get("ai_inbox") or "00_Inbox/AI_Candidates").replace("\\", "/")
    inbox = root / inbox_rel
    inbox.mkdir(parents=True, exist_ok=True)

    safe_title = _UNSAFE.sub("", (title or "AI_Note").strip())[:80] or "AI_Note"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    filename = f"{stamp}_{safe_title}.md"
    path = inbox / filename

    tag_line = " ".join(f"#{t}" for t in (tags or ["ai-candidate"]))
    body = (
        f"---\n"
        f"title: {safe_title}\n"
        f"created: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"source: hermes-ali\n"
        f"status: candidate\n"
        f"---\n\n"
        f"# {safe_title}\n\n"
        f"{content.strip()}\n\n"
        f"{tag_line}\n"
    )
    path.write_text(body, encoding="utf-8")
    rel = str(path.relative_to(root)).replace("\\", "/")
    return {"ok": True, "path": rel, "abs_path": str(path)}
