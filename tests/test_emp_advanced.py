from __future__ import annotations

import pytest

import hashlib
import time

import ali.emp_advanced as advanced
from ali.emp_advanced import endpoint_catalog, public_endpoint_catalog
from ali.emp_models import AnalysisPlan, DatasetFile, DatasetManifest, PlanStep
from ali.emp_service import EmpService


def test_remote_endpoint_catalog_is_disabled_by_default() -> None:
    config = {"emp": {"local_api_base": "http://127.0.0.1:8000", "remote_enabled": False}}
    assert endpoint_catalog(config) == []
    public = public_endpoint_catalog(config)
    assert public == [{
        "endpoint_id": "local-default",
        "base_url": "http://127.0.0.1:8000",
        "token_env": "EMP_API_TOKEN",
        "verify_tls": False,
        "mode": "local-api",
    }]


def test_remote_catalog_accepts_only_configured_https_endpoint() -> None:
    config = {"emp": {
        "remote_enabled": True,
        "remote_api_base": "https://emp.example.edu",
        "api_token_env": "EMP_LAB_TOKEN",
        "remote_upload_limit_mb": 64,
    }}
    endpoint = endpoint_catalog(config)[0]
    assert endpoint.endpoint_id == "remote-default"
    assert endpoint.origin == "https://emp.example.edu:443"
    assert endpoint.upload_limit_bytes == 64 * 1024 * 1024

    config["emp"]["remote_api_base"] = "http://emp.example.edu"
    with pytest.raises(ValueError, match="HTTPS"):
        endpoint_catalog(config)


def test_remote_approval_binds_configured_https_origin(tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    assay = workspace / "counts.csv"
    metadata = workspace / "meta.csv"
    assay.write_text("Feature,S1,S2\nA,1,2\n", encoding="utf-8")
    metadata.write_text("SampleID,Group\nS1,A\nS2,B\n", encoding="utf-8")
    config = {
        "workspace": str(workspace),
        "emp": {
            "enabled": True,
            "mode": "local-api",
            "remote_enabled": True,
            "remote_api_base": "https://emp.example.edu",
            "api_token_env": "EMP_LAB_TOKEN",
        },
    }
    service = EmpService(state_dir=tmp_path / "state", config_loader=lambda: config)
    manifest = DatasetManifest(
        manifest_id="manifest-approval",
        workspace=str(workspace),
        omics_type="transcriptomics",
        experiment_name="rna",
        files=[
            DatasetFile("assay", assay.name, assay.stat().st_size, assay.stat().st_mtime, sha256=hashlib.sha256(assay.read_bytes()).hexdigest()),
            DatasetFile("metadata", metadata.name, metadata.stat().st_size, metadata.stat().st_mtime, sha256=hashlib.sha256(metadata.read_bytes()).hexdigest()),
        ],
    )
    service.save_manifest(manifest)
    monkeypatch.setattr(advanced, "load_campus_config", lambda: config)
    monkeypatch.setattr(advanced, "_approval_key", lambda: b"k" * 32)

    approval = advanced.issue_remote_approval(
        manifest_id=manifest.manifest_id,
        endpoint_id="remote-default",
        hub_session_id="hub-1",
        data_policy="internal",
        service=service,
    )
    assert approval["endpoint_origin"] == "https://emp.example.edu:443"
    assert approval["file_count"] == 2


def test_remote_plan_uses_same_registered_step_contract_and_persists_artifacts(tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    assay = workspace / "counts.csv"
    metadata = workspace / "meta.csv"
    assay.write_text("Feature,S1,S2\nA,1,2\n", encoding="utf-8")
    metadata.write_text("SampleID,Group\nS1,A\nS2,B\n", encoding="utf-8")
    config = {"workspace": str(workspace), "emp": {"enabled": True, "mode": "local-api", "artifact_root": str(tmp_path / "artifacts")}}
    service = EmpService(state_dir=tmp_path / "state", config_loader=lambda: config)
    manifest = DatasetManifest(
        manifest_id="manifest-remote-plan", workspace=str(workspace), omics_type="transcriptomics", experiment_name="rna",
        files=[
            DatasetFile("assay", assay.name, assay.stat().st_size, assay.stat().st_mtime, sha256=hashlib.sha256(assay.read_bytes()).hexdigest()),
            DatasetFile("metadata", metadata.name, metadata.stat().st_size, metadata.stat().st_mtime, sha256=hashlib.sha256(metadata.read_bytes()).hexdigest()),
        ],
    )
    service.save_manifest(manifest)
    plan = AnalysisPlan(
        plan_id="plan-remote", title="Remote RNA", dataset_manifest_id=manifest.manifest_id,
        dataset_fingerprint=manifest.fingerprint(), hub_session_id="hub-remote", emp_mode="remote-api",
        workflow="transcriptomics", experiment_name="rna",
        steps=[PlanStep("validate", "emp.workflow.validate", {"workflow": "transcriptomics", "group_var": "Group", "min_group_size": 2})],
        output={"language": "en", "generate_report": True},
        confirmed_at=time.time(),
    )
    service.save_plan(plan)

    class FakeRemote:
        def request_json(self, method, path, payload=None):
            if path == "/api/capabilities":
                return {"success": True, "api_version": "1.0", "emp_version": "7.0"}
            assert method == "POST"
            assert path == "/api/workflows/transcriptomics/validate"
            assert payload["session_id"] == "REMOTESESSION"
            return {"success": True, "validation": {"checks": {"samples": True}}}

    monkeypatch.setattr(advanced, "_remote_client", lambda _endpoint, _sid: FakeRemote())
    started = advanced.start_remote_plan(
        plan_id=plan.plan_id, endpoint_id="lab", emp_session_id="REMOTESESSION",
        hub_session_id="hub-remote", service=service,
    )
    deadline = time.time() + 3
    while time.time() < deadline:
        job = service.get_job(started["job_id"])
        if job.status in {"done", "error"}:
            break
        time.sleep(0.02)
    assert job.status == "done"
    assert {item.mime_type for item in service.list_artifacts(job_id=job.job_id)} == {"application/json", "text/markdown"}
