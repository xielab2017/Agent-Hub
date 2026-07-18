"""Local secret store for API keys (never returned in full via API)."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

from .config import STATE_DIR, ensure_state_dirs

SECRETS_FILE = STATE_DIR / "secrets.json"


def _load_raw() -> dict[str, Any]:
    ensure_state_dirs()
    if not SECRETS_FILE.is_file():
        return {"keys": {}}
    try:
        data = json.loads(SECRETS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("keys", {})
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"keys": {}}


def _save_raw(data: dict[str, Any]) -> None:
    ensure_state_dirs()
    SECRETS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(SECRETS_FILE, stat.S_IRUSR | stat.S_IWUSR)  # 600
    except OSError:
        pass


def mask_key(key: str) -> str:
    k = (key or "").strip()
    if not k:
        return ""
    if len(k) <= 8:
        return "****"
    return k[:4] + "…" + k[-4:]


def set_api_key(slot: str, value: str) -> dict[str, Any]:
    """Save API key under a slot (provider id or env var name)."""
    slot = (slot or "").strip()
    value = (value or "").strip()
    if not slot:
        raise ValueError("empty key slot")
    data = _load_raw()
    keys = data.setdefault("keys", {})
    if not value:
        keys.pop(slot, None)
    else:
        keys[slot] = value
    _save_raw(data)
    return {"ok": True, "slot": slot, "present": bool(value), "masked": mask_key(value)}


def get_api_key(slot: str) -> str:
    if not slot:
        return ""
    data = _load_raw()
    return str((data.get("keys") or {}).get(slot) or "").strip()


def resolve_api_key(cfg: dict[str, Any] | None = None, provider: str = "") -> dict[str, Any]:
    """Resolve key from OS env first, then local secrets store.

    Strict isolation: when a provider is selected, never fall back to another
    vendor's slot (e.g. OpenRouter sk-or- must not be used for nvidia-nim).
    """
    from .settings import load_campus_config
    from .providers import get_provider, key_provider_mismatch

    cfg = cfg or load_campus_config()
    backend = cfg.get("backend") or {}
    provider_id = (provider or backend.get("type") or "").strip()
    env_name = str(backend.get("api_key_env") or "").strip()

    # Hybrid: use provider-specific env from catalog
    if provider_id and provider_id != "hybrid":
        prov = get_provider(provider_id)
        if prov and prov.get("api_key_env"):
            env_name = str(prov["api_key_env"])

    sources_tried = []
    key = ""
    source = ""

    if env_name:
        sources_tried.append(f"env:{env_name}")
        key = (os.environ.get(env_name) or "").strip()
        if key:
            source = f"env:{env_name}"

    if not key and provider_id and provider_id != "hybrid":
        sources_tried.append(f"secret:{provider_id}")
        key = get_api_key(provider_id)
        if key:
            source = f"secret:{provider_id}"

    if not key and env_name:
        sources_tried.append(f"secret:{env_name}")
        key = get_api_key(env_name)
        if key:
            source = f"secret:{env_name}"

    # Only use generic slots when provider is unset / hybrid / unknown
    if not key and provider_id in ("", "hybrid"):
        for slot in ("default", "api_key"):
            sources_tried.append(f"secret:{slot}")
            key = get_api_key(slot)
            if key:
                source = f"secret:{slot}"
                break

    mismatch = None
    if key and provider_id and provider_id != "hybrid":
        mismatch = key_provider_mismatch(provider_id, key)
        if mismatch:
            # Do not return a cross-vendor key — treat as missing for this provider.
            return {
                "present": False,
                "key": "",
                "source": "",
                "env_name": env_name,
                "provider": provider_id,
                "masked": "",
                "tried": sources_tried,
                "mismatch": mismatch,
                "rejected_source": source,
                "rejected_masked": mask_key(key),
            }

    return {
        "present": bool(key),
        "key": key,
        "source": source,
        "env_name": env_name,
        "provider": provider_id,
        "masked": mask_key(key),
        "tried": sources_tried,
        "mismatch": None,
    }


def public_key_status(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    info = resolve_api_key(cfg)
    hint = (
        "set"
        if info["present"]
        else "missing — paste API key in Control Center (saved locally) or set OS env"
    )
    if info.get("mismatch"):
        hint = info["mismatch"].get("message") or hint
    return {
        "present": info["present"],
        "env_name": info["env_name"],
        "provider": info["provider"],
        "source": info["source"],
        "masked": info["masked"],
        "mismatch": info.get("mismatch"),
        "hint": hint,
    }
