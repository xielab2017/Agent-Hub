"""Multi-vendor model connections ("多模型 API"): several vendors' keys and endpoints at once.

Saving a connection never switches ``backend.type``: the active backend (single vendor) or the hybrid tier map
decides who answers; connections only make vendors available with their own key, endpoint and TLS policy.
Keys live in the secrets store (``secrets.set_api_key(pid, …)``); config holds only non-secret fields.
"""

from __future__ import annotations

import time
from typing import Any

from .providers import PROVIDERS, connection, get_provider, key_provider_mismatch, list_connections


def _cfg() -> dict[str, Any]:
    from .settings import load_campus_config

    return load_campus_config()


def view() -> dict[str, Any]:
    cfg = _cfg()
    hybrid = cfg.get("hybrid") or {}
    return {"ok": True, "connections": list_connections(cfg),
            "mode": "hybrid" if str((cfg.get("backend") or {}).get("type") or "") == "hybrid" else "single",
            "backend": str((cfg.get("backend") or {}).get("type") or ""),
            "tiers": {rk: {"provider": (hybrid.get(rk) or {}).get("provider") or "",
                           "model": (hybrid.get(rk) or {}).get("model") or ""}
                      for rk in ("simple", "office", "reasoning", "vision")}}


def save(pid: str, body: dict[str, Any]) -> dict[str, Any]:
    """Save a vendor's key / endpoint / enabled flag (``api_key: ""`` with ``clear`` removes the key)."""
    from .secrets import mask_key, set_api_key
    from .settings import save_campus_config

    prov = get_provider(pid)
    if not prov or pid == "hybrid":
        raise ValueError(f"unknown provider: {pid}")
    key = str(body.get("api_key") or "").strip()
    if key:
        mismatch = key_provider_mismatch(pid, key)
        if mismatch:
            raise ValueError(mismatch.get("message") or "API key does not match this vendor")
        set_api_key(pid, key)
        if prov.get("api_key_env"):
            set_api_key(str(prov["api_key_env"]), key)
    elif body.get("clear"):
        set_api_key(pid, "")
        if prov.get("api_key_env"):
            set_api_key(str(prov["api_key_env"]), "")
    cfg = _cfg()
    conns = dict(cfg.get("connections") or {})
    conn = dict(conns.get(pid) or {})
    for field in ("enabled", "verify_tls", "custom_base_url"):
        if field in body:
            conn[field] = bool(body[field])
    if "base_url" in body:
        conn["base_url"] = str(body.get("base_url") or "").strip()
    if key and "enabled" not in body:
        conn["enabled"] = True
    conns[pid] = conn
    cfg["connections"] = conns
    save_campus_config(cfg)
    try:
        from . import audit

        audit.log_event("connection_save", {"provider": pid, "key": bool(key), "cleared": bool(body.get("clear")),
                                            "enabled": conn.get("enabled")})
    except Exception:  # noqa: BLE001
        pass
    out = connection(_cfg(), pid)
    out.pop("api_key", None)
    out["key_masked"] = mask_key(key) if key else out.get("key_masked")
    return {"ok": True, "connection": out}


def _probe_store(pid: str, result: dict[str, Any]) -> None:
    from .settings import save_campus_config

    cfg = _cfg()
    probes = dict(cfg.get("connection_probes") or {})
    probes[pid] = {"ok": bool(result.get("ok")), "count": int(result.get("count") or 0),
                   "via": result.get("via") or "models", "error": str(result.get("error") or "")[:300],
                   "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    cfg["connection_probes"] = probes
    if result.get("models"):
        avail = dict(cfg.get("available_models") or {})
        avail[pid] = list(result["models"])[:400]
        cfg["available_models"] = avail
    save_campus_config(cfg)


def test(pid: str, *, list_fn: Any = None, chat_fn: Any = None, timeout: float = 20.0) -> dict[str, Any]:
    """Check a vendor: list models, or (where /models is not offered) a one-token chat with a known model."""
    from . import llm_client

    list_fn = list_fn or llm_client.list_models
    c = connection(_cfg(), pid)
    if not c["base_url"]:
        return {"ok": False, "provider": pid, "error": "no base URL — set one for this vendor"}
    if not c["api_key"] and pid != "local-ollama":
        return {"ok": False, "provider": pid, "error": "no API key saved for this vendor"}
    result = dict(list_fn(c["base_url"], c["api_key"], timeout=timeout, verify_tls=c["verify_tls"]) or {})
    result.setdefault("via", "models")
    if not result.get("ok") and "401" not in str(result.get("error") or "") and "403" not in str(result.get("error") or ""):
        model = next(iter(c["models"]), "") or str((PROVIDERS[pid].get("models") or {}).get("main") or "")
        if model:
            chat_fn = chat_fn or _chat_ping
            chat = chat_fn(c["base_url"], c["api_key"], model=model, timeout=timeout, verify_tls=c["verify_tls"])
            if chat.get("ok"):
                result = {**chat, "via": "chat", "model": model}
    result["provider"] = pid
    _probe_store(pid, result)
    return {k: v for k, v in result.items() if k != "raw"}


def _chat_ping(base: str, key: str, *, model: str, timeout: float, verify_tls: bool) -> dict[str, Any]:
    from .llm_client import _chat_once

    try:
        _chat_once(base, key, model=model, messages=[{"role": "user", "content": "ping"}], timeout=timeout,
                   verify_tls=verify_tls, max_tokens=16)
        return {"ok": True, "models": [], "count": 0}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "models": [], "count": 0}


def route_test(message: str = "") -> dict[str, Any]:
    """Which vendor / model / endpoint each tier resolves to right now (no model call)."""
    from .routing import resolve_route

    cfg = _cfg()
    rows = []
    for rk, sample in (("simple", "你好"), ("office", "写一封会议通知"), ("reasoning", "证明这个定理"),
                       ("vision", "看这张图")):
        info = resolve_route(rk, message or sample, cfg)
        pid = str(info.get("provider") or "")
        c = connection(cfg, pid) if get_provider(pid) and pid != "hybrid" else {}
        rows.append({"route_key": rk, "tier": info.get("tier"), "provider": pid, "model": info.get("model"),
                     "base_url": info.get("base_url"), "key_present": bool(c.get("key_present")),
                     "blocked": bool(info.get("blocked"))})
    return {"ok": True, "routes": rows}


def set_tier(route_key: str, provider: str, model: str) -> dict[str, Any]:
    """Bind a tier to a vendor + model and switch the backend to hybrid (multi-vendor routing)."""
    from .settings import save_campus_config

    if route_key not in ("simple", "office", "reasoning", "vision"):
        raise ValueError(f"unknown tier: {route_key}")
    if provider and (not get_provider(provider) or provider == "hybrid"):
        raise ValueError(f"unknown provider: {provider}")
    cfg = _cfg()
    hybrid = dict(cfg.get("hybrid") or {})
    hybrid[route_key] = {"provider": provider, "model": model} if provider else {}
    cfg["hybrid"] = hybrid
    backend = dict(cfg.get("backend") or {})
    if backend.get("type") != "hybrid" and provider:
        prev = str(backend.get("type") or "")
        if prev and backend.get("base_url"):  # keep the old single vendor's endpoint for its connection
            conns = dict(cfg.get("connections") or {})
            pc = dict(conns.get(prev) or {})
            pc.setdefault("base_url", str(backend["base_url"]))
            pc.setdefault("enabled", True)
            conns[prev] = pc
            cfg["connections"] = conns
        backend["previous_type"] = prev
        backend["type"] = "hybrid"
        if prev and get_provider(prev) and prev != "hybrid":
            # unbound tiers keep being answered by the previous single vendor with its models
            from .routing import resolve_route

            for rk in ("simple", "office", "reasoning", "vision"):
                if rk != route_key and not (hybrid.get(rk) or {}).get("provider"):
                    prev_model = str(resolve_route(rk, "", cfg).get("model") or "")
                    if prev_model:
                        hybrid[rk] = {"provider": prev, "model": prev_model}
            cfg["hybrid"] = hybrid
    cfg["backend"] = backend
    cfg["mode"] = "hybrid"
    save_campus_config(cfg)
    return route_test()
