from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from ali.emp_r_direct import RDirectError, RDirectRunner


RUNNER = Path(__file__).parents[1] / "scripts" / "emp_r_runner.R"


def test_r_direct_is_disabled_by_default(tmp_path: Path) -> None:
    runner = RDirectRunner(RUNNER, allowed_roots=[tmp_path])
    assert runner.preflight()["enabled"] is False
    with pytest.raises(RDirectError, match="disabled"):
        runner.run("preflight")


def test_r_direct_rejects_unregistered_operation(tmp_path: Path) -> None:
    runner = RDirectRunner(RUNNER, enabled=True, allowed_roots=[tmp_path])
    with pytest.raises(ValueError, match="allowlisted"):
        runner.run("eval", {"code": "system('id')"})


@pytest.mark.skipif(not shutil.which("Rscript"), reason="Rscript unavailable")
def test_r_direct_preflight_and_table_summary(tmp_path: Path) -> None:
    table = tmp_path / "counts.csv"
    table.write_text("Feature,S1,S2\nA,1,2\nB,3,4\n", encoding="utf-8")
    runner = RDirectRunner(RUNNER, enabled=True, allowed_roots=[tmp_path], state_dir=tmp_path / "state")
    preflight = runner.run("preflight")
    assert preflight.success and preflight.versions and preflight.versions["R"]
    result = runner.run("summarize_table", {"path": str(table), "delimiter": ","})
    assert result.data["rows_read"] == 2
    assert result.data["columns"] == 3


@pytest.mark.skipif(not shutil.which("Rscript"), reason="Rscript unavailable")
def test_r_direct_dataset_preview_matches_sample_orientation(tmp_path: Path) -> None:
    assay = tmp_path / "counts.csv"
    metadata = tmp_path / "metadata.csv"
    assay.write_text("Feature,S1,S2\nA,1,2\nB,3,4\n", encoding="utf-8")
    metadata.write_text("SampleID,Group\nS1,A\nS2,B\n", encoding="utf-8")
    runner = RDirectRunner(RUNNER, enabled=True, allowed_roots=[tmp_path])
    result = runner.run("preview_dataset", {
        "data_path": str(assay),
        "metadata_path": str(metadata),
        "sample_id_column": "SampleID",
        "data_type": "normal",
    })
    assert result.data["data"]["orientation"] == "features_in_rows"
    assert result.data["sample_overlap"] == {"assay": 2, "metadata": 2, "matched": 2}


def test_r_direct_rejects_path_outside_allowed_roots(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside.csv"
    outside.write_text("a\n1\n", encoding="utf-8")
    runner = RDirectRunner(RUNNER, enabled=True, allowed_roots=[allowed])
    with pytest.raises(ValueError, match="outside allowed roots"):
        runner.run("summarize_table", {"path": str(outside)})
