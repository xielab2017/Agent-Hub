from __future__ import annotations

import json
from pathlib import Path

import pytest

from ali import sessions, skills, trellis


@pytest.fixture()
def trellis_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, sessions.Session]:
    state_dir = tmp_path / "state" / "sessions"
    state_dir.mkdir(parents=True)
    monkeypatch.setattr(sessions, "SESSIONS_DIR", state_dir)
    workspace = tmp_path / "workspace"
    (workspace / ".trellis" / "tasks").mkdir(parents=True)
    config = {
        "workspace": str(workspace),
        "trellis": {
            "enabled": True,
            "context_budget_chars": 4000,
            "artifact_budget_chars": 2000,
            "suggest_for_complex_tasks": True,
        },
    }
    monkeypatch.setattr(trellis, "load_campus_config", lambda: config)
    session = sessions.create_session("Trellis test")
    return workspace, session


def test_create_bind_approve_validate_and_complete(trellis_env: tuple[Path, sessions.Session]) -> None:
    workspace, session = trellis_env
    created = trellis.create_task(session.id, str(workspace), "Build controlled workflow", "Implement safely")
    task_id = created["task"]["id"]
    assert created["task"]["status"] == "planning"
    assert sessions.get_session(session.id).trellis["task_id"] == task_id

    with pytest.raises(trellis.TrellisError, match="invalid task transition"):
        trellis.transition(session.id, "completed")

    approved = trellis.approve(session.id, "tester", "Reviewed")
    assert approved["task"]["status"] == "in_progress"
    assert approved["task"]["approval"]["approved_by"] == "tester"

    checked = trellis.record_validation(session.id, "python3 -m pytest", True, "all passed")
    assert checked["task"]["status"] == "quality_check"
    completed = trellis.transition(session.id, "completed")
    assert completed["task"]["status"] == "completed"

    stored = json.loads((workspace / ".trellis" / "tasks" / task_id / "task.json").read_text(encoding="utf-8"))
    assert stored["completedAt"]


def test_failed_validation_cannot_complete(trellis_env: tuple[Path, sessions.Session]) -> None:
    workspace, session = trellis_env
    trellis.create_task(session.id, str(workspace), "Fix failing integration")
    with pytest.raises(trellis.TrellisError, match="only be recorded"):
        trellis.record_validation(session.id, "pytest", True, "not approved")
    trellis.approve(session.id)
    result = trellis.record_validation(session.id, "pytest", False, "one failure")
    assert result["task"]["status"] == "in_progress"
    with pytest.raises(trellis.TrellisError):
        trellis.transition(session.id, "completed")


def test_context_is_approval_gated_bounded_and_redacted(trellis_env: tuple[Path, sessions.Session]) -> None:
    workspace, session = trellis_env
    result = trellis.create_task(session.id, str(workspace), "Secret-safe implementation")
    task_dir = workspace / ".trellis" / "tasks" / result["task"]["id"]
    (task_dir / "design.md").write_text(
        "# Design\nAPI_TOKEN=visible-no-more\nsecret token sk-abcdefghijklmnop\n" + ("x" * 6000),
        encoding="utf-8",
    )

    block, meta = trellis.context_block(session.id)
    assert block == ""
    assert meta["approved"] is False

    trellis.approve(session.id)
    block, meta = trellis.context_block(session.id)
    assert "[REDACTED]" in block
    assert "visible-no-more" not in block
    assert "sk-abcdefghijklmnop" not in block
    assert len(block) <= 4000
    assert meta["sources"] == ["prd.md", "design.md"]


def test_task_path_traversal_and_symlink_are_rejected(trellis_env: tuple[Path, sessions.Session], tmp_path: Path) -> None:
    workspace, session = trellis_env
    with pytest.raises(trellis.TrellisError, match="invalid task id"):
        trellis.bind_task(session.id, str(workspace), "../outside")

    outside = tmp_path / "outside-task"
    outside.mkdir()
    (outside / "task.json").write_text('{"status":"planning"}', encoding="utf-8")
    link = workspace / ".trellis" / "tasks" / "linked-task"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    assert all(item["id"] != "linked-task" for item in trellis.list_tasks(str(workspace)))


def test_tasks_root_symlink_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = tmp_path / "workspace"
    trellis_root = workspace / ".trellis"
    trellis_root.mkdir(parents=True)
    outside = tmp_path / "outside-tasks"
    outside.mkdir()
    try:
        (trellis_root / "tasks").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    monkeypatch.setattr(trellis, "load_campus_config", lambda: {"workspace": str(workspace), "trellis": {"enabled": True}})
    with pytest.raises(trellis.TrellisError, match="must not be a symlink"):
        trellis.list_tasks(str(workspace))


def test_child_session_inherits_task_binding(trellis_env: tuple[Path, sessions.Session]) -> None:
    workspace, parent = trellis_env
    created = trellis.create_task(parent.id, str(workspace), "Parallel workflow")
    child = sessions.create_session("lane", hidden=True, parent_id=parent.id)
    assert child.trellis["task_id"] == created["task"]["id"]


def test_simple_message_does_not_create_or_suggest_task(trellis_env: tuple[Path, sessions.Session]) -> None:
    workspace, _session = trellis_env
    assert trellis.suggest("你好")["suggested"] is False
    assert trellis.list_tasks(str(workspace)) == []
    assert trellis.suggest("请实现一个跨模块系统集成，并制定详细计划和阶段验收方案")["suggested"] is True


def test_chinese_title_uses_safe_fallback_slug(trellis_env: tuple[Path, sessions.Session]) -> None:
    workspace, session = trellis_env
    result = trellis.create_task(session.id, str(workspace), "科研数据平台")
    assert result["task"]["id"].endswith("agent-hub-task")


def test_disabled_integration_returns_empty_context(trellis_env: tuple[Path, sessions.Session], monkeypatch: pytest.MonkeyPatch) -> None:
    workspace, session = trellis_env
    trellis.create_task(session.id, str(workspace), "Disabled integration")
    monkeypatch.setattr(trellis, "load_campus_config", lambda: {"workspace": str(workspace), "trellis": {"enabled": False}})
    assert trellis.context_block(session.id) == ("", {"enabled": False})
    assert trellis.status(session.id)["enabled"] is False


def test_project_trellis_skills_are_discoverable() -> None:
    catalog = {item["id"]: item for item in skills.list_skills().get("skills", [])}
    assert "trellis-start" in catalog
    assert "trellis-check" in catalog
    assert catalog["trellis-start"]["managed"] is False
