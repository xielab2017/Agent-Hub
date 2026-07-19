from __future__ import annotations

import json

from ali import settings


def _settings_file(monkeypatch, tmp_path):
    path = tmp_path / "campus-office-ai.json"
    monkeypatch.setattr(settings, "CAMPUS_CONFIG_FILE", path)
    monkeypatch.setattr(settings, "ensure_state_dirs", lambda: None)
    return path


def test_old_config_gets_governance_and_fusion_defaults(monkeypatch, tmp_path):
    path = _settings_file(monkeypatch, tmp_path)
    path.write_text(json.dumps({"models": {"main": "writer", "embedding": "embedder"}}))

    cfg = settings.load_campus_config()

    assert cfg["category_models"]["C1"] == "writer"
    assert cfg["category_models"]["Embedding"] == "embedder"
    assert all(cfg["category_auto"].values())
    assert cfg["model_health_cache"] == {}
    assert cfg["model_profiles"] == {}
    assert cfg["fusion_mode"] == "auto"
    assert cfg["fusion_token_budget"]["total_budget"] == 12000
    assert cfg["fusion_judge_model"] == ""


def test_legacy_nested_fusion_and_category_values_migrate(monkeypatch, tmp_path):
    path = _settings_file(monkeypatch, tmp_path)
    path.write_text(json.dumps({
        "routing": {"tier_models": {"C2": {"model": "coder"}}},
        "category_auto": False,
        "fusion": {"mode": "deep", "token_budget": 9000, "judge_model": "judge"},
    }))

    cfg = settings.load_campus_config()

    assert cfg["category_models"]["C2"] == "coder"
    assert not any(cfg["category_auto"].values())
    assert cfg["fusion_mode"] == "deep"
    assert cfg["fusion_token_budget"]["total_budget"] == 9000
    assert cfg["fusion_judge_model"] == "judge"


def test_partial_save_preserves_existing_governance(monkeypatch, tmp_path):
    path = _settings_file(monkeypatch, tmp_path)
    settings.save_campus_config({
        "model_health_cache": {"m": {"state": "healthy", "tested_at": 10}},
        "category_models": {"C3": "reasoner"},
        "category_auto": {"C3": False},
        "fusion_mode": "deep",
    })

    saved = settings.save_campus_config({"ali": {"language": "en"}})

    assert saved["model_health_cache"]["m"]["state"] == "healthy"
    assert saved["category_models"]["C3"] == "reasoner"
    assert saved["category_auto"]["C3"] is False
    assert saved["fusion_mode"] == "deep"


def test_partial_save_migrates_legacy_disk_config(monkeypatch, tmp_path):
    path = _settings_file(monkeypatch, tmp_path)
    path.write_text(json.dumps({
        "fusion": {"mode": "deep", "token_budget": 7000, "judge_model": "legacy-judge"},
        "model_health_cache": {"m": {"state": "healthy"}},
    }))

    saved = settings.save_campus_config({"ali": {"language": "en"}})

    assert saved["schema_version"] == "1.2"
    assert saved["fusion_mode"] == "deep"
    assert saved["fusion_token_budget"]["total_budget"] == 7000
    assert saved["fusion_judge_model"] == "legacy-judge"
    assert saved["model_health_cache"]["m"]["state"] == "healthy"


def test_public_governance_view_uses_healthy_profiles():
    cfg = settings._normalize_governance_settings({
        "model_health_cache": {
            "good": {"state": "healthy", "tested_at": 10},
            "bad": {"state": "unavailable", "tested_at": 10},
        },
        "model_profiles": {
            "good": {"model": "good", "recommended_categories": ["C1"]},
            "bad": {"model": "bad", "recommended_categories": ["C1"]},
        },
    })

    view = settings.public_model_governance_view(cfg)

    assert view["selectable_models"] == ["good"]
    assert view["recommendations"]["C1"]["model"] == "good"


def test_public_governance_recommendations_are_scoped_to_active_provider():
    cfg = settings._normalize_governance_settings({
        "backend": {"type": "provider-a"},
        "model_health_cache": {
            "model-a": {"provider": "provider-a", "state": "healthy", "tested_at": 10},
            "model-b": {"provider": "provider-b", "state": "healthy", "tested_at": 10},
        },
        "model_profiles": {
            "model-a": {
                "schema_version": 2,
                "model": "model-a",
                "provider": "provider-a",
                "healthy": True,
                "health_state": "healthy",
                "recommended_categories": ["C3"],
                "capabilities": {"reasoning": True},
                "performance": {"quality_score": 0.5},
            },
            "model-b": {
                "schema_version": 2,
                "model": "model-b",
                "provider": "provider-b",
                "healthy": True,
                "health_state": "healthy",
                "recommended_categories": ["C3"],
                "capabilities": {"reasoning": True},
                "performance": {"quality_score": 1.0},
            },
        },
    })

    view = settings.public_model_governance_view(cfg)

    assert view["recommendations"]["C3"]["model"] == "model-a"
    assert view["selectable_models"] == ["model-a"]


def test_language_modes_preserve_legacy_values_and_accept_auto(monkeypatch, tmp_path):
    path = _settings_file(monkeypatch, tmp_path)
    path.write_text(json.dumps({"ali": {"language": "en"}}))
    assert settings.load_campus_config()["ali"]["language"] == "en"

    saved = settings.save_campus_config({"ali": {"language": "auto"}})
    assert saved["ali"]["language"] == "auto"

    saved = settings.save_campus_config({"ali": {"language": "unsupported"}})
    assert saved["ali"]["language"] == "zh"
