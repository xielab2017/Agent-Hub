"""LLM provider catalogs — campus + commercial, single or hybrid fusion."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

# Generic role slots used by OpenSquilla-style routing
SLOTS = ("fast", "main", "vision", "reasoning", "embedding", "reranker")

# Map campus-office legacy keys → generic slots
LEGACY_SLOT_KEYS = {
    "qwen_fast": "fast",
    "qwen_main": "main",
    "qwen_vl": "vision",
    "deepseek_reasoning": "reasoning",
    "embedding": "embedding",
    "reranker": "reranker",
}

SLOT_TO_LEGACY = {
    "fast": "qwen_fast",
    "main": "qwen_main",
    "vision": "qwen_vl",
    "reasoning": "deepseek_reasoning",
    "embedding": "embedding",
    "reranker": "reranker",
}


def _m(**kwargs: str) -> dict[str, Any]:
    """Build a models block with both generic and legacy keys."""
    out: dict[str, Any] = {}
    for slot in SLOTS:
        val = kwargs.get(slot, "")
        out[slot] = val
        legacy = SLOT_TO_LEGACY.get(slot)
        if legacy:
            out[legacy] = val
    return out


PROVIDERS: dict[str, dict[str, Any]] = {
    "campus-openai-compatible": {
        "id": "campus-openai-compatible",
        "label": "Campus / 校园超算",
        "label_en": "Campus HPC",
        "base_url": "",
        "api_key_env": "CAMPUS_LLM_API_KEY",
        "openai_compatible": True,
        "hint": "向超管索取 Base URL 与真实模型 ID（GET /v1/models）",
        "models": _m(
            fast="",
            main="",
            vision="",
            reasoning="",
            embedding="",
            reranker="",
        ),
        "suggestions": {
            "fast": ["server-qwen-fast", "qwen2.5-7b-instruct"],
            "main": ["server-qwen-main", "qwen2.5-72b-instruct"],
            "vision": ["server-qwen-vl", "qwen2.5-vl-72b"],
            "reasoning": ["server-deepseek-r1", "deepseek-r1"],
            "embedding": ["server-embed", "bge-m3"],
            "reranker": ["server-rerank", "bge-reranker-v2"],
        },
        "routing": {
            "simple": "qwen_fast",
            "office": "qwen_main",
            "vision": "qwen_vl",
            "reasoning": "deepseek_reasoning",
        },
    },
    "openai": {
        "id": "openai",
        "label": "OpenAI",
        "label_en": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "openai_compatible": True,
        "hint": "官方 OpenAI API",
        "models": _m(
            fast="gpt-4o-mini",
            main="gpt-4o",
            vision="gpt-4o",
            reasoning="o3-mini",
            embedding="text-embedding-3-large",
            reranker="",
        ),
        "suggestions": {
            "fast": ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4.1-nano"],
            "main": ["gpt-4o", "gpt-4.1", "gpt-4.1-mini"],
            "vision": ["gpt-4o", "gpt-4.1"],
            "reasoning": ["o3-mini", "o4-mini", "o3"],
            "embedding": ["text-embedding-3-large", "text-embedding-3-small"],
            "reranker": [],
        },
        "routing": {
            "simple": "qwen_fast",
            "office": "qwen_main",
            "vision": "qwen_vl",
            "reasoning": "deepseek_reasoning",
        },
    },
    "anthropic": {
        "id": "anthropic",
        "label": "Claude / Anthropic",
        "label_en": "Claude",
        "base_url": "https://api.anthropic.com/v1",
        "api_key_env": "ANTHROPIC_API_KEY",
        "openai_compatible": False,
        "hint": "Claude API；Hermes 需 Anthropic 适配",
        "models": _m(
            fast="claude-3-5-haiku-latest",
            main="claude-sonnet-4-20250514",
            vision="claude-sonnet-4-20250514",
            reasoning="claude-opus-4-20250514",
            embedding="",
            reranker="",
        ),
        "suggestions": {
            "fast": ["claude-3-5-haiku-latest", "claude-haiku-4-5"],
            "main": ["claude-sonnet-4-20250514", "claude-3-7-sonnet-latest"],
            "vision": ["claude-sonnet-4-20250514", "claude-3-7-sonnet-latest"],
            "reasoning": ["claude-opus-4-20250514", "claude-sonnet-4-20250514"],
            "embedding": [],
            "reranker": [],
        },
        "routing": {
            "simple": "qwen_fast",
            "office": "qwen_main",
            "vision": "qwen_vl",
            "reasoning": "deepseek_reasoning",
        },
    },
    "nvidia-nim": {
        "id": "nvidia-nim",
        "label": "NVIDIA NIM / API",
        "label_en": "NVIDIA",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "api_key_env": "NVIDIA_API_KEY",
        "openai_compatible": True,
        "hint": "NVIDIA 托管 API 或校园 NIM；密钥用 NVIDIA_API_KEY 环境变量",
        "models": _m(
            fast="meta/llama-3.1-8b-instruct",
            main="meta/llama-3.1-70b-instruct",
            vision="meta/llama-3.2-90b-vision-instruct",
            reasoning="deepseek-ai/deepseek-r1",
            embedding="nvidia/nv-embedqa-e5-v5",
            reranker="",
        ),
        "suggestions": {
            "fast": [
                "meta/llama-3.1-8b-instruct",
                "google/gemma-2-9b-it",
                "qwen/qwen2.5-7b-instruct",
            ],
            "main": [
                "meta/llama-3.1-70b-instruct",
                "qwen/qwen2.5-72b-instruct",
                "nvidia/llama-3.1-nemotron-70b-instruct",
            ],
            "vision": [
                "meta/llama-3.2-90b-vision-instruct",
                "microsoft/phi-3-vision-128k-instruct",
            ],
            "reasoning": [
                "deepseek-ai/deepseek-r1",
                "deepseek-ai/deepseek-r1-distill-llama-70b",
            ],
            "embedding": ["nvidia/nv-embedqa-e5-v5", "nvidia/nv-embed-v1"],
            "reranker": ["nvidia/nv-rerankqa-mistral-4b-v3"],
        },
        "routing": {
            "simple": "qwen_fast",
            "office": "qwen_main",
            "vision": "qwen_vl",
            "reasoning": "deepseek_reasoning",
        },
    },
    "openrouter": {
        "id": "openrouter",
        "label": "OpenRouter",
        "label_en": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "openai_compatible": True,
        "hint": "聚合多家模型；适合混合路由试验",
        "models": _m(
            fast="openai/gpt-4o-mini",
            main="anthropic/claude-sonnet-4",
            vision="openai/gpt-4o",
            reasoning="deepseek/deepseek-r1",
            embedding="openai/text-embedding-3-large",
            reranker="",
        ),
        "suggestions": {
            "fast": ["openai/gpt-4o-mini", "google/gemini-2.0-flash-001", "qwen/qwen-2.5-7b-instruct"],
            "main": ["anthropic/claude-sonnet-4", "openai/gpt-4o", "google/gemini-2.5-pro"],
            "vision": ["openai/gpt-4o", "google/gemini-2.0-flash-001", "qwen/qwen-2.5-vl-72b-instruct"],
            "reasoning": ["deepseek/deepseek-r1", "openai/o3-mini", "anthropic/claude-opus-4"],
            "embedding": ["openai/text-embedding-3-large"],
            "reranker": [],
        },
        "routing": {
            "simple": "qwen_fast",
            "office": "qwen_main",
            "vision": "qwen_vl",
            "reasoning": "deepseek_reasoning",
        },
    },
    "minimax": {
        "id": "minimax",
        "label": "MiniMax",
        "label_en": "MiniMax",
        "base_url": "https://api.minimax.chat/v1",
        "api_key_env": "MINIMAX_API_KEY",
        "openai_compatible": True,
        "hint": "MiniMax 开放平台（OpenAI 兼容）",
        "models": _m(
            fast="MiniMax-Text-01",
            main="MiniMax-Text-01",
            vision="MiniMax-Text-01",
            reasoning="MiniMax-Text-01",
            embedding="",
            reranker="",
        ),
        "suggestions": {
            "fast": ["MiniMax-Text-01", "abab6.5s-chat"],
            "main": ["MiniMax-Text-01", "abab6.5s-chat"],
            "vision": ["MiniMax-Text-01"],
            "reasoning": ["MiniMax-Text-01"],
            "embedding": [],
            "reranker": [],
        },
        "routing": {
            "simple": "qwen_fast",
            "office": "qwen_main",
            "vision": "qwen_vl",
            "reasoning": "deepseek_reasoning",
        },
    },
    "gemini": {
        "id": "gemini",
        "label": "Google Gemini",
        "label_en": "Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GOOGLE_API_KEY",
        "openai_compatible": True,
        "hint": "Gemini OpenAI 兼容端点",
        "models": _m(
            fast="gemini-2.0-flash",
            main="gemini-2.5-pro",
            vision="gemini-2.0-flash",
            reasoning="gemini-2.5-pro",
            embedding="text-embedding-004",
            reranker="",
        ),
        "suggestions": {
            "fast": ["gemini-2.0-flash", "gemini-2.0-flash-lite"],
            "main": ["gemini-2.5-pro", "gemini-2.0-flash"],
            "vision": ["gemini-2.0-flash", "gemini-2.5-pro"],
            "reasoning": ["gemini-2.5-pro", "gemini-2.0-flash-thinking-exp"],
            "embedding": ["text-embedding-004"],
            "reranker": [],
        },
        "routing": {
            "simple": "qwen_fast",
            "office": "qwen_main",
            "vision": "qwen_vl",
            "reasoning": "deepseek_reasoning",
        },
    },
    "deepseek": {
        "id": "deepseek",
        "label": "DeepSeek",
        "label_en": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
        "openai_compatible": True,
        "hint": "DeepSeek 官方 API",
        "models": _m(
            fast="deepseek-chat",
            main="deepseek-chat",
            vision="",
            reasoning="deepseek-reasoner",
            embedding="",
            reranker="",
        ),
        "suggestions": {
            "fast": ["deepseek-chat"],
            "main": ["deepseek-chat"],
            "vision": [],
            "reasoning": ["deepseek-reasoner"],
            "embedding": [],
            "reranker": [],
        },
        "routing": {
            "simple": "qwen_fast",
            "office": "qwen_main",
            "vision": "qwen_vl",
            "reasoning": "deepseek_reasoning",
        },
    },
    "kimi": {
        "id": "kimi",
        "label": "Kimi / Moonshot",
        "label_en": "Kimi",
        "base_url": "https://api.moonshot.cn/v1",
        "api_key_env": "MOONSHOT_API_KEY",
        "openai_compatible": True,
        "hint": "月之暗面 Kimi（长上下文）",
        "models": _m(
            fast="moonshot-v1-8k",
            main="moonshot-v1-128k",
            vision="moonshot-v1-128k-vision-preview",
            reasoning="moonshot-v1-128k",
            embedding="",
            reranker="",
        ),
        "suggestions": {
            "fast": ["moonshot-v1-8k", "moonshot-v1-32k", "kimi-latest"],
            "main": ["moonshot-v1-128k", "kimi-latest", "moonshot-v1-32k"],
            "vision": ["moonshot-v1-128k-vision-preview", "kimi-latest"],
            "reasoning": ["moonshot-v1-128k", "kimi-latest"],
            "embedding": [],
            "reranker": [],
        },
        "routing": {
            "simple": "qwen_fast",
            "office": "qwen_main",
            "vision": "qwen_vl",
            "reasoning": "deepseek_reasoning",
        },
    },
    "local-ollama": {
        "id": "local-ollama",
        "label": "Ollama（本地）",
        "label_en": "Ollama",
        "base_url": "http://127.0.0.1:11434/v1",
        "api_key_env": "OLLAMA_API_KEY",
        "openai_compatible": True,
        "hint": "本机 Ollama；可填任意占位密钥",
        "models": _m(
            fast="qwen2.5:7b",
            main="qwen2.5:14b",
            vision="llava",
            reasoning="deepseek-r1:14b",
            embedding="nomic-embed-text",
            reranker="",
        ),
        "suggestions": {
            "fast": ["qwen2.5:7b", "llama3.2:3b", "gemma2:9b"],
            "main": ["qwen2.5:14b", "qwen2.5:32b", "llama3.1:70b"],
            "vision": ["llava", "qwen2.5vl"],
            "reasoning": ["deepseek-r1:14b", "deepseek-r1:32b"],
            "embedding": ["nomic-embed-text"],
            "reranker": [],
        },
        "routing": {
            "simple": "qwen_fast",
            "office": "qwen_main",
            "vision": "qwen_vl",
            "reasoning": "deepseek_reasoning",
        },
    },
    "hybrid": {
        "id": "hybrid",
        "label": "混合融合 Hybrid",
        "label_en": "Hybrid fusion",
        "base_url": "",
        "api_key_env": "",
        "openai_compatible": True,
        "hint": "按任务等级绑定不同厂商（C0/C1/C3/Vision 可拆分）",
        "models": _m(),
        "suggestions": {},
        "routing": {
            "simple": "qwen_fast",
            "office": "qwen_main",
            "vision": "qwen_vl",
            "reasoning": "deepseek_reasoning",
        },
        # Default hybrid recipe: cheap flash + strong office + deepseek reason + gemini vision
        "hybrid_defaults": {
            "simple": {"provider": "openai", "model": "gpt-4o-mini"},
            "office": {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
            "vision": {"provider": "gemini", "model": "gemini-2.0-flash"},
            "reasoning": {"provider": "deepseek", "model": "deepseek-reasoner"},
        },
    },
}

# Preset hybrid recipes user can one-click apply
HYBRID_PRESETS: dict[str, dict[str, Any]] = {
    "balanced": {
        "label": "均衡：OpenAI快 + Claude办 + DeepSeek推 + Gemini视",
        "routes": {
            "simple": {"provider": "openai", "model": "gpt-4o-mini"},
            "office": {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
            "vision": {"provider": "gemini", "model": "gemini-2.0-flash"},
            "reasoning": {"provider": "deepseek", "model": "deepseek-reasoner"},
        },
    },
    "china_office": {
        "label": "国内办公：Kimi办 + DeepSeek推 + MiniMax快",
        "routes": {
            "simple": {"provider": "minimax", "model": "MiniMax-Text-01"},
            "office": {"provider": "kimi", "model": "moonshot-v1-128k"},
            "vision": {"provider": "kimi", "model": "moonshot-v1-128k-vision-preview"},
            "reasoning": {"provider": "deepseek", "model": "deepseek-reasoner"},
        },
    },
    "openrouter_mix": {
        "label": "OpenRouter 全聚合",
        "routes": {
            "simple": {"provider": "openrouter", "model": "openai/gpt-4o-mini"},
            "office": {"provider": "openrouter", "model": "anthropic/claude-sonnet-4"},
            "vision": {"provider": "openrouter", "model": "openai/gpt-4o"},
            "reasoning": {"provider": "openrouter", "model": "deepseek/deepseek-r1"},
        },
    },
    "nvidia_stack": {
        "label": "NVIDIA 全家桶",
        "routes": {
            "simple": {"provider": "nvidia-nim", "model": "meta/llama-3.1-8b-instruct"},
            "office": {"provider": "nvidia-nim", "model": "meta/llama-3.1-70b-instruct"},
            "vision": {"provider": "nvidia-nim", "model": "meta/llama-3.2-90b-vision-instruct"},
            "reasoning": {"provider": "nvidia-nim", "model": "deepseek-ai/deepseek-r1"},
        },
    },
    "campus_first": {
        "label": "校园优先（需自行填模型 ID）",
        "routes": {
            "simple": {"provider": "campus-openai-compatible", "model": ""},
            "office": {"provider": "campus-openai-compatible", "model": ""},
            "vision": {"provider": "campus-openai-compatible", "model": ""},
            "reasoning": {"provider": "campus-openai-compatible", "model": ""},
        },
    },
}


def list_providers() -> list[dict[str, Any]]:
    out = []
    for p in PROVIDERS.values():
        out.append(
            {
                "id": p["id"],
                "label": p["label"],
                "label_en": p.get("label_en") or p["label"],
                "base_url": p.get("base_url") or "",
                "api_key_env": p.get("api_key_env") or "",
                "openai_compatible": bool(p.get("openai_compatible", True)),
                "hint": p.get("hint") or "",
                "suggestions": p.get("suggestions") or {},
            }
        )
    return out


def get_provider(provider_id: str) -> dict[str, Any] | None:
    return PROVIDERS.get((provider_id or "").strip())


def looks_like_secret(value: str) -> bool:
    """Detect accidental paste of real API keys into env-name fields."""
    v = (value or "").strip()
    if not v:
        return False
    lower = v.lower()
    if lower.startswith(("nvapi-", "sk-", "sk-ant-", "sk-or-", "akey-", "ya29.")):
        return True
    if " " in v:
        return False
    # Long opaque tokens that are not typical ENV_NAME style
    if len(v) >= 32 and "-" in v and v.upper() != v and not v.replace("_", "").isalnum():
        # nvapi style already caught; generic long keys with mixed case
        if any(c.islower() for c in v) and any(c.isdigit() for c in v):
            return True
    # ENV names are usually UPPER_SNAKE
    if v.isupper() or (v.replace("_", "").isalnum() and "_" in v):
        return False
    if len(v) > 40 and any(c.isdigit() for c in v):
        return True
    return False


# Key prefix → provider id
_KEY_PREFIX_PROVIDERS: list[tuple[str, str]] = [
    ("nvapi-", "nvidia-nim"),
    ("sk-or-", "openrouter"),
    ("sk-ant-", "anthropic"),
    ("sk-proj-", "openai"),
    ("sk-litellm-", "openai"),
]


def detect_provider_from_key(api_key: str) -> str | None:
    k = (api_key or "").strip().lower()
    if not k:
        return None
    for prefix, provider_id in _KEY_PREFIX_PROVIDERS:
        if k.startswith(prefix):
            return provider_id
    # generic sk- often OpenAI (but not sk-or / sk-ant)
    if k.startswith("sk-") and not k.startswith(("sk-or-", "sk-ant-")):
        return "openai"
    return None


def key_provider_mismatch(provider_id: str, api_key: str) -> dict[str, Any] | None:
    """Return mismatch info if key format conflicts with selected provider."""
    detected = detect_provider_from_key(api_key)
    pid = (provider_id or "").strip()
    if not detected or not pid or pid in ("hybrid", "campus-openai-compatible", "local-ollama"):
        return None
    # openrouter keys only work on openrouter
    if detected == "openrouter" and pid != "openrouter":
        return {
            "selected": pid,
            "detected": "openrouter",
            "message": (
                f"当前后端是 {pid}，但密钥是 OpenRouter 格式（sk-or-…）。"
                f"请把后端改为 openrouter，或粘贴对应厂商的密钥"
                f"（NVIDIA 应为 nvapi-…）。"
            ),
            "message_en": (
                f"Backend is {pid} but key looks like OpenRouter (sk-or-…). "
                f"Switch backend to openrouter, or paste a matching key "
                f"(NVIDIA keys start with nvapi-)."
            ),
        }
    if detected == "nvidia-nim" and pid != "nvidia-nim":
        return {
            "selected": pid,
            "detected": "nvidia-nim",
            "message": (
                f"当前后端是 {pid}，但密钥是 NVIDIA 格式（nvapi-…）。"
                f"请把后端改为 nvidia-nim，或粘贴对应厂商密钥。"
            ),
            "message_en": (
                f"Backend is {pid} but key looks like NVIDIA (nvapi-…). "
                f"Switch backend to nvidia-nim or paste a matching key."
            ),
        }
    if detected == "openai" and pid not in ("openai", "openrouter"):
        # OpenAI keys sometimes used via compatible proxies — soft warn only for nvidia
        if pid == "nvidia-nim":
            return {
                "selected": pid,
                "detected": "openai",
                "message": (
                    "当前后端是 nvidia-nim，但密钥像 OpenAI（sk-…）。"
                    "NVIDIA 密钥一般以 nvapi- 开头；OpenRouter 以 sk-or- 开头。"
                ),
                "message_en": (
                    "Backend is nvidia-nim but key looks like OpenAI (sk-…). "
                    "NVIDIA keys usually start with nvapi-; OpenRouter with sk-or-."
                ),
            }
    if detected == "anthropic" and pid != "anthropic":
        return {
            "selected": pid,
            "detected": "anthropic",
            "message": f"密钥像 Anthropic（sk-ant-…），但后端是 {pid}。请改为 anthropic 或换密钥。",
            "message_en": f"Key looks like Anthropic (sk-ant-…) but backend is {pid}.",
        }
    return None


def apply_provider_preset(cfg: dict[str, Any], provider_id: str, *, fill_models: bool = True) -> dict[str, Any]:
    """Return a new config with backend (+ optional models/routing) from provider catalog."""
    out = deepcopy(cfg)
    pid = (provider_id or "").strip()
    prov = get_provider(pid)
    if not prov:
        raise ValueError(f"unknown provider: {provider_id}")

    backend = dict(out.get("backend") or {})
    backend["type"] = pid
    if pid != "hybrid":
        backend["base_url"] = prov.get("base_url") or backend.get("base_url") or ""
        backend["api_key_env"] = prov.get("api_key_env") or backend.get("api_key_env") or ""
        # scrub secrets mistaken as env names
        if looks_like_secret(str(backend.get("api_key_env") or "")):
            backend["api_key_env"] = prov.get("api_key_env") or "API_KEY"
    else:
        backend["base_url"] = ""
        backend["api_key_env"] = ""
    out["backend"] = backend
    out["mode"] = "hybrid" if pid == "hybrid" else "single"

    if fill_models and pid != "hybrid":
        models = dict(out.get("models") or {})
        for k, v in (prov.get("models") or {}).items():
            if v:
                models[k] = v
        out["models"] = models
        if prov.get("routing"):
            routing = dict(out.get("routing") or {})
            routing.update(prov["routing"])
            out["routing"] = routing
        out["hybrid"] = {}
    elif pid == "hybrid":
        hybrid = deepcopy(prov.get("hybrid_defaults") or {})
        out["hybrid"] = hybrid
        # Mirror models from hybrid recipe into legacy slots for display
        models = dict(out.get("models") or {})
        slot_map = {
            "simple": "qwen_fast",
            "office": "qwen_main",
            "vision": "qwen_vl",
            "reasoning": "deepseek_reasoning",
        }
        for route_key, legacy in slot_map.items():
            entry = hybrid.get(route_key) or {}
            if entry.get("model"):
                models[legacy] = entry["model"]
                models[LEGACY_SLOT_KEYS.get(legacy, legacy)] = entry["model"]
        out["models"] = models

    return out


def apply_hybrid_preset(cfg: dict[str, Any], preset_id: str) -> dict[str, Any]:
    preset = HYBRID_PRESETS.get(preset_id)
    if not preset:
        raise ValueError(f"unknown hybrid preset: {preset_id}")
    out = apply_provider_preset(cfg, "hybrid", fill_models=False)
    out["hybrid"] = deepcopy(preset["routes"])
    models = dict(out.get("models") or {})
    slot_map = {
        "simple": "qwen_fast",
        "office": "qwen_main",
        "vision": "qwen_vl",
        "reasoning": "deepseek_reasoning",
    }
    for route_key, legacy in slot_map.items():
        entry = (preset["routes"] or {}).get(route_key) or {}
        if entry.get("model"):
            models[legacy] = entry["model"]
            gen = LEGACY_SLOT_KEYS.get(legacy, legacy)
            models[gen] = entry["model"]
    out["models"] = models
    return out


def catalog_payload() -> dict[str, Any]:
    return {
        "providers": list_providers(),
        "hybrid_presets": [
            {"id": k, "label": v["label"], "routes": v["routes"]} for k, v in HYBRID_PRESETS.items()
        ],
        "slots": [
            {"id": "fast", "legacy": "qwen_fast", "tier": "C0", "label": "Fast / 快速"},
            {"id": "main", "legacy": "qwen_main", "tier": "C1/C2", "label": "Main / 办公主模型"},
            {"id": "vision", "legacy": "qwen_vl", "tier": "Vision", "label": "Vision / 多模态"},
            {"id": "reasoning", "legacy": "deepseek_reasoning", "tier": "C3", "label": "Reasoning / 推理"},
            {"id": "embedding", "legacy": "embedding", "tier": "—", "label": "Embedding"},
            {"id": "reranker", "legacy": "reranker", "tier": "—", "label": "Reranker"},
        ],
    }
