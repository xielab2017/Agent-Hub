from __future__ import annotations

from pathlib import Path

from ali import fsutil


def test_list_dir_includes_directories_and_regular_files(tmp_path: Path) -> None:
    (tmp_path / "z-folder").mkdir()
    (tmp_path / "a-folder").mkdir()
    (tmp_path / "data.csv").write_bytes(b"a,b\n1,2\n")
    (tmp_path / ".secret").write_text("hidden", encoding="utf-8")

    result = fsutil.list_dir(str(tmp_path))

    assert result["ok"] is True
    assert [(item["name"], item["is_dir"]) for item in result["entries"]] == [
        ("a-folder", True),
        ("z-folder", True),
        ("data.csv", False),
    ]
    assert result["entries"][2]["size"] == 8


def test_list_dir_rejects_file_as_directory(tmp_path: Path) -> None:
    path = tmp_path / "data.csv"
    path.write_text("value", encoding="utf-8")

    result = fsutil.list_dir(str(path))

    assert result["ok"] is False
    assert result["error"] == "not a directory"
