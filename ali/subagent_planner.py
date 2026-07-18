"""Server-side auto planner for Hub parallel subagent lanes.

Replaces keyword catalogs and frontend heuristics: a lightweight C0 LLM decides
whether to fan out, which roles to spawn, and optional search queries for grounding.
"""

from __future__ import annotations

import json
import re
from typing import Any

from . import websearch
from .agents import DEFAULT_SUBAGENTS, get_agents, normalize_agent_route, resolve_subagent_binding
from .settings import load_campus_config, resolve_backend_verify_tls

_ROLE_PROTOTYPES = {s["id"]: s for s in DEFAULT_SUBAGENTS}

_PLANNER_SYSTEM = """You are Agent Hub's subagent planner. Reply with ONLY valid JSON (no markdown fences).

Schema:
{
  "need_parallel": boolean,
  "needs_search": boolean,
  "synthesis_focus": "string",
  "lanes": [
    {
      "id": "researcher|writer|reviewer|ops|custom_slug",
      "role": "short role name",
      "goal": "single concrete objective for this lane only",
      "route_hint": "C0|C1|C2|C3|Vision|auto",
      "soul_hint": "office|research|ops|...",
      "search_queries": ["optional queries"]
    }
  ],
  "single_role": null or same object as one lane when need_parallel is false but a specialty helps
}

Rules:
- need_parallel=true ONLY when the user task clearly benefits from ≥2 complementary roles (e.g. research+write, multi-group collect).
- Pure greetings, yes/no, or single short Q&A → need_parallel=false, lanes=[].
- Prefer 2–3 lanes; never exceed max_lanes.
- Each lane has ONE goal; do not overlap responsibilities.
- needs_search=true for facts, literature, news, standings, citations, or anything time-sensitive.
- Put search_queries on lanes that need grounding (1–3 short queries each).
- Do not use a coding/data-engineering role unless the user explicitly asks for code,
  scripts, APIs, repositories, debugging, or runnable analysis. The word "分析"
  alone is not a coding request.
- For news/events, prefer roles such as source verifier, fact checker, timeline
  analyst, trend analyst, and synthesis editor.
- Use id from: researcher, writer, reviewer, ops when they fit; otherwise a short english slug.
"""


def _ui_flags(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    data = get_agents()
    ui = data.get("ui") if isinstance(data.get("ui"), dict) else {}
    auto = ui.get("auto_parallel")
    if auto is None:
        auto = ui.get("auto_activate_subagents")
    if auto is None:
        auto = True
    try:
        max_lanes = int(ui.get("max_lanes") or 3)
    except (TypeError, ValueError):
        max_lanes = 3
    max_lanes = max(2, min(6, max_lanes))
    return {"auto_parallel": bool(auto), "max_lanes": max_lanes, "ui": ui}


def _extract_json(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def _detect_nl_count(message: str) -> int:
    s = message or ""
    cn_map = {"两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6}

    def parse_n(raw: str) -> int:
        if raw in cn_map:
            return cn_map[raw]
        try:
            n = int(raw)
        except ValueError:
            return 0
        return n if 2 <= n <= 6 else 0

    patterns = [
        r"(?:分成|分作|拆成|拆分(?:成)?|拆为|并行(?:调度)?)\s*([二三四五六两\d]+)\s*个?\s*(?:子代理|子\s*agent|sub[-\s]?agents?|agents?|代理)",
        r"(?:启动|调用|派发|开|用)\s*([二三四五六两\d]+)\s*个?\s*(?:子代理|子\s*agent|sub[-\s]?agents?|agents?)",
        r"([二三四五六两\d]+)\s*个\s*(?:子代理|子\s*agent|sub[-\s]?agents?|agents?)",
        r"(?:split|parallel|launch|spawn|start)\s*(?:into\s*)?(\d+)\s*(?:sub[-\s]?agents?|agents?)",
    ]
    for pat in patterns:
        m = re.search(pat, s, re.I)
        if m:
            n = parse_n(m.group(1))
            if n:
                return n
    if re.search(r"(?:子代理|sub[-\s]?agent)", s, re.I) and re.search(r"(?:分别|并行|同时)", s):
        return 3
    return 0


def _looks_like_greeting(message: str) -> bool:
    s = (message or "").strip()
    if len(s) > 40:
        return False
    return bool(
        re.fullmatch(
            r"(你好|您好|hi|hello|hey|早上好|下午好|晚上好|在吗|嗨)[!！.。?？\s]*",
            s,
            re.I,
        )
    )


def _heuristic_plan(message: str, *, max_lanes: int, force_count: int = 0) -> dict[str, Any]:
    """Fallback when LLM planner is unavailable."""
    if _looks_like_greeting(message) and not force_count:
        return {
            "ok": True,
            "need_parallel": False,
            "needs_search": False,
            "synthesis_focus": "",
            "lanes": [],
            "single_role": None,
            "source": "heuristic",
        }

    text = message or ""
    n = force_count or 0
    # Multi-part tasks → suggest parallel
    multi_signal = bool(
        re.search(
            r"并(?:且)?(?:写|起草|总结|审阅)|同时|分别|一边|调研.{0,12}(?:邮件|文稿|报告)|"
            r"research.+write|then\s+write|and\s+draft",
            text,
            re.I,
        )
    )
    # "分析/总结/预测" are ordinary research intents, not code intents.
    # Require explicit programming, repository, API, or reproducible-data
    # language before producing code-oriented lanes.
    code_signal = bool(
        re.search(
            r"(?:\bR\b|\bpython\b|代码|编程|脚本|源码|仓库|github|stackoverflow|"
            r"API|接口调用|调试|debug|traceback|报错|函数|class\b|ggplot|pandas|"
            r"dplyr|sql|npm|pypi|可运行代码|复现代码)",
            text,
            re.I,
        )
    )
    # Sports / event queries ("世界杯战况", "英超积分", "NBA playoffs")
    # also count as search signal AND as a force-multi signal when the user
    # asks for a structured summary (a single lane rarely covers standings
    # + scorelines + knockout scenarios + next matches in one go).
    event_signal = bool(
        re.search(
            r"世界杯|欧洲杯|美洲杯|欧冠|亚冠|英超|西甲|德甲|意甲|法甲|中超|J联赛|K联赛|"
            r"NBA|CBA|WNBA|FIFA|World\s*Cup|Euro|Champions\s*League|"
            r"小组赛|淘汰赛|半决赛|决赛|1/8|1/4|1/2|"
            r"战况|战局|战报|赛果|积分榜|赛程|今晚|昨日|昨天|今晚比赛|出线形势|晋级|夺冠|"
            r"playoff|standings|knockout|quarterfinal|semifinal|bracket",
            text,
            re.I,
        )
    )
    search_signal = bool(
        re.search(
            r"搜索|检索|调研|文献|论文|新闻|最新|赛果|积分|cite|arxiv|pubmed|web\s*search|google|"
            r"世界杯|战况|战局|小组赛|出线|晋级|积分榜|赛程|赛报",
            text,
            re.I,
        )
    )

    if not n and not multi_signal and not code_signal and not event_signal:
        # Single specialty if keyword-like match
        single = None
        low = text.lower()
        best_hits = 0
        for proto in DEFAULT_SUBAGENTS:
            hits = sum(1 for kw in (proto.get("keywords") or []) if str(kw).lower() in low)
            if hits > best_hits:
                best_hits = hits
                single = proto
        if best_hits >= 1 and single:
            return {
                "ok": True,
                "need_parallel": False,
                "needs_search": search_signal,
                "synthesis_focus": "",
                "lanes": [],
                "single_role": {
                    "id": single["id"],
                    "role": single.get("label") or single["id"],
                    "goal": single.get("desc") or "",
                    "route_hint": normalize_agent_route(single.get("model_slot")),
                    "soul_hint": single.get("soul_role") or "office",
                    "search_queries": [text[:120]] if search_signal else [],
                },
                "source": "heuristic",
            }
        return {
            "ok": True,
            "need_parallel": False,
            "needs_search": search_signal,
            "synthesis_focus": "",
            "lanes": [],
            "single_role": None,
            "source": "heuristic",
        }

    n = max(2, min(max_lanes, n or (3 if code_signal or event_signal else 2)))
    if event_signal and not code_signal:
        # Sports / event queries get a purpose-built lane pool: each lane
        # searches a distinct angle (standings / scorelines / scenarios /
        # key match / digest) so the synthesiser has a balanced matrix to
        # consolidate. The default depth is 3 lanes — enough to cover
        # "积分 / 赛果 / 出线" without over-spending tokens.
        pool = [
            {"id": "standings", "role": "积分榜与排名", "goal": "汇总当前各组/各队积分榜与净胜球", "route_hint": "C0", "soul_hint": "research"},
            {"id": "scorelines", "role": "近期赛果", "goal": "列出近 24 小时各场比赛比分与关键事件", "route_hint": "C0", "soul_hint": "research"},
            {"id": "bracket", "role": "出线与对阵", "goal": "梳理各组出线形势、关键对阵、晋级路径", "route_hint": "C3", "soul_hint": "research"},
            {"id": "keymatch", "role": "关键比赛复盘", "goal": "挑 1-2 场最具决定性的比赛做战术/数据复盘", "route_hint": "C3", "soul_hint": "research"},
            {"id": "upcoming", "role": "未来赛程与预测", "goal": "整理下一轮赛程与可量化的预测要素", "route_hint": "C1", "soul_hint": "office"},
            {"id": "synth", "role": "汇总简报", "goal": "把以上 5 路要点压缩为管理层可读简报", "route_hint": "C1", "soul_hint": "office"},
        ]
    elif code_signal:
        pool = [
            {"id": "data-prep", "role": "数据准备", "goal": "数据导入、清洗与可运行准备代码", "route_hint": "C0", "soul_hint": "office"},
            {"id": "analysis", "role": "核心分析", "goal": "统计/建模分析与关键结果", "route_hint": "C1", "soul_hint": "research"},
            {"id": "viz", "role": "可视化与报告", "goal": "图表与可读报告输出", "route_hint": "C1", "soul_hint": "office"},
            {"id": "qa", "role": "质量检查", "goal": "核对口径、复现步骤与异常值", "route_hint": "C3", "soul_hint": "research"},
            {"id": "risk", "role": "风险清单", "goal": "列出数据缺口与未证实推断", "route_hint": "C3", "soul_hint": "research"},
            {"id": "synth", "role": "交付整合", "goal": "汇总可执行交付物与下一步", "route_hint": "C1", "soul_hint": "office"},
        ]
    elif multi_signal and search_signal:
        pool = [
            {"id": "researcher", "role": "研究员", "goal": "检索与摘要关键事实/文献", "route_hint": "C3", "soul_hint": "research"},
            {"id": "writer", "role": "写作者", "goal": "基于检索结果起草可读交付", "route_hint": "C1", "soul_hint": "office"},
            {"id": "reviewer", "role": "审阅者", "goal": "核对语气、事实与遗漏", "route_hint": "C3", "soul_hint": "research"},
            {"id": "sources", "role": "来源核对", "goal": "整理 URL/引用并标注可信度", "route_hint": "C3", "soul_hint": "research"},
            {"id": "brief", "role": "简报压缩", "goal": "压缩为管理层可读要点", "route_hint": "C0", "soul_hint": "office"},
            {"id": "actions", "role": "行动建议", "goal": "给出可执行下一步", "route_hint": "C1", "soul_hint": "office"},
        ]
    else:
        pool = [
            {"id": "planner", "role": "方案拆解", "goal": "明确目标、约束与交付结构", "route_hint": "C0", "soul_hint": "office"},
            {"id": "writer", "role": "核心产出", "goal": "产出主体内容/草稿", "route_hint": "C1", "soul_hint": "office"},
            {"id": "reviewer", "role": "审阅补全", "goal": "检查缺口与风险并润色", "route_hint": "C3", "soul_hint": "research"},
            {"id": "background", "role": "背景调研", "goal": "补充背景与约束条件", "route_hint": "C3", "soul_hint": "research"},
            {"id": "visual", "role": "结构化呈现", "goal": "表格/要点可视化表达", "route_hint": "C1", "soul_hint": "office"},
            {"id": "risk", "role": "风险清单", "goal": "列出未证实处与风险", "route_hint": "C3", "soul_hint": "research"},
        ]
    # Cycle pool if force_count exceeds built-in roles.
    selected = []
    for i in range(n):
        item = dict(pool[i % len(pool)])
        if i >= len(pool):
            item["id"] = f"{item['id']}-{i+1}"
            item["role"] = f"{item['role']}#{i+1}"
        selected.append(item)
    lanes = []
    for i, item in enumerate(selected):
        lane = dict(item)
        if event_signal:
            # Per-lane search queries so each lane actually pulls a
            # different angle from the web, rather than every lane
            # running the same broad query.
            lane_id = item.get("id") or ""
            lane["search_queries"] = _event_lane_queries(lane_id, text)
        elif search_signal and i == 0:
            lane["search_queries"] = [text[:100]]
        else:
            lane["search_queries"] = []
        lanes.append(lane)
    return {
        "ok": True,
        "need_parallel": True,
        "needs_search": search_signal,
        "synthesis_focus": "综合各车道要点，标注冲突与未证实处，并附用来源",
        "lanes": lanes,
        "single_role": None,
        "source": "heuristic",
    }


# Per-lane search queries for sports / event intents. Each lane focuses
# on a distinct angle so the synthesiser has a balanced matrix to
# consolidate, instead of N lanes all running the same broad query.
_EVENT_LANE_QUERIES: dict[str, list[str]] = {
    "standings": [
        "<topic> 积分榜 排名 净胜球",
        "<topic> group standings table points goal difference",
    ],
    "scorelines": [
        "<topic> 昨日 今日 赛果 比分",
        "<topic> latest match results scorelines yesterday today",
    ],
    "bracket": [
        "<topic> 出线 晋级 淘汰赛 对阵",
        "<topic> knockout stage bracket qualification scenarios",
    ],
    "keymatch": [
        "<topic> 关键比赛 复盘 战术 进球",
        "<topic> key match tactical analysis goal breakdown",
    ],
    "upcoming": [
        "<topic> 下一轮 赛程 预测",
        "<topic> next round fixtures schedule prediction",
    ],
    "synth": [
        "<topic> 综述 简报 要点",
    ],
}


def _event_lane_queries(lane_id: str, user_text: str) -> list[str]:
    templates = _EVENT_LANE_QUERIES.get(lane_id) or ["<topic>"]
    topic = (user_text or "").strip()[:60]
    return [t.replace("<topic>", topic) for t in templates]


def _explicit_code_request(message: str) -> bool:
    return bool(re.search(
        r"(?:\bpython\b|\bR\b|代码|编程|脚本|源码|github|stackoverflow|API|接口调用|"
        r"调试|debug|traceback|报错|函数|class\b|ggplot|pandas|dplyr|sql|npm|pypi|"
        r"可运行代码|复现代码)",
        message or "",
        re.I,
    ))


# Recognised event-pool lane ids.  Used to detect when an LLM-generated plan
# ignored the sports/event signal and returned generic research lanes.
_EVENT_LANE_IDS = {"standings", "scorelines", "bracket", "keymatch", "upcoming", "synth"}


def _has_event_signal(message: str) -> bool:
    """Same regex as the heuristic — kept in sync so callers can detect
    event intent without duplicating the pattern."""
    return bool(re.search(
        r"世界杯|欧洲杯|美洲杯|欧冠|亚冠|英超|西甲|德甲|意甲|法甲|中超|J联赛|K联赛|"
        r"NBA|CBA|WNBA|FIFA|World\s*Cup|Euro|Champions\s*League|"
        r"小组赛|淘汰赛|半决赛|决赛|1/8|1/4|1/2|"
        r"战况|战局|战报|赛果|积分榜|赛程|今晚|昨日|昨天|今晚比赛|出线形势|晋级|夺冠|"
        r"playoff|standings|knockout|quarterfinal|semifinal|bracket",
        message or "",
        re.I,
    ))


def _plan_uses_event_pool(plan: dict[str, Any]) -> bool:
    lanes = plan.get("lanes") if isinstance(plan.get("lanes"), list) else []
    return any(isinstance(l, dict) and str(l.get("id") or "").split("-")[0] in _EVENT_LANE_IDS
               for l in lanes)


def _repair_unrelated_code_lanes(plan: dict[str, Any], message: str) -> dict[str, Any]:
    """Prevent a generic research/news task from inheriting code templates."""
    if _explicit_code_request(message):
        return plan
    lanes = plan.get("lanes") if isinstance(plan.get("lanes"), list) else []
    replacements = [
        ("来源核验", "核对关键事实、来源日期与原始链接"),
        ("证据整理", "提取来源支持的要点并标注冲突与缺口"),
        ("趋势分析", "基于已核验事实分析趋势与不确定性"),
        ("综合编辑", "压缩为主代理可直接引用的结构化摘要"),
    ]
    changed = False
    for i, lane in enumerate(lanes):
        if not isinstance(lane, dict):
            continue
        blob = f"{lane.get('id') or ''} {lane.get('role') or ''} {lane.get('goal') or ''}".lower()
        if not any(k in blob for k in ("code", "代码", "脚本", "数据准备", "建模", "可视化与报告")):
            continue
        role, goal = replacements[min(i, len(replacements) - 1)]
        lane["id"] = f"evidence-{i + 1}"
        lane["role"] = role
        lane["goal"] = goal
        lane["label"] = role
        lane["desc"] = goal
        lane["route_hint"] = "C1"
        lane["soul_hint"] = "research"
        lane["search_queries"] = [message[:120]] if message else []
        changed = True
    if changed:
        plan["source"] = str(plan.get("source") or "") + "+role-guard"
    return plan


def _call_planner_llm(message: str, session_context: str, max_lanes: int, cfg: dict[str, Any]) -> dict[str, Any] | None:
    from . import llm_client
    from .providers import coerce_model_for_provider, get_provider
    from .routing import resolve_route
    from .secrets import resolve_api_key

    route_info = resolve_route("C0", message, cfg)
    backend = cfg.get("backend") or {}
    provider = str(route_info.get("provider") or backend.get("type") or "").strip()
    if provider == "hybrid":
        provider = str(backend.get("type") or "").strip()
    prov = get_provider(provider) if provider else None
    base_url = str(route_info.get("base_url") or backend.get("base_url") or "").strip()
    if prov and provider not in ("", "hybrid", "campus-openai-compatible", "local-ollama"):
        catalog_url = str(prov.get("base_url") or "").strip()
        if catalog_url:
            base_url = catalog_url
    key_info = resolve_api_key(cfg, provider=provider if provider != "hybrid" else "")
    api_key = key_info.get("key") or ""
    model = coerce_model_for_provider(
        provider,
        str(route_info.get("model") or "").strip(),
        route_key=str(route_info.get("route_key") or "simple"),
    )
    if not base_url or not model:
        return None
    if not api_key and provider not in ("local-ollama",):
        return None

    user = (
        f"max_lanes={max_lanes}\n"
        f"session_context:\n{(session_context or '(none)')[:1200]}\n\n"
        f"user_message:\n{message}"
    )
    try:
        text = llm_client._chat_once(
            base_url,
            api_key,
            model=model,
            messages=[
                {"role": "system", "content": _PLANNER_SYSTEM},
                {"role": "user", "content": user},
            ],
            # Planning is a control-plane hint, not the user deliverable.  A
            # slow planner must fall back to heuristics quickly so the UI can
            # continue and the main task is never held hostage by it.
            timeout=min(8.0, float(backend.get("timeout_seconds") or 8)),
            verify_tls=resolve_backend_verify_tls(cfg, route_info),
            temperature=0.2,
            max_tokens=900,
        )
    except Exception:  # noqa: BLE001
        return None
    return _extract_json(text)


def _normalize_lane(raw: dict[str, Any], index: int, cfg: dict[str, Any]) -> dict[str, Any]:
    sid = str(raw.get("id") or f"lane-{index + 1}").strip() or f"lane-{index + 1}"
    proto = _ROLE_PROTOTYPES.get(sid) or {}
    role = str(raw.get("role") or proto.get("label") or sid).strip()
    goal = str(raw.get("goal") or proto.get("desc") or "").strip()
    route_hint = normalize_agent_route(
        raw.get("route_hint")
        if raw.get("route_hint") is not None
        else (proto.get("route") or proto.get("model_slot") or "auto")
    )
    soul_hint = str(raw.get("soul_hint") or proto.get("soul_role") or proto.get("role") or "office").strip() or "office"
    queries = raw.get("search_queries") if isinstance(raw.get("search_queries"), list) else []
    queries = [str(q).strip() for q in queries if str(q).strip()][:3]
    binding_src = {
        "id": sid,
        "route": route_hint,
        "model_slot": route_hint,
        "model": "",
        "soul_role": soul_hint,
        "role": soul_hint,
        "label": role,
        "desc": goal,
    }
    binding = resolve_subagent_binding(binding_src, cfg)
    system = (
        f'You are Agent Hub subagent "{role}" (id={sid}, soul={soul_hint}).\n'
        f"Single objective for this lane: {goal}\n"
        "Do not take on other lanes' work. Stay concise and actionable. "
        "Use Markdown fences with language tags for code. "
        "Cite URLs when search context is provided; mark unverified claims."
    )
    return {
        "id": sid,
        "subagent_id": sid,
        "role": role,
        "label": role,
        "goal": goal,
        "responsibility": goal,
        "route_hint": route_hint,
        "route": route_hint,
        "model_slot": route_hint,
        "soul_hint": soul_hint,
        "soul_role": soul_hint,
        "search_queries": queries,
        "resolved_model": binding.get("model") or "",
        "resolved_provider": binding.get("provider") or "",
        "tier": binding.get("tier") or route_hint if route_hint != "auto" else "",
        "system": system,
        "desc": goal,
    }


def _gather_sources(
    queries: list[str],
    *,
    enabled: bool,
    limit: int = 8,
    parallel: bool = True,
) -> tuple[list[dict[str, Any]], str]:
    """Run the per-lane search queries and aggregate a unique source list.

    When `parallel` is True and we have more than one query, we use the
    MiniMax-code style parallel fan-out (`parallel_search`) so the planner
    gets a wider angle in roughly the same wall-clock time.  When only one
    query is present (or the parallel budget would be wasted) we fall back
    to a serial call.
    """
    if not enabled or not queries:
        return [], ""
    all_sources: list[dict[str, Any]] = []
    chunks: list[str] = []
    seen_urls: set[str] = set()

    def _absorb(payload: dict[str, Any]) -> None:
        for s in payload.get("sources") or []:
            url = str(s.get("url") or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            all_sources.append(s)
        if payload.get("context_markdown"):
            chunks.append(payload["context_markdown"])

    if parallel and len(queries) > 1:
        try:
            from .minimax_search_parity import parallel_search as _parallel

            bounded = list(queries)[:4]  # keep planner previews bounded
            search_fn = lambda q: websearch.search_structured(
                q, limit=min(limit, 4), deep=False
            )
            par = _parallel(bounded, search_fn=search_fn, max_workers=len(bounded))
            # Aggregate sources from each block; the combined markdown is
            # added once at the end so we don't repeat the same blocks.
            for block in par.blocks:
                if not block.get("results"):
                    continue
                _absorb({"sources": block.get("results") or []})
            if par.combined_markdown:
                _absorb({"sources": [], "context_markdown": par.combined_markdown})
        except Exception:  # noqa: BLE001
            parallel = False  # graceful fallback to serial

    if not parallel or len(queries) <= 1:
        # Serial path kept for single-query / fallback cases.
        for q in queries[:2]:
            payload = websearch.search_structured(q, limit=min(limit, 4), deep=False)
            _absorb(payload)

    md = "\n\n".join(chunks)
    return all_sources[: max(limit * 2, 12)], md


def plan_lanes(
    message: str,
    *,
    session_context: str = "",
    cfg: dict[str, Any] | None = None,
    web_search_enabled: bool | None = None,
    force_parallel: bool = False,
    force_count: int = 0,
    run_search: bool = True,
) -> dict[str, Any]:
    """Plan parallel lanes (and optional search context) for one user turn."""
    cfg = cfg or load_campus_config()
    flags = _ui_flags(cfg)
    max_lanes = flags["max_lanes"]
    msg = (message or "").strip()
    nl_count = force_count or _detect_nl_count(msg)
    # Explicit force/NL count may exceed the settings default (often 3).
    if nl_count and nl_count > max_lanes:
        max_lanes = max(2, min(6, int(nl_count)))
    if force_parallel and not nl_count:
        # force_parallel without count still respects configured max
        pass

    if not msg:
        return {"ok": True, "need_parallel": False, "needs_search": False, "lanes": [], "single_role": None, "source": "empty"}

    if not flags["auto_parallel"] and not nl_count and not force_parallel:
        return {
            "ok": True,
            "need_parallel": False,
            "needs_search": False,
            "lanes": [],
            "single_role": None,
            "source": "disabled",
            "auto_parallel": False,
            "max_lanes": max_lanes,
        }

    # Avoid spending a planner-model call on ordinary short chat turns.
    # Explicit multi-agent requests and long/compound tasks still use planning.
    direct_signals = ("分别", "并行", "多代理", "子代理", "比较", "综合", "多来源", "分组", "parallel", "subagent", "compare", "synthesize")
    if not nl_count and not force_parallel and len(msg) <= 180 and not any(x in msg.lower() for x in direct_signals):
        return {
            "ok": True, "need_parallel": False, "needs_search": False,
            "lanes": [], "single_role": None, "source": "short-direct",
            "auto_parallel": flags["auto_parallel"], "max_lanes": max_lanes,
        }

    parsed = None
    if not _looks_like_greeting(msg) or nl_count:
        parsed = _call_planner_llm(msg, session_context, max_lanes, cfg)

    if not isinstance(parsed, dict):
        plan = _heuristic_plan(msg, max_lanes=max_lanes, force_count=nl_count)
    else:
        need_parallel = bool(parsed.get("need_parallel"))
        if nl_count or force_parallel:
            need_parallel = True
        raw_lanes = parsed.get("lanes") if isinstance(parsed.get("lanes"), list) else []
        if need_parallel and len(raw_lanes) < 2:
            # LLM said parallel but under-specified — fill via heuristic
            plan = _heuristic_plan(msg, max_lanes=max_lanes, force_count=nl_count or 2)
            plan["source"] = "llm+heuristic"
        else:
            lanes = [
                _normalize_lane(x, i, cfg)
                for i, x in enumerate(raw_lanes)
                if isinstance(x, dict)
            ][:max_lanes]
            pad = False
            if nl_count and len(lanes) < nl_count:
                filled = _heuristic_plan(msg, max_lanes=max_lanes, force_count=nl_count)
                for extra in filled.get("lanes") or []:
                    if len(lanes) >= nl_count:
                        break
                    lanes.append(_normalize_lane(extra, len(lanes), cfg))
                pad = True
            single_raw = parsed.get("single_role") if isinstance(parsed.get("single_role"), dict) else None
            single = _normalize_lane(single_raw, 0, cfg) if single_raw and not need_parallel else None
            if need_parallel and len(lanes) < 2:
                need_parallel = False
            plan = {
                "ok": True,
                "need_parallel": need_parallel and len(lanes) >= 2,
                "needs_search": bool(parsed.get("needs_search")),
                "synthesis_focus": str(parsed.get("synthesis_focus") or "").strip(),
                "lanes": lanes if need_parallel else [],
                "single_role": single,
                "source": "llm+pad" if pad else "llm",
            }

    # Event-intent guard: when the message is clearly a sports/event query but
    # neither the LLM nor the keyword fallback produced an event-aware lane
    # pool, retry with the heuristic so the user gets a purpose-built
    # standings / scorelines / bracket lane set instead of a generic
    # researcher/writer pair (which usually searches the same broad query
    # 3 times and wastes tokens).
    if _has_event_signal(msg) and not _plan_uses_event_pool(plan):
        event_plan = _heuristic_plan(msg, max_lanes=max_lanes, force_count=nl_count or max_lanes)
        if _plan_uses_event_pool(event_plan):
            plan = event_plan
            plan["source"] = (plan.get("source") or "heuristic") + "+event-guard"

    # Search gating
    plan = _repair_unrelated_code_lanes(plan, msg)
    search_cfg = cfg.get("search") if isinstance(cfg.get("search"), dict) else {}
    search_master = search_cfg.get("enabled") is not False
    if web_search_enabled is False:
        allow_search = False
    elif web_search_enabled is True:
        allow_search = search_master
    else:
        allow_search = search_master and bool(plan.get("needs_search"))

    queries: list[str] = []
    if allow_search:
        for lane in plan.get("lanes") or []:
            queries.extend(lane.get("search_queries") or [])
        single = plan.get("single_role")
        if isinstance(single, dict):
            queries.extend(single.get("search_queries") or [])
        if not queries and plan.get("needs_search"):
            queries = [msg[:120]]

    sources: list[dict[str, Any]] = []
    search_context = ""
    if run_search and allow_search and queries:
        sources, search_context = _gather_sources(queries, enabled=True)
        if search_context:
            for lane in plan.get("lanes") or []:
                lane["search_context"] = search_context
                lane["system"] = (lane.get("system") or "") + "\n\n" + search_context
            if isinstance(plan.get("single_role"), dict):
                plan["single_role"]["search_context"] = search_context
                plan["single_role"]["system"] = (plan["single_role"].get("system") or "") + "\n\n" + search_context

    # Frontend-friendly lane shape (letters etc. filled by client)
    out_lanes = []
    for i, lane in enumerate(plan.get("lanes") or []):
        out_lanes.append(
            {
                **lane,
                "key": f"lane-{chr(ord('a') + i)}",
                "letter": chr(ord("A") + i),
                "title": lane.get("role") or lane.get("id"),
                "shortTitle": lane.get("role") or lane.get("id"),
                "model": lane.get("resolved_model") or "",
                "provider": lane.get("resolved_provider") or "",
            }
        )

    return {
        "ok": True,
        "need_parallel": bool(plan.get("need_parallel")) and len(out_lanes) >= 2,
        "needs_search": bool(plan.get("needs_search")),
        "search_enabled": allow_search,
        "synthesis_focus": plan.get("synthesis_focus") or "",
        "lanes": out_lanes,
        "single_role": plan.get("single_role"),
        "sources": sources,
        "search_context": search_context,
        "source": plan.get("source") or "unknown",
        "auto_parallel": flags["auto_parallel"],
        "max_lanes": max_lanes,
    }
