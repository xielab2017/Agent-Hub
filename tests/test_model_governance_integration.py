from __future__ import annotations

import json

from ali import llm_client, model_intelligence, providers


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
