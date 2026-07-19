"""Model health, capability profiling, and category-aware Auto selection.

The module is intentionally provider-agnostic.  Callers supply a lightweight
probe function for health checks and may persist results through
``ModelIntelligenceCache``.  No network request is made at import time.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urljoin


HEALTH_STATES = (
    "healthy",
    "degraded",
    "timeout",
    "unsupported",
    "unavailable",
    "untested",
)
SELECTABLE_HEALTH_STATES = frozenset({"healthy", "degraded"})
CATEGORIES = ("C0", "C1", "C2", "C3", "Vision", "Embedding", "Reranker")
PROBE_CAPABILITIES = ("chat", "vision", "embedding", "reranker", "tool_calling", "reasoning")
DEFAULT_CACHE_TTL_SECONDS = 24 * 60 * 60
CACHE_SCHEMA_VERSION = 1

_CAPABILITY_KEYS = (
    "chat",
    "vision",
    "embedding",
    "reranker",
    "tool_calling",
    "reasoning",
    "coding",
    "writing",
)


def _now() -> float:
    return time.time()


def _number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _unit(value: Any, default: float = 0.0) -> float:
    return max(0.0, min(1.0, _number(value, default)))


def _error_summary(value: Any, limit: int = 240) -> str:
    return " ".join(str(value or "").split())[:limit]


def normalize_health_record(
    record: Mapping[str, Any] | None,
    *,
    model: str = "",
    provider: str = "",
) -> dict[str, Any]:
    """Return a stable, backward-compatible health record."""
    raw = dict(record or {})
    state = str(raw.get("state") or raw.get("status") or "untested").lower()
    if state not in HEALTH_STATES:
        state = "untested"
    tested_at = _number(raw.get("tested_at", raw.get("checked_at")), 0.0)
    latency = raw.get("latency_ms")
    latency_ms = max(0.0, _number(latency, 0.0)) if latency is not None else None
    return {
        **raw,
        "model": str(raw.get("model") or model),
        "provider": str(raw.get("provider") or provider),
        "state": state,
        "status": state,
        "healthy": state in SELECTABLE_HEALTH_STATES,
        "tested_at": tested_at,
        "latency_ms": latency_ms,
        "error": _error_summary(raw.get("error") or raw.get("error_summary")),
    }


def is_health_cache_fresh(
    record: Mapping[str, Any] | None,
    *,
    ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
    now: float | None = None,
) -> bool:
    normalized = normalize_health_record(record)
    if normalized["state"] == "untested" or normalized["tested_at"] <= 0:
        return False
    age = (now if now is not None else _now()) - normalized["tested_at"]
    return 0 <= age < max(0.0, ttl_seconds)


def health_record_from_probe(
    model: str,
    result: Mapping[str, Any] | None,
    *,
    provider: str = "nvidia-nim",
    latency_ms: float | None = None,
    tested_at: float | None = None,
) -> dict[str, Any]:
    """Classify a provider probe result into one of the public health states."""
    raw = dict(result or {})
    error = _error_summary(raw.get("error") or raw.get("message"))
    status_code = int(_number(raw.get("status_code", raw.get("http_status")), 0))
    content = raw.get("content", raw.get("text", raw.get("output")))
    raw_status = raw.get("status")
    if not status_code and isinstance(raw_status, (int, float)):
        status_code = int(raw_status)
    explicit = str(raw.get("state") or (raw_status if isinstance(raw_status, str) else "") or "").lower()

    if explicit in HEALTH_STATES:
        state = explicit
    elif raw.get("timeout") or "timeout" in error.lower() or "timed out" in error.lower():
        state = "timeout"
    elif status_code in (404, 405, 422) or raw.get("unsupported"):
        state = "unsupported"
    elif status_code >= 400 or raw.get("ok") is False or raw.get("available") is False:
        state = "unavailable"
    elif content is not None and not str(content).strip():
        state = "unavailable"
        error = error or "empty response"
    elif raw.get("degraded"):
        state = "degraded"
    elif explicit in ("ok", "available", "success") or raw.get("ok") is True or raw.get("available") is True or content is not None:
        state = "healthy"
    elif explicit in ("error", "failed", "failure"):
        state = "unavailable"
    else:
        state = "untested"

    measured_latency = latency_ms if latency_ms is not None else raw.get("latency_ms")
    return normalize_health_record(
        {
            "model": model,
            "provider": provider,
            "state": state,
            "tested_at": tested_at if tested_at is not None else _now(),
            "latency_ms": measured_latency,
            "error": error,
            "capability": str(raw.get("capability") or "chat"),
        }
    )


def quick_health_check(
    model: str,
    probe: Callable[[str], Mapping[str, Any]],
    *,
    provider: str = "nvidia-nim",
    capability: str = "chat",
    clock: Callable[[], float] = time.perf_counter,
) -> dict[str, Any]:
    """Run an injected quick probe and normalize errors without raising."""
    started = clock()
    try:
        result = dict(probe(model) or {})
    except TimeoutError as exc:
        result = {"timeout": True, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - provider errors become health data
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    latency_ms = max(0.0, (clock() - started) * 1000.0)
    result.setdefault("capability", capability)
    return health_record_from_probe(
        model,
        result,
        provider=provider,
        latency_ms=latency_ms,
    )


def probe_model_capabilities(
    model: str,
    probes: Mapping[str, Callable[[str], Mapping[str, Any]]],
    *,
    provider: str = "nvidia-nim",
) -> dict[str, dict[str, Any]]:
    """Run only the supplied capability probes and keep their states separate."""
    return {
        capability: quick_health_check(
            model,
            probe,
            provider=provider,
            capability=capability,
        )
        for capability, probe in probes.items()
        if capability in PROBE_CAPABILITIES
    }


class ModelIntelligenceCache:
    """JSON cache for health records and model profiles with atomic writes."""

    def __init__(self, path: str | os.PathLike[str], *, ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS):
        self.path = Path(path)
        self.ttl_seconds = ttl_seconds
        self.data: dict[str, Any] = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "health": {},
            "profiles": {},
        }
        self.load()

    def load(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return self.data
        if not isinstance(payload, dict):
            return self.data
        health = payload.get("health", payload.get("model_health_cache", {}))
        profiles = payload.get("profiles", payload.get("model_profiles", {}))
        self.data = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "health": dict(health) if isinstance(health, dict) else {},
            "profiles": dict(profiles) if isinstance(profiles, dict) else {},
        }
        return self.data

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self.data, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(temporary, self.path)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    def get_health(
        self,
        model: str,
        *,
        capability: str | None = None,
        allow_stale: bool = True,
    ) -> dict[str, Any] | None:
        raw = self.data["health"].get(model)
        if not isinstance(raw, dict):
            return None
        if capability:
            checks = raw.get("capability_checks")
            raw = checks.get(capability) if isinstance(checks, dict) else None
            if not isinstance(raw, dict):
                return None
        record = normalize_health_record(raw, model=model)
        if not allow_stale and not is_health_cache_fresh(record, ttl_seconds=self.ttl_seconds):
            return None
        return record

    def set_health(
        self,
        model: str,
        record: Mapping[str, Any],
        *,
        capability: str | None = None,
    ) -> dict[str, Any]:
        normalized = normalize_health_record(record, model=model)
        if capability:
            if capability not in PROBE_CAPABILITIES:
                raise ValueError(f"unknown probe capability: {capability}")
            current = self.data["health"].get(model)
            entry = dict(current) if isinstance(current, dict) else normalize_health_record({}, model=model)
            checks = dict(entry.get("capability_checks") or {})
            normalized["capability"] = capability
            checks[capability] = normalized
            entry["capability_checks"] = checks
            self.data["health"][model] = entry
        else:
            existing = self.data["health"].get(model)
            if isinstance(existing, dict) and isinstance(existing.get("capability_checks"), dict):
                normalized["capability_checks"] = existing["capability_checks"]
            self.data["health"][model] = normalized
        return deepcopy(normalized)

    def get_profile(self, model: str) -> dict[str, Any] | None:
        profile = self.data["profiles"].get(model)
        return deepcopy(profile) if isinstance(profile, dict) else None

    def set_profile(self, model: str, profile: Mapping[str, Any]) -> dict[str, Any]:
        value = deepcopy(dict(profile))
        value["model"] = str(value.get("model") or model)
        self.data["profiles"][model] = value
        return deepcopy(value)

    def models_requiring_test(
        self,
        models: Iterable[str],
        *,
        capability: str | None = None,
        now: float | None = None,
    ) -> list[str]:
        """Return new or expired models, optionally for one capability probe."""
        return [
            model
            for model in dict.fromkeys(str(item) for item in models if str(item).strip())
            if not is_health_cache_fresh(
                self.get_health(model, capability=capability),
                ttl_seconds=self.ttl_seconds,
                now=now,
            )
        ]


# Backward-friendly short name for callers that used the plan terminology.
ModelHealthCache = ModelIntelligenceCache


def _name_capabilities(model: str) -> dict[str, Any]:
    """Conservative fallback only; metadata and measured results override it."""
    name = model.lower()
    retrieval = "embed" in name or "rerank" in name
    vision = any(token in name for token in ("vision", "-vl", "/vl", "llava", "multimodal"))
    reasoning = any(token in name for token in ("reason", "thinking", "nemotron", "deepseek-r1", "o1", "o3", "o4"))
    coding = 0.8 if any(token in name for token in ("code", "coder", "codestral", "deepseek")) else 0.45
    writing = 0.7 if any(token in name for token in ("instruct", "chat", "qwen", "llama")) else 0.5
    return {
        "chat": not retrieval,
        "vision": vision,
        "embedding": "embed" in name,
        "reranker": "rerank" in name,
        "tool_calling": False,
        "reasoning": reasoning,
        "coding": coding,
        "writing": writing,
    }


def _capabilities_from_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = dict(metadata or {})
    result: dict[str, Any] = {}
    declared = raw.get("capabilities")
    if isinstance(declared, Mapping):
        result.update({key: declared[key] for key in _CAPABILITY_KEYS if key in declared})
    elif isinstance(declared, (list, tuple, set)):
        labels = {str(item).lower().replace("-", "_") for item in declared}
        result.update({key: key in labels for key in _CAPABILITY_KEYS if key not in ("coding", "writing")})
    task = str(raw.get("task") or raw.get("type") or "").lower()
    if task in ("embedding", "embed"):
        result.update({"chat": False, "embedding": True})
    elif task in ("reranking", "reranker", "rerank"):
        result.update({"chat": False, "reranker": True})
    elif task in ("vision", "multimodal"):
        result.update({"chat": True, "vision": True})
    return result


def _merge_capabilities(*sources: Mapping[str, Any] | None) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for source in sources:
        if not isinstance(source, Mapping):
            continue
        for key in _CAPABILITY_KEYS:
            if key in source:
                value = source[key]
                merged[key] = _unit(value) if key in ("coding", "writing") else bool(value)
    return {key: merged.get(key, 0.0 if key in ("coding", "writing") else False) for key in _CAPABILITY_KEYS}


def recommend_categories(profile: Mapping[str, Any]) -> list[str]:
    capabilities = profile.get("capabilities") if isinstance(profile.get("capabilities"), Mapping) else {}
    if capabilities.get("embedding"):
        return ["Embedding"]
    if capabilities.get("reranker"):
        return ["Reranker"]
    categories: list[str] = []
    if capabilities.get("chat"):
        categories.extend(("C0", "C1"))
    if _unit(capabilities.get("coding")) >= 0.65:
        categories.append("C2")
    if capabilities.get("reasoning"):
        categories.append("C3")
    if capabilities.get("vision"):
        categories.append("Vision")
    return [category for category in CATEGORIES if category in categories]


def build_model_profile(
    model: str,
    *,
    provider: str = "nvidia-nim",
    health: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    measured_capabilities: Mapping[str, Any] | None = None,
    manual_override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a capability profile using evidence before name heuristics.

    Name rules provide conservative defaults. Provider metadata supersedes
    those defaults, measured tests supersede metadata, and an explicit human
    override is applied last.
    """
    override = dict(manual_override or {})
    override_caps = override.get("capabilities") if isinstance(override.get("capabilities"), Mapping) else {}
    capabilities = _merge_capabilities(
        _name_capabilities(model),
        _capabilities_from_metadata(metadata),
        measured_capabilities,
        override_caps,
    )
    normalized_health = normalize_health_record(health, model=model, provider=provider)
    performance_source: dict[str, Any] = {}
    if isinstance(metadata, Mapping) and isinstance(metadata.get("performance"), Mapping):
        performance_source.update(metadata["performance"])
    if isinstance(override.get("performance"), Mapping):
        performance_source.update(override["performance"])
    performance = {
        "latency_ms": normalized_health.get("latency_ms"),
        "stability": _unit(performance_source.get("stability"), 0.5),
        "quality_score": _unit(performance_source.get("quality_score"), 0.5),
        "cost_score": _unit(performance_source.get("cost_score"), 0.5),
    }
    profile: dict[str, Any] = {
        "model": model,
        "provider": provider,
        "healthy": normalized_health["healthy"],
        "health_state": normalized_health["state"],
        "health": normalized_health,
        "capabilities": capabilities,
        "performance": performance,
        "recommended_categories": [],
        "profiled_at": _now(),
    }
    profile["recommended_categories"] = recommend_categories(profile)
    manual_categories = override.get("recommended_categories")
    if isinstance(manual_categories, (list, tuple)):
        profile["recommended_categories"] = [item for item in CATEGORIES if item in manual_categories]
    for key, value in override.items():
        if key not in ("capabilities", "performance", "recommended_categories"):
            profile[key] = deepcopy(value)
    return profile


def filter_healthy_models(
    profiles: Iterable[Mapping[str, Any]],
    *,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """Hide untested/unavailable models and optionally require category fit."""
    result = []
    for raw in profiles:
        profile = deepcopy(dict(raw))
        state = str(profile.get("health_state") or (profile.get("health") or {}).get("state") or "untested")
        if state not in SELECTABLE_HEALTH_STATES and not (state == "untested" and profile.get("healthy") is True):
            continue
        if category and category not in profile.get("recommended_categories", []):
            continue
        result.append(profile)
    return result


def score_model_for_category(profile: Mapping[str, Any], category: str) -> float:
    """Score quality, stability, latency, cost, and capability fit for Auto."""
    if category not in CATEGORIES or category not in profile.get("recommended_categories", []):
        return float("-inf")
    performance = profile.get("performance") if isinstance(profile.get("performance"), Mapping) else {}
    capabilities = profile.get("capabilities") if isinstance(profile.get("capabilities"), Mapping) else {}
    latency_ms = performance.get("latency_ms")
    latency_score = 0.5 if latency_ms is None else 1.0 / (1.0 + max(0.0, _number(latency_ms)) / 2000.0)
    ability = {
        "C0": 1.0 if capabilities.get("chat") else 0.0,
        "C1": _unit(capabilities.get("writing"), 0.5),
        "C2": _unit(capabilities.get("coding"), 0.5),
        "C3": 1.0 if capabilities.get("reasoning") else 0.0,
        "Vision": 1.0 if capabilities.get("vision") else 0.0,
        "Embedding": 1.0 if capabilities.get("embedding") else 0.0,
        "Reranker": 1.0 if capabilities.get("reranker") else 0.0,
    }[category]
    health_penalty = 0.08 if profile.get("health_state") == "degraded" else 0.0
    score = (
        0.35 * _unit(performance.get("quality_score"), 0.5)
        + 0.20 * _unit(performance.get("stability"), 0.5)
        + 0.15 * latency_score
        + 0.10 * _unit(performance.get("cost_score"), 0.5)
        + 0.20 * ability
        - health_penalty
    )
    return round(score, 6)


def recommend_model(
    profiles: Iterable[Mapping[str, Any]],
    category: str,
    *,
    manual_model: str = "",
    fallback_to_auto: bool = True,
) -> dict[str, Any]:
    """Resolve manual selection or the best healthy category-compatible model."""
    if category not in CATEGORIES:
        raise ValueError(f"unknown category: {category}")
    candidates = filter_healthy_models(profiles, category=category)
    if manual_model:
        selected = next((item for item in candidates if item.get("model") == manual_model), None)
        if selected:
            return {"category": category, "model": manual_model, "profile": selected, "source": "manual", "fallback_reason": ""}
        if not fallback_to_auto:
            return {"category": category, "model": "", "profile": None, "source": "manual", "fallback_reason": "manual model is unavailable or incompatible"}
    ranked = sorted(
        candidates,
        key=lambda item: (score_model_for_category(item, category), str(item.get("model") or "")),
        reverse=True,
    )
    selected = ranked[0] if ranked else None
    return {
        "category": category,
        "model": str(selected.get("model") or "") if selected else "",
        "profile": selected,
        "source": "auto",
        "score": score_model_for_category(selected, category) if selected else None,
        "fallback_reason": "manual model is unavailable or incompatible" if manual_model else ("no healthy compatible model" if not selected else ""),
    }


def recommend_category_models(
    profiles: Iterable[Mapping[str, Any]],
    *,
    manual_models: Mapping[str, str] | None = None,
    fallback_to_auto: bool = True,
) -> dict[str, dict[str, Any]]:
    """Return an independent Auto/manual decision for every system category."""
    materialized = list(profiles)
    overrides = manual_models or {}
    return {
        category: recommend_model(
            materialized,
            category,
            manual_model=str(overrides.get(category) or ""),
            fallback_to_auto=fallback_to_auto,
        )
        for category in CATEGORIES
    }


def select_configured_category_model(
    config: Mapping[str, Any],
    category: str,
    *,
    provider: str = "",
) -> dict[str, Any]:
    """Resolve the live Auto/manual model for one routing category.

    The settings view already exposes category recommendations; this helper is
    the execution-side counterpart.  It deliberately limits candidates to the
    active provider so a stale profile from an old backend cannot redirect a
    normal single-provider request to another vendor.
    """
    profiles_raw = config.get("model_profiles")
    if not isinstance(profiles_raw, Mapping):
        profiles_raw = {}
    active_provider = str(provider or "").strip()
    profiles = []
    for model, raw in profiles_raw.items():
        if not isinstance(raw, Mapping):
            continue
        item = dict(raw)
        item["model"] = str(item.get("model") or model)
        item_provider = str(item.get("provider") or "").strip()
        if active_provider and item_provider and item_provider != active_provider:
            continue
        profiles.append(item)

    category_auto = config.get("category_auto")
    category_auto = category_auto if isinstance(category_auto, Mapping) else {}
    category_models = config.get("category_models")
    category_models = category_models if isinstance(category_models, Mapping) else {}
    is_auto = bool(category_auto.get(category, True))
    manual_model = "" if is_auto else str(category_models.get(category) or "").strip()
    result = recommend_model(profiles, category, manual_model=manual_model)
    return {**result, "provider": active_provider, "auto": is_auto}


_JOB_LOCK = threading.RLock()
_JOBS: dict[str, dict[str, Any]] = {}


def _capability_for_model(model: str) -> str:
    name = model.lower()
    if "rerank" in name:
        return "reranker"
    if "embed" in name:
        return "embedding"
    return "chat"


def _probe_openai_capability(
    base_url: str,
    api_key: str,
    model: str,
    capability: str,
    *,
    timeout: float = 8.0,
    verify_tls: bool = True,
) -> dict[str, Any]:
    """Run a minimal real request against an OpenAI-compatible endpoint."""
    from . import llm_client

    base = llm_client._normalize_base(base_url)
    if capability == "embedding":
        endpoint = "embeddings"
        body = {"model": model, "input": "health check"}
    elif capability == "reranker":
        endpoint = "reranking"
        body = {"model": model, "query": "health check", "passages": [{"text": "health check"}]}
    else:
        endpoint = "chat/completions"
        body = {
            "model": model,
            "messages": [{"role": "user", "content": "Reply OK."}],
            "max_tokens": 2,
            "temperature": 0,
        }
        if capability == "tool_calling":
            body["tools"] = [{
                "type": "function",
                "function": {
                    "name": "health_check",
                    "description": "Return a health signal",
                    "parameters": {"type": "object", "properties": {}},
                },
            }]
            body["tool_choice"] = "auto"
        elif capability == "vision":
            body["messages"] = [{
                "role": "user",
                "content": [
                    {"type": "text", "text": "What color is this pixel?"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z8p8AAAAASUVORK5CYII="}},
                ],
            }]
    try:
        with llm_client._request(
            "POST",
            urljoin(base, endpoint),
            api_key=api_key,
            body=body,
            timeout=timeout,
            verify_tls=verify_tls,
        ) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
        if capability == "embedding":
            ok = bool(payload.get("data"))
        elif capability == "reranker":
            ok = bool(payload.get("rankings") or payload.get("data"))
        else:
            ok = bool(payload.get("choices"))
        return {"ok": ok, "content": "ok" if ok else "", "error": "" if ok else "empty response"}
    except TimeoutError as exc:
        return {"ok": False, "timeout": True, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        status_code = int(getattr(exc, "code", 0) or 0)
        return {"ok": False, "status_code": status_code, "error": f"{type(exc).__name__}: {exc}"}


def governance_job(provider: str = "") -> dict[str, Any]:
    with _JOB_LOCK:
        if provider:
            return deepcopy(_JOBS.get(provider) or {"provider": provider, "status": "idle", "completed": 0, "total": 0})
        return {key: deepcopy(value) for key, value in _JOBS.items()}


def start_governance_analysis(
    *,
    provider: str,
    models: Iterable[str],
    base_url: str,
    api_key: str,
    verify_tls: bool = True,
    deep: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Start background health/profile analysis and persist results to settings."""
    provider_id = str(provider or "").strip()
    unique_models = list(dict.fromkeys(str(model).strip() for model in models if str(model).strip()))
    with _JOB_LOCK:
        current = _JOBS.get(provider_id) or {}
        if current.get("status") == "running":
            return deepcopy(current)
        job = {
            "provider": provider_id,
            "status": "running",
            "mode": "deep" if deep else "quick",
            "completed": 0,
            "total": len(unique_models),
            "healthy": 0,
            "hidden": 0,
            "started_at": _now(),
            "error": "",
        }
        _JOBS[provider_id] = job

    def worker() -> None:
        from .settings import load_campus_config, save_campus_config

        try:
            cfg = load_campus_config()
            cached = cfg.get("model_health_cache") if isinstance(cfg.get("model_health_cache"), dict) else {}
            profiles = cfg.get("model_profiles") if isinstance(cfg.get("model_profiles"), dict) else {}
            targets = unique_models if force else [
                model for model in unique_models
                if not is_health_cache_fresh(cached.get(model))
            ]
            with _JOB_LOCK:
                job["total"] = len(targets)
            if not targets:
                with _JOB_LOCK:
                    job.update({"status": "complete", "finished_at": _now()})
                return

            def analyze(model: str) -> tuple[str, dict[str, Any], dict[str, Any]]:
                primary_capability = _capability_for_model(model)
                record = quick_health_check(
                    model,
                    lambda item: _probe_openai_capability(
                        base_url, api_key, item, primary_capability,
                        timeout=10.0 if deep else 6.0,
                        verify_tls=verify_tls,
                    ),
                    provider=provider_id,
                    capability=primary_capability,
                )
                # Keep an independent snapshot. Reusing ``record`` here would
                # make record -> capability_checks -> record circular and
                # prevent the settings JSON from being persisted.
                checks: dict[str, Any] = {primary_capability: dict(record)}
                if deep and record["healthy"] and primary_capability == "chat":
                    predicted = _name_capabilities(model)
                    capabilities = ["reasoning", "tool_calling"]
                    if predicted.get("vision"):
                        capabilities.append("vision")
                    for capability in capabilities:
                        checks[capability] = quick_health_check(
                            model,
                            lambda item, cap=capability: _probe_openai_capability(
                                base_url, api_key, item, cap, timeout=10.0, verify_tls=verify_tls,
                            ),
                            provider=provider_id,
                            capability=capability,
                        )
                record["capability_checks"] = checks
                actual = {
                    cap: bool(check.get("healthy"))
                    for cap, check in checks.items()
                }
                profile = build_model_profile(
                    model,
                    provider=provider_id,
                    health=record,
                    measured_capabilities=actual,
                )
                return model, record, profile

            with ThreadPoolExecutor(max_workers=min(6, max(1, len(targets)))) as pool:
                futures = [pool.submit(analyze, model) for model in targets]
                for future in as_completed(futures):
                    model, record, profile = future.result()
                    cached[model] = record
                    profiles[model] = profile
                    with _JOB_LOCK:
                        job["completed"] += 1
                        if record["healthy"]:
                            job["healthy"] += 1
                        else:
                            job["hidden"] += 1

            latest = load_campus_config()
            latest_health = dict(latest.get("model_health_cache") or {})
            latest_profiles = dict(latest.get("model_profiles") or {})
            latest_health.update(cached)
            latest_profiles.update(profiles)
            latest["model_health_cache"] = latest_health
            latest["model_profiles"] = latest_profiles
            save_campus_config(latest)
            with _JOB_LOCK:
                job.update({"status": "complete", "finished_at": _now()})
        except Exception as exc:  # noqa: BLE001
            with _JOB_LOCK:
                job.update({"status": "error", "error": f"{type(exc).__name__}: {exc}", "finished_at": _now()})

    threading.Thread(target=worker, name=f"model-governance-{provider_id}", daemon=True).start()
    return deepcopy(job)


def start_startup_governance_refresh() -> dict[str, Any] | None:
    """Refresh stale cached model health after startup without blocking serve.

    A catalog must already have been fetched by the user.  This avoids an
    expensive provider-wide model listing during every launch while ensuring
    cached model availability and category choices do not drift forever.
    """
    from .secrets import resolve_api_key
    from .settings import load_campus_config, resolve_backend_verify_tls

    cfg = load_campus_config()
    backend = cfg.get("backend") if isinstance(cfg.get("backend"), Mapping) else {}
    provider = str(backend.get("type") or "").strip()
    catalogs = cfg.get("available_models") if isinstance(cfg.get("available_models"), Mapping) else {}
    models = catalogs.get(provider) if isinstance(catalogs.get(provider), list) else []
    if not provider or provider == "hybrid" or not models:
        return None
    key_info = resolve_api_key(cfg, provider=provider)
    base_url = str(backend.get("base_url") or "").strip()
    if not base_url or not key_info.get("present"):
        return None
    return start_governance_analysis(
        provider=provider,
        models=models,
        base_url=base_url,
        api_key=str(key_info.get("key") or ""),
        verify_tls=resolve_backend_verify_tls(cfg, {"provider": provider}),
        deep=False,
        force=False,
    )
