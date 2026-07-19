from ali.model_intelligence import analyze_model, choose_auto_model, recommend_category_models
from ali.providers import model_options_payload
from ali.routing import resolve_route


def _cfg():
    return {
        "mode": "single",
        "backend": {"type": "nvidia-nim", "base_url": "https://example.test/v1"},
        "available_models": {
            "nvidia-nim": [
                "meta/llama-3.1-8b-instruct",
                "nvidia/nemotron-3-super-120b-a12b",
                "meta/llama-3.2-11b-vision-instruct",
                "nvidia/nv-embed-v1",
                "old/unavailable-model",
            ]
        },
        "model_health": {
            "nvidia-nim": {
                "meta/llama-3.1-8b-instruct": {
                    **analyze_model("meta/llama-3.1-8b-instruct"),
                    "state": "available", "chat_compatible": True, "latency_s": 1.0,
                },
                "nvidia/nemotron-3-super-120b-a12b": {
                    **analyze_model("nvidia/nemotron-3-super-120b-a12b"),
                    "state": "available", "chat_compatible": True, "latency_s": 4.0,
                },
                "meta/llama-3.2-11b-vision-instruct": {
                    **analyze_model("meta/llama-3.2-11b-vision-instruct"),
                    "state": "available", "chat_compatible": True, "latency_s": 2.0,
                },
                "nvidia/nv-embed-v1": {
                    **analyze_model("nvidia/nv-embed-v1"),
                    "state": "dedicated", "chat_compatible": False,
                },
                "old/unavailable-model": {
                    **analyze_model("old/unavailable-model"),
                    "state": "unavailable", "chat_compatible": False,
                },
            }
        },
        "models": {"fast": "meta/llama-3.1-8b-instruct", "main": "meta/llama-3.1-8b-instruct"},
        "routing": {"auto_model_enabled": True},
        "data_policy": "internal",
    }


def test_analysis_classifies_dedicated_and_multimodal_models():
    assert analyze_model("nvidia/nv-embed-v1")["kind"] == "embedding"
    assert "vision" in analyze_model("meta/llama-3.2-11b-vision-instruct")["capabilities"]
    assert "reasoning" in analyze_model("nvidia/nemotron-3-super-120b-a12b")["capabilities"]


def test_picker_hides_failed_but_keeps_dedicated_profile():
    options = model_options_payload(_cfg())["options"]
    ids = {item["model"] for item in options}
    assert "old/unavailable-model" not in ids
    assert "nvidia/nv-embed-v1" in ids
    assert next(x for x in options if x["model"] == "nvidia/nv-embed-v1")["kind"] == "embedding"


def test_auto_selection_matches_request_capability():
    cfg = _cfg()
    assert choose_auto_model(cfg, "请分析这张图片", "Vision") == "meta/llama-3.2-11b-vision-instruct"
    assert choose_auto_model(cfg, "请做复杂推理并给出架构方案", "C3") == "nvidia/nemotron-3-super-120b-a12b"
    assert choose_auto_model(cfg, "你好", "C0") == "meta/llama-3.1-8b-instruct"


def test_resolve_route_uses_live_auto_model():
    info = resolve_route("auto", "请做复杂推理并给出架构方案", _cfg())
    assert info["auto"] is True
    assert info["model"] == "nvidia/nemotron-3-super-120b-a12b"


def test_explicit_route_keeps_configured_binding():
    info = resolve_route("simple", "请做复杂推理", _cfg())
    assert info["auto"] is False
    assert info["model"] == "meta/llama-3.1-8b-instruct"


def test_category_recommendations_are_independent_and_healthy():
    health = _cfg()["model_health"]["nvidia-nim"]
    recs = recommend_category_models(health)
    assert recs["C0"] == "meta/llama-3.1-8b-instruct"
    assert recs["C3"] == "nvidia/nemotron-3-super-120b-a12b"
    assert recs["Vision"] == "meta/llama-3.2-11b-vision-instruct"
    assert recs["Embedding"] == "nvidia/nv-embed-v1"


def test_explicit_category_can_use_its_own_auto_recommendation():
    cfg = _cfg()
    recs = recommend_category_models(cfg["model_health"]["nvidia-nim"])
    cfg["model_recommendations"] = {"nvidia-nim": recs}
    cfg["routing"]["tier_models"] = {
        "C3": {"provider": "nvidia-nim", "mode": "auto", "recommended_model": recs["C3"]}
    }
    info = resolve_route("C3", "", cfg)
    assert info["auto"] is False
    assert info["model"] == "nvidia/nemotron-3-super-120b-a12b"
