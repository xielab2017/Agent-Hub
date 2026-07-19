from ali.fusion import normalize_mode, plan_fusion


def test_fast_mode_always_uses_one_model_and_small_budget():
    plan = plan_fusion("请深度分析架构并比较三个方案", "fast")
    assert plan["strategy"] == "single"
    assert plan["need_parallel"] is False
    assert plan["lane_count"] == 1
    assert plan["total_token_budget"] <= 1800
    assert plan["synthesis_token_budget"] == 0
    assert plan["review_required"] is False


def test_auto_keeps_trivial_request_single():
    plan = plan_fusion("你好", "auto")
    assert plan["tier"] == "C0"
    assert plan["strategy"] == "single"
    assert plan["lane_count"] == 1


def test_auto_fuses_complex_reasoning_with_reserved_synthesis_budget():
    plan = plan_fusion("审查这段 Python 架构，比较两个方案并给出风险", "auto")
    assert plan["tier"] == "C3"
    assert plan["strategy"] == "expert_fusion"
    assert plan["lane_count"] == 2
    assert plan["review_required"] is True
    assert plan["lane_token_budget"] * 2 + plan["synthesis_token_budget"] <= plan["total_token_budget"]


def test_deep_forces_multiple_complementary_experts():
    plan = plan_fusion("写一份研究计划", "deep")
    assert plan["strategy"] == "expert_fusion"
    assert plan["lane_count"] >= 2
    assert plan["review_required"] is True
    assert plan["early_exit"] is False
    assert plan["lane_token_budget"] * plan["lane_count"] + plan["synthesis_token_budget"] <= plan["total_token_budget"]


def test_mode_aliases():
    assert normalize_mode("single") == "fast"
    assert normalize_mode("auto_fusion") == "auto"
    assert normalize_mode("deep-fusion") == "deep"
