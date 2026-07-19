from __future__ import annotations

import pytest

from ali import sessions


@pytest.mark.parametrize("default_title", ["New chat", "New task", "新对话", "新任务", ""])
def test_first_user_turn_replaces_default_title(tmp_path, monkeypatch, default_title):
    monkeypatch.setattr(sessions, "SESSIONS_DIR", tmp_path)
    item = sessions.create_session(default_title)

    updated = sessions.append_messages(
        item.id,
        {"role": "user", "content": "  分析皮肤微生物与衰老的关系\n并给出研究方案  "},
        {"role": "assistant", "content": "好的"},
    )

    assert updated is not None
    assert updated.title.startswith("分析皮肤微生物与衰老的关系")
    assert updated.title not in sessions._DEFAULT_SESSION_TITLES


def test_existing_custom_title_is_not_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr(sessions, "SESSIONS_DIR", tmp_path)
    item = sessions.create_session("My project")

    updated = sessions.append_messages(item.id, {"role": "user", "content": "Different topic"})

    assert updated is not None
    assert updated.title == "My project"
