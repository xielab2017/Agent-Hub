"""Multi-step tasks typed in the chat box, advanced automatically step by step.

A task is a goal plus ordered steps.  ``create_task`` plans the steps
(explicit "1. … 2. …" / "第一步…" / "首先…然后…最后…", otherwise a
research or general template) and returns the first step's prompt.  After
each step's reply the client calls ``advance``: the step's result is recorded
(its "本步结论" section and reviewer verdict), a gate decides whether to go on,
and the next step's prompt — carrying the goal, earlier conclusions and open
issues — is returned.  The gate stops when the reviewer flagged warnings (mode
``auto``) or after every step (mode ``confirm``); the user can then continue
(``force``) or stop.

Tasks persist under ``STATE_DIR/tasks/<id>.json`` so a reload can restore the
board.  Everything here is deterministic; the steps themselves run through the
normal chat pipeline (search, evidence, review, provenance all apply).
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .config import STATE_DIR

TASKS_DIR = STATE_DIR / "tasks"
MAX_STEPS = 8
MODES = ("auto", "confirm")
_lock = threading.RLock()

_SEARCH_HINT = re.compile(
    r"检索|搜索|查找|查询|查阅|查一下|查查|调研|文献|资料|数据库|最新|联网|search|look up|literature|survey|find", re.I
)
_RESEARCH_HINT = re.compile(
    r"研究|调研|综述|文献|分析|数据|报告|对比|比较|评估|统计|进展|现状|趋势|research|review|analy|report|compare|trend",
    re.I,
)
_SUMMARY_HINT = re.compile(r"总结|汇总|整理|报告|综述|结论|summary|summari|report|conclude", re.I)
_ZH_NUM = "一二三四五六七八九十"

RESEARCH_TEMPLATE = [
    ("检索资料", "围绕目标联网检索，收集权威来源（官方 / 数据库 / 学术优先），列出来源清单 [n] 与每个来源的关键信息。", True),
    ("核对数据", "对上一步得到的关键数字与结论做跨来源核对：标出多源一致、单一来源和有分歧的数值，说明取舍依据。", True),
    ("整理总结", "按“结论摘要 / 关键数据表（指标 | 数值 | 来源 [n] | 一致性）/ 分歧与不确定”整理成结构化总结。", False),
    ("下一步建议", "基于以上结果给出 2–4 条可执行的下一步（需要补充的数据、实验、检索或决策）。", False),
]
GENERAL_TEMPLATE = [
    ("明确需求与方案", "复述目标与约束，列出交付物与执行方案（分几步、每步产出什么）。", False),
    ("执行并产出初稿", "按方案完成主要工作，给出完整初稿。", False),
    ("自查与完善", "逐条检查初稿是否满足目标与约束，修正错误、补全遗漏，输出修订版。", False),
    ("交付与下一步", "给出最终交付内容的摘要与使用说明，并列出后续可做的下一步。", False),
]


def _now() -> float:
    return time.time()


def _iso(ts: float | None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)) if ts else ""


# ── planning ──────────────────────────────────────────────────────────


def _split_numbered(text: str) -> tuple[str, list[str]]:
    """'goal … 1. a 2. b' / one step per line → (goal, [a, b])."""
    marks = list(re.finditer(r"(?:(?<=[\s：:，,；;。])|^)(\d{1,2})[.、)）](?!\d)\s*", text))
    seq: list[re.Match] = []
    for m in marks:
        if int(m.group(1)) == len(seq) + 1:
            seq.append(m)
    if len(seq) < 2:
        return text, []
    goal = text[: seq[0].start()].strip(" ：:，,\n")
    steps = [text[m.end(): (seq[i + 1].start() if i + 1 < len(seq) else len(text))].strip(" ；;，,。\n") for i, m in enumerate(seq)]
    return goal, [s for s in steps if s]


def _split_ordinals(text: str) -> tuple[str, list[str]]:
    pat = re.compile(rf"第[{_ZH_NUM}\d]+(?:步|阶段|部分)[：:，,、\s]*")
    marks = list(pat.finditer(text))
    if len(marks) < 2:
        return text, []
    goal = text[: marks[0].start()].strip(" ：:，,\n")
    steps = [text[m.end(): (marks[i + 1].start() if i + 1 < len(marks) else len(text))].strip(" ；;，,。\n") for i, m in enumerate(marks)]
    return goal, [s for s in steps if s]


def _split_sequence_words(text: str) -> tuple[str, list[str]]:
    pat = re.compile(r"(?:首先|先|然后|接着|随后|之后|再|最后|其次|first(?:ly)?|then|next|after that|finally)[，,：:\s]*", re.I)
    marks = [m for m in pat.finditer(text) if m.group(0).strip(" ，,：:").lower() not in ("再",) or m.start() > 0]
    starts_ok = [m for m in marks if re.match(r"首先|先|first", m.group(0), re.I)]
    if len(marks) < 2 or not starts_ok:
        return text, []
    goal = text[: marks[0].start()].strip(" ：:，,\n")
    steps = [text[m.end(): (marks[i + 1].start() if i + 1 < len(marks) else len(text))].strip(" ；;，,。\n") for i, m in enumerate(marks)]
    steps = [s for s in steps if len(s) >= 2]
    return goal, steps if len(steps) >= 2 else []


def _title(step: str) -> str:
    t = re.split(r"[，,；;。：:\n]", step.strip(), maxsplit=1)[0]
    return (t[:24] + "…") if len(t) > 24 else t


def plan_steps(message: str, *, steps: list[str] | None = None) -> dict[str, Any]:
    """Return ``{goal, source, steps:[{title, instruction, web_search}]}``."""
    text = (message or "").strip()
    source = "given"
    raw: list[str] = [str(s).strip() for s in (steps or []) if str(s).strip()]
    goal = text
    if not raw:
        for fn, name in ((_split_numbered, "numbered"), (_split_ordinals, "ordinal"), (_split_sequence_words, "sequence")):
            g, found = fn(text)
            if found:
                goal, raw, source = g or text, found, name
                break
    planned: list[dict[str, Any]] = []
    if raw:
        planned = [{"title": _title(s), "instruction": s, "web_search": bool(_SEARCH_HINT.search(s))} for s in raw]
        if len(planned) >= 2 and not _SUMMARY_HINT.search(planned[-1]["instruction"]):
            planned.append({"title": "汇总与下一步",
                            "instruction": "汇总前面所有步骤的结果，给出结构化结论（含关键数据表与来源），并列出下一步。",
                            "web_search": False})
    else:
        research = bool(_RESEARCH_HINT.search(text) or _SEARCH_HINT.search(text))
        source = "research-template" if research else "general-template"
        planned = [{"title": t, "instruction": i, "web_search": w}
                   for t, i, w in (RESEARCH_TEMPLATE if research else GENERAL_TEMPLATE)]
    return {"goal": goal or text, "source": source, "steps": planned[:MAX_STEPS]}


# ── persistence ───────────────────────────────────────────────────────


def _path(task_id: str) -> Path:
    safe = "".join(c for c in (task_id or "") if c.isalnum() or c in "-_") or "unknown"
    return Path(TASKS_DIR) / f"{safe}.json"


def _save(task: dict[str, Any]) -> dict[str, Any]:
    task["updated_at"] = _now()
    p = _path(task["id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)
    return task


def get_task(task_id: str) -> dict[str, Any] | None:
    p = _path(task_id)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def active_for_session(session_id: str) -> dict[str, Any] | None:
    """Most recent task of this session that is not finished / stopped."""
    d = Path(TASKS_DIR)
    if not d.is_dir():
        return None
    best = None
    for p in d.glob("*.json"):
        try:
            t = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if t.get("session_id") != session_id or t.get("status") in ("done", "stopped"):
            continue
        if best is None or float(t.get("updated_at") or 0) > float(best.get("updated_at") or 0):
            best = t
    return best


# ── prompts ───────────────────────────────────────────────────────────


def _section(md: str, names: tuple[str, ...]) -> str:
    """Body of the first '## <name>' section (any of names), until the next heading."""
    pat = re.compile(r"^#{1,4}\s*(?:" + "|".join(re.escape(n) for n in names) + r")[^\n]*\n([\s\S]*?)(?=^#{1,4}\s|\Z)", re.M)
    m = pat.search(md or "")
    return m.group(1).strip() if m else ""


def summarize_reply(content: str) -> dict[str, str]:
    text = content or ""
    concl = _section(text, ("本步结论", "结论摘要", "结论", "Summary", "Conclusions"))
    open_ = _section(text, ("待解决", "分歧与不确定", "未解决", "Open issues"))
    if not concl:
        plain = re.sub(r"```[\s\S]*?```", " ", text)
        plain = re.sub(r"[#>*`|_-]+", " ", plain)
        concl = re.sub(r"\s+", " ", plain).strip()
    return {"summary": concl[:600], "open_issues": open_[:400]}


def step_prompt(task: dict[str, Any], idx: int) -> dict[str, Any]:
    steps = task["steps"]
    st = steps[idx]
    total = len(steps)
    lines = [
        f"【任务目标】{task['goal']}",
        f"【当前步骤 {idx + 1}/{total}】{st['title']}",
        st["instruction"],
    ]
    done = [s for s in steps[:idx] if s.get("status") in ("done", "skipped")]
    if done:
        lines.append("【已完成步骤要点】")
        for s in done:
            lines.append(f"- 步骤 {s['n']}「{s['title']}」：{(s.get('summary') or '（无摘要）')[:300]}")
        prev = done[-1]
        if prev.get("open_issues"):
            lines.append(f"【上一步待解决】{prev['open_issues'][:300]}")
    lines.append(
        "【要求】只完成本步骤，不要提前做后面的步骤；数字必须标注来源 [n] 或说明来自用户材料；"
        "结尾用“## 本步结论”列出 3–5 条要点，用“## 待解决”列出仍不确定或需要下一步处理的问题。"
    )
    return {
        "step": idx + 1,
        "total": total,
        "title": st["title"],
        "prompt": "\n".join(lines),
        "display": f"▶ 步骤 {idx + 1}/{total}：{st['title']}" + (f" — {st['instruction'][:80]}" if st["instruction"] != st["title"] else ""),
        "web_search": bool(st.get("web_search")),
    }


# ── lifecycle ─────────────────────────────────────────────────────────


def create_task(session_id: str, message: str, *, mode: str = "auto", steps: list[str] | None = None) -> dict[str, Any]:
    from . import sessions as store

    if store.get_session(session_id) is None:
        raise FileNotFoundError("session not found")
    if not (message or "").strip() and not steps:
        raise ValueError("empty task")
    plan = plan_steps(message, steps=steps)
    task = {
        "id": "task-" + uuid.uuid4().hex[:12],
        "session_id": session_id,
        "goal": plan["goal"][:1000],
        "request": (message or "")[:4000],
        "plan_source": plan["source"],
        "mode": mode if mode in MODES else "auto",
        "status": "running",
        "cursor": 0,
        "blocked_reason": "",
        "created_at": _now(),
        "updated_at": _now(),
        "steps": [
            {"n": i + 1, "title": s["title"], "instruction": s["instruction"], "web_search": s["web_search"],
             "status": "pending", "message_id": "", "summary": "", "open_issues": "", "review": {},
             "started_at": None, "finished_at": None}
            for i, s in enumerate(plan["steps"])
        ],
    }
    task["steps"][0]["status"] = "running"
    task["steps"][0]["started_at"] = _now()
    with _lock:
        _save(task)
    _audit("task_created", task)
    return {"task": public(task), "next": {"status": "next", **step_prompt(task, 0)}}


def _record_step(task: dict[str, Any], message_id: str) -> None:
    from . import sessions as store

    idx = int(task.get("cursor") or 0)
    st = task["steps"][idx]
    session = store.get_session(task["session_id"])
    msg = None
    if session is not None:
        msg = next((m for m in session.messages if m.get("id") == message_id and m.get("role") == "assistant"), None)
    if msg is None:
        raise FileNotFoundError("step reply not found")
    info = summarize_reply(str(msg.get("content") or ""))
    rv = msg.get("review") or {}
    st.update(
        status="done" if not msg.get("error") else "blocked",
        message_id=message_id,
        summary=info["summary"],
        open_issues=info["open_issues"],
        review={k: rv.get(k) for k in ("ok", "warn", "info", "skipped") if k in rv},
        finished_at=_now(),
    )
    st["_issues"] = [f"{i.get('kind')}: {i.get('text')}" for i in (rv.get("issues") or []) if i.get("severity") == "warn"][:5]
    if msg.get("error"):
        task["status"] = "blocked"
        task["blocked_reason"] = "error"


def advance(task_id: str, *, message_id: str = "", force: bool = False) -> dict[str, Any]:
    """Record the finished step (if ``message_id``) and return what happens next.

    Returns ``{status: next|blocked|waiting|done|stopped, task, …}``; ``next`` carries the prompt.
    """
    with _lock:
        task = get_task(task_id)
        if task is None:
            raise FileNotFoundError("task not found")
        if task.get("status") in ("done", "stopped"):
            return {"status": task["status"], "task": public(task)}
        idx = int(task.get("cursor") or 0)
        cur = task["steps"][idx]
        if message_id and cur.get("status") == "running":
            _record_step(task, message_id)
        if task.get("status") == "blocked" and task.get("blocked_reason") == "error" and not force:
            _save(task)
            return {"status": "blocked", "reason": "error", "task": public(task)}
        if cur.get("status") == "running" and not force:
            _save(task)
            return {"status": "running", "task": public(task)}
        if not force:
            warn = int((cur.get("review") or {}).get("warn") or 0)
            if warn and task["mode"] == "auto":
                task["status"] = "blocked"
                task["blocked_reason"] = "review"
                _save(task)
                _audit("task_blocked", task)
                return {"status": "blocked", "reason": "review", "issues": cur.get("_issues") or [], "task": public(task)}
            if task["mode"] == "confirm" and idx + 1 < len(task["steps"]):
                task["status"] = "waiting"
                _save(task)
                return {"status": "waiting", "task": public(task), "upcoming": step_prompt(task, idx + 1)["display"]}
        if cur.get("status") == "running":  # forced past a step that never replied
            cur["status"] = "skipped"
            cur["finished_at"] = _now()
        nxt = idx + 1
        if nxt >= len(task["steps"]):
            task["status"] = "done"
            task["blocked_reason"] = ""
            _save(task)
            _audit("task_done", task)
            return {"status": "done", "task": public(task)}
        task["cursor"] = nxt
        task["status"] = "running"
        task["blocked_reason"] = ""
        task["steps"][nxt]["status"] = "running"
        task["steps"][nxt]["started_at"] = _now()
        _save(task)
        return {"status": "next", "task": public(task), **step_prompt(task, nxt)}


def stop(task_id: str) -> dict[str, Any]:
    with _lock:
        task = get_task(task_id)
        if task is None:
            raise FileNotFoundError("task not found")
        if task.get("status") != "done":
            task["status"] = "stopped"
            for st in task["steps"]:
                if st["status"] in ("pending", "running"):
                    st["status"] = "skipped"
            _save(task)
            _audit("task_stopped", task)
    return {"status": task["status"], "task": public(task)}


def set_mode(task_id: str, mode: str) -> dict[str, Any]:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}")
    with _lock:
        task = get_task(task_id)
        if task is None:
            raise FileNotFoundError("task not found")
        task["mode"] = mode
        _save(task)
    return {"task": public(task)}


def public(task: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in task.items() if not k.startswith("_")}
    out["steps"] = [{k: v for k, v in s.items() if not k.startswith("_")} for s in task.get("steps") or []]
    out["created_iso"] = _iso(task.get("created_at"))
    out["done_steps"] = sum(1 for s in out["steps"] if s["status"] in ("done", "skipped"))
    return out


def _audit(kind: str, task: dict[str, Any]) -> None:
    try:
        from . import audit

        audit.log_event(kind, {"task_id": task.get("id"), "session_id": task.get("session_id"),
                               "cursor": task.get("cursor"), "status": task.get("status")})
    except Exception:  # noqa: BLE001
        pass
