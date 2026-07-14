"""User-defined scheduled tasks (review / evolve / custom) for Agent-CLI."""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .home import ensure_home
from . import digest

_lock = threading.RLock()
_started = False


def _tasks_file() -> Path:
    return ensure_home()["state"] / "scheduled_tasks.json"


def _notif_file() -> Path:
    return ensure_home()["state"] / "schedule_notifications.json"


def _load() -> dict[str, Any]:
    path = _tasks_file()
    if not path.is_file():
        return {"tasks": [], "defaults": {"nightly_hour": 0, "morning_hour": 7}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("tasks", [])
            data.setdefault("defaults", {"nightly_hour": 0, "morning_hour": 7})
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"tasks": [], "defaults": {"nightly_hour": 0, "morning_hour": 7}}


def _save(data: dict[str, Any]) -> None:
    path = _tasks_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_notifs() -> dict[str, Any]:
    path = _notif_file()
    if not path.is_file():
        return {"items": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("items", [])
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"items": []}


def _save_notifs(data: dict[str, Any]) -> None:
    path = _notif_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    items = list(data.get("items") or [])
    # Cap history so UI/disk stay light
    if len(items) > 80:
        items = items[-80:]
        data["items"] = items
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def push_notification(
    *,
    title: str,
    title_en: str = "",
    kind: str = "custom",
    status: str = "ok",
    summary: str = "",
    summary_en: str = "",
    task_id: str = "",
) -> dict[str, Any]:
    """Persist a schedule-run tip so Hub UI can show it after the browser was closed overnight."""
    with _lock:
        data = _load_notifs()
        item = {
            "id": str(uuid.uuid4()),
            "ts": time.time(),
            "time": datetime.now().isoformat(timespec="seconds"),
            "title": (title or "定时任务").strip(),
            "title_en": (title_en or title or "Scheduled task").strip(),
            "kind": (kind or "custom").strip(),
            "status": (status or "ok").strip(),
            "summary": (summary or "").strip()[:400],
            "summary_en": (summary_en or summary or "").strip()[:400],
            "task_id": (task_id or "").strip(),
            "read": False,
        }
        items = list(data.get("items") or [])
        items.append(item)
        data["items"] = items
        _save_notifs(data)
        return item


def list_notifications(*, unread_only: bool = False, limit: int = 30) -> dict[str, Any]:
    data = _load_notifs()
    items = list(data.get("items") or [])
    items.sort(key=lambda x: float(x.get("ts") or 0), reverse=True)
    if unread_only:
        items = [x for x in items if not x.get("read")]
    lim = max(1, min(100, int(limit or 30)))
    items = items[:lim]
    unread = sum(1 for x in (data.get("items") or []) if not x.get("read"))
    return {"ok": True, "items": items, "unread": unread}


def mark_notifications_read(ids: list[str] | None = None, *, all_read: bool = False) -> dict[str, Any]:
    with _lock:
        data = _load_notifs()
        want = {str(x) for x in (ids or []) if str(x).strip()} if not all_read else None
        changed = 0
        for item in data.get("items") or []:
            if item.get("read"):
                continue
            if want is None or str(item.get("id")) in want:
                item["read"] = True
                changed += 1
        _save_notifs(data)
        return {"ok": True, "marked": changed, **list_notifications(unread_only=False, limit=20)}


def list_tasks() -> dict[str, Any]:
    data = _load()
    return {
        "ok": True,
        "tasks": data.get("tasks") or [],
        "defaults": data.get("defaults") or {},
        "builtins": [
            {
                "id": "builtin-nightly",
                "kind": "review",
                "label": "夜间复盘",
                "label_en": "Nightly review",
                "hour": int((data.get("defaults") or {}).get("nightly_hour", 0)),
                "minute": 0,
                "enabled": True,
                "builtin": True,
            },
            {
                "id": "builtin-morning",
                "kind": "evolve",
                "label": "早间进化简报",
                "label_en": "Morning evolve brief",
                "hour": int((data.get("defaults") or {}).get("morning_hour", 7)),
                "minute": 0,
                "enabled": True,
                "builtin": True,
            },
        ],
    }


def save_defaults(nightly_hour: int | None = None, morning_hour: int | None = None) -> dict[str, Any]:
    data = _load()
    defaults = dict(data.get("defaults") or {})
    if nightly_hour is not None:
        defaults["nightly_hour"] = max(0, min(23, int(nightly_hour)))
    if morning_hour is not None:
        defaults["morning_hour"] = max(0, min(23, int(morning_hour)))
    data["defaults"] = defaults
    _save(data)
    return list_tasks()


def upsert_task(body: dict[str, Any]) -> dict[str, Any]:
    data = _load()
    tasks = list(data.get("tasks") or [])
    tid = str(body.get("id") or "").strip() or str(uuid.uuid4())
    task = {
        "id": tid,
        "kind": str(body.get("kind") or "custom").strip() or "custom",
        "label": str(body.get("label") or "自定义任务").strip(),
        "hour": max(0, min(23, int(body.get("hour") if body.get("hour") is not None else 9))),
        "minute": max(0, min(59, int(body.get("minute") if body.get("minute") is not None else 0))),
        "enabled": bool(body.get("enabled", True)),
        "prompt": str(body.get("prompt") or "").strip(),
        "last_run": None,
        "builtin": False,
    }
    found = False
    for i, t in enumerate(tasks):
        if t.get("id") == tid:
            task["last_run"] = t.get("last_run")
            tasks[i] = task
            found = True
            break
    if not found:
        tasks.append(task)
    data["tasks"] = tasks
    _save(data)
    return {"ok": True, "task": task, **list_tasks()}


def delete_task(task_id: str) -> dict[str, Any]:
    data = _load()
    before = len(data.get("tasks") or [])
    data["tasks"] = [t for t in (data.get("tasks") or []) if t.get("id") != task_id]
    _save(data)
    return {"ok": True, "deleted": before != len(data["tasks"]), **list_tasks()}


def _run_custom(task: dict[str, Any]) -> None:
    """Append a note under digests for custom scheduled prompts."""
    ensure_home()
    dig = ensure_home()["digests"]
    today = datetime.now().strftime("%Y-%m-%d")
    safe = "".join(c for c in str(task.get("id")) if c.isalnum() or c in "-_")[:24]
    path = dig / f"{today}-custom-{safe}.md"
    label = str(task.get("label") or "自定义任务")
    path.write_text(
        f"# Scheduled task · {label}\n\n"
        f"- time: {datetime.now().isoformat(timespec='seconds')}\n"
        f"- kind: `{task.get('kind')}`\n\n"
        f"## Prompt\n\n{task.get('prompt') or '(empty)'}\n",
        encoding="utf-8",
    )
    prompt = str(task.get("prompt") or "").strip()
    snippet = (prompt[:120] + "…") if len(prompt) > 120 else prompt
    push_notification(
        title=f"定时任务完成 · {label}",
        title_en=f"Scheduled task done · {label}",
        kind=str(task.get("kind") or "custom"),
        status="ok",
        summary=snippet or f"已写入 {path.name}",
        summary_en=snippet or f"Wrote {path.name}",
        task_id=str(task.get("id") or ""),
    )


def start_custom_scheduler() -> None:
    """Run user-defined custom tasks only (builtins handled by digest.start_scheduler)."""
    global _started
    with _lock:
        if _started:
            return
        _started = True

    state_file = ensure_home()["state"] / "scheduler_custom.json"

    def _load_st() -> dict[str, str]:
        if state_file.is_file():
            try:
                return json.loads(state_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return {}
        return {}

    def _save_st(st: dict[str, str]) -> None:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(st, indent=2), encoding="utf-8")

    def _loop() -> None:
        while True:
            try:
                now = datetime.now()
                data = _load()
                st = _load_st()
                day = now.date().isoformat()
                for task in data.get("tasks") or []:
                    if not task.get("enabled"):
                        continue
                    minute = int(task.get("minute", 0))
                    key = f"{task.get('id')}:{day}"
                    if int(task.get("hour", -1)) != now.hour:
                        continue
                    if not (minute <= now.minute < minute + 5):
                        continue
                    if st.get(key) == "1":
                        continue
                    kind = task.get("kind")
                    if kind == "review":
                        # digest.run_nightly pushes its own notification
                        digest.run_nightly()
                    elif kind == "evolve":
                        digest.run_morning()
                    else:
                        _run_custom(task)
                    st[key] = "1"
                    with _lock:
                        d2 = _load()
                        for t in d2.get("tasks") or []:
                            if t.get("id") == task.get("id"):
                                t["last_run"] = time.time()
                        _save(d2)
                    _save_st(st)
            except Exception:  # noqa: BLE001
                pass
            time.sleep(60)

    threading.Thread(target=_loop, daemon=True, name="agent-cli-custom-sched").start()
