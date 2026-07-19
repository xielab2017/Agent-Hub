"""Model health probing, capability profiling, and automatic model selection."""

from __future__ import annotations

import concurrent.futures
import json
import threading
import time
import urllib.error
from typing import Any

from . import llm_client


_RUN_LOCK = threading.Lock()
_RUNNING = False


def analyze_model(model_id: str) -> dict[str, Any]:
    """Build a deterministic capability profile from a provider model id."""
    mid = str(model_id or "").strip()
    low = mid.lower()
    dedicated = "chat"
    if any(x in low for x in ("embed", "retriever", "nvclip", "bge-", "arctic-embed")):
        dedicated = "embedding"
    elif "rerank" in low:
        dedicated = "reranker"
    elif any(x in low for x in ("parse", "detector", "reward")):
        dedicated = "specialized"

    capabilities = ["chat"] if dedicated == "chat" else [dedicated]
    rules = {
        "vision": ("vision", "vl", "vila", "fuyu", "kosmos", "neva", "omni"),
        "code": ("code", "coder", "starcoder", "codestral", "gpt-oss", "qwen"),
        "reasoning": ("reason", "r1", "nemotron", "thinking", "glm-5", "deepseek", "qwen3"),
        "long_context": ("128k", "maverick", "kimi", "long", "large-3", "qwen3.5"),
        "safety": ("guard", "safety", "nemoguard"),
        "translation": ("translate", "sarvam"),
    }
    for name, needles in rules.items():
        if any(x in low for x in needles):
            capabilities.append(name)

    size = 0
    import re
    sizes = [int(x) for x in re.findall(r"(?<![.\d])(\d{1,3})b(?:-|$)", low)]
    if sizes:
        size = max(sizes)
    speed = 5 if 0 < size <= 10 else 4 if size <= 30 else 3 if size <= 80 else 2
    quality = 2 if size and size <= 4 else 3 if size <= 30 else 4 if size <= 120 else 5
    if any(x in low for x in ("flash", "nano", "mini", "small")):
        speed = min(5, speed + 1)
    if any(x in low for x in ("pro", "ultra", "super", "397b", "550b")):
        quality = 5
    return {
        "model": mid,
        "kind": dedicated,
        "capabilities": sorted(set(capabilities)),
        "speed_score": speed,
        "quality_score": quality,
        "size_b": size or None,
    }


def _probe_chat(base_url: str, api_key: str, model: str, timeout: float, verify_tls: bool) -> dict[str, Any]:
    url = llm_client.chat_completions_url(base_url)
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply OK"}],
        "max_tokens": 1,
        "temperature": 0.2,
        "stream": False,
    }
    try:
        with llm_client._request(  # shared TLS/auth behavior
            "POST", url, api_key=api_key, body=body, timeout=timeout,
            verify_tls=verify_tls,
        ) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        ok = isinstance(payload.get("choices"), list) and bool(payload["choices"])
        return {"ok": ok, "status": int(getattr(resp, "status", 200)), "error": ""}
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:  # noqa: BLE001
            detail = str(exc)
        return {"ok": False, "status": exc.code, "error": detail}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": 0, "error": f"{type(exc).__name__}: {exc}"[:300]}


def probe_models(
    base_url: str,
    api_key: str,
    models: list[str],
    *,
    timeout: float = 20,
    verify_tls: bool = True,
    workers: int = 8,
) -> dict[str, dict[str, Any]]:
    """Quickly probe chat-capable candidates; classify dedicated models without mislabelling them."""
    now = int(time.time())

    def one(mid: str) -> tuple[str, dict[str, Any]]:
        profile = analyze_model(mid)
        if profile["kind"] != "chat":
            return mid, {
                **profile, "ok": False, "chat_compatible": False,
                "status": 0, "latency_s": None, "checked_at": now,
                "state": "dedicated", "error": "dedicated non-chat model",
            }
        started = time.monotonic()
        result = _probe_chat(base_url, api_key, mid, timeout, verify_tls)
        latency = round(time.monotonic() - started, 2)
        status = int(result.get("status") or 0)
        state = "available" if result.get("ok") else (
            "transient" if status == 0 or status == 429 or status >= 500 else "unavailable"
        )
        return mid, {
            **profile, **result, "chat_compatible": bool(result.get("ok")),
            "latency_s": latency, "checked_at": now, "state": state,
        }

    output: dict[str, dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(workers, 12))) as pool:
        for mid, result in pool.map(one, models):
            output[mid] = result
    return output


def choose_auto_model(cfg: dict[str, Any], message: str, tier: str) -> str:
    """Choose the best currently healthy chat model for the request."""
    provider = str((cfg.get("backend") or {}).get("type") or "")
    health = ((cfg.get("model_health") or {}).get(provider) or {})
    candidates = [v for v in health.values() if isinstance(v, dict) and v.get("chat_compatible")]
    if not candidates:
        return ""
    low = str(message or "").lower()
    wanted: set[str] = set()
    if tier == "Vision": wanted.add("vision")
    if tier == "C3": wanted.add("reasoning")
    if tier == "C2": wanted.add("long_context")
    if any(x in low for x in ("代码", "编程", "debug", "bug", "code", "python", "javascript")):
        wanted.add("code")

    def score(item: dict[str, Any]) -> tuple[float, float, str]:
        caps = set(item.get("capabilities") or [])
        missing_required = 1 if tier == "Vision" and "vision" not in caps else 0
        match = len(wanted & caps) * 20
        quality = float(item.get("quality_score") or 0)
        speed = float(item.get("speed_score") or 0)
        latency = float(item.get("latency_s") or 30)
        tier_score = speed * 3 - latency / 10 if tier == "C0" else quality * 4 + speed
        return (-missing_required * 100 + match + tier_score, -latency, str(item.get("model") or ""))

    return str(max(candidates, key=score).get("model") or "")


def recommend_category_models(health: dict[str, dict[str, Any]]) -> dict[str, str]:
    """Recommend one healthy model for every system category.

    Recommendations are computed independently: C0 favors latency, C1 balance,
    C2 long context/quality, C3 reasoning/code, and Vision requires multimodal.
    Dedicated retrieval roles are selected only from their own model kinds.
    """
    chat = [x for x in health.values() if isinstance(x, dict) and x.get("chat_compatible")]

    def pick(category: str) -> str:
        required = "vision" if category == "Vision" else ""
        candidates = [x for x in chat if not required or required in set(x.get("capabilities") or [])]
        if not candidates:
            return ""

        def rank(x: dict[str, Any]) -> tuple[float, float, str]:
            caps = set(x.get("capabilities") or [])
            q = float(x.get("quality_score") or 0)
            s = float(x.get("speed_score") or 0)
            latency = float(x.get("latency_s") or 30)
            low = str(x.get("model") or "").lower()
            # Safety/guard/translation models are valid endpoints but poor
            # general assistants, so keep them out of automatic core roles.
            penalty = 80 if caps & {"safety", "translation"} else 0
            if category == "C0": value = s * 12 - latency
            elif category == "C1": value = q * 7 + s * 5 - latency / 2
            elif category == "C2": value = q * 10 + (20 if "long_context" in caps else 0) + s - latency / 3
            elif category == "C3": value = q * 10 + (22 if "reasoning" in caps else 0) + (8 if "code" in caps else 0) - latency / 3
            else:
                exact_vision = 20 if any(k in low for k in ("vision", "-vl", "vl-")) else 5 if "omni" in low else 0
                value = q * 8 + s * 3 + exact_vision - latency / 2
            if any(k in low for k in ("guard", "safety", "translate")):
                penalty += 40
            return (value - penalty, -latency, str(x.get("model") or ""))
        return str(max(candidates, key=rank).get("model") or "")

    out = {tier: pick(tier) for tier in ("C0", "C1", "C2", "C3", "Vision")}
    for role, kind in (("Embedding", "embedding"), ("Reranker", "reranker")):
        dedicated = [x for x in health.values() if isinstance(x, dict) and x.get("kind") == kind]
        if dedicated:
            dedicated.sort(key=lambda x: (float(x.get("quality_score") or 0), str(x.get("model") or "")), reverse=True)
            out[role] = str(dedicated[0].get("model") or "")
        else:
            out[role] = ""
    return out


def refresh_provider_models(*, force: bool = False, deep: bool = True) -> dict[str, Any]:
    """Fetch, probe, profile and persist the active provider's model catalog."""
    from .secrets import resolve_api_key
    from .settings import load_campus_config, resolve_backend_verify_tls, save_campus_config

    cfg = load_campus_config()
    backend = cfg.get("backend") or {}
    provider = str(backend.get("type") or "")
    if provider in ("", "hybrid", "local-ollama"):
        return {"ok": False, "error": "active provider is not probeable", "provider": provider}
    key_info = resolve_api_key(cfg, provider=provider)
    if not key_info.get("present"):
        return {"ok": False, "error": "API key missing", "provider": provider}
    base_url = str(backend.get("base_url") or "")
    listed = llm_client.list_models(base_url, key_info.get("key") or "", timeout=30,
                                    verify_tls=resolve_backend_verify_tls(cfg, {"provider": provider}))
    if not listed.get("ok"):
        return listed
    models = [str(x) for x in listed.get("models") or []]
    health = probe_models(
        base_url, key_info.get("key") or "", models,
        timeout=min(30, float(backend.get("model_probe_timeout_seconds") or 15)),
        verify_tls=resolve_backend_verify_tls(cfg, {"provider": provider}),
        workers=int(backend.get("model_probe_workers") or 8),
    ) if deep else {m: analyze_model(m) for m in models}
    cfg.setdefault("available_models", {})[provider] = models
    cfg.setdefault("model_health", {})[provider] = health
    recommendations = recommend_category_models(health)
    cfg.setdefault("model_recommendations", {})[provider] = recommendations
    cfg.setdefault("model_health_meta", {})[provider] = {
        "checked_at": int(time.time()), "catalog_count": len(models),
        "available_count": sum(1 for x in health.values() if x.get("chat_compatible")),
    }
    save_campus_config(cfg)
    return {
        "ok": True, "provider": provider, "catalog_count": len(models),
        "available_count": sum(1 for x in health.values() if x.get("chat_compatible")),
        "models": [m for m in models if health.get(m, {}).get("chat_compatible")],
        "health": health, "recommendations": recommendations,
    }


def start_startup_refresh(max_age_seconds: int = 21600) -> bool:
    """Start one non-blocking refresh when the cache is stale."""
    global _RUNNING
    from .settings import load_campus_config
    cfg = load_campus_config()
    provider = str((cfg.get("backend") or {}).get("type") or "")
    checked = int((((cfg.get("model_health_meta") or {}).get(provider) or {}).get("checked_at") or 0))
    if checked and time.time() - checked < max_age_seconds:
        return False
    with _RUN_LOCK:
        if _RUNNING:
            return False
        _RUNNING = True

    def run() -> None:
        global _RUNNING
        try:
            refresh_provider_models(force=True, deep=True)
        finally:
            with _RUN_LOCK:
                _RUNNING = False
    threading.Thread(target=run, daemon=True, name="model-health-refresh").start()
    return True
