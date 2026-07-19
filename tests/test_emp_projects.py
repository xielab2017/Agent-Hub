from __future__ import annotations

from ali.emp_projects import (
    EmpProjectStore,
    ProjectDataset,
    ProjectSession,
    render_reproducible_report,
    sample_map,
)


def dataset(manifest_id: str, omics: str, samples: tuple[str, ...]) -> ProjectDataset:
    return ProjectDataset(manifest_id, f"sha-{manifest_id}", omics, manifest_id, samples)


def test_project_persists_multi_endpoint_bindings(tmp_path) -> None:
    store = EmpProjectStore(tmp_path / "projects")
    project = store.create("Joint study", "hub-1")
    store.add_dataset(project, dataset("m1", "microbiome_16s", ("S1", "S2")))
    store.add_dataset(project, dataset("m2", "transcriptomics", ("S1", "S2")))
    store.bind_session(project, ProjectSession("local", "EMPSESSION00000000000001", "m1", "hub-1"))
    reopened = store.get(project.project_id, hub_session_id="hub-1")
    assert len(reopened.datasets) == 2
    assert reopened.sessions[0].endpoint_id == "local"
    assert len(store.list(hub_session_id="hub-1")) == 1


def test_project_ownership_is_enforced(tmp_path) -> None:
    store = EmpProjectStore(tmp_path)
    project = store.create("Study", "hub-a")
    try:
        store.get(project.project_id, hub_session_id="hub-b")
    except ValueError as exc:
        assert "does not belong" in str(exc)
    else:
        raise AssertionError("cross-session project read was allowed")


def test_sample_map_hashes_identifiers_and_checks_overlap() -> None:
    mapping = sample_map([
        dataset("m1", "microbiome_16s", ("S1", "S2", "S3")),
        dataset("m2", "transcriptomics", ("S2", "S3", "S4")),
    ])
    assert mapping["shared_count"] == 2
    assert "S2" not in str(mapping)


def test_report_links_sources_and_separates_interpretation(tmp_path) -> None:
    store = EmpProjectStore(tmp_path)
    project = store.create("Study", "hub-a")
    store.add_dataset(project, dataset("m1", "microbiome_16s", ("S1", "S2")))
    report = render_reproducible_report(
        project,
        runs=[{"run_id": "r1", "workflow": "microbiome_16s", "status": "done", "emp_version": "7", "r_version": "4.4"}],
        artifacts=[{"artifact_id": "a1", "name": "alpha.csv", "sha256": "abc", "analysis_step_id": "alpha"}],
    )
    assert "fingerprint" in report and "SHA-256 `abc`" in report
    assert "相关性不代表因果关系" in report
