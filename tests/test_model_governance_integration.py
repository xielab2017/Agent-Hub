from __future__ import annotations

import json
import time
from pathlib import Path

from ali import llm_client, model_intelligence, providers, settings


APP_JS = Path(__file__).resolve().parents[1] / "static" / "app.js"
ROUTES_PY = Path(__file__).resolve().parents[1] / "ali" / "routes.py"


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return json.dumps(self.payload).encode()


def test_real_probe_builds_minimal_chat_request(monkeypatch):
    seen = {}

    def fake_request(method, url, **kwargs):
        seen.update({"method": method, "url": url, **kwargs})
        return _Response({"choices": [{"message": {"content": "OK"}}]})

    monkeypatch.setattr(llm_client, "_request", fake_request)
    result = model_intelligence._probe_openai_capability(
        "https://integrate.api.nvidia.com/v1",
        "secret",
        "nvidia/test-model",
        "chat",
    )

    assert result["ok"] is True
    assert seen["url"].endswith("/v1/chat/completions")
    assert seen["body"]["max_tokens"] == 2


def test_unavailable_fetched_model_is_hidden_from_picker():
    cfg = {
        "backend": {"type": "nvidia-nim"},
        "available_models": {"nvidia-nim": ["nvidia/good", "nvidia/bad"]},
        "model_health_cache": {
            "nvidia/good": {"provider": "nvidia-nim", "state": "healthy", "latency_ms": 120},
            "nvidia/bad": {"provider": "nvidia-nim", "state": "unavailable", "error": "HTTP 404"},
        },
        "models": {},
    }

    payload = providers.model_options_payload(cfg)

    assert [item["model"] for item in payload["options"]] == ["nvidia/good"]
    assert payload["options"][0]["health_state"] == "healthy"


def test_background_health_job_builds_profiles_and_persists_results(monkeypatch):
    provider = "integration-test-provider"
    stored = {"model_health_cache": {}, "model_profiles": {}}

    def load_config():
        return json.loads(json.dumps(stored))

    def save_config(config):
        stored.clear()
        stored.update(json.loads(json.dumps(config)))
        return config

    monkeypatch.setattr(settings, "load_campus_config", load_config)
    monkeypatch.setattr(settings, "save_campus_config", save_config)
    monkeypatch.setattr(
        model_intelligence,
        "_probe_openai_capability",
        lambda *_args, **_kwargs: {"ok": True, "content": "OK"},
    )

    model_intelligence.start_governance_analysis(
        provider=provider,
        models=["vendor/test-model"],
        base_url="https://example.invalid/v1",
        api_key="secret",
        force=True,
    )
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        job = model_intelligence.governance_job(provider)
        if job["status"] != "running":
            break
        time.sleep(0.01)

    assert not job.get("error"), job["error"]
    assert job["status"] == "complete", job
    assert job["completed"] == 1
    assert stored["model_health_cache"]["vendor/test-model"]["state"] == "healthy"
    assert stored["model_profiles"]["vendor/test-model"]["provider"] == provider


def test_health_progress_lives_in_backend_and_models_page_is_results_only():
    source = APP_JS.read_text(encoding="utf-8")

    assert 'id="backend-governance-box"' in source
    assert 'id="model-governance-results"' in source
    assert 'id="model-governance-box"' not in source
    assert "拉取模型并自动检测" in source
    assert "最终结果统一显示在“模型”页" in source
    assert 'class="model-progress" role="progressbar"' in source
    assert 'class="model-progress is-indeterminate"' in source
    assert "resultsBox.dataset.resultsSignature" in source
    assert "if (resultsBox && !resultsBox.hasChildNodes())" in source


def test_manual_catalog_refresh_forces_a_fresh_health_check():
    source = ROUTES_PY.read_text(encoding="utf-8")
    refresh_block = source.split('if path == "/api/settings/refresh-models":', 1)[1].split(
        'if path == "/api/models/governance/refresh":', 1
    )[0]

    assert "start_governance_analysis(" in refresh_block
    assert "force=True" in refresh_block
