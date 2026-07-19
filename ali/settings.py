"""Campus Office AI settings — compatible with campus-office-ai.json schema."""

from __future__ import annotations

import json
import os
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any

from .config import STATE_DIR, ensure_state_dirs

SETTINGS_FILE = STATE_DIR / "settings.json"
CAMPUS_CONFIG_FILE = STATE_DIR / "campus-office-ai.json"

MODEL_CATEGORIES = ("C0", "C1", "C2", "C3", "Vision", "Embedding", "Reranker")
DEFAULT_FUSION_TOKEN_BUDGET: dict[str, Any] = {
    "total_budget": 12000,
    "planner": 800,
    "lanes": 6000,
    "judge": 3200,
}

DEFAULT_CAMPUS: dict[str, Any] = {
    "schema_version": "1.2",
    "install_root": "",
    "mode": "single",  # single | hybrid
    "backend": {
        "type": "campus-openai-compatible",
        "base_url": "",
        "api_key_env": "CAMPUS_LLM_API_KEY",
        "verify_tls": True,
        "timeout_seconds": 60,
    },
    # Per-tier provider override when mode=hybrid
    "hybrid": {
        # "simple": {"provider": "openai", "model": "gpt-4o-mini"},
    },
    # Provider-scoped model ids returned by the real /models endpoint.
    # Kept separate from role bindings so every model picker can share it.
    "available_models": {},
    "model_health_cache": {},
    "model_profiles": {},
    "category_models": {category: "" for category in MODEL_CATEGORIES},
    "category_auto": {category: True for category in MODEL_CATEGORIES},
    "fusion_mode": "auto",  # fast | auto | deep
    "fusion_token_budget": deepcopy(DEFAULT_FUSION_TOKEN_BUDGET),
    "fusion_judge_model": "",
    "models": {
        "fast": "",
        "main": "",
        "vision": "",
        "reasoning": "",
        "qwen_fast": "",
        "qwen_main": "",
        "qwen_vl": "",
        "deepseek_reasoning": "",
        "embedding": "",
        "reranker": "",
    },
    "routing": {
        "simple": "qwen_fast",
        "office": "qwen_main",
        "vision": "qwen_vl",
        "reasoning": "deepseek_reasoning",
        "restricted_external_fallback": False,
    },
    "obsidian": {
        "vault_path": "",
        "ai_inbox": "00_Inbox/AI_Candidates",
        "allowed_roots": [
            "02_Team",
            "03_Projects",
            "04_Meetings",
            "05_Research",
            "06_SOP_and_Skills",
            "07_Templates",
            "08_Decisions",
        ],
        "excluded_globs": [
            ".obsidian/**",
            ".trash/**",
            "**/Private/**",
            "**/*credential*",
            "**/*secret*",
        ],
        "write_requires_approval": True,
    },
    "windows": {
        "install_obsidian": False,
        "enable_startup": False,
        "create_firewall_rule": False,
    },
    "data_policy": "internal",  # internal | restricted | public
    "workspace": "",
    "emp": {
        "enabled": False,
        "mode": "auto",
        "local_api_base": "http://127.0.0.1:8000",
        "remote_api_base": "",
        "api_token_env": "EMP_API_TOKEN",
        "request_timeout_seconds": 60,
        "job_timeout_minutes": 120,
        "poll_interval_seconds": 2,
        "allowed_roots": [],
        "artifact_root": "",
        "remote_upload_limit_mb": 2048,
        "allow_r_direct": False,
        "require_remote_upload_approval": True,
    },
    "ali": {
        "default_route": "auto",  # simple | office | vision | reasoning | auto
        "show_route_badge": True,
        "thinking_depth": "medium",  # light | medium | high | very_high
        "agent_runtime": "auto",  # auto | hermes | openclaw | … (Connect pins a concrete claw)
        "auto_runtime": "hermes",  # what `auto → X` prefers first (user-settable)
        # agent = Hermes/OpenClaw tools (hermes-webui style); direct = Hub HTTP chat only
        "hub_chat_mode": "agent",  # agent | direct
        "hub_fast_chat": False,  # legacy alias: True ⇒ force direct (kept for old configs)
        # recommended | observe | disabled — written into Hermes hub_route_contract.json
        "token_optimizer_mode": "recommended",
        "language": "zh",  # currently resolved UI language
        "language_mode": "auto",  # zh | en | auto
        "theme": "dark",  # dark | light
        "accent": "ocean",  # ocean | forest | amber | rose | slate | teal
        "logo_sidebar": "",  # empty = SUAT default; /brand/... or /brand/custom/...
        "logo_empty": "",  # empty = same policy; independent of sidebar when set
        "require_approval_for": [
            "email_send",
            "file_delete",
            "file_overwrite",
            "external_upload",
            "firewall",
            "startup",
            "vault_write_formal",
        ],
    },
    "search": {
        "enabled": True,
        "provider": "auto",  # auto | google_cse | serpapi | bing | so360
        "deep": True,
        "max_results": 10,
        "google_cse_cx": "",
        "proxy": "",  # e.g. http://127.0.0.1:7890 for Google CSE/SerpAPI on campus
        "verify_tls": True,
    },
}


def _deep_merge(base: dict, overlay: dict) -> dict:
    out = deepcopy(base)
    for k, v in (overlay or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _normalize_governance_settings(data: dict[str, Any] | None) -> dict[str, Any]:
    """Migrate model-governance and fusion fields without dropping old data."""
    source = deepcopy(data) if isinstance(data, dict) else {}
    source["schema_version"] = "1.2"
    routing = source.get("routing") if isinstance(source.get("routing"), dict) else {}
    tiers = routing.get("tier_models") if isinstance(routing.get("tier_models"), dict) else {}

    category_models = source.get("category_models")
    category_models = dict(category_models) if isinstance(category_models, dict) else {}
    legacy_slots = source.get("models") if isinstance(source.get("models"), dict) else {}
    slot_fallbacks = {
        "C0": legacy_slots.get("fast") or legacy_slots.get("qwen_fast"),
        "C1": legacy_slots.get("main") or legacy_slots.get("qwen_main"),
        "C2": legacy_slots.get("main") or legacy_slots.get("qwen_main"),
        "C3": legacy_slots.get("reasoning") or legacy_slots.get("deepseek_reasoning"),
        "Vision": legacy_slots.get("vision") or legacy_slots.get("qwen_vl"),
        "Embedding": legacy_slots.get("embedding"),
        "Reranker": legacy_slots.get("reranker"),
    }
    for category in MODEL_CATEGORIES:
        if category not in category_models:
            tier = tiers.get(category) if isinstance(tiers.get(category), dict) else {}
            category_models[category] = str(tier.get("model") or slot_fallbacks.get(category) or "")
        elif not isinstance(category_models[category], str):
            entry = category_models[category]
            category_models[category] = str(entry.get("model") or "") if isinstance(entry, dict) else ""
    source["category_models"] = category_models

    category_auto = source.get("category_auto")
    if isinstance(category_auto, bool):
        category_auto = {category: category_auto for category in MODEL_CATEGORIES}
    else:
        category_auto = dict(category_auto) if isinstance(category_auto, dict) else {}
    source["category_auto"] = {
        category: bool(category_auto.get(category, True)) for category in MODEL_CATEGORIES
    }

    for key in ("model_health_cache", "model_profiles"):
        if not isinstance(source.get(key), dict):
            source[key] = {}

    legacy_fusion = source.get("fusion") if isinstance(source.get("fusion"), dict) else {}
    ali = source.get("ali") if isinstance(source.get("ali"), dict) else {}
    mode = str(
        source.get("fusion_mode")
        or legacy_fusion.get("mode")
        or ali.get("fusion_mode")
        or "auto"
    ).lower()
    source["fusion_mode"] = mode if mode in ("fast", "auto", "deep") else "auto"

    budget = source.get("fusion_token_budget")
    if budget is None:
        budget = legacy_fusion.get("token_budget", ali.get("fusion_token_budget"))
    if isinstance(budget, (int, float)) and not isinstance(budget, bool):
        budget = {"total_budget": max(1, int(budget))}
    budget = dict(budget) if isinstance(budget, dict) else {}
    source["fusion_token_budget"] = _deep_merge(DEFAULT_FUSION_TOKEN_BUDGET, budget)
    source["fusion_judge_model"] = str(
        source.get("fusion_judge_model")
        or legacy_fusion.get("judge_model")
        or ali.get("fusion_judge_model")
        or ""
    )
    return source


def load_campus_config() -> dict[str, Any]:
    ensure_state_dirs()
    if CAMPUS_CONFIG_FILE.is_file():
        try:
            data = json.loads(CAMPUS_CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                merged = _deep_merge(DEFAULT_CAMPUS, _normalize_governance_settings(data))
                routing = merged.get("routing") if isinstance(merged.get("routing"), dict) else {}
                tiers = routing.get("tier_models") if isinstance(routing.get("tier_models"), dict) else {}
                if tiers:
                    fixed_tiers = dict(tiers)
                    changed = False
                    for tier, entry in tiers.items():
                        if not isinstance(entry, dict):
                            continue
                        model = str(entry.get("model") or "").strip()
                        if not model or not any(k in model.lower() for k in ("embedding", "embed", "rerank")):
                            continue
                        provider = str(entry.get("provider") or (merged.get("backend") or {}).get("type") or "").strip()
                        route_key = {"C0": "simple", "C1": "office", "C2": "office", "C3": "reasoning", "Vision": "vision"}.get(str(tier), "office")
                        try:
                            from .providers import coerce_model_for_provider
                            replacement = coerce_model_for_provider(provider, model, route_key=route_key)
                        except Exception:  # noqa: BLE001
                            replacement = ""
                        if replacement and replacement != model:
                            item = dict(entry)
                            item["model"] = replacement
                            item["repaired_from"] = model
                            fixed_tiers[tier] = item
                            changed = True
                    if changed:
                        merged["routing"] = dict(routing, tier_models=fixed_tiers)
                return merged
        except (OSError, json.JSONDecodeError):
            pass
    return deepcopy(DEFAULT_CAMPUS)


def resolve_backend_verify_tls(
    cfg: dict[str, Any],
    route_info: dict[str, Any] | None = None,
) -> bool:
    """Resolve TLS verification for the concrete routed LLM provider.

    Inheritance, most-specific first:
    route_info.verify_tls → backend.provider_tls[provider] →
    hybrid[route_key].verify_tls → backend.verify_tls → secure default True.
    """
    route = route_info if isinstance(route_info, dict) else {}
    if isinstance(route.get("verify_tls"), bool):
        return bool(route["verify_tls"])

    backend = cfg.get("backend") if isinstance(cfg.get("backend"), dict) else {}
    provider = str(route.get("provider") or route.get("backend_type") or backend.get("type") or "")
    provider_tls = backend.get("provider_tls")
    if isinstance(provider_tls, dict) and provider:
        scoped = provider_tls.get(provider)
        if isinstance(scoped, bool):
            return scoped
        if isinstance(scoped, dict) and isinstance(scoped.get("verify_tls"), bool):
            return bool(scoped["verify_tls"])

    route_key = str(route.get("route_key") or "")
    hybrid = cfg.get("hybrid") if isinstance(cfg.get("hybrid"), dict) else {}
    routed = hybrid.get(route_key) if route_key else None
    if isinstance(routed, dict) and isinstance(routed.get("verify_tls"), bool):
        return bool(routed["verify_tls"])

    return bool(backend.get("verify_tls", True))


def save_campus_config(
    data: dict[str, Any], *, preserve_existing: bool = True
) -> dict[str, Any]:
    """Persist settings without dropping fields omitted by a partial/stale writer.

    Most callers update one section after loading the current config, but browser
    tabs and older clients can still submit a config that predates a newly added
    field. Merge the on-disk document first so those writes cannot silently
    restore defaults (notably backend.verify_tls). Imports opt out below because
    they intentionally replace the complete configuration.
    """
    ensure_state_dirs()
    from .providers import looks_like_secret

    merged = deepcopy(DEFAULT_CAMPUS)
    if preserve_existing and CAMPUS_CONFIG_FILE.is_file():
        try:
            existing = json.loads(CAMPUS_CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                merged = _deep_merge(merged, _normalize_governance_settings(existing))
        except (OSError, json.JSONDecodeError):
            pass
    incoming = data if isinstance(data, dict) else {}
    if not preserve_existing:
        incoming = _normalize_governance_settings(incoming)
    merged = _deep_merge(merged, incoming)
    # A partial legacy writer may still send only the former nested Fusion
    # block. Honor explicitly supplied legacy values before final normalization.
    legacy_fusion = incoming.get("fusion") if isinstance(incoming.get("fusion"), dict) else {}
    incoming_ali = incoming.get("ali") if isinstance(incoming.get("ali"), dict) else {}
    if "fusion_mode" not in incoming and ("mode" in legacy_fusion or "fusion_mode" in incoming_ali):
        merged["fusion_mode"] = legacy_fusion.get("mode", incoming_ali.get("fusion_mode"))
    if "fusion_token_budget" not in incoming and (
        "token_budget" in legacy_fusion or "fusion_token_budget" in incoming_ali
    ):
        merged["fusion_token_budget"] = legacy_fusion.get(
            "token_budget", incoming_ali.get("fusion_token_budget")
        )
    if "fusion_judge_model" not in incoming and (
        "judge_model" in legacy_fusion or "fusion_judge_model" in incoming_ali
    ):
        merged["fusion_judge_model"] = legacy_fusion.get(
            "judge_model", incoming_ali.get("fusion_judge_model")
        )
    merged = _normalize_governance_settings(merged)
    # Never persist secrets
    backend = merged.get("backend") or {}
    for secret_key in ("api_key", "password", "token", "secret"):
        backend.pop(secret_key, None)
    env_name = str(backend.get("api_key_env") or "").strip()
    if looks_like_secret(env_name):
        # Accidentally pasted key into env-name — stash it as secret and restore proper env name
        from .secrets import set_api_key
        from .providers import get_provider

        provider_id = str(backend.get("type") or "default")
        set_api_key(provider_id, env_name)
        prov = get_provider(provider_id)
        proper = (prov or {}).get("api_key_env") or "API_KEY"
        set_api_key(str(proper), env_name)
        backend["api_key_env"] = proper
        merged["_warning"] = (
            "Detected API key in api_key_env field. "
            f"Saved it securely to local secrets and set api_key_env={proper}."
        )
    merged["backend"] = backend

    # Sync generic ↔ legacy model keys
    models = dict(merged.get("models") or {})
    pairs = [
        ("fast", "qwen_fast"),
        ("main", "qwen_main"),
        ("vision", "qwen_vl"),
        ("reasoning", "deepseek_reasoning"),
    ]
    for gen, legacy in pairs:
        if models.get(gen) and not models.get(legacy):
            models[legacy] = models[gen]
        elif models.get(legacy) and not models.get(gen):
            models[gen] = models[legacy]
    merged["models"] = models

    # Repair stale Control Center tier bindings written by older model-picker
    # versions.  Retrieval models remain valid in models.embedding/reranker,
    # but are never valid as chat models for C0-C3 or Vision.
    routing = merged.get("routing") if isinstance(merged.get("routing"), dict) else {}
    tier_models = routing.get("tier_models") if isinstance(routing.get("tier_models"), dict) else {}
    if tier_models:
        routing = dict(routing)
        repaired = dict(tier_models)
        changed = False
        for tier, entry in list(repaired.items()):
            if not isinstance(entry, dict):
                continue
            selected = str(entry.get("model") or "").strip()
            if not selected or not any(k in selected.lower() for k in ("embedding", "embed", "rerank")):
                continue
            provider_id = str(entry.get("provider") or merged.get("backend", {}).get("type") or "").strip()
            route_key = {"C0": "simple", "C1": "office", "C2": "office", "C3": "reasoning", "Vision": "vision"}.get(str(tier), "office")
            try:
                from .providers import coerce_model_for_provider
                fallback = coerce_model_for_provider(provider_id, selected, route_key=route_key)
            except Exception:  # noqa: BLE001
                fallback = ""
            if fallback and fallback != selected:
                fixed = dict(entry)
                fixed["model"] = fallback
                fixed["repaired_from"] = selected
                repaired[tier] = fixed
                changed = True
        if changed:
            routing["tier_models"] = repaired
            merged["routing"] = routing

    # Normalize composer thinking depth + Claws Control Center prefs
    ali = merged.get("ali") if isinstance(merged.get("ali"), dict) else {}
    if isinstance(ali, dict):
        from . import routing as routing_mod
        from . import runtimes as runtimes_mod

        ali = dict(ali)
        language = str(ali.get("language") or "zh").strip().lower()
        ali["language"] = language if language in ("zh", "en", "auto") else "zh"
        language_mode = str(ali.get("language_mode") or ali["language"]).strip().lower()
        ali["language_mode"] = language_mode if language_mode in ("zh", "en", "auto") else "auto"
        ali["thinking_depth"] = routing_mod.normalize_thinking_depth(
            ali.get("thinking_depth"), "medium"
        )
        active = str(ali.get("agent_runtime") or "auto").strip() or "auto"
        if active != "auto" and not runtimes_mod.get_runtime(active):
            active = "auto"
        ali["agent_runtime"] = active
        ali["auto_runtime"] = runtimes_mod.normalize_auto_runtime(
            str(ali.get("auto_runtime") or "")
        )
        merged["ali"] = ali

    # Strip internal warning from disk file but keep in return
    warning = merged.pop("_warning", None)
    to_write = {k: v for k, v in merged.items() if not str(k).startswith("_")}
    CAMPUS_CONFIG_FILE.write_text(
        json.dumps(to_write, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if warning:
        merged["_warning"] = warning
    return merged


def import_campus_config(path: str) -> dict[str, Any]:
    src = Path(path).expanduser()
    if not src.is_file():
        raise FileNotFoundError(f"config not found: {src}")
    data = json.loads(src.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("config must be a JSON object")
    return save_campus_config(data, preserve_existing=False)


def export_campus_config(dest: str) -> str:
    cfg = load_campus_config()
    out = Path(dest).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(out)


def api_key_status(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    from .secrets import public_key_status

    return public_key_status(cfg)


def public_settings_view() -> dict[str, Any]:
    from .providers import catalog_payload, model_options_payload
    from . import websearch

    cfg = load_campus_config()
    return {
        "config": cfg,
        "config_path": str(CAMPUS_CONFIG_FILE),
        "api_key": api_key_status(cfg),
        "defaults": DEFAULT_CAMPUS,
        "catalog": catalog_payload(),
        "model_options": model_options_payload(cfg),
        "model_governance": public_model_governance_view(cfg),
        "search": websearch.search_status(),
    }


def public_model_governance_view(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return health, profiles, and independent category Auto decisions."""
    config = cfg if isinstance(cfg, dict) else load_campus_config()
    health_cache = config.get("model_health_cache")
    health_cache = health_cache if isinstance(health_cache, dict) else {}
    stored_profiles = config.get("model_profiles")
    stored_profiles = stored_profiles if isinstance(stored_profiles, dict) else {}
    category_models = config.get("category_models")
    category_models = category_models if isinstance(category_models, dict) else {}
    category_auto = config.get("category_auto")
    category_auto = category_auto if isinstance(category_auto, dict) else {}

    try:
        from .model_intelligence import (
            filter_healthy_models,
            normalize_health_record,
            recommend_category_models,
            upgrade_model_profile,
        )

        normalized_health = {
            str(model): normalize_health_record(record, model=str(model))
            for model, record in health_cache.items()
            if isinstance(record, dict)
        }
        profiles = []
        for model, raw in stored_profiles.items():
            if not isinstance(raw, dict):
                continue
            profile = upgrade_model_profile(str(model), raw, health=normalized_health.get(model))
            profiles.append(profile)
        manual = {
            category: str(category_models.get(category) or "")
            for category in MODEL_CATEGORIES
            if not bool(category_auto.get(category, True))
        }
        active_provider = str((config.get("backend") or {}).get("type") or "").strip()
        active_profiles = [
            profile for profile in profiles
            if not active_provider or not profile.get("provider") or profile.get("provider") == active_provider
        ]
        recommendations = recommend_category_models(active_profiles, manual_models=manual)
        selectable = filter_healthy_models(active_profiles)
    except (ImportError, TypeError, ValueError):
        normalized_health = deepcopy(health_cache)
        profiles = [deepcopy(item) for item in stored_profiles.values() if isinstance(item, dict)]
        recommendations = {}
        selectable = []

    return {
        "health": normalized_health,
        "profiles": profiles,
        "selectable_models": [str(item.get("model") or "") for item in selectable],
        "category_models": {category: str(category_models.get(category) or "") for category in MODEL_CATEGORIES},
        "category_auto": {category: bool(category_auto.get(category, True)) for category in MODEL_CATEGORIES},
        "recommendations": recommendations,
        "fusion": {
            "mode": config.get("fusion_mode") or "auto",
            "token_budget": deepcopy(config.get("fusion_token_budget") or DEFAULT_FUSION_TOKEN_BUDGET),
            "judge_model": str(config.get("fusion_judge_model") or ""),
        },
    }


def copy_example_to_state(example_path: Path) -> str:
    ensure_state_dirs()
    if not CAMPUS_CONFIG_FILE.is_file() and example_path.is_file():
        shutil.copy2(example_path, CAMPUS_CONFIG_FILE)
    return str(CAMPUS_CONFIG_FILE)
