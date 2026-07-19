"""Versioned data contracts for the EasyMultiProfiler integration."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional


MANIFEST_VERSION = "1.0"
PLAN_VERSION = "1.0"
MODEL_VERSION = "1.0"


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def utc_timestamp() -> float:
    return time.time()


def _text(data: dict[str, Any], key: str, *, required: bool = False) -> str:
    value = str(data.get(key) or "").strip()
    if required and not value:
        raise ValueError(f"{key} is required")
    return value


def _list(data: dict[str, Any], key: str) -> list[Any]:
    value = data.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value


@dataclass
class DatasetFile:
    role: str
    path: str
    size: int
    mtime: float
    sha256: str = ""
    delimiter: str = ""
    rows: Optional[int] = None
    columns: Optional[int] = None
    preview: list[list[str]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DatasetFile":
        if not isinstance(data, dict):
            raise ValueError("dataset file must be an object")
        role = _text(data, "role", required=True)
        if role not in {"assay", "metadata", "taxonomy", "mapping", "clinical", "bam", "peak", "unknown"}:
            raise ValueError(f"unsupported dataset role: {role}")
        return cls(
            role=role,
            path=_text(data, "path", required=True),
            size=max(0, int(data.get("size") or 0)),
            mtime=float(data.get("mtime") or 0),
            sha256=_text(data, "sha256"),
            delimiter=_text(data, "delimiter"),
            rows=int(data["rows"]) if data.get("rows") is not None else None,
            columns=int(data["columns"]) if data.get("columns") is not None else None,
            preview=[list(map(str, row)) for row in _list(data, "preview") if isinstance(row, list)],
        )


@dataclass
class DatasetManifest:
    manifest_id: str
    workspace: str
    omics_type: str
    experiment_name: str
    files: list[DatasetFile]
    orientation: str = "unknown"
    sample_id_column: str = ""
    sample_overlap: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=utc_timestamp)
    manifest_version: str = MANIFEST_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DatasetManifest":
        if not isinstance(data, dict):
            raise ValueError("manifest must be an object")
        version = _text(data, "manifest_version") or MANIFEST_VERSION
        if version != MANIFEST_VERSION:
            raise ValueError(f"unsupported manifest_version: {version}")
        files = [DatasetFile.from_dict(item) for item in _list(data, "files")]
        if not files:
            raise ValueError("manifest files cannot be empty")
        return cls(
            manifest_id=_text(data, "manifest_id", required=True),
            workspace=_text(data, "workspace", required=True),
            omics_type=_text(data, "omics_type") or "unknown",
            experiment_name=_text(data, "experiment_name") or "study",
            files=files,
            orientation=_text(data, "orientation") or "unknown",
            sample_id_column=_text(data, "sample_id_column"),
            sample_overlap=dict(data.get("sample_overlap") or {}),
            warnings=[str(item) for item in _list(data, "warnings")],
            created_at=float(data.get("created_at") or utc_timestamp()),
            manifest_version=version,
        )

    def file_for_role(self, role: str) -> Optional[DatasetFile]:
        return next((item for item in self.files if item.role == role), None)

    def fingerprint(self) -> str:
        stable = self.to_dict()
        stable.pop("created_at", None)
        for item in stable.get("files", []):
            item.pop("preview", None)
        payload = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class PlanStep:
    id: str
    tool: str
    params: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlanStep":
        if not isinstance(data, dict):
            raise ValueError("plan step must be an object")
        return cls(
            id=_text(data, "id", required=True),
            tool=_text(data, "tool", required=True),
            params=dict(data.get("params") or {}),
            depends_on=[str(value) for value in _list(data, "depends_on")],
        )


@dataclass
class AnalysisPlan:
    plan_id: str
    title: str
    dataset_manifest_id: str
    dataset_fingerprint: str
    hub_session_id: str
    emp_mode: str
    workflow: str
    experiment_name: str
    steps: list[PlanStep]
    output: dict[str, Any]
    requires_confirmation: bool = True
    confirmed_at: Optional[float] = None
    created_at: float = field(default_factory=utc_timestamp)
    plan_version: str = PLAN_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AnalysisPlan":
        if not isinstance(data, dict):
            raise ValueError("plan must be an object")
        version = _text(data, "plan_version") or PLAN_VERSION
        if version != PLAN_VERSION:
            raise ValueError(f"unsupported plan_version: {version}")
        return cls(
            plan_id=_text(data, "plan_id", required=True),
            title=_text(data, "title") or "16S analysis",
            dataset_manifest_id=_text(data, "dataset_manifest_id", required=True),
            dataset_fingerprint=_text(data, "dataset_fingerprint"),
            hub_session_id=_text(data, "hub_session_id", required=True),
            emp_mode=_text(data, "emp_mode") or "local-api",
            workflow=_text(data, "workflow", required=True),
            experiment_name=_text(data, "experiment_name", required=True),
            steps=[PlanStep.from_dict(item) for item in _list(data, "steps")],
            output=dict(data.get("output") or {}),
            requires_confirmation=bool(data.get("requires_confirmation", True)),
            confirmed_at=float(data["confirmed_at"]) if data.get("confirmed_at") is not None else None,
            created_at=float(data.get("created_at") or utc_timestamp()),
            plan_version=version,
        )

    def fingerprint(self) -> str:
        stable = self.to_dict()
        for key in ("plan_id", "created_at", "confirmed_at"):
            stable.pop(key, None)
        payload = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class EmpJob:
    job_id: str
    plan_id: str
    hub_session_id: str
    fingerprint: str
    status: str = "pending"
    progress: int = 0
    message: str = ""
    step_id: str = ""
    emp_session_id: str = ""
    error: dict[str, Any] = field(default_factory=dict)
    artifact_ids: list[str] = field(default_factory=list)
    cancel_requested: bool = False
    created_at: float = field(default_factory=utc_timestamp)
    updated_at: float = field(default_factory=utc_timestamp)
    model_version: str = MODEL_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EmpJob":
        if not isinstance(data, dict):
            raise ValueError("job must be an object")
        values = dict(data)
        values["artifact_ids"] = [str(item) for item in values.get("artifact_ids") or []]
        values["error"] = dict(values.get("error") or {})
        return cls(**{key: values[key] for key in cls.__dataclass_fields__ if key in values})


@dataclass
class EmpArtifact:
    artifact_id: str
    kind: str
    name: str
    mime_type: str
    hub_session_id: str
    emp_session_id: str
    job_id: str
    analysis_step_id: str
    local_path: str
    sha256: str
    size: int
    created_at: float = field(default_factory=utc_timestamp)
    source: str = "emp"
    model_version: str = MODEL_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EmpArtifact":
        if not isinstance(data, dict):
            raise ValueError("artifact must be an object")
        return cls(**{key: data[key] for key in cls.__dataclass_fields__ if key in data})


@dataclass
class EmpSessionMapping:
    mapping_id: str
    agent_hub_session_id: str
    emp_endpoint_id: str
    emp_session_id: str
    dataset_manifest_id: str
    analysis_plan_id: str
    created_at: float = field(default_factory=utc_timestamp)
    last_seen_at: float = field(default_factory=utc_timestamp)
    emp_project_id: str = ""
    model_version: str = MODEL_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EmpSessionMapping":
        if not isinstance(data, dict):
            raise ValueError("mapping must be an object")
        return cls(**{key: data[key] for key in cls.__dataclass_fields__ if key in data})
