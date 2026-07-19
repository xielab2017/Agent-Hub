from __future__ import annotations

import json

import pytest

from ali.model_intelligence import (
    CATEGORIES,
    ModelIntelligenceCache,
    build_model_profile,
    filter_healthy_models,
    health_record_from_probe,
    is_health_cache_fresh,
    probe_model_capabilities,
    quick_health_check,
    recommend_category_models,
    recommend_model,
)


def _health(model: str, state: str = "healthy", latency_ms: float = 500):
    return health_record_from_probe(
        model,
        {"state": state, "latency_ms": latency_ms},
        tested_at=1_000,
    )


@pytest.mark.parametrize(
    ("probe", "state"),
    [
        ({"ok": True, "content": "pong"}, "healthy"),
        ({"ok": True, "content": "pong", "degraded": True}, "degraded"),
        ({"timeout": True}, "timeout"),
        ({"status_code": 404}, "unsupported"),
        ({"ok": False, "status_code": 503}, "unavailable"),
        ({"ok": True, "content": ""}, "unavailable"),
        ({}, "untested"),
    ],
)
def test_probe_results_map_to_stable_health_states(probe, state):
    assert health_record_from_probe("org/model", probe, tested_at=100)["state"] == state


def test_quick_health_check_converts_exceptions_without_network():
    def probe(_model):
        raise TimeoutError("provider was too slow")

    values = iter((2.0, 2.25))
    result = quick_health_check("org/model", probe, clock=lambda: next(values))
    assert result["state"] == "timeout"
    assert result["latency_ms"] == 250
    assert "too slow" in result["error"]


def test_cache_reuses_fresh_records_and_retests_new_or_expired(tmp_path):
    cache_path = tmp_path / "model-intelligence.json"
    cache = ModelIntelligenceCache(cache_path, ttl_seconds=100)
    cache.set_health("fresh", _health("fresh"))
    cache.set_health("expired", {**_health("expired"), "tested_at": 800})
    cache.save()

    loaded = ModelIntelligenceCache(cache_path, ttl_seconds=100)
    assert loaded.models_requiring_test(["fresh", "expired", "new"], now=1_050) == ["expired", "new"]
    assert loaded.get_health("fresh")["healthy"] is True
    assert json.loads(cache_path.read_text())["schema_version"] == 1


def test_cache_reads_legacy_plan_keys_and_survives_invalid_json(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text(json.dumps({"model_health_cache": {"m": _health("m")}, "model_profiles": {"m": {"model": "m"}}}))
    cache = ModelIntelligenceCache(path)
    assert cache.get_health("m")["state"] == "healthy"
    assert cache.get_profile("m")["model"] == "m"

    path.write_text("not json")
    assert ModelIntelligenceCache(path).data["health"] == {}


def test_cache_keeps_capability_health_checks_independent(tmp_path):
    cache = ModelIntelligenceCache(tmp_path / "cache.json")
    cache.set_health("multi", _health("multi", "healthy"), capability="chat")
    cache.set_health("multi", _health("multi", "unsupported"), capability="embedding")
    assert cache.get_health("multi", capability="chat")["state"] == "healthy"
    assert cache.get_health("multi", capability="embedding")["state"] == "unsupported"
    assert cache.get_health("multi", capability="vision") is None
    assert cache.models_requiring_test(["multi"], capability="chat", now=1_050) == []
    assert cache.models_requiring_test(["multi"], capability="vision", now=1_050) == ["multi"]


def test_capability_probes_are_injected_and_unknown_probe_names_are_ignored():
    results = probe_model_capabilities(
        "multi",
        {
            "chat": lambda _model: {"ok": True, "content": "pong"},
            "embedding": lambda _model: {"status_code": 404},
            "not-a-capability": lambda _model: {"ok": True},
        },
    )
    assert set(results) == {"chat", "embedding"}
    assert results["chat"]["state"] == "healthy"
    assert results["embedding"]["state"] == "unsupported"


def test_profile_uses_metadata_and_measured_evidence_before_name_fallback():
    profile = build_model_profile(
        "vendor/plain-model",
        health=_health("vendor/plain-model"),
        metadata={"capabilities": ["chat", "vision"], "performance": {"quality_score": 0.8}},
        measured_capabilities={"vision": False, "reasoning": True, "coding": 0.9},
    )
    assert profile["capabilities"]["vision"] is False
    assert profile["capabilities"]["reasoning"] is True
    assert profile["recommended_categories"] == ["C0", "C1", "C2", "C3"]
    assert profile["performance"]["quality_score"] == 0.8


def test_manual_profile_override_is_explicit_and_final():
    profile = build_model_profile(
        "vendor/embed-model",
        health=_health("vendor/embed-model"),
        manual_override={
            "capabilities": {"embedding": False, "chat": True, "writing": 0.95},
            "recommended_categories": ["C1"],
            "note": "verified by administrator",
        },
    )
    assert profile["recommended_categories"] == ["C1"]
    assert profile["note"] == "verified by administrator"


def test_unhealthy_models_are_hidden_from_normal_selection():
    healthy = build_model_profile("chat-a", health=_health("chat-a"), metadata={"capabilities": ["chat"]})
    unavailable = build_model_profile("chat-b", health=_health("chat-b", "unavailable"), metadata={"capabilities": ["chat"]})
    assert [item["model"] for item in filter_healthy_models([healthy, unavailable])] == ["chat-a"]


def test_category_auto_balances_quality_latency_stability_and_cost():
    slow = build_model_profile(
        "slow-writer",
        health=_health("slow-writer", latency_ms=8_000),
        metadata={"capabilities": {"chat": True, "writing": 0.9}, "performance": {"quality_score": 0.9, "stability": 0.9, "cost_score": 0.3}},
    )
    balanced = build_model_profile(
        "balanced-writer",
        health=_health("balanced-writer", latency_ms=500),
        metadata={"capabilities": {"chat": True, "writing": 0.85}, "performance": {"quality_score": 0.85, "stability": 0.95, "cost_score": 0.9}},
    )
    result = recommend_model([slow, balanced], "C1")
    assert result["model"] == "balanced-writer"
    assert result["source"] == "auto"


def test_manual_unavailable_model_falls_back_to_category_auto():
    available = build_model_profile("coder-a", health=_health("coder-a"), measured_capabilities={"chat": True, "coding": 0.9})
    failed = build_model_profile("coder-b", health=_health("coder-b", "timeout"), measured_capabilities={"chat": True, "coding": 0.95})
    result = recommend_model([available, failed], "C2", manual_model="coder-b")
    assert result["model"] == "coder-a"
    assert result["source"] == "auto"
    assert "unavailable" in result["fallback_reason"]


def test_each_category_has_an_independent_auto_decision():
    profiles = [
        build_model_profile("chat", health=_health("chat"), measured_capabilities={"chat": True, "writing": 0.8, "coding": 0.8, "reasoning": True, "vision": True}),
        build_model_profile("embed", health=_health("embed"), metadata={"task": "embedding"}),
        build_model_profile("rerank", health=_health("rerank"), metadata={"task": "reranker"}),
    ]
    decisions = recommend_category_models(profiles)
    assert tuple(decisions) == CATEGORIES
    assert decisions["Vision"]["model"] == "chat"
    assert decisions["Embedding"]["model"] == "embed"
    assert decisions["Reranker"]["model"] == "rerank"


def test_unknown_category_is_rejected():
    with pytest.raises(ValueError, match="unknown category"):
        recommend_model([], "C9")


def test_health_freshness_rejects_untested_and_future_records():
    assert is_health_cache_fresh({"state": "healthy", "tested_at": 90}, ttl_seconds=20, now=100)
    assert not is_health_cache_fresh({"state": "untested", "tested_at": 90}, now=100)
    assert not is_health_cache_fresh({"state": "healthy", "tested_at": 110}, now=100)
