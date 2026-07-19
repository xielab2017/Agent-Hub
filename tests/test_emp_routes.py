from __future__ import annotations

import io
import json
from types import SimpleNamespace

from ali import routes


class Handler:
    def __init__(self, path: str, payload=None):
        raw = json.dumps(payload or {}).encode()
        self.path = path
        self.headers = {"Content-Length": str(len(raw))}
        self.rfile = io.BytesIO(raw)
        self.wfile = io.BytesIO()
        self.status = None

    def send_response(self, status):
        self.status = status

    def send_header(self, *_args):
        pass

    def end_headers(self):
        pass

    def json(self):
        return json.loads(self.wfile.getvalue())


class FakeService:
    def status(self):
        return {"enabled": True, "reachable": True, "compatible": True}

    def scan(self, path, **kwargs):
        assert path == "/data/study"
        assert kwargs["hub_session_id"] == "hub-1"
        return SimpleNamespace(manifest_id="manifest-1", files=[1, 2], to_dict=lambda: {"manifest_id": "manifest-1"})

    def create_16s_plan(self, manifest_id, **kwargs):
        assert manifest_id == "manifest-1"
        return SimpleNamespace(plan_id="plan-1", hub_session_id="hub-1", to_dict=lambda: {"plan_id": "plan-1"})

    def update_manifest_pairing(self, manifest_id, **kwargs):
        assert manifest_id == "manifest-1"
        assert kwargs["assay_path"] == "assay.csv"
        return SimpleNamespace(
            manifest_id=manifest_id,
            sample_overlap={"matched": 3},
            to_dict=lambda: {"manifest_id": manifest_id, "sample_overlap": {"matched": 3}},
        )

    def confirm_plan(self, plan_id):
        assert plan_id == "plan-1"
        return SimpleNamespace(plan_id=plan_id, hub_session_id="hub-1", to_dict=lambda: {"plan_id": plan_id, "confirmed_at": 1})

    def get_plan(self, plan_id):
        assert plan_id == "plan-1"
        return SimpleNamespace(plan_id=plan_id, hub_session_id="hub-1")

    def run_plan(self, plan_id):
        assert plan_id == "plan-1"
        return SimpleNamespace(job_id="job-1", plan_id=plan_id, hub_session_id="hub-1", to_dict=lambda: {"job_id": "job-1"})


def test_emp_status_route(monkeypatch):
    monkeypatch.setattr(routes, "get_emp_service", lambda: FakeService())
    handler = Handler("/api/emp/status")
    routes.handle_get(handler)
    assert handler.status == 200
    assert handler.json()["compatible"] is True


def test_emp_scan_plan_confirm_and_run_routes(monkeypatch):
    service = FakeService()
    events = []
    monkeypatch.setattr(routes, "get_emp_service", lambda: service)
    monkeypatch.setattr(routes.audit, "log_event", lambda kind, payload: events.append((kind, payload)))

    scan = Handler("/api/emp/scan", {"path": "/data/study", "session_id": "hub-1"})
    routes.handle_post(scan)
    assert scan.status == 200 and scan.json()["manifest"]["manifest_id"] == "manifest-1"

    plan = Handler("/api/emp/plans", {"manifest_id": "manifest-1", "session_id": "hub-1", "group_var": "Group"})
    routes.handle_post(plan)
    assert plan.status == 200 and plan.json()["plan"]["plan_id"] == "plan-1"

    pairing = Handler("/api/emp/manifests/manifest-1/pairing", {
        "session_id": "hub-1", "assay_path": "assay.csv", "metadata_path": "meta.csv"
    })
    routes.handle_post(pairing)
    assert pairing.status == 200 and pairing.json()["manifest"]["sample_overlap"]["matched"] == 3

    confirm = Handler("/api/emp/plans/plan-1/confirm", {"session_id": "hub-1"})
    routes.handle_post(confirm)
    assert confirm.status == 200 and confirm.json()["plan"]["confirmed_at"] == 1
    assert confirm.rfile.tell() == int(confirm.headers["Content-Length"])

    run = Handler("/api/emp/plans/plan-1/run", {"session_id": "hub-1"})
    routes.handle_post(run)
    assert run.status == 202 and run.json()["job"]["job_id"] == "job-1"
    assert run.rfile.tell() == int(run.headers["Content-Length"])
    assert [kind for kind, _payload in events] == [
        "emp_dataset_scan", "emp_plan_create", "emp_dataset_pairing", "emp_plan_confirm", "emp_plan_run"
    ]
