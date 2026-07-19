"""Pure planning primitives for Agent Hub multi-model fusion.

This module deliberately does not execute models.  It turns a task, a fusion
mode, and optional model inventory into a serializable plan that the streaming
layer can execute later.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from .routing import classify_message, normalize_thinking_depth

FUSION_MODES = ("fast", "auto", "deep")
_MODE_ALIASES = {
    "fast": "fast",
    "single": "fast",
    "speed": "fast",
    "快速": "fast",
    "auto": "auto",
    "automatic": "auto",
    "自动": "auto",
    "deep": "deep",
    "fusion": "deep",
    "parallel": "deep",
    "深度": "deep",
}
_TIER_ORDER = {"C0": 0, "C1": 1, "C2": 2, "C3": 3, "Vision": 3}
_COMPLEX_KEYWORDS = (
    "研究", "调研", "比较", "评估", "决策", "方案", "架构", "实现", "代码",
    "调试", "审查", "风险", "证据", "论文", "综述", "诊断", "优化", "分析",
    "research", "compare", "evaluate", "decision", "architecture", "implement",
    "debug", "review", "risk", "evidence", "optimize", "analysis",
)
_HIGH_RISK_KEYWORDS = (
    "医疗", "诊断", "临床", "法律", "合规", "财务", "投资", "安全", "高风险",
    "medical", "clinical", "legal", "compliance", "financial", "security",
)


def normalize_fusion_mode(value: str | None, default: str = "auto") -> str:
    """Return ``fast``, ``auto``, or ``deep`` while accepting legacy aliases."""
    fallback = default if default in FUSION_MODES else "auto"
    return _MODE_ALIASES.get(str(value or "").strip().lower(), fallback)


def assess_complexity(
    prompt: str,
    *,
    task_type: str = "auto",
    thinking_depth: str = "medium",
) -> dict[str, Any]:
    """Estimate whether parallel work is worth its token and latency cost.

    The score is deterministic and intentionally conservative: Auto only fans
    out for tasks with multiple complexity signals.  Explicit C2/C3/Vision and
    higher thinking depths are respected without requiring a model call.
    """
    text = str(prompt or "").strip()
    lowered = text.lower()
    requested = _normalize_task_type(task_type)
    tier = classify_message(text) if requested == "auto" else requested
    depth = normalize_thinking_depth(thinking_depth)
    signals: list[str] = []
    keyword_hits = sorted({kw for kw in _COMPLEX_KEYWORDS if kw in lowered})
    # The shared router intentionally favors latency for very short messages.
    # Fusion needs a semantic backstop so a concise research/architecture task
    # is not mistaken for chit-chat merely because it has few CJK characters.
    if requested == "auto" and tier in ("C0", "C1") and len(keyword_hits) >= 2:
        tier = "C3" if any(kw in lowered for kw in ("架构", "代码", "实现", "调试", "安全", "architecture", "code", "debug")) else "C2"
        signals.append("semantic_tier_upgrade")
    score = {"C0": 0.08, "C1": 0.24, "C2": 0.58, "C3": 0.72, "Vision": 0.60}[tier]

    if tier in ("C2", "C3", "Vision"):
        signals.append(f"task_tier:{tier}")
    if keyword_hits:
        score += min(0.18, 0.045 * len(keyword_hits))
        signals.append("complex_intent")
    if any(kw in lowered for kw in _HIGH_RISK_KEYWORDS):
        score += 0.15
        signals.append("high_risk")
    if len(text) >= 600:
        score += 0.10
        signals.append("long_context")
    elif len(text) >= 220:
        score += 0.05
        signals.append("medium_context")
    if _has_multiple_deliverables(text):
        score += 0.10
        signals.append("multiple_deliverables")
    if depth == "high":
        score += 0.08
        signals.append("thinking_depth:high")
    elif depth == "very_high":
        score += 0.16
        signals.append("thinking_depth:very_high")
    elif depth == "light":
        score -= 0.08
        signals.append("thinking_depth:light")

    score = round(max(0.0, min(1.0, score)), 2)
    return {
        "score": score,
        "level": "high" if score >= 0.72 else ("medium" if score >= 0.45 else "low"),
        "tier": tier,
        "thinking_depth": depth,
        "signals": signals,
        "fusion_recommended": score >= 0.56,
        "threshold": 0.56,
    }


def allocate_token_budget(
    mode: str,
    lane_roles: Iterable[str],
    *,
    complexity_score: float = 0.5,
    thinking_depth: str = "medium",
    total_budget: int | None = None,
) -> dict[str, Any]:
    """Allocate planner, per-lane, and judge caps without exceeding total."""
    normalized_mode = normalize_fusion_mode(mode)
    roles = [str(role or "analysis") for role in lane_roles]
    depth = normalize_thinking_depth(thinking_depth)
    if total_budget is None:
        base = 4000 if normalized_mode == "fast" else (12000 if normalized_mode == "deep" else 9000)
        if depth == "light":
            base = int(base * 0.75)
        elif depth == "high":
            base = int(base * 1.20)
        elif depth == "very_high":
            base = int(base * 1.45)
        if normalized_mode != "fast" and float(complexity_score) >= 0.8:
            base += 1500
        total = base
    else:
        total = max(1000, int(total_budget))

    planner = min(800, max(100, int(total * 0.065)))
    judge = 0 if len(roles) < 2 else min(
        3600,
        max(300, int(total * 0.25)),
        max(0, total - planner),
    )
    available = max(0, total - planner - judge)
    weights = {"research": 1.10, "analysis": 1.05, "solution": 1.15, "critic": 0.80, "risk": 0.75}
    denom = sum(weights.get(role, 1.0) for role in roles) or 1.0
    lanes: list[dict[str, Any]] = []
    assigned = 0
    for index, role in enumerate(roles):
        if index == len(roles) - 1:
            cap = available - assigned
        else:
            cap = int(available * weights.get(role, 1.0) / denom)
            assigned += cap
        lanes.append({"role": role, "max_tokens": max(0, cap)})
    return {
        "total_budget": total,
        "planner": planner,
        "lanes": lanes,
        "judge": judge,
        "allocated": planner + judge + sum(item["max_tokens"] for item in lanes),
    }


def plan_fusion(
    prompt: str,
    task_type: str = "auto",
    fusion_mode: str = "auto",
    thinking_depth: str = "medium",
    *,
    cfg: Mapping[str, Any] | None = None,
    models: Iterable[Mapping[str, Any]] | None = None,
    max_lanes: int = 3,
    total_budget: int | None = None,
    route_resolver: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a backward-compatible, JSON-serializable fusion execution plan.

    ``models`` may contain health records or simple route records.  Candidate
    keys understood here include ``model``, ``provider``, ``tier``/``tiers``,
    ``healthy``/``status``, and optional quality/latency scores.  No network or
    model execution occurs.
    """
    text = str(prompt or "").strip()
    if not text:
        raise ValueError("prompt must not be empty")
    mode = normalize_fusion_mode(fusion_mode)
    complexity = assess_complexity(text, task_type=task_type, thinking_depth=thinking_depth)
    enabled = mode == "deep" or (mode == "auto" and complexity["fusion_recommended"])
    lane_count = 1 if not enabled else max(2, min(4, int(max_lanes or 3)))
    roles = _roles_for(complexity["tier"], text, lane_count)
    candidates = _candidate_pool(models, cfg=cfg, prompt=text, resolver=route_resolver)
    primary_candidate = _fast_candidate(candidates) if mode == "fast" else _best_candidate(candidates, complexity["tier"])
    selected = _select_diverse(candidates, roles, complexity["tier"])
    if not selected:
        selected = [primary_candidate]
    while len(selected) < lane_count:
        selected.append(dict(selected[len(selected) % len(selected)]))

    budget = allocate_token_budget(
        mode,
        roles,
        complexity_score=complexity["score"],
        thinking_depth=thinking_depth,
        total_budget=total_budget,
    )
    lanes = []
    for index, (role, candidate) in enumerate(zip(roles, selected)):
        lane_budget = budget["lanes"][index]["max_tokens"]
        lanes.append({
            "id": f"fusion-{role}-{index + 1}",
            "role": role,
            "tier": _lane_tier(role, complexity["tier"]),
            "model": candidate.get("model", ""),
            "provider": candidate.get("provider", ""),
            "max_tokens": lane_budget,
            "max_tokens_override": lane_budget,
            "hidden": True,
            "failure_tolerant": True,
        })

    judge_candidate = _judge_candidate(candidates, selected, primary_candidate)
    judge = None
    if enabled:
        judge = {
            "role": "judge",
            "tier": "C3",
            "model": judge_candidate.get("model", ""),
            "provider": judge_candidate.get("provider", ""),
            "max_tokens": budget["judge"],
            "max_tokens_override": budget["judge"],
            "input_policy": "structured_key_findings",
        }

    primary = {
        "tier": complexity["tier"],
        "model": primary_candidate.get("model", ""),
        "provider": primary_candidate.get("provider", ""),
        "max_tokens": lanes[0]["max_tokens"],
        "max_tokens_override": lanes[0]["max_tokens"],
    }
    reason = _plan_reason(mode, complexity, enabled)
    return {
        "enabled": enabled,
        "mode": mode,
        "requested_mode": str(fusion_mode or "auto"),
        "reason": reason,
        "complexity": complexity,
        "primary": primary,
        "lanes": lanes if enabled else [],
        "judge": judge,
        "budget": budget,
        "failure_policy": {
            "lane_failure": "continue_with_successful_lanes",
            "minimum_successful_lanes": 1,
            "all_lanes_failed": "fallback_to_primary",
            "hide_internal_sessions": True,
        },
        "fallback": {
            "enabled": True,
            "trigger": "all_candidates_failed",
            "strategy": "best_healthy_single_model",
            "tier": primary["tier"],
            "model": primary["model"],
            "provider": primary["provider"],
            "reason": "All fusion lanes failed; retry once with the primary healthy model.",
        },
        "metadata": {
            "planner": "opensquilla-compatible",
            "pure_plan": True,
            "candidate_count": len(candidates),
            "model_diversity": len({lane["model"] for lane in lanes if lane["model"]}),
        },
    }


def build_fusion_plan(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Compatibility alias for callers using the earlier proposed name."""
    return plan_fusion(*args, **kwargs)


def fusion_plan(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Compatibility alias suitable for a thin ``/api/fusion/plan`` route."""
    return plan_fusion(*args, **kwargs)


def _normalize_task_type(value: str | None) -> str:
    raw = str(value or "auto").strip().lower()
    return {"c0": "C0", "c1": "C1", "c2": "C2", "c3": "C3", "vision": "Vision"}.get(raw, "auto")


def _has_multiple_deliverables(text: str) -> bool:
    markers = len(re.findall(r"(?:^|\n)\s*(?:[-*]|\d+[.)、])\s+", text))
    conjunctions = sum(text.lower().count(word) for word in ("并且", "同时", "以及", " and ", " then "))
    return markers >= 2 or conjunctions >= 2


def _roles_for(tier: str, prompt: str, count: int) -> list[str]:
    lowered = prompt.lower()
    if any(word in lowered for word in ("代码", "实现", "debug", "架构", "code", "api")):
        pool = ["solution", "critic", "risk", "analysis"]
    elif any(word in lowered for word in ("研究", "论文", "证据", "调研", "research", "evidence")):
        pool = ["research", "analysis", "critic", "risk"]
    elif tier in ("C2", "C3", "Vision"):
        pool = ["analysis", "solution", "critic", "risk"]
    else:
        pool = ["solution", "critic", "analysis", "risk"]
    return pool[:count]


def _candidate_pool(
    models: Iterable[Mapping[str, Any]] | None,
    *,
    cfg: Mapping[str, Any] | None,
    prompt: str,
    resolver: Callable[..., Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    pool = [_normalize_candidate(item) for item in (models or [])]
    healthy = [item for item in pool if item["healthy"]]
    if healthy:
        return healthy
    if pool:
        return pool

    if resolver is None and cfg is not None:
        from .routing import resolve_route

        resolver = resolve_route
    resolved: list[dict[str, Any]] = []
    if resolver is not None:
        for tier in ("C0", "C1", "C2", "C3", "Vision"):
            route = resolver(tier, prompt, dict(cfg or {}))
            resolved.append(_normalize_candidate({**dict(route), "tier": tier, "healthy": not route.get("blocked")}))
    return resolved or [{"model": "", "provider": "", "tiers": [], "healthy": True, "quality": 0.0, "latency": 0.0}]


def _normalize_candidate(raw: Mapping[str, Any]) -> dict[str, Any]:
    status = str(raw.get("status") or "").lower()
    healthy = bool(raw.get("healthy", status not in {"unavailable", "unsupported", "timeout"}))
    tiers_raw = raw.get("tiers") or raw.get("recommended_categories") or [raw.get("tier")]
    if isinstance(tiers_raw, str):
        tiers_raw = [tiers_raw]
    tiers = [str(tier) for tier in tiers_raw if tier]
    performance = raw.get("performance") if isinstance(raw.get("performance"), Mapping) else {}
    quality = float(raw.get("quality") or performance.get("quality_score") or 0.5)
    latency = float(raw.get("latency_ms") or performance.get("latency_ms") or 0.0)
    return {
        "model": str(raw.get("model") or raw.get("id") or ""),
        "provider": str(raw.get("provider") or raw.get("backend_type") or ""),
        "tiers": tiers,
        "healthy": healthy,
        "quality": max(0.0, min(1.0, quality)),
        "latency": max(0.0, latency),
    }


def _candidate_score(candidate: Mapping[str, Any], tier: str) -> float:
    match = 0.3 if tier in candidate.get("tiers", []) else 0.0
    quality = float(candidate.get("quality") or 0.0) * 0.6
    latency_penalty = min(0.15, float(candidate.get("latency") or 0.0) / 40000.0)
    return match + quality - latency_penalty + (0.1 if candidate.get("healthy") else -0.5)


def _best_candidate(candidates: list[dict[str, Any]], tier: str) -> dict[str, Any]:
    return dict(max(candidates, key=lambda item: _candidate_score(item, tier)))


def _fast_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return dict(min(candidates, key=lambda item: (float(item.get("latency") or 0.0), -float(item.get("quality") or 0.0))))


def _select_diverse(candidates: list[dict[str, Any]], roles: list[str], tier: str) -> list[dict[str, Any]]:
    ranked = sorted(candidates, key=lambda item: _candidate_score(item, tier), reverse=True)
    selected: list[dict[str, Any]] = []
    used_models: set[str] = set()
    for _role in roles:
        choice = next((item for item in ranked if item["model"] and item["model"] not in used_models), None)
        choice = choice or next((item for item in ranked if item not in selected), None) or ranked[0]
        selected.append(dict(choice))
        if choice["model"]:
            used_models.add(choice["model"])
    return selected


def _judge_candidate(
    candidates: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    fallback: dict[str, Any],
) -> dict[str, Any]:
    lane_models = {item.get("model") for item in selected}
    ranked = sorted(candidates, key=lambda item: _candidate_score(item, "C3"), reverse=True)
    return dict(next((item for item in ranked if item.get("model") not in lane_models), ranked[0] if ranked else fallback))


def _lane_tier(role: str, task_tier: str) -> str:
    if role in ("critic", "risk"):
        return "C3"
    if role == "research":
        return "C2"
    return task_tier


def _plan_reason(mode: str, complexity: Mapping[str, Any], enabled: bool) -> str:
    if mode == "fast":
        return "Fast mode uses one low-overhead primary model."
    if mode == "deep":
        return "Deep mode forces diverse parallel lanes and an independent judge."
    if enabled:
        return f"Auto enabled fusion because complexity score {complexity['score']:.2f} meets the {complexity['threshold']:.2f} threshold."
    return f"Auto kept single-model execution because complexity score {complexity['score']:.2f} is below the {complexity['threshold']:.2f} threshold."
