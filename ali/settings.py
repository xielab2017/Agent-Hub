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

DEFAULT_CAMPUS: dict[str, Any] = {
    "schema_version": "1.0",
    "install_root": "",
    "backend": {
        "type": "campus-openai-compatible",
        "base_url": "",
        "api_key_env": "CAMPUS_LLM_API_KEY",
        "verify_tls": True,
        "timeout_seconds": 60,
    },
    "models": {
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
    "ali": {
        "default_route": "office",  # simple | office | vision | reasoning | auto
        "show_route_badge": True,
        "language": "zh",  # zh | en
        "theme": "dark",  # dark | light
        "accent": "ocean",  # ocean | forest | amber | rose | slate | teal
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
}


def _deep_merge(base: dict, overlay: dict) -> dict:
    out = deepcopy(base)
    for k, v in (overlay or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_campus_config() -> dict[str, Any]:
    ensure_state_dirs()
    if CAMPUS_CONFIG_FILE.is_file():
        try:
            data = json.loads(CAMPUS_CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return _deep_merge(DEFAULT_CAMPUS, data)
        except (OSError, json.JSONDecodeError):
            pass
    return deepcopy(DEFAULT_CAMPUS)


def save_campus_config(data: dict[str, Any]) -> dict[str, Any]:
    ensure_state_dirs()
    merged = _deep_merge(DEFAULT_CAMPUS, data or {})
    # Never persist secrets
    backend = merged.get("backend") or {}
    for secret_key in ("api_key", "password", "token", "secret"):
        backend.pop(secret_key, None)
    merged["backend"] = backend
    CAMPUS_CONFIG_FILE.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return merged


def import_campus_config(path: str) -> dict[str, Any]:
    src = Path(path).expanduser()
    if not src.is_file():
        raise FileNotFoundError(f"config not found: {src}")
    data = json.loads(src.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("config must be a JSON object")
    return save_campus_config(data)


def export_campus_config(dest: str) -> str:
    cfg = load_campus_config()
    out = Path(dest).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(out)


def api_key_status(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or load_campus_config()
    env_name = ((cfg.get("backend") or {}).get("api_key_env") or "CAMPUS_LLM_API_KEY").strip()
    present = bool(os.environ.get(env_name))
    return {
        "env_name": env_name,
        "present": present,
        "hint": "set" if present else "missing — set via OS env / Credential Manager, never paste into chat",
    }


def public_settings_view() -> dict[str, Any]:
    cfg = load_campus_config()
    return {
        "config": cfg,
        "config_path": str(CAMPUS_CONFIG_FILE),
        "api_key": api_key_status(cfg),
        "defaults": DEFAULT_CAMPUS,
    }


def copy_example_to_state(example_path: Path) -> str:
    ensure_state_dirs()
    if not CAMPUS_CONFIG_FILE.is_file() and example_path.is_file():
        shutil.copy2(example_path, CAMPUS_CONFIG_FILE)
    return str(CAMPUS_CONFIG_FILE)
