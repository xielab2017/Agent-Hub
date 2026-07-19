from __future__ import annotations

from pathlib import Path

import pytest

from ali.emp_discovery import (
    DiscoveryError,
    path_is_within_text,
    resolve_allowed_path,
    scan_dataset,
    select_manifest_pairing,
)


def _dataset(root: Path) -> None:
    root.mkdir()
    (root / "16s_abundance.csv").write_text(
        "Feature,S1,S2,S3\nTaxa_A,1,2,3\nTaxa_B,3,2,1\n", encoding="utf-8"
    )
    (root / "metadata.csv").write_text(
        "SampleID,Group\nS1,A\nS2,A\nS3,B\n", encoding="utf-8"
    )
    (root / ".env").write_text("SECRET=value\n", encoding="utf-8")
    hidden = root / ".git"
    hidden.mkdir()
    (hidden / "config").write_text("private", encoding="utf-8")


def test_cross_platform_path_containment() -> None:
    assert path_is_within_text("/data/study/a.csv", "/data/study")
    assert not path_is_within_text("/data/study-two/a.csv", "/data/study")
    assert path_is_within_text(r"C:\Data\Study\a.csv", r"c:\data\study", platform="windows")
    assert not path_is_within_text(r"D:\Data\Study\a.csv", r"C:\Data\Study", platform="windows")
    assert not path_is_within_text(r"C:\Data\Study2\a.csv", r"C:\Data\Study", platform="windows")


def test_scan_manifest_and_secret_exclusion(tmp_path: Path) -> None:
    root = tmp_path / "study"
    _dataset(root)
    manifest = scan_dataset(root, allowed_roots=[tmp_path])
    assert manifest.omics_type == "microbiome_16s"
    assert manifest.orientation == "features_in_rows"
    assert manifest.sample_id_column == "SampleID"
    assert manifest.sample_overlap["matched"] == 3
    assert {item.role for item in manifest.files} >= {"assay", "metadata"}
    assert all(".env" not in item.path and ".git" not in item.path for item in manifest.files)
    assert all(item.sha256 for item in manifest.files)


def test_sample_matching_is_not_limited_to_ui_preview_rows(tmp_path: Path) -> None:
    root = tmp_path / "study"
    root.mkdir()
    sample_ids = [f"S{i}" for i in range(1, 61)]
    (root / "16s_abundance.csv").write_text(
        "Feature," + ",".join(sample_ids) + "\nTaxa_A," + ",".join("1" for _ in sample_ids) + "\n",
        encoding="utf-8",
    )
    (root / "metadata.csv").write_text(
        "SampleID,Group\n" + "\n".join(f"{sample},A" for sample in sample_ids) + "\n",
        encoding="utf-8",
    )
    manifest = scan_dataset(root, allowed_roots=[tmp_path], preview_rows=20)
    metadata = manifest.file_for_role("metadata")
    assert metadata is not None and metadata.preview == [["SampleID", "Group"]]
    assert manifest.sample_overlap["matched"] == 60


def test_manifest_pairing_can_be_corrected(tmp_path: Path) -> None:
    root = tmp_path / "study"
    _dataset(root)
    (root / "wrong_metadata.csv").write_text("SampleID,Group\nX1,C\n", encoding="utf-8")
    manifest = scan_dataset(root, allowed_roots=[tmp_path])
    selected = select_manifest_pairing(
        manifest, assay_path="16s_abundance.csv", metadata_path="wrong_metadata.csv"
    )
    assert selected.file_for_role("metadata").path == "wrong_metadata.csv"
    assert selected.sample_overlap["matched"] == 0
    with pytest.raises(DiscoveryError):
        select_manifest_pairing(manifest, assay_path="missing.csv", metadata_path="metadata.csv")


def test_outside_root_and_symlink_escape_rejected(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    secret = outside / "secret.csv"
    secret.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(DiscoveryError):
        resolve_allowed_path(secret, [allowed])
    link = allowed / "escape.csv"
    try:
        link.symlink_to(secret)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(DiscoveryError):
        resolve_allowed_path(link, [allowed])


def test_scan_depth_limit(tmp_path: Path) -> None:
    root = tmp_path / "study"
    root.mkdir()
    deep = root / "one" / "two" / "three"
    deep.mkdir(parents=True)
    (deep / "abundance.csv").write_text("Feature,S1\nA,1\n", encoding="utf-8")
    with pytest.raises(DiscoveryError):
        scan_dataset(root, allowed_roots=[tmp_path], max_depth=2)
