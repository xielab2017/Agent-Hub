import json

import pytest

from ali.fusion import (
    allocate_token_budget,
    assess_complexity,
    build_fusion_plan,
    fusion_plan,
    normalize_fusion_mode,
    plan_fusion,
)


MODELS = [
    {"model": "fast-a", "provider": "local", "tiers": ["C0", "C1"], "healthy": True, "quality": 0.65, "latency_ms": 100},
    {"model": "research-b", "provider": "nvidia", "tiers": ["C2", "C3"], "healthy": True, "quality": 0.92, "latency_ms": 900},
    {"model": "critic-c", "provider": "deepseek", "tiers": ["C3"], "healthy": True, "quality": 0.88, "latency_ms": 700},
    {"model": "judge-d", "provider": "openai", "tiers": ["C3"], "healthy": True, "quality": 0.95, "latency_ms": 1100},
    {"model": "broken-e", "provider": "test", "tiers": ["C3"], "status": "unavailable", "quality": 1.0},
]


def test_mode_normalization_keeps_legacy_aliases():
    assert normalize_fusion_mode("single") == "fast"
    assert normalize_fusion_mode("parallel") == "deep"
    assert normalize_fusion_mode("unknown") == "auto"


def test_complexity_gates_simple_and_complex_auto_tasks():
    simple = assess_complexity("你好", task_type="auto", thinking_depth="medium")
    complex_task = assess_complexity("研究并比较三种系统架构，评估证据、风险以及实现方案", thinking_depth="high")
    assert simple["tier"] == "C0"
    assert simple["fusion_recommended"] is False
    assert complex_task["fusion_recommended"] is True
    assert complex_task["tier"] in {"C2", "C3"}
    assert complex_task["score"] > simple["score"]


def test_fast_is_single_model_even_for_complex_prompt():
    plan = plan_fusion("研究复杂架构并给出风险评估", fusion_mode="fast", models=MODELS)
    assert plan["enabled"] is False
    assert plan["lanes"] == []
    assert plan["judge"] is None
    assert plan["primary"]["model"] == "fast-a"


def test_auto_skips_fusion_for_simple_prompt():
    plan = plan_fusion("把它改个名", fusion_mode="auto", models=MODELS)
    assert plan["enabled"] is False
    assert plan["complexity"]["tier"] == "C0"
    assert plan["budget"]["judge"] == 0


def test_auto_enables_diverse_budgeted_lanes_for_complex_work():
    plan = plan_fusion(
        "研究并比较两个代码架构，分析证据并审查实现风险",
        fusion_mode="auto",
        thinking_depth="high",
        models=MODELS,
    )
    assert plan["enabled"] is True
    assert len(plan["lanes"]) == 3
    assert len({lane["model"] for lane in plan["lanes"]}) == 3
    assert all(lane["hidden"] and lane["failure_tolerant"] for lane in plan["lanes"])
    assert all(lane["max_tokens"] == lane["max_tokens_override"] > 0 for lane in plan["lanes"])
    assert plan["judge"]["max_tokens"] == plan["budget"]["judge"]
    assert plan["budget"]["allocated"] == plan["budget"]["total_budget"]


def test_deep_forces_fusion_and_respects_lane_limit_and_total_budget():
    plan = plan_fusion(
        "写一封短邮件",
        fusion_mode="deep",
        max_lanes=2,
        total_budget=6000,
        models=MODELS,
    )
    assert plan["enabled"] is True
    assert len(plan["lanes"]) == 2
    assert plan["budget"]["total_budget"] == 6000
    assert plan["budget"]["allocated"] == 6000
    assert plan["judge"]["max_tokens"] > 0


def test_unhealthy_candidates_are_excluded_and_fallback_is_explicit():
    plan = plan_fusion("实现并审查一个复杂 API", fusion_mode="deep", models=MODELS)
    assert "broken-e" not in {lane["model"] for lane in plan["lanes"]}
    assert plan["fallback"]["enabled"] is True
    assert plan["fallback"]["strategy"] == "best_healthy_single_model"
    assert plan["failure_policy"]["lane_failure"] == "continue_with_successful_lanes"
    assert plan["failure_policy"]["hide_internal_sessions"] is True


def test_route_resolver_is_injectable_and_never_needs_network():
    calls = []

    def fake_resolver(tier, prompt, cfg):
        calls.append((tier, prompt, cfg))
        return {"model": f"model-{tier}", "provider": "offline", "tier": tier}

    plan = plan_fusion(
        "详细分析科研方案与风险",
        fusion_mode="deep",
        route_resolver=fake_resolver,
        cfg={"test": True},
    )
    assert len(calls) == 5
    assert plan["metadata"]["candidate_count"] == 5
    assert all(lane["provider"] == "offline" for lane in plan["lanes"])


def test_compatibility_aliases_and_json_serialization():
    direct = plan_fusion("你好", models=MODELS)
    assert build_fusion_plan("你好", models=MODELS) == direct
    assert fusion_plan("你好", models=MODELS) == direct
    assert json.loads(json.dumps(direct))["mode"] == "auto"


def test_budget_helper_and_validation():
    budget = allocate_token_budget("deep", ["analysis", "critic", "solution"], total_budget=12000)
    assert budget["allocated"] == 12000
    assert budget["lanes"][2]["max_tokens"] > budget["lanes"][1]["max_tokens"]
    small = allocate_token_budget("deep", ["analysis", "critic"], total_budget=1000)
    assert small["allocated"] == small["total_budget"] == 1000
    assert all(lane["max_tokens"] > 0 for lane in small["lanes"])
    with pytest.raises(ValueError, match="prompt"):
        plan_fusion("   ")
