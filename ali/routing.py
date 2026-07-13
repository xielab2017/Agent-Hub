"""OpenSquilla-style model routing for campus office workloads."""

from __future__ import annotations

import re
from typing import Any

from .settings import load_campus_config

# Complexity tiers from the campus handbook
TIERS = {
    "C0": {
        "label": "简单 / 分类摘要",
        "route_key": "simple",
        "examples": "分类、文件命名、短摘要",
    },
    "C1": {
        "label": "日常办公",
        "route_key": "office",
        "examples": "邮件草稿、会议纪要、中文办公",
    },
    "C2": {
        "label": "长文档 / 科研",
        "route_key": "office",  # generate; optional review via reasoning
        "review": True,
        "examples": "长文档、科研写作、数据解释",
    },
    "C3": {
        "label": "复杂推理 / 代码",
        "route_key": "reasoning",
        "examples": "复杂推理、代码、项目决策",
    },
    "Vision": {
        "label": "多模态",
        "route_key": "vision",
        "examples": "PPT、PDF、科研图表",
    },
}

ROUTE_ALIASES = {
    "simple": "simple",
    "c0": "simple",
    "fast": "simple",
    "office": "office",
    "c1": "office",
    "main": "office",
    "vision": "vision",
    "vl": "vision",
    "reasoning": "reasoning",
    "c3": "reasoning",
    "deepseek": "reasoning",
    "auto": "auto",
}


def _model_for_slot(cfg: dict[str, Any], slot: str) -> str:
    models = cfg.get("models") or {}
    routing = cfg.get("routing") or {}
    model_key = routing.get(slot) or slot
    # Prefer explicit model id from models map (legacy or generic)
    for key in (model_key, slot, f"qwen_{slot}" if not slot.startswith("qwen_") else slot):
        val = (models.get(key) or "").strip()
        if val:
            return val
    # Generic slot names
    generic = {"simple": "fast", "office": "main", "vision": "vision", "reasoning": "reasoning"}.get(slot)
    if generic:
        val = (models.get(generic) or "").strip()
        if val:
            return val
    return ""


def classify_message(text: str) -> str:
    """Heuristic auto-tier when route=auto."""
    raw = (text or "").strip()
    t = raw.lower()
    n = len(raw)

    vision_kw = (
        "ppt", "pdf", "图片", "图表", "截图", "image", "figure", "slide", "扫描",
        "ocr", "截屏", "看图", "多模态", "vision",
    )
    if any(k in t for k in vision_kw):
        return "Vision"

    reason_kw = (
        "推理", "证明", "算法", "代码审查", "code review", "架构决策", "debug",
        "复杂度", "实现", "重构", "bug", "traceback", "写代码", "编程", "leetcode",
        "prove", "optimize", "设计方案",
    )
    if any(k in t for k in reason_kw) or n > 2500:
        return "C3"

    long_kw = (
        "长文", "论文", "综述", "科研", "数据解释", "报告全文", "详细分析",
        "研究报告", "调研", "白皮书",
    )
    if any(k in t for k in long_kw) or n > 1200:
        return "C2"

    office_kw = (
        "邮件", "会议", "纪要", "通知", "公文", "周报", "日程", "审批",
        "总结", "起草", "回复", "email", "meeting", "memo", "写一封", "帮我写",
    )
    if any(k in t for k in office_kw):
        return "C1"

    simple_kw = (
        "分类", "命名", "短摘要", "一句话", "标签", "翻译成", "改个名",
        "hello", "hi", "你好", "在吗", "测试", "ping", "哈哈",
    )
    # short chit-chat / trivial → C0 (fast model)
    if n < 24 or (any(k in t for k in simple_kw) and n < 400):
        return "C0"

    # medium-length default office
    if n < 800:
        return "C1"
    return "C2"


def resolve_route(
    route: str = "auto",
    message: str = "",
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve to concrete model id + audit metadata."""
    from .providers import get_provider

    cfg = cfg or load_campus_config()
    data_policy = (cfg.get("data_policy") or "internal").lower()
    routing = cfg.get("routing") or {}
    backend = cfg.get("backend") or {}
    backend_type = (backend.get("type") or "").lower()
    mode = (cfg.get("mode") or "single").lower()
    hybrid = cfg.get("hybrid") or {}

    raw = (route or "auto").strip().lower()
    if raw in ("auto", ""):
        tier = classify_message(message)
        route_key = TIERS[tier]["route_key"]
    elif raw.upper() in TIERS or raw == "vision":
        if raw.lower() == "vision":
            tier = "Vision"
        else:
            tier = raw.upper()
        route_key = TIERS[tier]["route_key"]
    else:
        route_key = ROUTE_ALIASES.get(raw, "office")
        tier = {
            "simple": "C0",
            "office": "C1",
            "vision": "Vision",
            "reasoning": "C3",
        }.get(route_key, "C1")

    provider_id = backend_type
    base_url = backend.get("base_url") or ""
    api_key_env = backend.get("api_key_env") or ""
    model = _model_for_slot(cfg, route_key)

    if mode == "hybrid" or backend_type == "hybrid":
        entry = hybrid.get(route_key) or {}
        provider_id = (entry.get("provider") or "").strip() or provider_id
        if entry.get("model"):
            model = str(entry["model"]).strip()
        prov = get_provider(provider_id) if provider_id and provider_id != "hybrid" else None
        if prov:
            base_url = prov.get("base_url") or base_url
            api_key_env = prov.get("api_key_env") or api_key_env

    blocked = False
    block_reason = ""

    external_ids = {
        "openai",
        "anthropic",
        "nvidia-nim",
        "nvidia-api",
        "nvidia-hosted",
        "openrouter",
        "minimax",
        "gemini",
        "deepseek",
        "kimi",
        "hybrid",
    }
    if data_policy == "restricted":
        effective = provider_id if (mode == "hybrid" or backend_type == "hybrid") else backend_type
        if effective in external_ids and effective not in ("campus-openai-compatible", "local-ollama"):
            blocked = True
            block_reason = f"data_policy=restricted forbids external provider '{effective}'"

    review = bool(TIERS.get(tier, {}).get("review"))

    return {
        "tier": tier,
        "route_key": route_key,
        "model": model,
        "model_slot": (routing.get(route_key) or route_key),
        "mode": mode if mode == "hybrid" or backend_type == "hybrid" else "single",
        "auto": raw in ("auto", ""),
        "provider": provider_id,
        "backend_type": backend_type,
        "base_url": base_url,
        "api_key_env": api_key_env,
        "data_policy": data_policy,
        "review_recommended": review,
        "blocked": blocked,
        "block_reason": block_reason,
        "label": TIERS.get(tier, {}).get("label", route_key),
    }


def routing_matrix() -> list[dict[str, Any]]:
    cfg = load_campus_config()
    rows = []
    for tier, meta in TIERS.items():
        resolved = resolve_route(tier if tier != "Vision" else "vision", "", cfg)
        rows.append(
            {
                "tier": tier,
                "label": meta["label"],
                "examples": meta["examples"],
                "route_key": meta["route_key"],
                "model": resolved["model"],
                "provider": resolved.get("provider") or resolved.get("backend_type"),
                "review": bool(meta.get("review")),
            }
        )
    return rows


def system_preamble(route_info: dict[str, Any], cfg: dict[str, Any] | None = None) -> str:
    """Inject office-governance context into agent turns."""
    cfg = cfg or load_campus_config()
    obs = cfg.get("obsidian") or {}
    lines = [
        "You are Hermes running inside Hermes-ALI Campus Office mode.",
        "Role split: Hermes owns tasks/skills/workflows; OpenSquilla-style routing selects models; Obsidian stores reviewed knowledge only.",
        f"Active route: tier={route_info.get('tier')} slot={route_info.get('route_key')} model={route_info.get('model') or '(unset)'}.",
        f"Data policy: {cfg.get('data_policy')}.",
    ]
    if cfg.get("data_policy") == "restricted":
        lines.append("Do NOT send content to external/cloud models. Stay on campus endpoints.")
    if obs.get("vault_path"):
        lines.append(f"Obsidian vault: {obs['vault_path']}")
        lines.append(f"AI writes only to inbox: {obs.get('ai_inbox')} (approval required before moving to formal folders).")
    lines.append(
        "Require explicit user approval before: sending email, deleting/overwriting files, firewall changes, startup registration, or writing outside AI_Candidates."
    )
    if route_info.get("review_recommended"):
        lines.append("This task is C2-class: prefer generate-then-review (Qwen generate, DeepSeek review) when both models are configured.")
    return "\n".join(lines)
