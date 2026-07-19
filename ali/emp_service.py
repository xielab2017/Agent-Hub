"""Business orchestration and persistent state for local EMP analysis."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import quote

from .config import STATE_DIR
from .emp_client import EmpClient, EmpClientError
from .emp_discovery import DiscoveryError, resolve_allowed_path, scan_dataset, select_manifest_pairing
from .emp_models import (
    AnalysisPlan,
    DatasetManifest,
    EmpArtifact,
    EmpJob,
    EmpSessionMapping,
    PlanStep,
    new_id,
    utc_timestamp,
)
from .settings import load_campus_config
from .uploads import uploads_root


EMP_STATE_DIR = STATE_DIR / "emp"
MANIFESTS_DIR = EMP_STATE_DIR / "manifests"
PLANS_DIR = EMP_STATE_DIR / "plans"
MAPPINGS_DIR = EMP_STATE_DIR / "mappings"
JOBS_DIR = EMP_STATE_DIR / "jobs"
ARTIFACT_INDEX_DIR = EMP_STATE_DIR / "artifact-index"
DEFAULT_ARTIFACT_DIR = EMP_STATE_DIR / "artifacts"

TAXONOMY_LEVELS = {"Kingdom", "Phylum", "Class", "Order", "Family", "Genus", "Species"}
ALPHA_METRICS = {"shannon", "simpson", "observed", "chao1"}
PLAN_TOOLS = {
    "emp.workflow.validate",
    "emp.prepare.taxonomy",
    "emp.analyze.alpha",
    "emp.visualize.alpha",
    "emp.prepare.normalize",
    "emp.analyze.differential",
    "emp.analyze.enrichment",
    "emp.analyze.association",
}
TERMINAL_JOB_STATES = {"done", "error", "cancelled"}


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid EMP state file: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"invalid EMP state object: {path.name}")
    return value


def _safe_name(value: str, fallback: str = "study") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "")).strip("_")
    return cleaned[:80] or fallback


class EmpService:
    def __init__(
        self,
        *,
        state_dir: Optional[Path] = None,
        config_loader: Callable[[], dict[str, Any]] = load_campus_config,
        client_factory: Optional[Callable[[dict[str, Any]], EmpClient]] = None,
    ) -> None:
        self.state_dir = (state_dir or EMP_STATE_DIR).expanduser().resolve()
        self.manifests_dir = self.state_dir / "manifests"
        self.plans_dir = self.state_dir / "plans"
        self.mappings_dir = self.state_dir / "mappings"
        self.jobs_dir = self.state_dir / "jobs"
        self.artifact_index_dir = self.state_dir / "artifact-index"
        self.default_artifact_dir = self.state_dir / "artifacts"
        self._config_loader = config_loader
        self._client_factory = client_factory
        self._lock = threading.RLock()
        self._threads: dict[str, threading.Thread] = {}
        for path in (
            self.manifests_dir, self.plans_dir, self.mappings_dir,
            self.jobs_dir, self.artifact_index_dir, self.default_artifact_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
        self._recover_interrupted_jobs()

    def config(self) -> dict[str, Any]:
        root = self._config_loader()
        value = root.get("emp") if isinstance(root, dict) else {}
        return dict(value) if isinstance(value, dict) else {}

    def _require_enabled(self) -> dict[str, Any]:
        cfg = self.config()
        if not bool(cfg.get("enabled", False)):
            raise EmpClientError("EMP_UNAVAILABLE", "EMP integration is disabled")
        mode = str(cfg.get("mode") or "auto")
        if mode not in {"auto", "local-api"}:
            raise EmpClientError("EMP_VERSION_INCOMPATIBLE", "Phase 1 supports local-api mode only")
        return cfg

    def client(self) -> EmpClient:
        cfg = self._require_enabled()
        if self._client_factory is not None:
            return self._client_factory(cfg)
        return EmpClient(
            str(cfg.get("local_api_base") or "http://127.0.0.1:8000"),
            timeout=float(cfg.get("request_timeout_seconds") or 60),
            token_env=str(cfg.get("api_token_env") or "EMP_API_TOKEN"),
        )

    def allowed_roots(self, hub_session_id: str = "") -> list[Path]:
        cfg = self.config()
        root_cfg = self._config_loader()
        values: list[str] = []
        workspace = str(root_cfg.get("workspace") or "").strip()
        if workspace:
            values.append(workspace)
        values.append(str(uploads_root(hub_session_id)))
        configured = cfg.get("allowed_roots")
        if isinstance(configured, list):
            values.extend(str(item) for item in configured if str(item).strip())
        roots: list[Path] = []
        for value in values:
            try:
                resolved = Path(value).expanduser().resolve(strict=True)
            except OSError:
                continue
            if resolved.is_dir() and resolved not in roots:
                roots.append(resolved)
        return roots

    def status(self) -> dict[str, Any]:
        cfg = self.config()
        payload: dict[str, Any] = {
            "enabled": bool(cfg.get("enabled", False)),
            "mode": str(cfg.get("mode") or "auto"),
            "endpoint": str(cfg.get("local_api_base") or "http://127.0.0.1:8000"),
            "reachable": False,
            "compatible": False,
            "capabilities": {},
        }
        if not payload["enabled"]:
            return payload
        try:
            capabilities = self.client().capabilities()
            features = capabilities.get("features") if isinstance(capabilities.get("features"), dict) else {}
            workflows = capabilities.get("workflows") if isinstance(capabilities.get("workflows"), list) else []
            compatible = features.get("path_import") is True and "microbiome_16s" in workflows
            payload.update({"reachable": True, "compatible": compatible, "capabilities": capabilities})
            if not compatible:
                payload["error"] = EmpClientError(
                    "EMP_VERSION_INCOMPATIBLE", "EMP must support path_import and microbiome_16s"
                ).to_dict()
        except EmpClientError as exc:
            payload["error"] = exc.to_dict()
        except ValueError as exc:
            payload["error"] = EmpClientError("EMP_VERSION_INCOMPATIBLE", str(exc)).to_dict()
        return payload

    def scan(
        self,
        path: str,
        *,
        hub_session_id: str,
        max_depth: int = 2,
        experiment_name: str = "",
    ) -> DatasetManifest:
        self._require_enabled()
        manifest = scan_dataset(
            path,
            allowed_roots=self.allowed_roots(hub_session_id),
            max_depth=max_depth,
            experiment_name=experiment_name,
        )
        self.save_manifest(manifest)
        return manifest

    def save_manifest(self, manifest: DatasetManifest) -> None:
        _atomic_json(self.manifests_dir / f"{manifest.manifest_id}.json", manifest.to_dict())

    def get_manifest(self, manifest_id: str) -> DatasetManifest:
        return DatasetManifest.from_dict(_load_json(self.manifests_dir / f"{_safe_name(manifest_id)}.json"))

    def update_manifest_pairing(
        self,
        manifest_id: str,
        *,
        hub_session_id: str,
        assay_path: str,
        metadata_path: str,
    ) -> DatasetManifest:
        manifest = self.get_manifest(manifest_id)
        resolve_allowed_path(manifest.workspace, self.allowed_roots(hub_session_id))
        select_manifest_pairing(manifest, assay_path=assay_path, metadata_path=metadata_path)
        self.save_manifest(manifest)
        return manifest

    def preview_manifest(self, manifest_id: str, hub_session_id: str) -> dict[str, Any]:
        manifest = self.get_manifest(manifest_id)
        data, metadata = self._manifest_inputs(manifest, hub_session_id)
        return self.client().preview_path({
            "data_path": str(data),
            "metadata_path": str(metadata),
            "data_type": "tax",
        })

    def create_16s_plan(
        self,
        manifest_id: str,
        *,
        hub_session_id: str,
        group_var: str,
        taxonomy_level: str = "Genus",
        alpha_metric: str = "shannon",
        language: str = "zh",
    ) -> AnalysisPlan:
        manifest = self.get_manifest(manifest_id)
        if manifest.omics_type != "microbiome_16s":
            raise ValueError("the Phase 1 plan requires a microbiome_16s manifest")
        taxonomy_level = str(taxonomy_level or "Genus").title()
        alpha_metric = str(alpha_metric or "shannon").lower()
        language = "en" if str(language).lower() == "en" else "zh"
        if taxonomy_level not in TAXONOMY_LEVELS:
            raise ValueError("unsupported taxonomy level")
        if alpha_metric not in ALPHA_METRICS:
            raise ValueError("unsupported Alpha diversity metric")
        metadata = manifest.file_for_role("metadata") or manifest.file_for_role("clinical")
        headers = metadata.preview[0] if metadata and metadata.preview else []
        if group_var and group_var not in headers:
            raise ValueError("group variable is not present in metadata")
        if not group_var:
            raise ValueError("group variable is required")
        experiment = _safe_name(manifest.experiment_name)
        steps = [
            PlanStep("validate", "emp.workflow.validate", {"tax_sep": ";"}),
            PlanStep(
                "taxonomy_prepare",
                "emp.prepare.taxonomy",
                {"collapse_level": taxonomy_level, "drop_unassigned": False, "keep_top_n": 40, "tax_sep": ";"},
                ["validate"],
            ),
            PlanStep("alpha", "emp.analyze.alpha", {"method": alpha_metric, "source": "current"}, ["taxonomy_prepare"]),
            PlanStep(
                "alpha_plot",
                "emp.visualize.alpha",
                {"metric": alpha_metric, "source": "current", "group": group_var, "width": 8, "height": 6},
                ["alpha"],
            ),
        ]
        plan = AnalysisPlan(
            plan_id=new_id("plan"),
            title=f"16S {group_var} comparison",
            dataset_manifest_id=manifest.manifest_id,
            dataset_fingerprint=manifest.fingerprint(),
            hub_session_id=hub_session_id,
            emp_mode="local-api",
            workflow="microbiome_16s",
            experiment_name=experiment,
            steps=steps,
            output={
                "language": language,
                "include_tables": True,
                "include_plots": True,
                "include_bundle": False,
                "generate_report": True,
            },
        )
        self.validate_plan(plan)
        _atomic_json(self.plans_dir / f"{plan.plan_id}.json", plan.to_dict())
        return plan

    def validate_plan(self, plan: AnalysisPlan) -> None:
        if plan.emp_mode not in {"local-api", "remote-api", "r-direct"}:
            raise ValueError("unsupported EMP mode")
        if plan.workflow not in {"microbiome_16s", "transcriptomics", "metabolomics", "metagenomics", "clinical"}:
            raise ValueError("unsupported EMP workflow")
        if not plan.steps:
            raise ValueError("analysis plan has no steps")
        ids = {step.id for step in plan.steps}
        if len(ids) != len(plan.steps):
            raise ValueError("analysis step identifiers must be unique")
        for step in plan.steps:
            if step.tool not in PLAN_TOOLS:
                raise ValueError(f"unregistered EMP tool: {step.tool}")
            if any(dependency not in ids for dependency in step.depends_on):
                raise ValueError(f"unknown dependency for step {step.id}")
        visited: set[str] = set()
        active: set[str] = set()
        by_id = {step.id: step for step in plan.steps}

        def visit(step_id: str) -> None:
            if step_id in active:
                raise ValueError("analysis plan dependency cycle detected")
            if step_id in visited:
                return
            active.add(step_id)
            for dependency in by_id[step_id].depends_on:
                visit(dependency)
            active.remove(step_id)
            visited.add(step_id)

        for step_id in ids:
            visit(step_id)

    def save_plan(self, plan: AnalysisPlan) -> AnalysisPlan:
        """Persist a plan after strict local tool/DAG validation."""
        self.validate_plan(plan)
        self._validate_plan_dataset(plan)
        _atomic_json(self.plans_dir / f"{plan.plan_id}.json", plan.to_dict())
        return plan

    def get_plan(self, plan_id: str) -> AnalysisPlan:
        return AnalysisPlan.from_dict(_load_json(self.plans_dir / f"{_safe_name(plan_id)}.json"))

    def confirm_plan(self, plan_id: str) -> AnalysisPlan:
        with self._lock:
            plan = self.get_plan(plan_id)
            self.validate_plan(plan)
            self._validate_plan_dataset(plan)
            plan.confirmed_at = utc_timestamp()
            _atomic_json(self.plans_dir / f"{plan.plan_id}.json", plan.to_dict())
            return plan

    def run_plan(self, plan_id: str) -> EmpJob:
        with self._lock:
            plan = self.get_plan(plan_id)
            self.validate_plan(plan)
            self._validate_plan_dataset(plan)
            if plan.requires_confirmation and plan.confirmed_at is None:
                raise ValueError("analysis plan must be confirmed before running")
            fingerprint = plan.fingerprint()
            for job in self.list_jobs(hub_session_id=plan.hub_session_id):
                if job.fingerprint == fingerprint and job.status in {"pending", "running", "done"}:
                    return job
            job = EmpJob(
                job_id=new_id("empjob"),
                plan_id=plan.plan_id,
                hub_session_id=plan.hub_session_id,
                fingerprint=fingerprint,
                message="Queued",
                step_states={step.id: "pending" for step in plan.steps},
            )
            self._save_job(job)
            thread = threading.Thread(target=self._execute_plan, args=(job.job_id,), daemon=True)
            self._threads[job.job_id] = thread
            thread.start()
            return job

    def retry_job(self, job_id: str, *, hub_session_id: str) -> EmpJob:
        from .emp_planning import retry_closure

        with self._lock:
            previous = self.get_job(job_id, hub_session_id=hub_session_id)
            if previous.status != "error":
                raise ValueError("only failed EMP jobs can be retried")
            plan = self.get_plan(previous.plan_id)
            failed_step = previous.step_id or (plan.steps[0].id if plan.steps else "")
            selected = retry_closure(plan, [failed_step]) if failed_step else [step.id for step in plan.steps]
            job = EmpJob(
                job_id=new_id("empjob"),
                plan_id=plan.plan_id,
                hub_session_id=hub_session_id,
                fingerprint=f"{plan.fingerprint()}:retry:{new_id('attempt')}",
                message="Retry queued",
                emp_session_id=previous.emp_session_id,
                artifact_ids=list(previous.artifact_ids),
                retry_step_ids=selected,
                step_states={
                    step.id: ("pending" if step.id in selected else previous.step_states.get(step.id, "done"))
                    for step in plan.steps
                },
            )
            self._save_job(job)
            thread = threading.Thread(target=self._execute_plan, args=(job.job_id,), daemon=True)
            self._threads[job.job_id] = thread
            thread.start()
            return job

    def _validate_plan_dataset(self, plan: AnalysisPlan) -> DatasetManifest:
        manifest = self.get_manifest(plan.dataset_manifest_id)
        if not plan.dataset_fingerprint or manifest.fingerprint() != plan.dataset_fingerprint:
            raise ValueError("dataset manifest changed after the analysis plan was created")
        for item in manifest.files:
            path = resolve_allowed_path(Path(manifest.workspace) / item.path, self.allowed_roots(plan.hub_session_id))
            stat = path.stat()
            if stat.st_size != item.size or abs(stat.st_mtime - item.mtime) > 0.01:
                raise ValueError(f"dataset file changed after scanning: {item.path}")
            if item.sha256:
                digest = hashlib.sha256()
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                if digest.hexdigest() != item.sha256:
                    raise ValueError(f"dataset checksum changed after scanning: {item.path}")
        return manifest

    def _execute_plan(self, job_id: str) -> None:
        try:
            job = self.get_job(job_id)
            plan = self.get_plan(job.plan_id)
            manifest = self.get_manifest(plan.dataset_manifest_id)
            client = self.client()
            self._update_job(job, status="running", progress=3, message="Checking EMP capabilities")
            capabilities = client.capabilities()
            self._check_cancel(job)

            if plan.emp_mode != "local-api":
                raise EmpClientError("EMP_VERSION_INCOMPATIBLE", f"{plan.emp_mode} plans use their dedicated adapter")
            imported: dict[str, Any] = {"reused_session": bool(job.emp_session_id)}
            emp_session_id = job.emp_session_id
            if not emp_session_id:
                data, metadata = self._manifest_inputs(manifest, plan.hub_session_id)
                self._update_job(job, progress=10, message="Previewing input data", step_id="import")
                data_type = "tax" if plan.workflow == "microbiome_16s" else "normal"
                client.preview_path({"data_path": str(data), "metadata_path": str(metadata), "data_type": data_type})
                self._check_cancel(job)
                imported = client.import_path({
                    "data_path": str(data),
                    "metadata_path": str(metadata),
                    "experiment_name": plan.experiment_name,
                    "data_type": data_type,
                    "assay_name": "counts",
                    "start_level": "Species",
                    "tax_sep": ";",
                })
                emp_session_id = str(imported.get("session_id") or "")
                if not emp_session_id:
                    raise EmpClientError("EMP_RESULT_MISSING", "session_id missing after import")
                job.emp_session_id = emp_session_id
                self._save_mapping(plan, emp_session_id)

            steps = [step for step in plan.steps if not job.retry_step_ids or step.id in job.retry_step_ids]
            step_count = max(1, len(steps))
            outputs: dict[str, dict[str, Any]] = {"capabilities": capabilities, "import": imported}
            for step_index, step in enumerate(steps):
                self._check_cancel(job)
                step_progress = 25 + int((step_index / step_count) * 65)
                self._update_job(job, progress=step_progress, message=f"Running {step.id}", step_id=step.id)
                job.step_states[step.id] = "running"
                self._save_job(job)
                params = {
                    **step.params,
                    "_workflow": plan.workflow,
                    "session_id": emp_session_id,
                    "experiment": plan.experiment_name,
                }
                result = client.run_step(step.tool, params)
                if step.id == "validate":
                    checks = (result.get("validation") or {}).get("checks") or {}
                    if checks and not all(bool(value) for value in checks.values()):
                        raise EmpClientError("EMP_DATA_VALIDATION_FAILED", "one or more EMP validation checks failed", details=result)
                outputs[step.id] = result
                if step.tool != "emp.visualize.alpha":
                    artifact = self._write_json_artifact(job, step.id, f"{_safe_name(step.id)}.json", result)
                    job.artifact_ids.append(artifact.artifact_id)
                if step.tool == "emp.visualize.alpha":
                    self._save_plot_artifacts(job, plan, result, client)
                job.step_states[step.id] = "done"
                self._save_job(job)

            if plan.output.get("generate_report", True):
                report = self._write_report(job, plan, manifest, outputs)
                job.artifact_ids.append(report.artifact_id)
            self._update_job(job, status="done", progress=100, message="Analysis completed", step_id="")
        except EmpClientError as exc:
            self._fail_job(job_id, exc.to_dict())
        except Exception as exc:  # noqa: BLE001
            error = EmpClientError("EMP_JOB_FAILED", str(exc)).to_dict()
            self._fail_job(job_id, error)
        finally:
            self._threads.pop(job_id, None)

    def _manifest_inputs(self, manifest: DatasetManifest, hub_session_id: str) -> tuple[Path, Path]:
        assay = manifest.file_for_role("assay")
        metadata = manifest.file_for_role("metadata") or manifest.file_for_role("clinical")
        if assay is None or metadata is None:
            raise DiscoveryError("manifest requires an assay and metadata file")
        workspace = resolve_allowed_path(manifest.workspace, self.allowed_roots(hub_session_id))
        data = resolve_allowed_path(workspace / assay.path, [workspace])
        meta = resolve_allowed_path(workspace / metadata.path, [workspace])
        if not data.is_file() or not meta.is_file():
            raise DiscoveryError("manifest input is not a regular file")
        return data, meta

    def _save_mapping(self, plan: AnalysisPlan, emp_session_id: str) -> EmpSessionMapping:
        mapping = EmpSessionMapping(
            mapping_id=new_id("mapping"),
            agent_hub_session_id=plan.hub_session_id,
            emp_endpoint_id="local-default",
            emp_session_id=emp_session_id,
            dataset_manifest_id=plan.dataset_manifest_id,
            analysis_plan_id=plan.plan_id,
        )
        _atomic_json(self.mappings_dir / f"{mapping.mapping_id}.json", mapping.to_dict())
        return mapping

    def _artifact_root(self) -> Path:
        value = str(self.config().get("artifact_root") or "").strip()
        root = Path(value).expanduser() if value else self.default_artifact_dir
        root.mkdir(parents=True, exist_ok=True)
        return root.resolve()

    def artifact_root(self) -> Path:
        """Return the configured artifact root for validated file serving."""
        return self._artifact_root()

    def _artifact_path(self, job: EmpJob, filename: str) -> Path:
        root = self._artifact_root()
        destination = (root / _safe_name(job.hub_session_id, "session") / job.job_id / Path(filename).name).resolve()
        if os.path.commonpath([str(root), str(destination)]) != str(root):
            raise ValueError("invalid artifact destination")
        destination.parent.mkdir(parents=True, exist_ok=True)
        return destination

    def _register_artifact(self, job: EmpJob, step_id: str, path: Path, kind: str, mime_type: str) -> EmpArtifact:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        artifact = EmpArtifact(
            artifact_id=new_id("artifact"),
            kind=kind,
            name=path.name,
            mime_type=mime_type,
            hub_session_id=job.hub_session_id,
            emp_session_id=job.emp_session_id,
            job_id=job.job_id,
            analysis_step_id=step_id,
            local_path=str(path),
            sha256=digest,
            size=path.stat().st_size,
        )
        _atomic_json(self.artifact_index_dir / f"{artifact.artifact_id}.json", artifact.to_dict())
        return artifact

    def _write_json_artifact(self, job: EmpJob, step_id: str, name: str, payload: dict[str, Any]) -> EmpArtifact:
        path = self._artifact_path(job, name)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return self._register_artifact(job, step_id, path, "table", "application/json")

    def _save_plot_artifacts(self, job: EmpJob, plan: AnalysisPlan, result: dict[str, Any], client: EmpClient) -> None:
        encoded = str(result.get("plot") or "")
        if encoded:
            try:
                raw = base64.b64decode(encoded, validate=True)
            except ValueError as exc:
                raise EmpClientError("EMP_RESULT_MISSING", "invalid plot payload") from exc
            if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
                raise EmpClientError("EMP_RESULT_MISSING", "EMP plot is not a PNG")
            png_path = self._artifact_path(job, "alpha_diversity.png")
            png_path.write_bytes(raw)
            artifact = self._register_artifact(job, "alpha_plot", png_path, "plot", "image/png")
            job.artifact_ids.append(artifact.artifact_id)
        pdf_name = Path(str(result.get("pdf_name") or "")).name
        if result.get("pdf_available") and pdf_name:
            path = self._artifact_path(job, pdf_name)
            endpoint = "/api/download/plot/{}/{}/{}".format(
                quote(job.emp_session_id, safe=""),
                quote(plan.experiment_name, safe=""),
                quote(pdf_name, safe=""),
            )
            client.download_artifact(endpoint, path)
            artifact = self._register_artifact(job, "alpha_plot", path, "plot", "application/pdf")
            job.artifact_ids.append(artifact.artifact_id)

    def _write_report(
        self,
        job: EmpJob,
        plan: AnalysisPlan,
        manifest: DatasetManifest,
        outputs: dict[str, dict[str, Any]],
    ) -> EmpArtifact:
        language = str(plan.output.get("language") or "zh")
        alpha = outputs.get("alpha") or {}
        capabilities = outputs.get("capabilities") or {}
        taxonomy = next((step.params.get("collapse_level") for step in plan.steps if step.id == "taxonomy_prepare"), "")
        alpha_metric = next((step.params.get("method") for step in plan.steps if step.id == "alpha"), "")
        sources = []
        for artifact_id in job.artifact_ids:
            try:
                item = self.get_artifact(artifact_id)
            except (TypeError, ValueError):
                continue
            sources.append(f"- `{item.artifact_id}` · `{item.name}` · SHA-256 `{item.sha256}`")
        if language == "en":
            lines = [
                f"# {plan.title}", "", "## Computation summary", "",
                f"- EMP session: `{job.emp_session_id}`",
                f"- EMP/API version: `{capabilities.get('emp_version') or 'unknown'}` / `{capabilities.get('api_version') or 'unknown'}`",
                f"- Workflow: `{plan.workflow}`",
                f"- Experiment: `{plan.experiment_name}`",
                f"- Input manifest: `{manifest.manifest_id}`",
                f"- Taxonomy level: `{taxonomy}`",
                f"- Alpha metric: `{alpha_metric}`",
                f"- Alpha rows: {int(alpha.get('n_rows') or 0)}",
                "", "## Source artifacts", "", *(sources or ["- No source artifact was registered."]),
                "", "## Interpretation boundary", "",
                "This file records computed outputs and provenance. It does not alter or replace EMP statistical results.",
            ]
        else:
            lines = [
                f"# {plan.title}", "", "## 计算摘要", "",
                f"- EMP session：`{job.emp_session_id}`",
                f"- EMP/API 版本：`{capabilities.get('emp_version') or 'unknown'}` / `{capabilities.get('api_version') or 'unknown'}`",
                f"- 工作流：`{plan.workflow}`",
                f"- 实验：`{plan.experiment_name}`",
                f"- 输入清单：`{manifest.manifest_id}`",
                f"- Taxonomy 层级：`{taxonomy}`",
                f"- Alpha 指标：`{alpha_metric}`",
                f"- Alpha 结果行数：{int(alpha.get('n_rows') or 0)}",
                "", "## 来源产物", "", *(sources or ["- 未登记来源产物。"]),
                "", "## 解释边界", "",
                "本文件只记录计算输出与来源，不修改或替代 EMP 的统计结果。",
            ]
        path = self._artifact_path(job, "report.md")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return self._register_artifact(job, "report", path, "report", "text/markdown")

    def _check_cancel(self, job: EmpJob) -> None:
        current = self.get_job(job.job_id)
        if current.cancel_requested:
            current.status = "cancelled"
            current.progress = min(current.progress, 99)
            current.message = "Cancelled"
            current.updated_at = utc_timestamp()
            self._save_job(current)
            raise EmpClientError("EMP_CANCELLED")

    def cancel_job(self, job_id: str, *, hub_session_id: str = "") -> EmpJob:
        with self._lock:
            job = self.get_job(job_id, hub_session_id=hub_session_id)
            if job.status in TERMINAL_JOB_STATES:
                return job
            job.cancel_requested = True
            job.message = "Cancellation requested"
            job.updated_at = utc_timestamp()
            self._save_job(job)
            return job

    def _update_job(self, job: EmpJob, **changes: Any) -> None:
        for key, value in changes.items():
            setattr(job, key, value)
        job.updated_at = utc_timestamp()
        self._save_job(job)

    def _save_job(self, job: EmpJob) -> None:
        _atomic_json(self.jobs_dir / f"{job.job_id}.json", job.to_dict())

    def _fail_job(self, job_id: str, error: dict[str, Any]) -> None:
        try:
            job = self.get_job(job_id)
        except ValueError:
            return
        if str(error.get("error_code")) == "EMP_CANCELLED":
            job.status = "cancelled"
            job.message = str(error.get("user_message_en") or "Cancelled")
        else:
            job.status = "error"
            job.message = str(error.get("user_message_en") or error.get("message") or "EMP job failed")
            if job.step_id:
                job.step_states[job.step_id] = "error"
        job.error = error
        job.updated_at = utc_timestamp()
        self._save_job(job)

    def get_job(self, job_id: str, *, hub_session_id: str = "") -> EmpJob:
        job = EmpJob.from_dict(_load_json(self.jobs_dir / f"{_safe_name(job_id)}.json"))
        if hub_session_id and job.hub_session_id != hub_session_id:
            raise ValueError("EMP job does not belong to this session")
        return job

    def list_jobs(self, *, hub_session_id: str = "") -> list[EmpJob]:
        jobs: list[EmpJob] = []
        for path in self.jobs_dir.glob("*.json"):
            try:
                job = EmpJob.from_dict(_load_json(path))
            except ValueError:
                continue
            if not hub_session_id or job.hub_session_id == hub_session_id:
                jobs.append(job)
        return sorted(jobs, key=lambda item: item.updated_at, reverse=True)

    def get_artifact(self, artifact_id: str, *, hub_session_id: str = "") -> EmpArtifact:
        artifact = EmpArtifact.from_dict(_load_json(self.artifact_index_dir / f"{_safe_name(artifact_id)}.json"))
        if hub_session_id and artifact.hub_session_id != hub_session_id:
            raise ValueError("EMP artifact does not belong to this session")
        return artifact

    def list_artifacts(self, *, hub_session_id: str = "", job_id: str = "") -> list[EmpArtifact]:
        artifacts: list[EmpArtifact] = []
        for path in self.artifact_index_dir.glob("*.json"):
            try:
                item = EmpArtifact.from_dict(_load_json(path))
            except (TypeError, ValueError):
                continue
            if hub_session_id and item.hub_session_id != hub_session_id:
                continue
            if job_id and item.job_id != job_id:
                continue
            artifacts.append(item)
        return sorted(artifacts, key=lambda item: item.created_at)

    def artifact_file(self, artifact_id: str, *, hub_session_id: str = "") -> tuple[EmpArtifact, Path]:
        artifact = self.get_artifact(artifact_id, hub_session_id=hub_session_id)
        path = Path(artifact.local_path).resolve(strict=True)
        root = self._artifact_root()
        if os.path.commonpath([str(root), str(path)]) != str(root) or not path.is_file():
            raise ValueError("artifact path is invalid")
        return artifact, path

    def _recover_interrupted_jobs(self) -> None:
        for path in self.jobs_dir.glob("*.json"):
            try:
                job = EmpJob.from_dict(_load_json(path))
            except ValueError:
                continue
            if job.status in {"pending", "running"}:
                job.status = "error"
                job.error = EmpClientError(
                    "EMP_JOB_FAILED",
                    "Agent Hub restarted before this local orchestration finished; confirm and retry the plan.",
                    retryable=True,
                ).to_dict()
                job.message = job.error["message"]
                job.updated_at = utc_timestamp()
                self._save_job(job)


_SERVICE: Optional[EmpService] = None
_SERVICE_LOCK = threading.Lock()


def get_emp_service() -> EmpService:
    global _SERVICE
    if _SERVICE is None:
        with _SERVICE_LOCK:
            if _SERVICE is None:
                _SERVICE = EmpService()
    return _SERVICE
