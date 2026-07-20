from __future__ import annotations

import json
import urllib.error
from typing import Any

import pytest

from ali.emp_client import EmpClient, EmpClientError


def _transport(payload: dict[str, Any], *, status: int = 200):
    def send(_request, _timeout):
        return status, {"content-type": "application/json"}, json.dumps(payload).encode()
    return send


@pytest.mark.parametrize(
    "url",
    ["http://192.168.1.2:8000", "https://127.0.0.1:8000", "http://example.com", "http://127.0.0.1:8000/api"],
)
def test_phase1_rejects_non_loopback_or_non_origin_url(url: str) -> None:
    with pytest.raises(ValueError):
        EmpClient(url)


def test_capabilities_contract() -> None:
    client = EmpClient(
        "http://localhost:8000",
        transport=_transport({"success": True, "api_version": "1.0", "workflows": ["microbiome_16s"]}),
    )
    assert client.capabilities()["api_version"] == "1.0"


def test_incompatible_api_is_normalized() -> None:
    client = EmpClient("http://127.0.0.1:8000", transport=_transport({"success": True, "api_version": "2.0"}))
    with pytest.raises(EmpClientError) as caught:
        client.capabilities()
    assert caught.value.error_code == "EMP_VERSION_INCOMPATIBLE"


def test_business_validation_error_is_normalized() -> None:
    client = EmpClient(
        "http://127.0.0.1:8000",
        transport=_transport({"success": False, "error": "metadata sample validation failed"}),
    )
    with pytest.raises(EmpClientError) as caught:
        client.preview_path({})
    assert caught.value.error_code == "EMP_DATA_VALIDATION_FAILED"
    assert caught.value.to_dict()["user_message_zh"]


def test_get_retries_but_post_does_not() -> None:
    calls = []

    def broken(request, _timeout):
        calls.append(request.method)
        raise urllib.error.URLError("offline")

    client = EmpClient("http://127.0.0.1:8000", transport=broken)
    with pytest.raises(EmpClientError):
        client.health()
    assert calls == ["GET", "GET", "GET"]
    calls.clear()
    with pytest.raises(EmpClientError):
        client.import_path({})
    assert calls == ["POST"]


def test_only_registered_step_tools_are_callable() -> None:
    client = EmpClient("http://127.0.0.1:8000", transport=_transport({"success": True}))
    with pytest.raises(ValueError):
        client.run_step("emp.user_r.run", {})


def test_workflow_step_uses_registered_endpoint_and_translates_groups() -> None:
    seen = []

    def transport(request, _timeout):
        seen.append((request.full_url, json.loads(request.data.decode("utf-8"))))
        return 200, {}, b'{"success":true,"n_rows":1}'

    client = EmpClient("http://127.0.0.1:8000", transport=transport)
    result = client.run_step("emp.analyze.differential", {
        "_workflow": "transcriptomics",
        "workflow": "transcriptomics",
        "session_id": "EMP1",
        "experiment": "rna",
        "group_var": "Group",
        "reference_level": "control",
        "test_level": "treated",
        "method": "deseq2",
        "adjust_method": "BH",
        "alpha": 0.05,
    })
    assert result["n_rows"] == 1
    assert seen[0][0].endswith("/api/workflows/transcriptomics/analyze/differential")
    assert seen[0][1]["ref_group"] == "control"
    assert seen[0][1]["test_group"] == "treated"
    assert "workflow" not in seen[0][1]


def test_alpha_plot_preserves_selected_group_level_names() -> None:
    seen = []

    def transport(request, _timeout):
        seen.append(json.loads(request.data.decode("utf-8")))
        return 200, {}, b'{"success":true}'

    client = EmpClient("http://127.0.0.1:8000", transport=transport)
    client.run_step("emp.visualize.alpha", {
        "_workflow": "microbiome_16s",
        "session_id": "EMP1",
        "experiment": "study",
        "group": "Group",
        "reference_level": "control",
        "test_level": "treated",
        "metric": "shannon",
    })

    assert seen[0]["reference_level"] == "control"
    assert seen[0]["test_level"] == "treated"
    assert "ref_group" not in seen[0]
    assert "test_group" not in seen[0]
