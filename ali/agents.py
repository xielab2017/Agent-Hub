"""Main agent / subagent layout and Control Center tab preferences."""

from __future__ import annotations

from typing import Any

from .settings import load_campus_config, save_campus_config

# Dedicated models: empty = inherit route; slot keys map via routing models config.
DEFAULT_SUBAGENTS = [
    {
        "id": "researcher",
        "label": "研究员",
        "label_en": "Researcher",
        "role": "research",
        "soul_role": "research",
        "enabled": True,
        "desc": "文献检索与摘要",
        "model": "",
        "model_slot": "reasoning",
        "keywords": [
            "文献", "检索", "综述", "论文", "调研", "research", "paper", "literature",
            "pubmed", "arxiv", "引用", "参考",
        ],
    },
    {
        "id": "writer",
        "label": "写作者",
        "label_en": "Writer",
        "role": "office",
        "soul_role": "office",
        "enabled": True,
        "desc": "邮件与文稿起草",
        "model": "",
        "model_slot": "office",
        "keywords": [
            "邮件", "起草", "公文", "通知", "周报", "文稿", "写信", "draft", "email",
            "memo", "write", "撰写", "回复邮件",
        ],
    },
    {
        "id": "reviewer",
        "label": "审阅者",
        "label_en": "Reviewer",
        "role": "research",
        "soul_role": "research",
        "enabled": True,
        "desc": "质量检查与校对",
        "model": "",
        "model_slot": "reasoning",
        "keywords": [
            "审阅", "校对", "检查", "质检", "review", "proofread", "找错", "润色检查",
            "合规", "核对",
        ],
    },
    {
        "id": "ops",
        "label": "运维",
        "label_en": "Ops",
        "role": "ops",
        "soul_role": "ops",
        "enabled": True,
        "desc": "部署与 Skill 安装",
        "model": "",
        "model_slot": "simple",
        "keywords": [
            "部署", "安装", "skill", "运维", "docker", "服务", "端口", "deploy", "install",
            "runtime", "配置环境",
        ],
    },
]

DEFAULT_UI = {
    "layout": "tabs",  # sidebar | split | tabs — default: picker only, no chip wall
    "show_subagent_toolbar": False,  # legacy top bar off; use composer picker
    "active_subagent": "",
    "auto_activate_subagents": True,
    "cc_tabs": {
        "overview": True,
        "providers": True,
        "skills": True,
        "soul": True,
        "agents": True,
        "workflows": True,
        "feedback": True,
    },
}


def _normalize_subagent(raw: dict[str, Any], fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    fb = fallback or {}
    out = {**fb, **raw}
    out["id"] = str(out.get("id") or fb.get("id") or "").strip()
    out["label"] = str(out.get("label") or out["id"])
    out["label_en"] = str(out.get("label_en") or out["label"])
    out["role"] = str(out.get("role") or "office")
    out["soul_role"] = str(out.get("soul_role") or out["role"] or "office")
    out["enabled"] = out.get("enabled") is not False
    out["desc"] = str(out.get("desc") or "")
    out["model"] = str(out.get("model") or "").strip()
    out["model_slot"] = str(out.get("model_slot") or fb.get("model_slot") or "").strip()
    kws = out.get("keywords")
    if not isinstance(kws, list):
        kws = list(fb.get("keywords") or [])
    out["keywords"] = [str(k).strip() for k in kws if str(k).strip()]
    return out


def get_agents() -> dict[str, Any]:
    cfg = load_campus_config()
    ali = cfg.get("ali") if isinstance(cfg.get("ali"), dict) else {}
    agents = ali.get("agents") if isinstance(ali.get("agents"), dict) else {}
    subagents = agents.get("subagents")
    defaults_by_id = {s["id"]: s for s in DEFAULT_SUBAGENTS}
    if not isinstance(subagents, list) or not subagents:
        subagents = [_normalize_subagent(dict(s)) for s in DEFAULT_SUBAGENTS]
    else:
        subagents = [
            _normalize_subagent(s if isinstance(s, dict) else {}, defaults_by_id.get(str((s or {}).get("id") or "")))
            for s in subagents
            if isinstance(s, dict) and str(s.get("id") or "").strip()
        ]
    ui = agents.get("ui") if isinstance(agents.get("ui"), dict) else {}
    merged_ui = {**DEFAULT_UI, **ui}
    if isinstance(ui.get("cc_tabs"), dict):
        merged_ui["cc_tabs"] = {**DEFAULT_UI["cc_tabs"], **ui["cc_tabs"]}
    return {
        "ok": True,
        "main": agents.get("main")
        or {
            "id": "main",
            "label": "主 Agent",
            "label_en": "Main Agent",
            "desc": "Agent Hub 主工作流代理",
            "soul_role": "office",
        },
        "subagents": subagents,
        "ui": merged_ui,
    }


def save_agents(payload: dict[str, Any]) -> dict[str, Any]:
    cfg = load_campus_config()
    ali = cfg.setdefault("ali", {})
    if not isinstance(ali, dict):
        ali = {}
        cfg["ali"] = ali
    agents = ali.setdefault("agents", {})
    if not isinstance(agents, dict):
        agents = {}
        ali["agents"] = agents

    if "main" in payload and isinstance(payload["main"], dict):
        agents["main"] = payload["main"]
    if "subagents" in payload and isinstance(payload["subagents"], list):
        agents["subagents"] = [
            _normalize_subagent(s) for s in payload["subagents"] if isinstance(s, dict) and s.get("id")
        ]
    if "ui" in payload and isinstance(payload["ui"], dict):
        prev = agents.get("ui") if isinstance(agents.get("ui"), dict) else {}
        agents["ui"] = {**prev, **payload["ui"]}
        if isinstance(payload["ui"].get("cc_tabs"), dict):
            tabs = prev.get("cc_tabs") if isinstance(prev.get("cc_tabs"), dict) else {}
            agents["ui"]["cc_tabs"] = {**tabs, **payload["ui"]["cc_tabs"]}

    save_campus_config(cfg)
    return get_agents()


def resolve_subagent_model(sub: dict[str, Any], cfg: dict[str, Any] | None = None) -> str:
    """Pick a dedicated fast/specialized model for a subagent."""
    explicit = str((sub or {}).get("model") or "").strip()
    if explicit:
        return explicit
    cfg = cfg or load_campus_config()
    models = cfg.get("models") if isinstance(cfg.get("models"), dict) else {}
    slot = str((sub or {}).get("model_slot") or "").strip()
    slot_map = {
        "simple": ("fast", "qwen_fast", "simple"),
        "office": ("main", "qwen_main", "office"),
        "reasoning": ("reasoning", "deepseek_reasoning", "reason"),
        "vision": ("vision", "qwen_vl", "vision"),
        # OpenSquilla-facing aliases
        "c0": ("fast", "qwen_fast", "simple"),
        "c1": ("main", "qwen_main", "office"),
        "c2": ("main", "qwen_main", "office"),
        "c3": ("reasoning", "deepseek_reasoning", "reason"),
        "fast": ("fast", "qwen_fast", "simple"),
        "main": ("main", "qwen_main", "office"),
    }
    keys = slot_map.get(slot) or ((slot,) if slot else ("fast", "qwen_fast", "main"))
    for k in keys:
        v = str((models or {}).get(k) or "").strip()
        if v:
            return v
    return ""


def slot_to_tier(slot: str) -> str:
    s = (slot or "").strip().lower()
    return {
        "simple": "C0",
        "fast": "C0",
        "c0": "C0",
        "office": "C1",
        "main": "C1",
        "c1": "C1",
        "c2": "C2",
        "reasoning": "C3",
        "c3": "C3",
        "vision": "Vision",
    }.get(s, "")


def pick_subagents_for_parallel(
    count: int,
    message: str = "",
    *,
    agents: dict[str, Any] | None = None,
    prefer_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Pick N catalog subagents with diverse model slots for parallel speed.

    Each item is enriched with ``resolved_model``, ``tier``, and ``soul_role``.
    """
    n = max(2, min(6, int(count or 2)))
    data = agents or get_agents()
    cfg = load_campus_config()
    catalog = [
        dict(s)
        for s in (data.get("subagents") or [])
        if isinstance(s, dict) and str(s.get("id") or "").strip()
    ]
    # "enabled" in Hub UI means “show in composer picker”. For auto-parallel we still
    # want the full catalog so work can fan out across tiers/souls.
    picker_on = [s for s in catalog if s.get("enabled") is not False]
    enabled = picker_on or catalog
    by_id = {str(s.get("id")): s for s in catalog}
    picked: list[dict[str, Any]] = []

    # 1) Explicit composer selection (may include picker-off entries)
    for sid in prefer_ids or []:
        if len(picked) >= n:
            break
        sub = by_id.get(str(sid or "").strip())
        if sub and sub not in picked:
            picked.append(sub)

    # 2) Keyword matches (auto soul/model binding)
    text = (message or "").strip().lower()
    scored: list[tuple[int, dict[str, Any]]] = []
    for s in enabled:
        if s in picked:
            continue
        kws = s.get("keywords") or []
        hits = sum(1 for kw in kws if str(kw).lower() in text) if text else 0
        scored.append((hits, s))
    scored.sort(key=lambda x: (-x[0], str(x[1].get("id") or "")))
    for hits, s in scored:
        if hits <= 0:
            break
        if len(picked) >= n:
            break
        if s not in picked:
            picked.append(s)

    # 3) Fill remaining with diverse model_slots (different tiers → true parallel speed)
    used_slots = {str(s.get("model_slot") or "") for s in picked}
    for _, s in scored:
        if len(picked) >= n:
            break
        if s in picked:
            continue
        slot = str(s.get("model_slot") or "")
        if slot and slot in used_slots and len(enabled) > len(picked):
            continue
        picked.append(s)
        used_slots.add(slot)
    for _, s in scored:
        if len(picked) >= n:
            break
        if s not in picked:
            picked.append(s)
    while len(picked) < n and enabled:
        picked.append(enabled[len(picked) % len(enabled)])

    # If catalog empty, synthesize lightweight tier lanes so parallel still works
    if not picked:
        stubs = [
            {"id": "lane-fast", "label": "Fast", "label_en": "Fast", "model_slot": "simple", "soul_role": "office", "desc": "C0 fast lane"},
            {"id": "lane-main", "label": "Main", "label_en": "Main", "model_slot": "office", "soul_role": "office", "desc": "C1/C2 main lane"},
            {"id": "lane-reason", "label": "Reason", "label_en": "Reason", "model_slot": "reasoning", "soul_role": "research", "desc": "C3 reasoning lane"},
            {"id": "lane-vision", "label": "Vision", "label_en": "Vision", "model_slot": "vision", "soul_role": "research", "desc": "Vision lane"},
        ]
        picked = [dict(stubs[i % len(stubs)]) for i in range(n)]

    out: list[dict[str, Any]] = []
    cycle = ("C0", "C1", "C2")
    for i, s in enumerate(picked[:n]):
        item = dict(s)
        slot = str(item.get("model_slot") or "").strip()
        tier = slot_to_tier(slot) or cycle[i % len(cycle)]
        item["soul_role"] = str(item.get("soul_role") or item.get("role") or "office").strip() or "office"
        item["resolved_model"] = resolve_subagent_model(item, cfg)
        item["tier"] = tier
        out.append(item)
    return out


def pick_subagent_for_message(message: str, *, agents: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Activate a specialized subagent when the message clearly matches its keywords."""
    text = (message or "").strip().lower()
    if not text:
        return None
    data = agents or get_agents()
    ui = data.get("ui") or {}
    if ui.get("auto_activate_subagents") is False:
        return None
    best: tuple[int, dict[str, Any]] | None = None
    for sub in data.get("subagents") or []:
        if sub.get("enabled") is False:
            continue
        kws = sub.get("keywords") or []
        hits = sum(1 for kw in kws if kw.lower() in text)
        if hits <= 0:
            continue
        # Prefer more specific (more hits); tie-break by keyword density
        score = hits * 10 + min(len(kws), 5)
        if best is None or score > best[0]:
            best = (score, sub)
    if not best or best[0] < 10:
        return None
    return best[1]


def subagent_system_prompt(sub: dict[str, Any]) -> str:
    label = sub.get("label") or sub.get("id") or "subagent"
    return (
        f'You are Agent Hub subagent "{label}" '
        f'(role={sub.get("role") or ""}, soul={sub.get("soul_role") or sub.get("role") or ""}). '
        f'{sub.get("desc") or ""}\n'
        "Stay focused on this specialized role; keep answers concise and actionable. "
        "When emitting code, always use Markdown fenced blocks with a language tag "
        "(```python, ```r, ```bash, ```perl, ```markdown, etc.)."
    )


def _slug_id(label: str, fallback: str = "sub") -> str:
    import re

    raw = (label or "").strip().lower()
    slug = re.sub(r"[^a-z0-9_-]+", "-", raw).strip("-")
    if slug:
        return slug[:48]
    # CJK / other: keep a short hash-ish suffix
    return f"{fallback}-{abs(hash(label)) % 100000}"


def upsert_subagent(payload: dict[str, Any]) -> dict[str, Any]:
    """Create or update one subagent in the catalog; returns full agents view."""
    raw = payload if isinstance(payload, dict) else {}
    label = str(raw.get("label") or "").strip()
    sid = str(raw.get("id") or "").strip() or _slug_id(label or "sub")
    if not sid:
        raise ValueError("id or label required")
    data = get_agents()
    subs = list(data.get("subagents") or [])
    normalized = _normalize_subagent({**raw, "id": sid, "label": label or sid, "enabled": raw.get("enabled", True)})
    found = False
    for i, s in enumerate(subs):
        if s.get("id") == sid:
            subs[i] = _normalize_subagent({**s, **normalized})
            found = True
            break
    if not found:
        subs.append(normalized)
    return save_agents({"subagents": subs, "ui": data.get("ui") or {}})
