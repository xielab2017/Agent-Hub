"""Typed EMP tool registry exposed to agents and the Hub API."""

from __future__ import annotations

from typing import Any, Optional
from urllib.parse import quote

from .emp_service import EmpService, get_emp_service


def _object(properties: dict[str, Any], required: Optional[list[str]] = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


EMP_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "emp.status": _object({}),
    "emp.dataset.scan": _object(
        {
            "path": {"type": "string"},
            "hub_session_id": {"type": "string"},
            "max_depth": {"type": "integer", "minimum": 0, "maximum": 10},
            "experiment_name": {"type": "string"},
        },
        ["path", "hub_session_id"],
    ),
    "emp.dataset.preview": _object(
        {"manifest_id": {"type": "string"}, "hub_session_id": {"type": "string"}},
        ["manifest_id", "hub_session_id"],
    ),
    "emp.session.create": _object({}),
    "emp.dataset.import": _object(
        {"manifest_id": {"type": "string"}, "hub_session_id": {"type": "string"}},
        ["manifest_id", "hub_session_id"],
    ),
    "emp.workflow.list": _object({}),
    "emp.workflow.validate": _object({"plan_id": {"type": "string"}}, ["plan_id"]),
    "emp.analysis.plan": _object(
        {
            "manifest_id": {"type": "string"},
            "hub_session_id": {"type": "string"},
            "group_var": {"type": "string"},
            "taxonomy_level": {"type": "string", "enum": ["Kingdom", "Phylum", "Class", "Order", "Family", "Genus", "Species"]},
            "alpha_metric": {"type": "string", "enum": ["shannon", "simpson", "observed", "chao1"]},
            "language": {"type": "string", "enum": ["zh", "en"]},
        },
        ["manifest_id", "hub_session_id", "group_var"],
    ),
    "emp.analysis.run": _object({"plan_id": {"type": "string"}}, ["plan_id"]),
    "emp.job.status": _object(
        {"job_id": {"type": "string"}, "hub_session_id": {"type": "string"}},
        ["job_id", "hub_session_id"],
    ),
    "emp.job.cancel": _object(
        {"job_id": {"type": "string"}, "hub_session_id": {"type": "string"}},
        ["job_id", "hub_session_id"],
    ),
    "emp.result.list": _object(
        {"hub_session_id": {"type": "string"}, "job_id": {"type": "string"}}
    ),
    "emp.result.download": _object(
        {"artifact_id": {"type": "string"}, "hub_session_id": {"type": "string"}},
        ["artifact_id", "hub_session_id"],
    ),
    "emp.report.generate": _object(
        {"job_id": {"type": "string"}, "hub_session_id": {"type": "string"}},
        ["job_id", "hub_session_id"],
    ),
}


def tool_catalog() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "description": f"Constrained EasyMultiProfiler tool: {name}",
            "inputSchema": schema,
        }
        for name, schema in EMP_TOOL_SCHEMAS.items()
    ]


def invoke(name: str, arguments: dict[str, Any], *, service: Optional[EmpService] = None) -> dict[str, Any]:
    if name not in EMP_TOOL_SCHEMAS:
        raise ValueError(f"unregistered EMP tool: {name}")
    args = dict(arguments or {})
    svc = service or get_emp_service()
    if name == "emp.status":
        return svc.status()
    if name == "emp.dataset.scan":
        manifest = svc.scan(
            str(args.get("path") or ""),
            hub_session_id=str(args.get("hub_session_id") or ""),
            max_depth=int(args.get("max_depth") or 2),
            experiment_name=str(args.get("experiment_name") or ""),
        ).to_dict()
        for item in manifest.get("files", []):
            item.pop("preview", None)
        return manifest
    if name in {"emp.dataset.preview", "emp.dataset.import"}:
        return svc.preview_manifest(
            str(args.get("manifest_id") or ""), str(args.get("hub_session_id") or "")
        )
    if name == "emp.session.create":
        return {"session_id": svc.client().create_session()}
    if name == "emp.workflow.list":
        capabilities = svc.client().capabilities()
        return {"workflows": capabilities.get("workflows") or [], "capabilities": capabilities}
    if name == "emp.workflow.validate":
        plan = svc.get_plan(str(args.get("plan_id") or ""))
        svc.validate_plan(plan)
        return {"valid": True, "plan": plan.to_dict()}
    if name == "emp.analysis.plan":
        return svc.create_16s_plan(
            str(args.get("manifest_id") or ""),
            hub_session_id=str(args.get("hub_session_id") or ""),
            group_var=str(args.get("group_var") or ""),
            taxonomy_level=str(args.get("taxonomy_level") or "Genus"),
            alpha_metric=str(args.get("alpha_metric") or "shannon"),
            language=str(args.get("language") or "zh"),
        ).to_dict()
    if name == "emp.analysis.run":
        return svc.run_plan(str(args.get("plan_id") or "")).to_dict()
    if name == "emp.job.status":
        return svc.get_job(
            str(args.get("job_id") or ""), hub_session_id=str(args.get("hub_session_id") or "")
        ).to_dict()
    if name == "emp.job.cancel":
        return svc.cancel_job(
            str(args.get("job_id") or ""), hub_session_id=str(args.get("hub_session_id") or "")
        ).to_dict()
    if name == "emp.result.list":
        return {
            "artifacts": [
                item.to_dict()
                for item in svc.list_artifacts(
                    hub_session_id=str(args.get("hub_session_id") or ""),
                    job_id=str(args.get("job_id") or ""),
                )
            ]
        }
    if name == "emp.result.download":
        sid = str(args.get("hub_session_id") or "")
        artifact, _path = svc.artifact_file(str(args.get("artifact_id") or ""), hub_session_id=sid)
        return {
            "artifact": artifact.to_dict(),
            "download_url": f"/api/emp/artifacts/{artifact.artifact_id}/download?session_id={quote(sid)}",
        }
    if name == "emp.report.generate":
        artifacts = svc.list_artifacts(
            hub_session_id=str(args.get("hub_session_id") or ""), job_id=str(args.get("job_id") or "")
        )
        reports = [item.to_dict() for item in artifacts if item.kind == "report"]
        return {"reports": reports, "generated_during_run": True}
    raise AssertionError("unreachable EMP tool dispatch")
