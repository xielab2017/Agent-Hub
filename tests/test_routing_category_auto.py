from __future__ import annotations

from ali import routing
from ali.model_intelligence import build_model_profile, health_record_from_probe


def _profile(model: str, quality: float) -> dict:
    health = health_record_from_probe(model, {"ok": True, "content": "ok"}, tested_at=1_000)
    profile = build_model_profile(
        model,
        health=health,
        metadata={"performance": {"quality_score": quality, "stability": 0.95, "cost_score": 0.8}},
        measured_capabilities={"chat": True, "reasoning": True, "writing": quality, "coding": 0.8},
    )
    profile["provider"] = "nvidia-nim"
    return profile


def _config(*, auto: bool = True) -> dict:
    smart = _profile("nvidia-smart-research", 0.95)
    manual = _profile("nvidia-manual-research", 0.6)
    return {
        "mode": "single",
        "backend": {"type": "nvidia-nim", "base_url": "https://example.invalid/v1", "api_key_env": "NVIDIA_API_KEY"},
        "models": {"qwen_main": "legacy-slot-model", "main": "legacy-slot-model"},
        "routing": {},
        "category_auto": {"C3": auto},
        "category_models": {"C3": "nvidia-manual-research"},
        "model_profiles": {smart["model"]: smart, manual["model"]: manual},
    }


def test_auto_route_uses_health_scored_category_recommendation():
    route = routing.resolve_route("auto", "请对该系统做复杂推理，并给出架构决策和实现方案。", _config())
    assert route["tier"] == "C3"
    assert route["model"] == "nvidia-smart-research"
    assert route["model_selection_source"] == "category_auto"


def test_manual_category_model_overrides_auto_recommendation():
    route = routing.resolve_route("auto", "请对该系统做复杂推理，并给出架构决策和实现方案。", _config(auto=False))
    assert route["tier"] == "C3"
    assert route["model"] == "nvidia-manual-research"
    assert route["model_selection_source"] == "category_manual"
