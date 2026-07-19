"""Persistent multi-omics EMP projects and provenance-first reports."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


PROJECT_VERSION = "1.0"


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _safe_id(value: str) -> str:
    value = str(value or "")
    if not value or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in value):
        raise ValueError("invalid project identifier")
    return value


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


@dataclass(frozen=True)
class ProjectDataset:
    manifest_id: str
    manifest_fingerprint: str
    omics_type: str
    experiment_name: str
    sample_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProjectSession:
    endpoint_id: str
    emp_session_id: str
    manifest_id: str
    hub_session_id: str


@dataclass
class EmpProject:
    project_id: str
    name: str
    hub_session_id: str
    datasets: list[ProjectDataset] = field(default_factory=list)
    sessions: list[ProjectSession] = field(default_factory=list)
    artifact_ids: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    project_version: str = PROJECT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EmpProject":
        if str(data.get("project_version") or PROJECT_VERSION) != PROJECT_VERSION:
            raise ValueError("unsupported project version")
        return cls(
            project_id=_safe_id(str(data.get("project_id") or "")),
            name=str(data.get("name") or "Untitled project"),
            hub_session_id=str(data.get("hub_session_id") or ""),
            datasets=[ProjectDataset(**item) for item in data.get("datasets") or []],
            sessions=[ProjectSession(**item) for item in data.get("sessions") or []],
            artifact_ids=[str(value) for value in data.get("artifact_ids") or []],
            created_at=float(data.get("created_at") or time.time()),
            updated_at=float(data.get("updated_at") or time.time()),
        )


class EmpProjectStore:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def create(self, name: str, hub_session_id: str) -> EmpProject:
        if not str(hub_session_id or "").strip():
            raise ValueError("hub_session_id is required")
        project = EmpProject(_id("empproj"), str(name or "EMP project").strip(), hub_session_id)
        self.save(project)
        return project

    def save(self, project: EmpProject) -> None:
        project.updated_at = time.time()
        with self._lock:
            _atomic_json(self.root / f"{_safe_id(project.project_id)}.json", project.to_dict())

    def get(self, project_id: str, *, hub_session_id: str) -> EmpProject:
        path = self.root / f"{_safe_id(project_id)}.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("EMP project not found") from exc
        project = EmpProject.from_dict(data)
        if project.hub_session_id != hub_session_id:
            raise ValueError("EMP project does not belong to this session")
        return project

    def list(self, *, hub_session_id: str) -> list[EmpProject]:
        values: list[EmpProject] = []
        for path in self.root.glob("*.json"):
            try:
                project = EmpProject.from_dict(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if project.hub_session_id == hub_session_id:
                values.append(project)
        return sorted(values, key=lambda item: item.updated_at, reverse=True)

    def add_dataset(self, project: EmpProject, dataset: ProjectDataset) -> EmpProject:
        with self._lock:
            if any(item.manifest_id == dataset.manifest_id for item in project.datasets):
                return project
            project.datasets.append(dataset)
            self.save(project)
            return project

    def bind_session(self, project: EmpProject, binding: ProjectSession) -> EmpProject:
        with self._lock:
            key = (binding.endpoint_id, binding.emp_session_id)
            if not any((item.endpoint_id, item.emp_session_id) == key for item in project.sessions):
                project.sessions.append(binding)
                self.save(project)
            return project


def sample_map(datasets: Iterable[ProjectDataset], *, minimum_shared: int = 2) -> dict[str, Any]:
    values = list(datasets)
    if len(values) < 2:
        raise ValueError("joint analysis requires at least two datasets")
    sets = [set(item.sample_ids) for item in values]
    if any(not value for value in sets):
        raise ValueError("every dataset requires bounded sample identifiers")
    shared = set.intersection(*sets)
    if len(shared) < minimum_shared:
        raise ValueError(f"only {len(shared)} samples are shared across datasets")
    return {
        "dataset_count": len(values),
        "shared_count": len(shared),
        "shared_sample_hashes": [hashlib.sha256(value.encode("utf-8")).hexdigest() for value in sorted(shared)],
        "per_dataset": {
            item.manifest_id: {"samples": len(current), "missing_from_shared": len(current - shared)}
            for item, current in zip(values, sets)
        },
    }


def render_reproducible_report(
    project: EmpProject,
    *,
    runs: Iterable[dict[str, Any]],
    artifacts: Iterable[dict[str, Any]],
    language: str = "zh",
) -> str:
    runs = list(runs)
    artifacts = list(artifacts)
    zh = language != "en"
    title = "多组学联合分析报告" if zh else "Multi-omics joint analysis report"
    boundary = (
        "以下解释与 EMP 原始计算结果分开保存；相关性不代表因果关系。"
        if zh else
        "Interpretation is stored separately from EMP computation; association does not imply causation."
    )
    lines = [f"# {project.name} - {title}", "", boundary, "", "## Provenance", ""]
    lines.extend(
        f"- `{item.omics_type}` / `{item.experiment_name}`: manifest `{item.manifest_id}`, fingerprint `{item.manifest_fingerprint}`"
        for item in project.datasets
    )
    lines.extend(["", "## Runs", ""])
    for run in runs:
        lines.append(
            f"- `{run.get('run_id', 'unknown')}`: `{run.get('workflow', 'unknown')}` / "
            f"`{run.get('status', 'unknown')}` / EMP `{run.get('emp_version', 'unknown')}` / R `{run.get('r_version', 'unknown')}`"
        )
    lines.extend(["", "## Source artifacts", ""])
    for artifact in artifacts:
        lines.append(
            f"- `{artifact.get('artifact_id', 'unknown')}` `{artifact.get('name', 'artifact')}` "
            f"SHA-256 `{artifact.get('sha256', '')}` from step `{artifact.get('analysis_step_id', '')}`"
        )
    lines.extend(["", "## Limitations", "", "- " + (
        "联合结论必须回到各组学表格、图形、参数和样本匹配记录进行复核。"
        if zh else
        "Joint conclusions must be checked against each omics table, figure, parameter set, and sample map."
    )])
    return "\n".join(lines) + "\n"
