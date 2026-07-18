"""Append-only audit log for routes, tools, approvals (no secrets)."""

from __future__ import annotations

import json
import time
from typing import Any

from .config import STATE_DIR, ensure_state_dirs

AUDIT_FILE = STATE_DIR / "audit.jsonl"


def log_event(kind: str, payload: dict[str, Any]) -> None:
    ensure_state_dirs()
    safe = dict(payload or {})
    for k in list(safe.keys()):
        lk = k.lower()
        if any(s in lk for s in ("key", "secret", "password", "token", "authorization")):
            safe[k] = "***"
    line = json.dumps(
        {"ts": time.time(), "kind": kind, **safe},
        ensure_ascii=False,
    )
    with AUDIT_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def recent(limit: int = 50) -> list[dict[str, Any]]:
    if not AUDIT_FILE.is_file():
        return []
    lines = AUDIT_FILE.read_text(encoding="utf-8").splitlines()
    out: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    out.reverse()
    return out
