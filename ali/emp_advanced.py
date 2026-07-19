"""Integration facade for remote, multi-workflow, project, and R Direct features."""

from __future__ import annotations

import csv
import hashlib
import os
import secrets
import stat
import threading
from pathlib import Path
from typing import Any, Optional

from .config import REPO_ROOT, STATE_DIR
from .emp_planning import compile_analysis_plan
from .emp_models import EmpJob
from .emp_client import EmpClient, EmpClientError
from .emp_projects import EmpProjectStore, ProjectDataset, ProjectSession, render_reproducible_report, sample_map
from .emp_r_direct import RDirectRunner
from .emp_remote import EmpRemoteClient, EmpRemoteEndpoint, RemoteUploadFile, UploadApprovalSigner
from .emp_service import EmpService, get_emp_service
from .secrets import get_api_key
from .settings import load_campus_config


ADVANCED_STATE = STATE_DIR / "emp"
PROJECT_STORE = EmpProjectStore(ADVANCED_STATE / "projects")


def _approval_key() -> bytes:
    path = ADVANCED_STATE / "approval-signing.key"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(secrets.token_bytes(32))
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
    key = path.read_bytes()
    if len(key) != 32:
        raise ValueError("invalid EMP approval signing key")
    return key


def endpoint_catalog(config: Optional[dict[str, Any]] = None) -> list[EmpRemoteEndpoint]:
    config = config or load_campus_config()
    emp = config.get("emp") if isinstance(config.get("emp"), dict) else {}
    values: list[EmpRemoteEndpoint] = []
    if emp.get("remote_enabled") is True:
        raw_endpoints = emp.get("endpoints") if isinstance(emp.get("endpoints"), list) else []
        if not raw_endpoints and str(emp.get("remote_api_base") or "").strip():
            raw_endpoints = [{"id": "remote-default", "base_url": emp["remote_api_base"]}]
        for item in raw_endpoints:
            if not isinstance(item, dict) or item.get("enabled") is False:
                continue
            limit = int(emp.get("remote_upload_limit_mb") or 2048) * 1024 * 1024
            endpoint = EmpRemoteEndpoint(
                endpoint_id=str(item.get("id") or ""),
                origin=str(item.get("base_url") or item.get("origin") or ""),
                token_env=str(item.get("token_env") or emp.get("api_token_env") or "EMP_API_TOKEN"),
                timeout_seconds=float(emp.get("request_timeout_seconds") or 60),
                upload_limit_bytes=limit,
            )
            values.append(endpoint)
    return values


def public_endpoint_catalog(config: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    cfg = config or load_campus_config()
    emp = cfg.get("emp") if isinstance(cfg.get("emp"), dict) else {}
    return [{
        "endpoint_id": "local-default",
        "base_url": str(emp.get("local_api_base") or "http://127.0.0.1:8000"),
        "token_env": str(emp.get("api_token_env") or "EMP_API_TOKEN"),
        "verify_tls": False,
        "mode": "local-api",
    }] + [
        {
            "endpoint_id": item.endpoint_id,
            "base_url": item.origin,
            "token_env": item.token_env,
            "verify_tls": True,
            "mode": "remote-api",
        }
        for item in endpoint_catalog(config)
    ]


def endpoint_capabilities(endpoint_id: str) -> dict[str, Any]:
    if endpoint_id == "local-default":
        return get_emp_service().client().capabilities()
    endpoints = {item.endpoint_id: item for item in endpoint_catalog()}
    endpoint = endpoints.get(endpoint_id)
    if endpoint is None:
        raise ValueError("EMP endpoint is not configured")
    signer = UploadApprovalSigner(_approval_key())
    transport = EmpRemoteClient(
        endpoint,
        approval_signer=signer,
        allowed_roots=get_emp_service().allowed_roots(""),
        token_resolver=lambda env_name: os.environ.get(env_name, "") or get_api_key(env_name),
    )
    return transport.request_json("GET", "/api/capabilities")


def _manifest_paths(service: EmpService, manifest_id: str, hub_session_id: str) -> tuple[Any, list[Path]]:
    manifest = service.get_manifest(manifest_id)
    workspace = Path(manifest.workspace)
    allowed = service.allowed_roots(hub_session_id)
    paths: list[Path] = []
    for item in manifest.files:
        if item.role not in {"assay", "metadata", "clinical"}:
            continue
        path = (workspace / item.path).resolve(strict=True)
        if not any(os.path.commonpath([str(root), str(path)]) == str(root) for root in allowed):
            raise ValueError("manifest file is outside allowed roots")
        paths.append(path)
    if not paths:
        raise ValueError("manifest has no transferable files")
    return manifest, paths


def issue_remote_approval(
    *, manifest_id: str, endpoint_id: str, hub_session_id: str, data_policy: str,
    service: Optional[EmpService] = None,
) -> dict[str, Any]:
    service = service or get_emp_service()
    manifest, paths = _manifest_paths(service, manifest_id, hub_session_id)
    endpoints = {item.endpoint_id: item for item in endpoint_catalog()}
    if endpoint_id == "local-default" or endpoint_id not in endpoints:
        raise ValueError("a configured remote endpoint is required")
    emp = load_campus_config().get("emp") or {}
    limit = int(emp.get("remote_upload_limit_mb") or 2048) * 1024 * 1024
    if sum(path.stat().st_size for path in paths) > limit:
        raise ValueError("remote upload exceeds the configured limit")
    signer = UploadApprovalSigner(
        _approval_key(), allow_restricted=emp.get("allow_restricted_remote") is True
    )
    token = signer.issue(
        endpoint_id=endpoint_id,
        endpoint_origin=endpoints[endpoint_id].origin,
        manifest_fingerprint=manifest.fingerprint(),
        hub_session_id=hub_session_id,
        file_count=len(paths),
        total_bytes=sum(path.stat().st_size for path in paths),
        data_policy=data_policy,
        approver=hub_session_id,
    )
    approval = signer.verify(
        token,
        endpoint_id=endpoint_id,
        endpoint_origin=endpoints[endpoint_id].origin,
        manifest_fingerprint=manifest.fingerprint(),
        hub_session_id=hub_session_id,
        file_count=len(paths),
        total_bytes=sum(path.stat().st_size for path in paths),
        data_policy=data_policy,
    )
    return {"token": token, **approval.to_dict()}


def execute_remote_import(
    *,
    manifest_id: str,
    endpoint_id: str,
    hub_session_id: str,
    data_policy: str,
    approval_token: str,
    service: Optional[EmpService] = None,
) -> dict[str, Any]:
    service = service or get_emp_service()
    manifest, paths = _manifest_paths(service, manifest_id, hub_session_id)
    endpoints = {item.endpoint_id: item for item in endpoint_catalog()}
    endpoint = endpoints.get(endpoint_id)
    if endpoint is None:
        raise ValueError("EMP endpoint is not configured")
    signer = UploadApprovalSigner(
        _approval_key(), allow_restricted=(load_campus_config().get("emp") or {}).get("allow_restricted_remote") is True
    )
    by_name = {Path(manifest.workspace, item.path).resolve(): item for item in manifest.files}
    upload_files: list[RemoteUploadFile] = []
    for path in paths:
        item = by_name[path]
        field_name = "data_file" if item.role == "assay" else "metadata_file"
        if item.role not in {"assay", "metadata", "clinical"}:
            continue
        if len(item.sha256) != 64:
            raise ValueError(f"remote upload requires a completed checksum: {item.path}")
        upload_files.append(RemoteUploadFile(field_name, path, item.sha256))
    client = EmpRemoteClient(
        endpoint,
        approval_signer=signer,
        allowed_roots=service.allowed_roots(hub_session_id),
        token_resolver=lambda env_name: os.environ.get(env_name, "") or get_api_key(env_name),
    )
    return client.upload_multipart(
        "/api/import",
        files=upload_files,
        fields={
            "experiment_name": manifest.experiment_name,
            "data_type": "tax" if manifest.omics_type == "microbiome_16s" else "normal",
            "assay_name": "counts",
        },
        approval_token=approval_token,
        manifest_fingerprint=manifest.fingerprint(),
        hub_session_id=hub_session_id,
        data_policy=data_policy,
    )


def _remote_client(endpoint_id: str, hub_session_id: str) -> EmpRemoteClient:
    endpoints = {item.endpoint_id: item for item in endpoint_catalog()}
    endpoint = endpoints.get(endpoint_id)
    if endpoint is None:
        raise ValueError("EMP endpoint is not configured")
    return EmpRemoteClient(
        endpoint,
        approval_signer=UploadApprovalSigner(_approval_key()),
        allowed_roots=get_emp_service().allowed_roots(hub_session_id),
        token_resolver=lambda env_name: os.environ.get(env_name, "") or get_api_key(env_name),
    )


def start_remote_plan(
    *, plan_id: str, endpoint_id: str, emp_session_id: str, hub_session_id: str,
    service: Optional[EmpService] = None,
) -> dict[str, Any]:
    service = service or get_emp_service()
    plan = service.get_plan(plan_id)
    if plan.hub_session_id != hub_session_id:
        raise ValueError("analysis plan does not belong to this session")
    if plan.emp_mode != "remote-api":
        raise ValueError("analysis plan is not configured for remote-api")
    if plan.requires_confirmation and plan.confirmed_at is None:
        raise ValueError("analysis plan must be confirmed before running")
    if not str(emp_session_id or "").strip():
        raise ValueError("remote EMP session_id is required")
    _remote_client(endpoint_id, hub_session_id)
    fingerprint = f"{plan.fingerprint()}:{endpoint_id}:{emp_session_id}"
    for existing in service.list_jobs(hub_session_id=hub_session_id):
        if existing.fingerprint == fingerprint and existing.status in {"pending", "running", "done"}:
            return existing.to_dict()
    job = EmpJob(
        job_id=f"empjob-{secrets.token_hex(16)}",
        plan_id=plan_id,
        hub_session_id=hub_session_id,
        fingerprint=fingerprint,
        emp_session_id=emp_session_id,
        message="Remote analysis queued",
        step_states={step.id: "pending" for step in plan.steps},
    )
    service._save_job(job)
    thread = threading.Thread(
        target=_execute_remote_plan,
        args=(job.job_id, endpoint_id, service),
        daemon=True,
    )
    service._threads[job.job_id] = thread
    thread.start()
    return job.to_dict()


def _execute_remote_plan(job_id: str, endpoint_id: str, service: EmpService) -> None:
    try:
        job = service.get_job(job_id)
        plan = service.get_plan(job.plan_id)
        manifest = service.get_manifest(plan.dataset_manifest_id)
        client = _remote_client(endpoint_id, plan.hub_session_id)
        capabilities = client.request_json("GET", "/api/capabilities")
        outputs: dict[str, dict[str, Any]] = {"capabilities": capabilities}
        service._update_job(job, status="running", progress=5, message="Remote EMP connected")
        for index, step in enumerate(plan.steps):
            service._check_cancel(job)
            service._update_job(
                job,
                progress=15 + int(index / max(1, len(plan.steps)) * 75),
                message=f"Running remote {step.id}",
                step_id=step.id,
            )
            job.step_states[step.id] = "running"
            service._save_job(job)
            method, path, payload = EmpClient.prepare_step_request(step.tool, {
                **step.params,
                "_workflow": plan.workflow,
                "session_id": job.emp_session_id,
                "experiment": plan.experiment_name,
            })
            result = client.request_json(method, path, payload if method == "POST" else None)
            outputs[step.id] = result
            artifact = service._write_json_artifact(job, step.id, f"{step.id}.json", result)
            job.artifact_ids.append(artifact.artifact_id)
            job.step_states[step.id] = "done"
            service._save_job(job)
        if plan.output.get("generate_report", True):
            job.artifact_ids.append(service._write_report(job, plan, manifest, outputs).artifact_id)
        service._update_job(job, status="done", progress=100, message="Remote analysis completed", step_id="")
    except EmpClientError as exc:
        service._fail_job(job_id, exc.to_dict())
    except Exception as exc:  # noqa: BLE001
        service._fail_job(job_id, EmpClientError("EMP_JOB_FAILED", str(exc)).to_dict())
    finally:
        service._threads.pop(job_id, None)


def _manifest_with_metadata_preview(service: EmpService, manifest_id: str, hub_session_id: str):
    manifest, _paths = _manifest_paths(service, manifest_id, hub_session_id)
    metadata = manifest.file_for_role("metadata") or manifest.file_for_role("clinical")
    if metadata is None:
        raise ValueError("metadata is required")
    path = Path(manifest.workspace) / metadata.path
    delimiter = metadata.delimiter or ("\t" if path.suffix.lower() in {".tsv", ".txt"} else ",")
    rows: list[list[str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        for index, row in enumerate(reader):
            if index > 10000:
                break
            rows.append([str(value) for value in row])
    metadata.preview = rows
    return manifest


def compile_manifest_plan(
    *, manifest_id: str, hub_session_id: str, workflow: str, session_id: str,
    experiment: str, parameters: dict[str, Any], capabilities: dict[str, Any],
    language: str = "zh",
    service: Optional[EmpService] = None,
) -> dict[str, Any]:
    service = service or get_emp_service()
    manifest = _manifest_with_metadata_preview(service, manifest_id, hub_session_id)
    manifest.experiment_name = experiment or manifest.experiment_name
    values = dict(parameters)
    mode = str(values.pop("emp_mode", "local-api"))
    plan = compile_analysis_plan(
        capabilities,
        manifest,
        hub_session_id=hub_session_id,
        parameters=values,
        workflow=workflow,
        emp_mode=mode,
        language=language,
    )
    service.save_plan(plan)
    return {"plan": plan.to_dict(), "fingerprint": plan.fingerprint()}


def create_project(name: str, hub_session_id: str) -> dict[str, Any]:
    return PROJECT_STORE.create(name, hub_session_id).to_dict()


def add_project_manifest(project_id: str, hub_session_id: str, manifest_id: str) -> dict[str, Any]:
    service = get_emp_service()
    manifest = _manifest_with_metadata_preview(service, manifest_id, hub_session_id)
    project = PROJECT_STORE.get(project_id, hub_session_id=hub_session_id)
    metadata = manifest.file_for_role("metadata") or manifest.file_for_role("clinical")
    rows = metadata.preview if metadata else []
    headers = rows[0] if rows else []
    try:
        sample_index = headers.index(manifest.sample_id_column)
    except ValueError:
        sample_index = 0
    sample_hashes = tuple(
        hashlib.sha256(row[sample_index].strip().encode("utf-8")).hexdigest()
        for row in rows[1:]
        if len(row) > sample_index and row[sample_index].strip()
    )
    dataset = ProjectDataset(
        manifest.manifest_id, manifest.fingerprint(), manifest.omics_type, manifest.experiment_name, sample_hashes
    )
    return PROJECT_STORE.add_dataset(project, dataset).to_dict()


def project_sample_map(project_id: str, hub_session_id: str) -> dict[str, Any]:
    project = PROJECT_STORE.get(project_id, hub_session_id=hub_session_id)
    return sample_map(project.datasets)


def bind_project_session(
    project_id: str, hub_session_id: str, endpoint_id: str, emp_session_id: str, manifest_id: str,
) -> dict[str, Any]:
    if endpoint_id != "local-default" and endpoint_id not in {item.endpoint_id for item in endpoint_catalog()}:
        raise ValueError("EMP endpoint is not configured")
    if not str(emp_session_id or "").strip():
        raise ValueError("emp_session_id is required")
    service = get_emp_service()
    manifest = service.get_manifest(manifest_id)
    if manifest.manifest_id != manifest_id:
        raise ValueError("manifest not found")
    project = PROJECT_STORE.get(project_id, hub_session_id=hub_session_id)
    if not any(item.manifest_id == manifest_id for item in project.datasets):
        raise ValueError("manifest must be added to the project before binding a session")
    binding = ProjectSession(endpoint_id, emp_session_id, manifest_id, hub_session_id)
    return PROJECT_STORE.bind_session(project, binding).to_dict()


def generate_project_report(project_id: str, hub_session_id: str, language: str = "zh") -> dict[str, Any]:
    service = get_emp_service()
    project = PROJECT_STORE.get(project_id, hub_session_id=hub_session_id)
    manifest_ids = {item.manifest_id for item in project.datasets}
    jobs = []
    plans: dict[str, Any] = {}
    for job in service.list_jobs(hub_session_id=hub_session_id):
        try:
            plan = service.get_plan(job.plan_id)
        except ValueError:
            continue
        if plan.dataset_manifest_id in manifest_ids:
            jobs.append(job)
            plans[job.plan_id] = plan
    job_ids = {job.job_id for job in jobs}
    artifacts = [item for item in service.list_artifacts(hub_session_id=hub_session_id) if item.job_id in job_ids]
    runs = []
    for job in jobs:
        workflow = "unknown"
        if job.plan_id:
            workflow = plans.get(job.plan_id).workflow if job.plan_id in plans else "unknown"
        runs.append({
            "run_id": job.job_id,
            "workflow": workflow,
            "status": job.status,
            "emp_version": "recorded in run artifact",
            "r_version": "recorded in run artifact",
        })
    text = render_reproducible_report(
        project,
        runs=runs,
        artifacts=[item.to_dict() for item in artifacts],
        language=language,
    )
    virtual_job = EmpJob(
        job_id=f"project-{project.project_id}",
        plan_id=project.project_id,
        hub_session_id=hub_session_id,
        fingerprint=project.project_id,
        status="done",
    )
    path = service._artifact_path(virtual_job, f"{project.project_id}-report.md")
    path.write_text(text, encoding="utf-8")
    artifact = service._register_artifact(virtual_job, "joint-report", path, "report", "text/markdown")
    if artifact.artifact_id not in project.artifact_ids:
        project.artifact_ids.append(artifact.artifact_id)
        PROJECT_STORE.save(project)
    return artifact.to_dict()


def r_direct_runner() -> RDirectRunner:
    cfg = load_campus_config()
    emp = cfg.get("emp") if isinstance(cfg.get("emp"), dict) else {}
    service = get_emp_service()
    return RDirectRunner(
        REPO_ROOT / "scripts" / "emp_r_runner.R",
        enabled=emp.get("allow_r_direct") is True,
        allowed_roots=service.allowed_roots(""),
        timeout_seconds=int(emp.get("request_timeout_seconds") or 60),
        state_dir=ADVANCED_STATE / "r-direct",
    )
