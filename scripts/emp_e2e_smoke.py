#!/usr/bin/env python3
"""Run the Agent Hub -> local EMP Phase 1 smoke workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def request(base: str, method: str, path: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        base.rstrip("/") + path,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as response:  # noqa: S310
        result = json.loads(response.read().decode("utf-8"))
    if not isinstance(result, dict) or result.get("ok") is False:
        raise RuntimeError(f"{path} failed: {result}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hub", default="http://127.0.0.1:8765", help="Agent Hub origin")
    parser.add_argument("--workspace", required=True, help="Directory containing the 16S fixture")
    parser.add_argument("--assay", default="16S_level-7.csv")
    parser.add_argument("--metadata", default="16S_mapping.csv")
    parser.add_argument("--group", default="Group")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve(strict=True)
    inputs = [workspace / args.assay, workspace / args.metadata]
    before = {path: checksum(path) for path in inputs}
    session_id = f"emp-smoke-{int(time.time())}"

    status = request(args.hub, "GET", "/api/emp/status")
    if not status.get("compatible"):
        raise RuntimeError(f"EMP is not compatible: {status.get('error') or status}")
    manifest = request(
        args.hub,
        "POST",
        "/api/emp/scan",
        {"path": str(workspace), "session_id": session_id, "max_depth": 0},
    )["manifest"]
    manifest = request(
        args.hub,
        "POST",
        f"/api/emp/manifests/{urllib.parse.quote(manifest['manifest_id'])}/pairing",
        {
            "session_id": session_id,
            "assay_path": args.assay,
            "metadata_path": args.metadata,
        },
    )["manifest"]
    if int((manifest.get("sample_overlap") or {}).get("matched") or 0) <= 0:
        raise RuntimeError("no samples matched after explicit pairing")

    plan = request(
        args.hub,
        "POST",
        "/api/emp/plans",
        {
            "manifest_id": manifest["manifest_id"],
            "session_id": session_id,
            "group_var": args.group,
            "taxonomy_level": "Genus",
            "alpha_metric": "shannon",
            "language": "zh",
        },
    )["plan"]
    plan_path = urllib.parse.quote(plan["plan_id"])
    session_body = {"session_id": session_id}
    request(args.hub, "POST", f"/api/emp/plans/{plan_path}/confirm", session_body)
    job = request(args.hub, "POST", f"/api/emp/plans/{plan_path}/run", session_body)["job"]

    deadline = time.monotonic() + max(10, args.timeout)
    while time.monotonic() < deadline:
        job = request(
            args.hub,
            "GET",
            f"/api/emp/jobs/{urllib.parse.quote(job['job_id'])}?session_id={urllib.parse.quote(session_id)}",
        )["job"]
        if job["status"] in {"done", "error", "cancelled"}:
            break
        time.sleep(0.5)
    if job["status"] != "done":
        raise RuntimeError(f"EMP job did not complete: {job}")

    artifacts = request(
        args.hub,
        "GET",
        f"/api/emp/artifacts?job_id={urllib.parse.quote(job['job_id'])}&session_id={urllib.parse.quote(session_id)}",
    )["artifacts"]
    required = {"application/json", "image/png", "application/pdf", "text/markdown"}
    observed = {str(item.get("mime_type") or "") for item in artifacts}
    if not required.issubset(observed):
        raise RuntimeError(f"missing artifacts: required={required}, observed={observed}")
    if any(not item.get("sha256") or int(item.get("size") or 0) <= 0 for item in artifacts):
        raise RuntimeError("one or more artifacts lack checksum/size provenance")
    after = {path: checksum(path) for path in inputs}
    if before != after:
        raise RuntimeError("EMP workflow modified an input fixture")

    print(json.dumps({
        "ok": True,
        "manifest_id": manifest["manifest_id"],
        "matched": manifest["sample_overlap"]["matched"],
        "plan_id": plan["plan_id"],
        "job_id": job["job_id"],
        "artifacts": [{"name": item["name"], "size": item["size"]} for item in artifacts],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
