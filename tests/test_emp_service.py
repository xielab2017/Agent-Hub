from __future__ import annotations

import base64
import time
from pathlib import Path

import pytest

from ali.emp_models import EmpJob
from ali.emp_service import EmpService
from ali.emp_tools import EMP_TOOL_SCHEMAS, invoke


PNG = base64.b64encode(b"\x89PNG\r\n\x1a\nmock-png").decode()


class FakeEmpClient:
    def __init__(self) -> None:
        self.calls = []

    def capabilities(self):
        self.calls.append("capabilities")
        return {"success": True, "api_version": "1.0", "features": {"path_import": True}, "workflows": ["microbiome_16s"]}

    def preview_path(self, payload):
        self.calls.append("preview")
        return {"success": True, "sample_overlap": {"matched": 3}, "payload_seen": sorted(payload)}

    def import_path(self, payload):
        self.calls.append("import")
        return {"success": True, "session_id": "EMPSESSION", "samples": 3, "features": 2}

    def run_step(self, tool, params):
        self.calls.append(tool)
        if tool == "emp.workflow.validate":
            return {"success": True, "validation": {"checks": {"samples": True, "taxonomy": True}}}
        if tool == "emp.analyze.alpha":
            return {"success": True, "n_rows": 3, "columns": ["SampleID", "shannon"], "data": "[]"}
        if tool == "emp.visualize.alpha":
            return {"success": True, "plot": PNG, "pdf_available": True, "pdf_name": "alpha.pdf"}
        return {"success": True, "n_features_after": 2}

    def download_artifact(self, _path, destination):
        destination.write_bytes(b"%PDF-1.4 mock")
        return destination

    def create_session(self):
        return "EMPSESSION"


class FailOnceEmpClient(FakeEmpClient):
    def __init__(self) -> None:
        super().__init__()
        self.failed = False

    def run_step(self, tool, params):
        if tool == "emp.analyze.alpha" and not self.failed:
            self.calls.append(tool)
            self.failed = True
            raise RuntimeError("transient alpha failure")
        return super().run_step(tool, params)


def _setup(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "16s_abundance.csv").write_text(
        "Feature,S1,S2,S3\nTaxa_A,1,2,3\nTaxa_B,3,2,1\n", encoding="utf-8"
    )
    (workspace / "metadata.csv").write_text(
        "SampleID,Group\nS1,A\nS2,A\nS3,B\n", encoding="utf-8"
    )
    fake = FakeEmpClient()
    config = {
        "workspace": str(workspace),
        "emp": {
            "enabled": True,
            "mode": "local-api",
            "local_api_base": "http://127.0.0.1:8000",
            "allowed_roots": [],
            "artifact_root": str(tmp_path / "artifacts"),
        },
    }
    service = EmpService(
        state_dir=tmp_path / "state",
        config_loader=lambda: config,
        client_factory=lambda _cfg: fake,
    )
    return workspace, fake, config, service


def _wait(service: EmpService, job_id: str) -> EmpJob:
    deadline = time.time() + 5
    while time.time() < deadline:
        job = service.get_job(job_id)
        if job.status in {"done", "error", "cancelled"}:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_disabled_integration_reports_online_but_not_ready(tmp_path: Path) -> None:
    fake = FakeEmpClient()
    service = EmpService(
        state_dir=tmp_path / "state",
        config_loader=lambda: {"workspace": str(tmp_path), "emp": {"enabled": False}},
        client_factory=lambda _cfg: fake,
    )
    status = service.status()
    assert status["enabled"] is False
    assert status["reachable"] is True
    assert status["compatible"] is True
    assert status["ready"] is False
    assert status["analysis_ready"] is False
    assert fake.calls == ["capabilities"]


def test_enabled_compatible_integration_is_ready(tmp_path: Path) -> None:
    fake = FakeEmpClient()
    service = EmpService(
        state_dir=tmp_path / "state",
        config_loader=lambda: {"workspace": str(tmp_path), "emp": {"enabled": True}},
        client_factory=lambda _cfg: fake,
    )
    status = service.status()
    assert status["ready"] is True
    assert status["analysis_ready"] is True
    assert status["arbitrary_r_enabled"] is False


def test_path_import_is_reported_without_rejecting_supported_workflow(tmp_path: Path) -> None:
    fake = FakeEmpClient()
    fake.capabilities = lambda: {
        "success": True,
        "api_version": "1.0",
        "features": {"path_import": False},
        "workflows": ["microbiome_16s"],
    }
    service = EmpService(
        state_dir=tmp_path / "state",
        config_loader=lambda: {"workspace": str(tmp_path), "emp": {"enabled": True}},
        client_factory=lambda _cfg: fake,
    )

    status = service.status()

    assert status["compatible"] is True
    assert status["ready"] is True
    assert status["path_import_available"] is False
    assert status["analysis_ready"] is False


def test_arbitrary_r_is_reported_as_not_analysis_ready(tmp_path: Path) -> None:
    fake = FakeEmpClient()
    fake.capabilities = lambda: {
        "success": True,
        "api_version": "1.0",
        "features": {"path_import": True, "arbitrary_r": True},
        "workflows": ["microbiome_16s"],
    }
    service = EmpService(
        state_dir=tmp_path / "state",
        config_loader=lambda: {"workspace": str(tmp_path), "emp": {"enabled": True}},
        client_factory=lambda _cfg: fake,
    )

    status = service.status()

    assert status["ready"] is True
    assert status["arbitrary_r_enabled"] is True
    assert status["analysis_ready"] is False


def test_confirm_gate_dedup_and_artifact_persistence(tmp_path: Path) -> None:
    workspace, fake, config, service = _setup(tmp_path)
    manifest = service.scan(str(workspace), hub_session_id="hub-1")
    plan = service.create_16s_plan(manifest.manifest_id, hub_session_id="hub-1", group_var="Group")
    with pytest.raises(ValueError, match="confirmed"):
        service.run_plan(plan.plan_id)
    service.confirm_plan(plan.plan_id)
    job = service.run_plan(plan.plan_id)
    completed = _wait(service, job.job_id)
    assert completed.status == "done"
    assert completed.progress == 100
    assert set(completed.step_states.values()) == {"done"}
    assert service.run_plan(plan.plan_id).job_id == completed.job_id
    artifacts = service.list_artifacts(job_id=completed.job_id)
    assert {item.mime_type for item in artifacts} >= {"application/json", "image/png", "application/pdf", "text/markdown"}
    assert all(Path(item.local_path).is_file() for item in artifacts)
    report = next(item for item in artifacts if item.mime_type == "text/markdown")
    report_text = Path(report.local_path).read_text(encoding="utf-8")
    assert "SHA-256" in report_text
    assert "API" in report_text and "Taxonomy" in report_text
    assert "不修改或替代 EMP" in report_text
    assert "emp.user_r.run" not in EMP_TOOL_SCHEMAS
    assert "url" not in str(EMP_TOOL_SCHEMAS)

    restarted = EmpService(
        state_dir=tmp_path / "state",
        config_loader=lambda: config,
        client_factory=lambda _cfg: fake,
    )
    assert restarted.get_job(completed.job_id).status == "done"
    assert len(restarted.list_artifacts(job_id=completed.job_id)) == len(artifacts)


def test_interrupted_job_is_recoverable_error(tmp_path: Path) -> None:
    _workspace, _fake, config, service = _setup(tmp_path)
    job = EmpJob("empjob-interrupted", "plan-x", "hub-1", "fingerprint", status="running")
    service._save_job(job)
    restarted = EmpService(state_dir=tmp_path / "state", config_loader=lambda: config)
    recovered = restarted.get_job(job.job_id)
    assert recovered.status == "error"
    assert recovered.error["retryable"] is True


def test_typed_tool_plan_dispatch(tmp_path: Path) -> None:
    workspace, _fake, _config, service = _setup(tmp_path)
    manifest = invoke(
        "emp.dataset.scan",
        {"path": str(workspace), "hub_session_id": "hub-2"},
        service=service,
    )
    plan = invoke(
        "emp.analysis.plan",
        {"manifest_id": manifest["manifest_id"], "hub_session_id": "hub-2", "group_var": "Group"},
        service=service,
    )
    assert plan["workflow"] == "microbiome_16s"
    with pytest.raises(ValueError):
        invoke("emp.user_r.run", {}, service=service)


def test_service_persists_manual_pairing(tmp_path: Path) -> None:
    workspace, _fake, _config, service = _setup(tmp_path)
    (workspace / "alternate_metadata.csv").write_text(
        "SampleID,Treatment\nS1,X\nS2,Y\nS3,Y\n", encoding="utf-8"
    )
    manifest = service.scan(str(workspace), hub_session_id="hub-pair")
    updated = service.update_manifest_pairing(
        manifest.manifest_id,
        hub_session_id="hub-pair",
        assay_path="16s_abundance.csv",
        metadata_path="alternate_metadata.csv",
    )
    assert updated.file_for_role("metadata").path == "alternate_metadata.csv"
    assert service.get_manifest(manifest.manifest_id).sample_overlap["matched"] == 3


def test_confirmed_plan_rejects_changed_input_file(tmp_path: Path) -> None:
    workspace, _fake, _config, service = _setup(tmp_path)
    manifest = service.scan(str(workspace), hub_session_id="hub-stale")
    plan = service.create_16s_plan(manifest.manifest_id, hub_session_id="hub-stale", group_var="Group")
    service.confirm_plan(plan.plan_id)
    (workspace / "16s_abundance.csv").write_text(
        "Feature,S1,S2,S3\nTaxa_A,99,2,3\nTaxa_B,3,2,1\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="changed after scanning"):
        service.run_plan(plan.plan_id)


def test_failed_job_retries_from_failed_step_without_reimport(tmp_path: Path) -> None:
    workspace, _fake, config, _service = _setup(tmp_path)
    fake = FailOnceEmpClient()
    service = EmpService(
        state_dir=tmp_path / "retry-state",
        config_loader=lambda: config,
        client_factory=lambda _cfg: fake,
    )
    manifest = service.scan(str(workspace), hub_session_id="hub-retry")
    plan = service.create_16s_plan(manifest.manifest_id, hub_session_id="hub-retry", group_var="Group")
    service.confirm_plan(plan.plan_id)
    failed = _wait(service, service.run_plan(plan.plan_id).job_id)
    assert failed.status == "error"
    assert failed.step_id == "alpha"
    assert failed.step_states["alpha"] == "error"
    assert fake.calls.count("import") == 1

    retried = _wait(service, service.retry_job(failed.job_id, hub_session_id="hub-retry").job_id)
    assert retried.status == "done"
    assert retried.retry_step_ids == ["alpha", "alpha_plot"]
    assert retried.step_states["validate"] == "done"
    assert retried.step_states["alpha"] == "done"
    assert fake.calls.count("import") == 1
