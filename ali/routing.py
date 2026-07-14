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
    "agent": "office",
    "vision": "vision",
    "vl": "vision",
    "reasoning": "reasoning",
    "c3": "reasoning",
    "deepseek": "reasoning",
    "auto": "auto",
}

# Composer 「思考深度」— fused into preamble, sampling, and optional auto-route nudge
THINKING_DEPTHS = ("light", "medium", "high", "very_high")
THINKING_DEPTH_ALIASES = {
    "light": "light",
    "低": "light",
    "轻": "light",
    "l": "light",
    "medium": "medium",
    "中": "medium",
    "m": "medium",
    "med": "medium",
    "high": "high",
    "高": "high",
    "h": "high",
    "very_high": "very_high",
    "very-high": "very_high",
    "veryhigh": "very_high",
    "非常高": "very_high",
    "vh": "very_high",
    "max": "very_high",
}
THINKING_DEPTH_SPECS: dict[str, dict[str, Any]] = {
    "light": {
        "label": "轻 / Light",
        "temperature": 0.45,
        "max_tokens": 2048,
        "step_budget": 2,
        "nudge": None,
        "instructions": (
            "## Thinking depth: Light\n"
            "Prefer brief, direct answers. Skip long chain-of-thought unless the user asks. "
            "At most ~2 short reasoning steps internally; deliver the result first."
        ),
    },
    "medium": {
        "label": "中 / Medium",
        "temperature": 0.7,
        "max_tokens": 4096,
        "step_budget": 5,
        "nudge": None,
        "instructions": (
            "## Thinking depth: Medium\n"
            "Balance speed and rigor. Use a short plan when the task is multi-step "
            "(~3–5 internal steps), then produce a clear campus-office deliverable."
        ),
    },
    "high": {
        "label": "高 / High",
        "temperature": 0.55,
        "max_tokens": 8192,
        "step_budget": 10,
        "nudge": "C2",
        "instructions": (
            "## Thinking depth: High\n"
            "Think carefully before answering. Prefer structured analysis "
            "(assumptions → options → recommendation) with ~6–10 internal steps. "
            "Check edge cases; do not invent files or facts."
        ),
    },
    "very_high": {
        "label": "非常高 / Very high",
        "temperature": 0.35,
        "max_tokens": 16384,
        "step_budget": 16,
        "nudge": "C3",
        "instructions": (
            "## Thinking depth: Very high\n"
            "Deep reasoning mode: exhaustively examine the problem, trade-offs, and failure modes "
            "before concluding (~10–16 internal steps). Prefer the reasoning-tier model when routed. "
            "Still output a clean deliverable — never dump raw reasoning boxes or tool JSON to the user."
        ),
    },
}


def normalize_thinking_depth(value: str | None, default: str = "medium") -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return default if default in THINKING_DEPTHS else "medium"
    key = THINKING_DEPTH_ALIASES.get(raw) or THINKING_DEPTH_ALIASES.get(str(value or "").strip())
    if key in THINKING_DEPTHS:
        return key
    return default if default in THINKING_DEPTHS else "medium"


def thinking_depth_spec(depth: str | None = None) -> dict[str, Any]:
    key = normalize_thinking_depth(depth)
    spec = dict(THINKING_DEPTH_SPECS[key])
    spec["depth"] = key
    return spec


def apply_thinking_depth(
    route_info: dict[str, Any],
    depth: str | None,
    *,
    cfg: dict[str, Any] | None = None,
    chat_mode: str = "auto",
) -> dict[str, Any]:
    """Annotate route_info with depth profile; optionally nudge auto routes toward deeper tiers."""
    cfg = cfg or load_campus_config()
    ali = cfg.get("ali") if isinstance(cfg.get("ali"), dict) else {}
    fallback = normalize_thinking_depth((ali or {}).get("thinking_depth"), "medium")
    key = normalize_thinking_depth(depth, fallback)
    spec = thinking_depth_spec(key)
    out = dict(route_info or {})
    out["thinking_depth"] = key
    out["thinking_label"] = spec["label"]
    out["temperature"] = spec["temperature"]
    out["max_tokens"] = spec["max_tokens"]
    out["step_budget"] = spec["step_budget"]
    out["thinking_instructions"] = spec["instructions"]

    # Only nudge automatic routes (not single-model / explicit user route)
    mode = str(chat_mode or "").strip().lower()
    if mode == "single" or not out.get("auto"):
        return out
    nudge = spec.get("nudge")
    if not nudge:
        return out
    cur_tier = str(out.get("tier") or "")
    # Never override vision
    if cur_tier == "Vision" or out.get("route_key") == "vision":
        return out
    order = {"C0": 0, "C1": 1, "C2": 2, "C3": 3}
    if order.get(cur_tier, 1) >= order.get(str(nudge), 0):
        return out
    # Re-resolve toward nudged tier while preserving auto flag
    nudged = resolve_route(nudge if nudge != "Vision" else "vision", "", cfg)
    out["tier"] = nudged.get("tier") or nudge
    out["route_key"] = nudged.get("route_key") or out.get("route_key")
    if nudged.get("model"):
        out["model"] = nudged["model"]
        out["model_slot"] = nudged.get("model_slot") or out.get("model_slot")
    out["review_recommended"] = bool(nudged.get("review_recommended") or out.get("review_recommended"))
    out["label"] = nudged.get("label") or out.get("label")
    out["thinking_nudge"] = nudge
    out["auto"] = True
    return out


def thinking_depth_block(route_info: dict[str, Any] | None = None) -> str:
    info = route_info or {}
    text = str(info.get("thinking_instructions") or "").strip()
    if text:
        return text
    return str(thinking_depth_spec(info.get("thinking_depth")).get("instructions") or "")


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


_GREETING_RE = re.compile(
    r"^\s*(?:"
    r"你好[啊呀吗嘛]?|您好|嗨|哈喽|在吗|在不在|早上好|下午好|晚上好|早安|晚安|"
    r"谢谢|感谢|拜拜|再见|"
    r"hi+|hello|hey+|yo|thanks|thank\s*you|bye|good\s*(?:morning|afternoon|evening|night)|"
    r"how\s+are\s+you|what'?s\s+up|测试一下?|ping|哈哈+"
    r")[\s!！?？。.~～…、，,]*$",
    re.I,
)


def is_simple_chat(message: str) -> bool:
    """True for greetings / chit-chat that should skip skills, search, heal, workflow."""
    raw = (message or "").strip()
    if not raw or len(raw) > 48:
        return False
    if _GREETING_RE.match(raw):
        return True
    low = raw.lower()
    if len(raw) <= 8 and low in {
        "hi", "hey", "yo", "你好", "您好", "嗨", "在吗", "hello", "测试", "ping",
    }:
        return True
    return False


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

    # Hybrid tier map only when backend is Hybrid. A concrete backend.type
    # (e.g. deepseek) must win — leftover hybrid nvidia bindings must not hijack.
    use_hybrid = backend_type == "hybrid" or (
        mode == "hybrid" and backend_type in ("", "hybrid")
    )
    if use_hybrid:
        entry = hybrid.get(route_key) or {}
        provider_id = (entry.get("provider") or "").strip() or provider_id
        if entry.get("model"):
            model = str(entry["model"]).strip()
        prov = get_provider(provider_id) if provider_id and provider_id != "hybrid" else None
        if prov:
            base_url = prov.get("base_url") or base_url
            api_key_env = prov.get("api_key_env") or api_key_env
        # Hybrid often leaves model empty while global models still hold another
        # vendor's short ids — coerce to the active provider's catalog form.
        from .providers import coerce_model_for_provider

        model = coerce_model_for_provider(provider_id, model, route_key=route_key)
    elif provider_id and provider_id not in ("", "hybrid"):
        from .providers import coerce_model_for_provider

        model = coerce_model_for_provider(provider_id, model, route_key=route_key)
        # Prefer provider catalog base_url / env when backend left them stale
        prov = get_provider(provider_id)
        if prov:
            if not base_url:
                base_url = prov.get("base_url") or ""
            if not api_key_env:
                api_key_env = prov.get("api_key_env") or ""

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
        effective = provider_id if use_hybrid else backend_type
        if effective in external_ids and effective not in ("campus-openai-compatible", "local-ollama"):
            blocked = True
            block_reason = f"data_policy=restricted forbids external provider '{effective}'"

    review = bool(TIERS.get(tier, {}).get("review"))
    use_opensquilla = bool(routing.get("use_opensquilla") or routing.get("token_saving"))
    eco = cfg.get("ecosystem") or {}
    if isinstance(eco, dict):
        act = (eco.get("activated") or {}).get("opensquilla") or {}
        if isinstance(act, dict) and act.get("active"):
            use_opensquilla = True

    # When OpenSquilla is active, prefer auto C0–C3 tiering (token-saving)
    if use_opensquilla and raw in ("auto", "", "office"):
        # Keep classified tier; annotate engine for Hub/UI
        pass

    return {
        "tier": tier,
        "route_key": route_key,
        "model": model,
        "model_slot": (routing.get(route_key) or route_key),
        "mode": "hybrid" if use_hybrid else "single",
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
        "routing_engine": "opensquilla" if use_opensquilla else "hub",
        "token_saving": use_opensquilla,
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
    from . import language as lang_mod

    cfg = cfg or load_campus_config()
    obs = cfg.get("obsidian") or {}
    lines = [
        "You are running inside Agent Hub (multi-agent campus terminal).",
        "Role split: local Agent/Claw owns tools when available; OpenSquilla-style routing selects models; Obsidian stores reviewed knowledge only.",
        f"Active route: tier={route_info.get('tier')} slot={route_info.get('route_key')} model={route_info.get('model') or '(unset)'}.",
        f"Routing engine: {route_info.get('routing_engine') or 'hub'}"
        + (" (token-saving)" if route_info.get("token_saving") else "")
        + ".",
        f"Data policy: {cfg.get('data_policy')}.",
        "Identity: You are Agent Hub — not a standalone Hermes CLI chatbot.",
    ]
    msg = str(route_info.get("_user_message") or "")
    if msg:
        lines.append(lang_mod.language_system_rule(msg, cfg))
    else:
        lines.append(
            "## Working language\n"
            "Match the user's message language (Chinese → 简体中文). "
            "Only switch when the user explicitly requests another language."
        )
    if cfg.get("data_policy") == "restricted":
        lines.append("Do NOT send content to external/cloud models. Stay on campus endpoints.")
    if obs.get("vault_path"):
        lines.append(f"Obsidian vault: {obs['vault_path']}")
        lines.append(f"AI writes only to inbox: {obs.get('ai_inbox')} (approval required before moving to formal folders).")
    try:
        from . import ecosystem as eco_mod

        eco_block = eco_mod.ecosystem_context_block(cfg)
        if eco_block:
            lines.append(eco_block)
    except Exception:  # noqa: BLE001
        pass
    lines.append(
        "Require explicit user approval before: sending email, deleting/overwriting files, firewall changes, startup registration, or writing outside AI_Candidates."
    )
    lines.append(
        "Agent Hub owns orchestration: prefer multi-step workflow deliverables over chatty Q&A. "
        "Never dump skill/tool JSON or reasoning boxes to the end user."
    )
    lines.append(
        "Grounding: never invent workspace files or contents. "
        "Only cite paths from the verified listing injected by Agent Hub. "
        "Session attachments with VERIFIED EXCERPTS are valid even when no workspace folder is set — use them; do not refuse."
    )
    lines.append(
        "If a skill/tool is missing and the task fails, Agent Hub will auto-search GitHub, install a matching skill, and retry — "
        "acknowledge briefly then continue the deliverable."
    )
    lines.append(
        "## Code output (required)\n"
        "Whenever you output code or commands (Python, R, Bash/Linux shell, Perl, JavaScript/TypeScript, SQL, Markdown samples, "
        "config snippets, etc.), wrap them in Markdown fenced code blocks with an explicit language tag, e.g.\n"
        "```python\n...\n```\n```r\n...\n```\n```bash\n...\n```\n```perl\n...\n```\n"
        "Do not dump multi-line code as plain indented text. Inline `backticks` only for short identifiers.\n"
        "Exception: never wrap raw skill/tool call JSON in fences for the end user."
    )
    if route_info.get("review_recommended"):
        lines.append("This task is C2-class: prefer generate-then-review (Qwen generate, DeepSeek review) when both models are configured.")
    depth_block = thinking_depth_block(route_info)
    if depth_block:
        lines.append(depth_block)
    return "\n".join(lines)
