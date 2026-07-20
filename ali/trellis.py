"""Controlled Trellis task integration for Agent Hub."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from . import sessions
from .settings import load_campus_config

ARTIFACT_NAMES = ("prd.md", "design.md", "implement.md")
TASK_STATUSES = {
    "planning",
    "pending_approval",
    "in_progress",
    "quality_check",
    "blocked",
    "completed",
}
TRANSITIONS = {
    "planning": {"pending_approval", "blocked"},
    "pending_approval": {"planning", "in_progress", "blocked"},
    "in_progress": {"quality_check", "blocked"},
    "quality_check": {"in_progress", "blocked", "completed"},
    "blocked": {"planning", "in_progress", "quality_check"},
    "completed": set(),
}
_TASK_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
_SECRET_PATTERNS = (
    re.compile(r"(?im)^\s*([A-Z][A-Z0-9_]*(?:TOKEN|KEY|SECRET|PASSWORD)[A-Z0-9_]*)\s*[=:]\s*\S+"),
    re.compile(r"(?i)\b(?:sk|nvapi|ghp|github_pat|xox[baprs])-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"(?is)-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----"),
)


class TrellisError(ValueError):
    """Safe user-facing Trellis integration error."""


def _config() -> dict[str, Any]:
    cfg = load_campus_config().get("trellis") or {}
    return cfg if isinstance(cfg, dict) else {}


def enabled() -> bool:
    return bool(_config().get("enabled", True))


def _workspace(value: str) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raw = str(load_campus_config().get("workspace") or "").strip()
    if not raw:
        raise TrellisError("workspace is required")
    path = Path(raw).expanduser().resolve(strict=True)
    if not path.is_dir():
        raise TrellisError("workspace must be a directory")
    return path


def _trellis_root(workspace: str) -> tuple[Path, Path]:
    root = _workspace(workspace)
    trellis_root = (root / ".trellis").resolve()
    if not trellis_root.is_dir() or trellis_root.parent != root:
        raise TrellisError("Trellis is not initialized in this workspace")
    return root, trellis_root


def _tasks_root(workspace: str) -> tuple[Path, Path]:
    root, trellis_root = _trellis_root(workspace)
    tasks_root = trellis_root / "tasks"
    tasks_root.mkdir(parents=True, exist_ok=True)
    resolved = tasks_root.resolve()
    if resolved.parent != trellis_root or tasks_root.is_symlink():
        raise TrellisError(".trellis/tasks must not be a symlink")
    return root, resolved


def _task_dir(workspace: str, task_id: str, *, must_exist: bool = True) -> tuple[Path, Path]:
    if not _TASK_RE.fullmatch(str(task_id or "")):
        raise TrellisError("invalid task id")
    root, tasks_root = _tasks_root(workspace)
    candidate = (tasks_root / task_id).resolve(strict=must_exist)
    if candidate.parent != tasks_root:
        raise TrellisError("task path escapes .trellis/tasks")
    if must_exist and not candidate.is_dir():
        raise TrellisError("task not found")
    return root, candidate


def _read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise TrellisError("Trellis task metadata must not be a symlink")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TrellisError(f"invalid Trellis task metadata: {path.name}") from exc
    if not isinstance(data, dict):
        raise TrellisError("invalid Trellis task metadata")
    return data


def _atomic_json(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _agent_meta(task: dict[str, Any]) -> dict[str, Any]:
    meta = task.setdefault("meta", {})
    if not isinstance(meta, dict):
        meta = {}
        task["meta"] = meta
    hub = meta.setdefault("agent_hub", {})
    if not isinstance(hub, dict):
        hub = {}
        meta["agent_hub"] = hub
    return hub


def _public_task(task_dir: Path, task: dict[str, Any]) -> dict[str, Any]:
    hub = _agent_meta(task)
    checks = list(hub.get("validations") or [])
    return {
        "id": task_dir.name,
        "title": str(task.get("title") or task.get("name") or task_dir.name),
        "description": str(task.get("description") or ""),
        "status": str(task.get("status") or "planning"),
        "priority": str(task.get("priority") or ""),
        "created_at": task.get("createdAt"),
        "updated_at": hub.get("updated_at") or task.get("createdAt"),
        "approved": bool(hub.get("approval")),
        "approval": dict(hub.get("approval") or {}),
        "validations": checks[-20:],
        "artifacts": [name for name in ARTIFACT_NAMES if (task_dir / name).is_file()],
    }


def list_tasks(workspace: str) -> list[dict[str, Any]]:
    _root, tasks_root = _tasks_root(workspace)
    result: list[dict[str, Any]] = []
    for child in tasks_root.iterdir():
        if not child.is_dir() or child.is_symlink() or not _TASK_RE.fullmatch(child.name):
            continue
        metadata = child / "task.json"
        if not metadata.is_file():
            continue
        try:
            result.append(_public_task(child, _read_json(metadata)))
        except TrellisError:
            continue
    result.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return result


def _binding(session_id: str) -> dict[str, Any]:
    session = sessions.get_session(session_id)
    if session is None:
        raise TrellisError("session not found")
    return dict(session.trellis or {})


def _save_binding(session_id: str, binding: dict[str, Any]) -> None:
    if sessions.update_session(session_id, trellis=binding) is None:
        raise TrellisError("session not found")


def bind_task(session_id: str, workspace: str, task_id: str) -> dict[str, Any]:
    root, task_dir = _task_dir(workspace, task_id)
    task = _read_json(task_dir / "task.json")
    binding = {
        "workspace": str(root),
        "task_id": task_id,
        "bound_at": time.time(),
        "status": str(task.get("status") or "planning"),
    }
    _save_binding(session_id, binding)
    return {"binding": binding, "task": _public_task(task_dir, task)}


def unbind_task(session_id: str) -> dict[str, Any]:
    previous = _binding(session_id)
    _save_binding(session_id, {})
    return {"ok": True, "previous": previous}


def status(session_id: str = "", workspace: str = "") -> dict[str, Any]:
    cfg = _config()
    result: dict[str, Any] = {"enabled": bool(cfg.get("enabled", True)), "initialized": False, "tasks": []}
    binding = _binding(session_id) if session_id else {}
    target = str(binding.get("workspace") or workspace or load_campus_config().get("workspace") or "")
    if not result["enabled"]:
        result["binding"] = binding
        return result
    try:
        root, _trellis = _trellis_root(target)
        result["initialized"] = True
        result["workspace"] = str(root)
        result["tasks"] = list_tasks(str(root))
    except (OSError, TrellisError) as exc:
        result["workspace"] = target
        result["message"] = str(exc)
    if binding:
        result["binding"] = binding
        task = next((item for item in result["tasks"] if item["id"] == binding.get("task_id")), None)
        if task:
            result["task"] = task
    return result


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", str(value or "").strip()).strip("-").lower()
    if not slug:
        slug = "agent-hub-task"
    return slug[:72]


def create_task(session_id: str, workspace: str, title: str, description: str = "") -> dict[str, Any]:
    root, tasks_root = _tasks_root(workspace)
    clean_title = " ".join(str(title or "").split())[:160]
    if not clean_title:
        raise TrellisError("task title is required")
    base = f"{datetime.now().strftime('%m-%d')}-{_slug(clean_title)}"
    task_id = base
    suffix = 2
    while (tasks_root / task_id).exists():
        task_id = f"{base}-{suffix}"
        suffix += 1
    task_dir = tasks_root / task_id
    task_dir.mkdir()
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    task = {
        "id": task_id,
        "name": _slug(clean_title),
        "title": clean_title,
        "description": str(description or "").strip()[:2000],
        "status": "planning",
        "priority": "P2",
        "creator": "agent-hub",
        "assignee": "",
        "createdAt": now,
        "completedAt": None,
        "branch": None,
        "base_branch": None,
        "subtasks": [],
        "children": [],
        "parent": None,
        "meta": {"agent_hub": {"created_by": "agent-hub", "updated_at": now}},
    }
    _atomic_json(task_dir / "task.json", task)
    prd = (
        f"# {clean_title}\n\n## Goal\n\n{str(description or clean_title).strip()}\n\n"
        "## Requirements\n\n- [ ] Define the required behavior.\n\n"
        "## Acceptance Criteria\n\n- [ ] The implementation is verified against this task.\n"
    )
    (task_dir / "prd.md").write_text(prd, encoding="utf-8")
    return bind_task(session_id, str(root), task_id)


def read_artifact(session_id: str, name: str) -> dict[str, Any]:
    if name not in ARTIFACT_NAMES:
        raise TrellisError("artifact is not allowed")
    binding = _binding(session_id)
    _root, task_dir = _task_dir(str(binding.get("workspace") or ""), str(binding.get("task_id") or ""))
    path = (task_dir / name).resolve(strict=True)
    if path.parent != task_dir or not path.is_file():
        raise TrellisError("artifact not found")
    limit = max(1000, min(int(_config().get("artifact_budget_chars") or 7000), 40000))
    content = path.read_text(encoding="utf-8", errors="replace")
    return {"name": name, "content": redact(content[:limit]), "truncated": len(content) > limit}


def _write_task(task_dir: Path, task: dict[str, Any], status_value: str) -> dict[str, Any]:
    task["status"] = status_value
    hub = _agent_meta(task)
    hub["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    if status_value == "completed":
        task["completedAt"] = hub["updated_at"]
    _atomic_json(task_dir / "task.json", task)
    return _public_task(task_dir, task)


def approve(session_id: str, identity: str = "local-user", summary: str = "") -> dict[str, Any]:
    binding = _binding(session_id)
    _root, task_dir = _task_dir(str(binding.get("workspace") or ""), str(binding.get("task_id") or ""))
    task = _read_json(task_dir / "task.json")
    current = str(task.get("status") or "planning")
    if current not in {"planning", "pending_approval"}:
        raise TrellisError("task is not waiting for planning approval")
    prd_path = task_dir / "prd.md"
    if not prd_path.is_file() or prd_path.is_symlink():
        raise TrellisError("prd.md is required before approval")
    digest = hashlib.sha256()
    for name in ARTIFACT_NAMES:
        path = task_dir / name
        if path.is_file() and not path.is_symlink():
            digest.update(path.read_bytes())
    _agent_meta(task)["approval"] = {
        "approved_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "approved_by": str(identity or "local-user")[:80],
        "artifact_sha256": digest.hexdigest(),
        "summary": redact(str(summary or ""))[:500],
    }
    public = _write_task(task_dir, task, "in_progress")
    binding["status"] = "in_progress"
    _save_binding(session_id, binding)
    return {"task": public, "binding": binding}


def transition(session_id: str, target: str, reason: str = "") -> dict[str, Any]:
    if target not in TASK_STATUSES:
        raise TrellisError("invalid target status")
    binding = _binding(session_id)
    _root, task_dir = _task_dir(str(binding.get("workspace") or ""), str(binding.get("task_id") or ""))
    task = _read_json(task_dir / "task.json")
    current = str(task.get("status") or "planning")
    if target not in TRANSITIONS.get(current, set()):
        raise TrellisError(f"invalid task transition: {current} -> {target}")
    if target == "in_progress" and not _agent_meta(task).get("approval"):
        raise TrellisError("planning approval is required")
    if target == "completed":
        validations = list(_agent_meta(task).get("validations") or [])
        if not validations or not bool(validations[-1].get("ok")):
            raise TrellisError("a successful validation is required before completion")
    if reason:
        _agent_meta(task).setdefault("transitions", []).append({
            "from": current,
            "to": target,
            "reason": redact(str(reason))[:500],
            "at": datetime.now().astimezone().isoformat(timespec="seconds"),
        })
    public = _write_task(task_dir, task, target)
    binding["status"] = target
    _save_binding(session_id, binding)
    return {"task": public, "binding": binding}


def record_validation(session_id: str, command: str, ok: bool, summary: str = "") -> dict[str, Any]:
    binding = _binding(session_id)
    _root, task_dir = _task_dir(str(binding.get("workspace") or ""), str(binding.get("task_id") or ""))
    task = _read_json(task_dir / "task.json")
    current = str(task.get("status") or "planning")
    if current not in {"in_progress", "quality_check"}:
        raise TrellisError("validation can only be recorded during execution or quality check")
    record = {
        "command": redact(str(command or ""))[:300],
        "ok": bool(ok),
        "summary": redact(str(summary or ""))[:1000],
        "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    _agent_meta(task).setdefault("validations", []).append(record)
    target = "quality_check" if ok else "in_progress"
    public = _write_task(task_dir, task, target)
    binding["status"] = target
    _save_binding(session_id, binding)
    return {"task": public, "validation": record, "binding": binding}


def redact(text: str) -> str:
    value = str(text or "")
    for pattern in _SECRET_PATTERNS:
        value = pattern.sub(lambda match: f"{match.group(1)}=[REDACTED]" if match.lastindex else "[REDACTED]", value)
    return value


def context_block(session_id: str) -> tuple[str, dict[str, Any]]:
    if not enabled():
        return "", {"enabled": False}
    binding = _binding(session_id)
    if not binding:
        return "", {"enabled": True, "bound": False}
    _root, task_dir = _task_dir(str(binding.get("workspace") or ""), str(binding.get("task_id") or ""))
    task = _read_json(task_dir / "task.json")
    status_value = str(task.get("status") or "planning")
    if status_value in {"planning", "pending_approval"}:
        return "", {"enabled": True, "bound": True, "task_id": task_dir.name, "status": status_value, "approved": False}
    total_limit = max(2000, min(int(_config().get("context_budget_chars") or 18000), 50000))
    parts = [
        "## Trellis controlled task context",
        f"Source task: .trellis/tasks/{task_dir.name}",
        f"Phase: {status_value}",
        "Follow approved artifacts. Do not mark the task complete without a recorded successful validation.",
    ]
    sources: list[str] = []
    remaining = total_limit - sum(len(item) for item in parts)
    for name in ARTIFACT_NAMES:
        path = task_dir / name
        if not path.is_file() or path.is_symlink() or remaining <= 200:
            continue
        raw = redact(path.read_text(encoding="utf-8", errors="replace"))
        chunk = raw[:remaining]
        parts.append(f"\n### {name}\n{chunk}")
        sources.append(name)
        remaining -= len(chunk) + len(name) + 8
    block = "\n".join(parts)[:total_limit]
    return block, {
        "enabled": True,
        "bound": True,
        "task_id": task_dir.name,
        "status": status_value,
        "sources": sources,
        "chars": len(block),
    }


def suggest(message: str) -> dict[str, Any]:
    if not enabled() or not bool(_config().get("suggest_for_complex_tasks", True)):
        return {"suggested": False, "reason": "disabled"}
    text = str(message or "").strip()
    low = text.lower()
    signals = (
        "implement", "refactor", "migration", "architecture", "integration", "multi-step",
        "开发", "实现", "重构", "迁移", "架构", "集成", "系统", "详细计划", "阶段",
    )
    hits = sum(1 for token in signals if token in low)
    suggested = len(text) >= 220 or hits >= 2 or (hits >= 1 and len(text) >= 80)
    return {"suggested": suggested, "reason": "complex_task" if suggested else "simple_task", "signals": hits}
