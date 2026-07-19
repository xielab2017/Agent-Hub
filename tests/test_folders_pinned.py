from __future__ import annotations

from ali import folders


def test_folder_pin_persists_and_old_records_default_false(tmp_path, monkeypatch):
    store = tmp_path / "session_folders.json"
    monkeypatch.setattr(folders, "_path", lambda: store)

    first = folders.create_folder("Alpha")
    assert first["pinned"] is False
    assert folders.update_folder(first["id"], pinned=True)["pinned"] is True
    assert folders.list_folders()[0]["pinned"] is True

    store.write_text('[{"id":"legacy","name":"Legacy","sort_order":0}]', encoding="utf-8")
    assert folders.list_folders()[0]["pinned"] is False


def test_folder_can_be_unpinned(tmp_path, monkeypatch):
    store = tmp_path / "session_folders.json"
    monkeypatch.setattr(folders, "_path", lambda: store)
    item = folders.create_folder("Pinned")

    folders.update_folder(item["id"], pinned=True)
    updated = folders.update_folder(item["id"], pinned=False)

    assert updated is not None
    assert updated["pinned"] is False
