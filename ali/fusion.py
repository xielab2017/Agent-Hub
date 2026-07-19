"""OpenSquilla-aware multi-model fusion policy and token budgeting."""

from __future__ import annotations

import re
from typing import Any

from .routing import classify_message


MODES = {"fast", "auto", "deep"}


def normalize_mode(value: Any) -> str:
    raw = str(value or "auto").strip().lower().replace("_", "-")
    aliases = {
        "single": "fast", "off": "fast", "fast-only": "fast",
        "auto-fusion": "auto", "fusion": "auto", "balanced": "auto",
        "deep-fusion": "deep", "experts": "deep", "max": "deep",
    }
    return aliases.get(raw, raw if raw in MODES else "auto")


def plan_fusion(message: str, mode: str = "auto") -> dict[str, Any]:
    """Return a deterministic execution strategy and hard output budgets."""
    text = str(message or "").strip()
    selected = normalize_mode(mode)
    tier = classify_message(text)
    compare = bool(re.search(r"比较|对比|权衡|争议|反驳|审查|验证|多视角|compare|trade.?off|review|verify", text, re.I))
    multipart = bool(re.search(r"并且|同时|分别|然后|以及|方案.{0,12}风险|and then|plus|multiple", text, re.I))

    if selected == "fast":
        strategy, lanes = "single", 1
    elif selected == "deep":
        strategy = "expert_fusion"
        lanes = 2 if tier in ("C0", "C1") and not multipart else 3
    elif tier in ("C0", "Vision") and not compare and not multipart:
        strategy, lanes = "single", 1
    elif tier == "C1" and not compare and not multipart:
        strategy, lanes = "single", 1
    elif tier == "C2":
        strategy, lanes = "expert_fusion", 2
    elif tier == "C3" or compare or multipart:
        strategy, lanes = "expert_fusion", 2
    else:
        strategy, lanes = "single", 1

    totals = {
        "C0": (800, 900), "C1": (1800, 1400), "C2": (6000, 2200),
        "C3": (8000, 2600), "Vision": (4500, 1800),
    }
    total_budget, synthesis = totals.get(tier, totals["C1"])
    if selected == "fast":
        total_budget = min(total_budget, 1800)
    elif selected == "deep":
        total_budget = int(total_budget * 1.5)
        synthesis = int(synthesis * 1.25)

    if lanes == 1:
        lane_budget = total_budget
        synthesis = 0
    else:
        total_budget = max(total_budget, lanes * 500 + 600)
        # Reserve synthesis first; experts share the remaining budget.
        synthesis = min(synthesis, max(600, total_budget // 3))
        lane_budget = max(500, (total_budget - synthesis) // lanes)
    return {
        "ok": True,
        "mode": selected,
        "tier": tier,
        "strategy": strategy,
        "need_parallel": lanes > 1,
        "lane_count": lanes,
        "total_token_budget": total_budget,
        "lane_token_budget": lane_budget,
        "synthesis_token_budget": synthesis,
        "review_required": lanes > 1 and (selected == "deep" or tier in ("C2", "C3") or compare),
        "early_exit": selected != "deep",
        "token_policy": "short-specialists-then-compress" if lanes > 1 else "single-model",
    }
