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
            main="meta/llama-3.3-70b-instruct",
            vision="meta/llama-3.2-90b-vision-instruct",
            reasoning="nvidia/nemotron-3-nano-30b-a3b",
            embedding="nvidia/nv-embedqa-e5-v5",
            reranker="",
        ),
        "suggestions": {
            "fast": [
                "meta/llama-3.1-8b-instruct",
                "meta/llama-3.2-3b-instruct",
                "google/gemma-3-4b-it",
                "nvidia/nvidia-nemotron-nano-9b-v2",
            ],
            "main": [
                "meta/llama-3.3-70b-instruct",
                "meta/llama-3.1-70b-instruct",
                "nvidia/llama-3.3-nemotron-super-49b-v1.5",
                "nvidia/llama-3.1-nemotron-70b-instruct",
                "qwen/qwen3.5-122b-a10b",
                "deepseek-ai/deepseek-v4-flash",
            ],
            "vision": [
                "meta/llama-3.2-90b-vision-instruct",
                "meta/llama-3.2-11b-vision-instruct",
                "microsoft/phi-4-multimodal-instruct",
                "nvidia/nemotron-nano-12b-v2-vl",
            ],
            "reasoning": [
                "nvidia/nemotron-3-nano-30b-a3b",
                "nvidia/nemotron-3-super-120b-a12b",
                "deepseek-ai/deepseek-v4-pro",
                "nvidia/llama-3.1-nemotron-ultra-253b-v1",
            ],
            "embedding": [
                "nvidia/nv-embedqa-e5-v5",
                "nvidia/nv-embed-v1",
                "nvidia/llama-3.2-nv-embedqa-1b-v1",
            ],
            "reranker": [],
        },
        "routing": {
            "simple": "fast",
            "office": "main",
            "vision": "vision",
            "reasoning": "reasoning",
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
            "simple": "fast",
            "office": "main",
            "vision": "vision",
            "reasoning": "reasoning",
        },
    },
    "dashscope": {
        "id": "dashscope",
        "label": "Qwen / 阿里百炼",
        "label_en": "Qwen",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key_env": "DASHSCOPE_API_KEY",
        "openai_compatible": True,
        "hint": "阿里云百炼 DashScope（OpenAI 兼容模式）；API Key 使用 DASHSCOPE_API_KEY",
        "models": _m(
            fast="qwen-flash",
            main="qwen3.7-plus",
            vision="qwen-vl-plus",
            reasoning="qwen3.7-max",
            embedding="text-embedding-v4",
            reranker="gte-rerank-v2",
        ),
        "suggestions": {
            "fast": ["qwen-flash", "qwen-turbo", "qwen-plus"],
            "main": ["qwen3.7-plus", "qwen-plus", "qwen-max", "qwen3-max", "qwen3-coder-plus"],
            "vision": ["qwen-vl-plus", "qwen-vl-max", "qwen2.5-vl-72b-instruct"],
            "reasoning": ["qwen3.7-max", "qwen-max", "qwen3-max", "qwen3.7-plus"],
            "embedding": ["text-embedding-v4", "text-embedding-v3"],
            "reranker": ["gte-rerank-v2"],
        },
        "routing": {
            "simple": "fast",
            "office": "main",
            "vision": "vision",
            "reasoning": "reasoning",
        },
    },
    "zhipu": {
        "id": "zhipu",
        "label": "GLM / 智谱",
        "label_en": "GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4/",
        "api_key_env": "ZHIPUAI_API_KEY",
        "openai_compatible": True,
        "hint": "智谱 BigModel GLM（OpenAI 兼容）；API Key 使用 ZHIPUAI_API_KEY",
        "models": _m(
            fast="glm-4-flash",
            main="glm-5.2",
            vision="glm-5v-turbo",
            reasoning="glm-5.2",
            embedding="embedding-3",
            reranker="",
        ),
        "suggestions": {
            "fast": ["glm-4-flash", "glm-4-air", "glm-4.5-air"],
            "main": ["glm-5.2", "glm-4.5", "glm-4.5-air", "glm-4-plus"],
            "vision": ["glm-5v-turbo", "glm-4v-plus", "glm-4v", "glm-4.5v"],
            "reasoning": ["glm-5.2", "glm-4.5", "glm-4.5-air"],
            "embedding": ["embedding-3", "embedding-2"],
            "reranker": [],
        },
        "routing": {
            "simple": "fast",
            "office": "main",
            "vision": "vision",
            "reasoning": "reasoning",
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
        "hint": "DeepSeek 官方 API（api.deepseek.com）— 勿与 NVIDIA 上的 deepseek-ai/* 混淆",
        "models": _m(
            fast="deepseek-v4-flash",
            main="deepseek-v4-pro",
            vision="",
            reasoning="deepseek-v4-pro",
            embedding="",
            reranker="",
        ),
        "suggestions": {
            "fast": ["deepseek-v4-flash", "deepseek-chat"],
            "main": ["deepseek-v4-pro", "deepseek-chat"],
            "vision": [],
            "reasoning": ["deepseek-v4-pro", "deepseek-reasoner"],
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
        "label": "Kimi Coding",
        "label_en": "Kimi",
        "base_url": "https://api.kimi.com/coding/v1",
        "api_key_env": "KIMI_CODE_API_KEY",
        "openai_compatible": True,
        "hint": "Kimi Coding OpenAI-compatible API",
        "models": _m(
            fast="kimi-for-coding",
            main="kimi-for-coding",
            vision="kimi-for-coding",
            reasoning="k3",
            embedding="",
            reranker="",
        ),
        "suggestions": {
            "fast": ["kimi-for-coding", "k3"],
            "main": ["kimi-for-coding", "k3"],
            "vision": ["kimi-for-coding", "k3"],
            "reasoning": ["k3", "kimi-for-coding"],
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
            "office": {"provider": "kimi", "model": "kimi-for-coding"},
            "vision": {"provider": "kimi", "model": "kimi-for-coding"},
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


# Providers that expect org/model ids (NVIDIA NIM, OpenRouter, …)
_NAMESPACED_PROVIDERS = frozenset(
    {"nvidia-nim", "nvidia-api", "nvidia-hosted", "openrouter"}
)
# Official APIs that reject org prefixes
_SHORT_NAME_PROVIDERS = frozenset(
    {
        "deepseek",
        "openai",
        "anthropic",
        "minimax",
        "kimi",
        "dashscope",
        "zhipu",
        "local-ollama",
        "campus-openai-compatible",
        "gemini",
    }
)

_ROUTE_TO_GENERIC = {
    "simple": "fast",
    "office": "main",
    "vision": "vision",
    "reasoning": "reasoning",
    "fast": "fast",
    "main": "main",
}


def _provider_model_candidates(prov: dict[str, Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for v in (prov.get("models") or {}).values():
        s = str(v or "").strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    for lst in (prov.get("suggestions") or {}).values():
        for x in lst or []:
            s = str(x or "").strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
    return out


def coerce_model_for_provider(
    provider_id: str,
    model: str,
    *,
    route_key: str = "office",
) -> str:
    """Align model id with the active provider (fix hybrid / short-name 404s).

    NVIDIA / OpenRouter need ``org/model``; DeepSeek official rejects the org prefix.
    When hybrid leaves ``model`` empty, fall back to the provider catalog default.
    """
    pid = resolve_provider_id(provider_id) if provider_id else ""
    prov = get_provider(pid) if pid else None
    m = (model or "").strip()
    generic = _ROUTE_TO_GENERIC.get((route_key or "office").strip().lower(), "main")
    defaults = (prov or {}).get("models") or {}

    def _default() -> str:
        return str(
            defaults.get(generic) or defaults.get("fast") or defaults.get("main") or ""
        ).strip()

    if not prov:
        return m

    # Embedding and reranker ids are not chat-completion models.  A stale
    # Control Center tier binding must never be allowed to route a chat turn
    # into those endpoints (the resulting symptom is usually an empty stream
    # or a provider 404).  Keep the dedicated model slots available to search
    # and retrieval callers by only applying this guard to chat route keys.
    if (route_key or "").strip().lower() not in ("embedding", "reranker"):
        low = m.lower()
        non_chat = (
            "embedding" in low
            or "embed" in low
            or "rerank" in low
            or low.startswith("gte-")
        )
        if non_chat:
            return _default()

    if not m:
        return _default()

    # Kimi Coding and the legacy Moonshot Open Platform use different
    # accounts, endpoints, and model ids. Never carry old Moonshot ids into
    # the Kimi Coding endpoint.
    if pid == "kimi":
        allowed = {"kimi-for-coding", "k3"}
        if m.lower() not in allowed:
            return _default()

    # DeepSeek / OpenAI-style: strip accidental org prefix (NVIDIA uses deepseek-ai/…)
    if pid in _SHORT_NAME_PROVIDERS and "/" in m:
        short = m.rsplit("/", 1)[-1].strip()
        cands = _provider_model_candidates(prov)
        if short in cands or any(c.endswith(short) for c in cands):
            return short
        if pid == "deepseek" and short.startswith("deepseek-"):
            return short
        m = short

    # Official DeepSeek: keep v4 ids; never send deepseek-ai/ org prefix to api.deepseek.com
    if pid == "deepseek":
        cands = {c.lower() for c in _provider_model_candidates(prov)}
        low = m.lower()
        if low in cands:
            return m
        if "reason" in low or low.endswith("-r1"):
            return str(defaults.get("reasoning") or defaults.get("main") or "deepseek-v4-pro")
        if "pro" in low:
            return str(defaults.get("main") or "deepseek-v4-pro")
        if "flash" in low or "chat" in low or "v3" in low or "v4" in low:
            return str(defaults.get(generic) or defaults.get("fast") or "deepseek-v4-flash")
        fb = _default()
        return fb or m

    # Namespaced gateways: promote bare ids via catalog match
    if pid in _NAMESPACED_PROVIDERS and "/" not in m:
        short = m.lower()
        for c in _provider_model_candidates(prov):
            cl = c.lower()
            if cl == short or cl.endswith("/" + short):
                return c
        for c in _provider_model_candidates(prov):
            if short in c.lower().rsplit("/", 1)[-1]:
                return c
        # Bare id will 404 on NIM — use provider default for this slot
        fb = _default()
        if fb:
            return fb

    return m


# Popular-model provider ids → catalog provider ids (when they differ)
PROVIDER_ALIASES: dict[str, str] = {
    "moonshot": "kimi",
    "kimi": "kimi",
    "dashscope": "dashscope",
    "aliyun": "dashscope",
    "alibaba": "dashscope",
    "qwen": "dashscope",
    "01ai": "openrouter",
    "xai": "openrouter",
    "mistral": "openrouter",
    "cohere": "openrouter",
    "zhipu": "zhipu",
    "glm": "zhipu",
    "bigmodel": "zhipu",
    "volcengine": "openrouter",
    "tencent": "openrouter",
}


def resolve_provider_id(provider: str) -> str:
    pid = (provider or "").strip()
    if not pid:
        return ""
    if pid in PROVIDERS:
        return pid
    alias = PROVIDER_ALIASES.get(pid, "")
    if alias and alias in PROVIDERS:
        return alias
    return pid


def model_options_payload(cfg: dict[str, Any]) -> dict[str, Any]:
    """Build the shared provider-aware model picker payload.

    Real provider catalogs win. Configured values are always retained and marked
    unavailable when absent from the latest catalog, so old configs never clear.
    """
    backend = cfg.get("backend") if isinstance(cfg.get("backend"), dict) else {}
    current = str((backend or {}).get("type") or "").strip()
    mode = str(cfg.get("mode") or "single").strip().lower()
    saved = cfg.get("available_models")
    if not isinstance(saved, dict):
        saved = {}
    health_by_provider = cfg.get("model_health")
    if not isinstance(health_by_provider, dict):
        health_by_provider = {}

    configured: list[tuple[str, str]] = []
    default_provider = current if current != "hybrid" else ""
    for value in (cfg.get("models") or {}).values():
        model = str(value or "").strip()
        if model:
            configured.append((default_provider, model))
    for entry in (cfg.get("hybrid") or {}).values():
        if not isinstance(entry, dict):
            continue
        provider = str(entry.get("provider") or "").strip()
        model = str(entry.get("model") or "").strip()
        if model:
            configured.append((provider, model))
    tier_models = (cfg.get("routing") or {}).get("tier_models") or {}
    if isinstance(tier_models, dict):
        for entry in tier_models.values():
            if not isinstance(entry, dict):
                continue
            provider = str(entry.get("provider") or default_provider).strip()
            model = str(entry.get("model") or "").strip()
            if model:
                configured.append((provider, model))

    provider_ids: list[str]
    if current == "hybrid" or mode == "hybrid":
        provider_ids = [str(pid) for pid, models in saved.items() if isinstance(models, list)]
        provider_ids.extend(p for p, _ in configured if p)
    else:
        provider_ids = [current] if current else []

    options: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add(provider: str, model: str, source: str, available: bool) -> None:
        pid = str(provider or "").strip()
        mid = str(model or "").strip()
        if pid == "kimi" and mid == "kimi-for-coding-highspeed":
            return
        key = (pid, mid)
        if not mid or key in seen:
            return
        seen.add(key)
        health = (health_by_provider.get(pid) or {}).get(mid) or {}
        # Once a provider has health results, failed chat models disappear from
        # ordinary model pickers. Dedicated models remain available to their
        # role-specific selectors via kind/capability metadata.
        checked_provider = bool(health_by_provider.get(pid))
        if source == "fetched" and pid == "nvidia-nim" and not checked_provider:
            return
        if checked_provider and health and not (
            health.get("chat_compatible") or health.get("state") == "dedicated"
        ):
            return
        options.append(
            {
                "provider": pid,
                "model": mid,
                "source": source,
                "available": bool(available),
                "health": health.get("state") or ("unchecked" if not health else "unavailable"),
                "kind": health.get("kind") or "unknown",
                "capabilities": health.get("capabilities") or [],
                "latency_s": health.get("latency_s"),
                "quality_score": health.get("quality_score"),
                "speed_score": health.get("speed_score"),
            }
        )

    # Primary source: last successful live catalog for the relevant provider(s).
    for pid in dict.fromkeys(provider_ids):
        for model in saved.get(pid) or []:
            add(pid, str(model), "fetched", True)

    fetched_keys = set(seen)
    for pid, model in configured:
        effective_pid = pid or default_provider
        add(effective_pid, model, "configured", (effective_pid, model) in fetched_keys)

    # Catalog suggestions are only a fallback when no real catalog is available.
    if not options:
        fallback_ids = provider_ids or ([current] if current else [])
        for pid in dict.fromkeys(fallback_ids):
            prov = get_provider(pid)
            if not prov:
                continue
            for model in _provider_model_candidates(prov):
                add(pid, model, "suggested", True)

    return {
        "provider": current,
        "mode": "hybrid" if current == "hybrid" or mode == "hybrid" else "single",
        "options": options,
        "fetched_providers": [
            str(pid) for pid, models in saved.items() if isinstance(models, list) and models
        ],
        "health_meta": cfg.get("model_health_meta") or {},
        "recommendations": cfg.get("model_recommendations") or {},
    }


def apply_recommended_model(
    cfg: dict[str, Any],
    *,
    model_id: str,
    provider: str = "",
    role: str = "main",
    apply_provider: bool = True,
) -> dict[str, Any]:
    """Write a recommended model into campus config slots + last_model.

    Does not install runtimes — only configures model ids for the Direct LLM path.
    """
    mid = (model_id or "").strip()
    if not mid:
        raise ValueError("model_id required")
    out = deepcopy(cfg)
    slot = (role or "main").strip().lower()
    if slot in ("code", "office", "coder"):
        slot = "main"
    if slot not in SLOTS:
        slot = "main"

    resolved_provider = resolve_provider_id(provider)
    provider_applied = False
    if apply_provider and resolved_provider and get_provider(resolved_provider):
        # Switch backend to matching provider but keep filling only this model below
        try:
            out = apply_provider_preset(out, resolved_provider, fill_models=False)
            provider_applied = True
        except ValueError:
            provider_applied = False

    models = dict(out.get("models") or {})
    models[slot] = mid
    legacy = SLOT_TO_LEGACY.get(slot)
    if legacy:
        models[legacy] = mid
    out["models"] = models

    ali = dict(out.get("ali") or {})
    ali["last_model"] = mid
    out["ali"] = ali

    out["_apply_meta"] = {
        "model_id": mid,
        "slot": slot,
        "provider": resolved_provider or provider,
        "provider_applied": provider_applied,
    }
    return out


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
    from .digest import POPULAR_AGENT_MODELS

    providers = list_providers()
    for p in providers:
        pid = p.get("id") or ""
        if pid in (
            "campus-openai-compatible",
            "dashscope",
            "deepseek",
            "kimi",
            "minimax",
            "nvidia-nim",
            "zhipu",
            "hybrid",
        ) or "qwen" in pid or "dashscope" in pid or "zhipu" in pid or "volc" in pid:
            p["region"] = "cn" if pid not in ("nvidia-nim", "hybrid", "campus-openai-compatible") else "both"
        if pid in ("openai", "anthropic", "gemini", "openrouter", "local-ollama"):
            p["region"] = "global" if pid != "openrouter" else "both"
        if pid == "campus-openai-compatible":
            p["region"] = "both"
        if pid == "nvidia-nim":
            p["region"] = "both"
        if pid == "hybrid":
            p["region"] = "both"
        if pid in ("dashscope", "deepseek", "kimi", "minimax", "zhipu"):
            p["region"] = "cn"
    # ensure region key
    for p in providers:
        p.setdefault("region", "both")

    return {
        "providers": providers,
        "regions": {
            "cn": [p for p in providers if p.get("region") in ("cn", "both")],
            "global": [p for p in providers if p.get("region") in ("global", "both")],
        },
        "popular_agent_models": POPULAR_AGENT_MODELS,
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
