"""Agent discovery and streaming bridge for Hermes-ALI."""

from __future__ import annotations

import queue
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Callable

from . import sessions as store
from .config import discover_agent_dirs, hermes_home

# ── OpenSquilla token optimization ──────────────────────────────────────────────
try:
    from opensquilla.engine.usage import UsageTracker, estimate_cost, lookup_price
    _USAGE_TRACKER = UsageTracker()
    _HAS_SQUILLA = True
except Exception:
    _USAGE_TRACKER = None
    _HAS_SQUILLA = False

try:
    import tiktoken
    _ENCODERS: dict[str, Any] = {}

    def _count_tokens(text: str, model: str = "gpt-4o") -> int:
        if not text:
            return 0
        # Never block the chat finalize path on tiktoken network/disk downloads.
        try:
            enc_name = "cl100k_base"
            ml = (model or "").lower()
            if "o1" in ml or "o3" in ml:
                enc_name = "o200k_base"
            elif "4o" in ml:
                enc_name = "cl100k_base"
            enc = _ENCODERS.get(enc_name)
            if enc is None:
                return max(1, len(text) // 4)
            return len(enc.encode(text or ""))
        except Exception:
            return max(1, len(text) // 4)
except Exception:
    def _count_tokens(text: str, model: str = "gpt-4o") -> int:
        return max(1, len(text) // 4)


def _track_usage(
    session_id: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    billed_cost: float = 0.0,
    provider: str = "",
) -> dict[str, Any]:
    """Record usage and return the snapshot dict for SSE events."""
    if _USAGE_TRACKER is not None:
        _USAGE_TRACKER.add(
            session_key=session_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model_id=model,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            billed_cost=billed_cost,
            provider=provider,
        )
        snap = _USAGE_TRACKER.session_snapshot(session_id)
        if snap:
            return {
                "inputTokens": snap.input_tokens,
                "outputTokens": snap.output_tokens,
                "cacheReadTokens": snap.cache_read_tokens,
                "cacheWriteTokens": snap.cache_write_tokens,
                "costUsd": round(snap.cost_usd, 8),
                "billedCostUsd": round(snap.billed_cost, 8),
            }
    # Fallback: estimate from token counts
    price = lookup_price(model, provider) if _HAS_SQUILLA else None
    est = estimate_cost(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        price=price,
    ) if price else None
    return {
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "cacheReadTokens": cache_read_tokens,
        "cacheWriteTokens": cache_write_tokens,
        "costUsd": round(est.cost_usd, 8) if est else 0.0,
        "billedCostUsd": 0.0,
    }


def get_usage_tracker() -> Any:
    """Return the shared UsageTracker for the /api/usage endpoint."""
    return _USAGE_TRACKER


def get_has_squilla() -> bool:
    return _HAS_SQUILLA


# ── Stream queues ─────────────────────────────────────────────────────────────
# stream_id -> Queue of SSE event dicts
STREAMS: dict[str, queue.Queue] = {}
# session_id -> stream_id currently running
ACTIVE: dict[str, str] = {}
# Durable job buffers — survive client disconnect / page refresh
JOBS: dict[str, dict[str, Any]] = {}
QUEUE_STREAM: dict[int, str] = {}
_JOB_RETAIN_SEC = 3600  # keep finished job buffers for replay
_MAX_JOB_EVENTS = 4000
_lock = threading.RLock()

_AIAgent = None
_agent_dir: Path | None = None
_import_error: str | None = None


def _ensure_agent_on_path() -> Path | None:
    global _agent_dir
    if _agent_dir is not None and _agent_dir.is_dir():
        path = str(_agent_dir)
        if path not in sys.path:
            sys.path.insert(0, path)
        return _agent_dir
    for d in discover_agent_dirs():
        path = str(d)
        if path not in sys.path:
            sys.path.insert(0, path)
        _agent_dir = d
        return d
    return None


def get_ai_agent():
    """Lazy-import run_agent.AIAgent from Hermes Agent install."""
    global _AIAgent, _import_error
    if _AIAgent is not None:
        return _AIAgent
    _ensure_agent_on_path()
    try:
        from run_agent import AIAgent  # type: ignore

        _AIAgent = AIAgent
        _import_error = None
        return _AIAgent
    except Exception as exc:  # noqa: BLE001 — surface any import failure
        _import_error = f"{type(exc).__name__}: {exc}"
        return None


_OPENCLAW_FAMILY = frozenset({"openclaw", "qqclaw", "aliyun_claw"})


def _resolve_hub_chat_mode(ali: dict[str, Any] | None) -> str:
    hub_chat_mode = str((ali or {}).get("hub_chat_mode") or "").strip().lower()
    if hub_chat_mode in ("agent", "direct"):
        return hub_chat_mode
    if (ali or {}).get("hub_fast_chat") is True:
        return "direct"
    return "agent"


def _chat_engine_for_runtime(
    hub_chat_mode: str,
    runtime_resolved: str,
    *,
    simple_chat: bool = False,
) -> str:
    prefer_agent = hub_chat_mode == "agent"
    if simple_chat or runtime_resolved in ("", "direct", "auto") or not prefer_agent:
        return "direct"
    if runtime_resolved == "hermes":
        return "hermes"
    if runtime_resolved in _OPENCLAW_FAMILY:
        return "openclaw"
    return "direct"


def agent_status() -> dict[str, Any]:
    from . import claw_cli, hermes_cli, runtimes, soul as soul_mod
    from .secrets import resolve_api_key
    from .settings import load_campus_config, resolve_backend_verify_tls

    cls = get_ai_agent()
    cli = hermes_cli.hermes_cli_status()
    dirs = [str(p) for p in discover_agent_dirs()]
    cfg = load_campus_config()
    ali = cfg.get("ali") if isinstance(cfg.get("ali"), dict) else {}
    key = resolve_api_key(cfg)
    backend = cfg.get("backend") or {}
    direct_ready = bool(backend.get("base_url") and (key.get("present") or backend.get("type") == "local-ollama"))
    rt = runtimes.peek_runtime()
    resolved = str(rt.get("resolved") or "direct")
    hub_chat_mode = _resolve_hub_chat_mode(ali)
    planned = _chat_engine_for_runtime(hub_chat_mode, resolved)
    hermes_ready = resolved == "hermes" and (cls is not None or cli.get("available"))
    if planned == "hermes":
        if cls is not None:
            engine = "hermes"
        elif cli.get("available"):
            engine = "hermes-cli"
        elif direct_ready:
            engine = "direct-llm"
        else:
            engine = "demo"
    elif planned == "openclaw":
        if claw_cli.find_openclaw_bin():
            engine = "openclaw"
        elif direct_ready:
            engine = "direct-llm"
        else:
            engine = "demo"
    elif direct_ready:
        engine = "direct-llm"
    else:
        engine = "demo"
    import_hint = _import_error
    if _import_error and "unsupported operand type(s) for |" in (_import_error or ""):
        import_hint = (
            f"{_import_error} — system Python is too old for in-process Hermes; "
            "Agent-CLI will use the Hermes CLI (venv Python 3.11+) instead."
        )
    try:
        soul_status = soul_mod.soul_runtime_status()
    except Exception:  # noqa: BLE001
        soul_status = {}

    def _claw_labels(rid: str) -> tuple[str, str]:
        meta = runtimes.get_runtime(str(rid or "").strip()) or {}
        label = str(meta.get("label") or rid or "")
        label_zh = str(meta.get("label_zh") or label)
        return label, label_zh

    linked = rt.get("linked") or resolved
    auto_rt = rt.get("auto_runtime") or ""
    resolved_label, resolved_label_zh = _claw_labels(str(resolved))
    linked_label, linked_label_zh = _claw_labels(str(linked))
    auto_label, auto_label_zh = _claw_labels(str(auto_rt)) if auto_rt else ("", "")
    return {
        "available": hermes_ready or cls is not None,
        "hermes_import": cls is not None,
        "hermes_cli": cli,
        "direct_llm": direct_ready,
        "agent_dir": str(_agent_dir) if _agent_dir else (dirs[0] if dirs else None),
        "hermes_home": str(hermes_home()),
        "import_error": import_hint,
        "candidates": dirs,
        "api_key_present": bool(key.get("present")),
        "api_key_masked": key.get("masked") or "",
        "runtime_active": rt.get("active"),
        "runtime_auto": auto_rt,
        "runtime_resolved": resolved,
        "runtime_linked": linked,
        # User-facing Claw display names (catalog labels); ids stay in runtime_* fields
        "claw_id": resolved,
        "claw_label": resolved_label,
        "claw_label_zh": resolved_label_zh,
        "claw_linked_label": linked_label,
        "claw_linked_label_zh": linked_label_zh,
        "claw_auto_label": auto_label,
        "claw_auto_label_zh": auto_label_zh,
        "soul": soul_status,
        "app_name": "Agent Hub",
        "chat_engine": engine,
        "hub_chat_mode": hub_chat_mode,
        "hub_fast_chat": hub_chat_mode == "direct",
        "agent_mode": planned in ("hermes", "openclaw"),
        "python": sys.version.split()[0],
    }


def _register_job(stream_id: str, session_id: str, route: dict[str, Any] | None = None) -> None:
    JOBS[stream_id] = {
        "stream_id": stream_id,
        "session_id": session_id,
        "status": "running",
        "started_at": time.time(),
        "finished_at": None,
        "events": [],
        "pct": 0,
        "content_preview": "",
        "route": dict(route or {}),
        "error": "",
    }


def _stamp_job_elapsed(job: dict[str, Any], data: dict[str, Any] | None = None) -> int | None:
    """Ensure finished_at/elapsed_ms on job; optionally copy into event payload."""
    now = time.time()
    if job.get("finished_at") is None:
        job["finished_at"] = now
    started = job.get("started_at")
    if started is None:
        return None
    elapsed_ms = int(max(0, (float(job["finished_at"]) - float(started)) * 1000))
    job["elapsed_ms"] = elapsed_ms
    if data is not None:
        data["elapsed_ms"] = elapsed_ms
        data["started_at"] = started
        data["finished_at"] = job["finished_at"]
    return elapsed_ms


def _append_job_event(stream_id: str, event: str, data: dict[str, Any]) -> None:
    job = JOBS.get(stream_id)
    if not job:
        return
    job["events"].append({"event": event, "data": data, "ts": time.time()})
    if len(job["events"]) > _MAX_JOB_EVENTS:
        job["events"] = job["events"][-_MAX_JOB_EVENTS:]
    # Phase 2: durable JSONL journal (seq is 1-based index into events)
    try:
        from . import run_journal

        run_journal.append_event(stream_id, len(job["events"]), event, data)
    except Exception:  # noqa: BLE001
        pass
    if event == "token":
        job["content_preview"] = (job.get("content_preview") or "") + str(data.get("text") or "")
    elif event == "progress":
        job["pct"] = int(data.get("pct") or job.get("pct") or 0)
    elif event == "done":
        job["status"] = "error" if data.get("error") else "done"
        _stamp_job_elapsed(job, data)
    elif event == "error":
        job["status"] = "error"
        job["error"] = str(data.get("message") or "")
        _stamp_job_elapsed(job, data)
    elif event == "cancelled":
        job["status"] = "cancelled"
        _stamp_job_elapsed(job, data)


def _job_public(job: dict[str, Any]) -> dict[str, Any]:
    started = job.get("started_at")
    finished = job.get("finished_at")
    elapsed_ms = job.get("elapsed_ms")
    if elapsed_ms is None and started is not None:
        end = float(finished) if finished is not None else time.time()
        elapsed_ms = int(max(0, (end - float(started)) * 1000))
    return {
        "stream_id": job.get("stream_id"),
        "session_id": job.get("session_id"),
        "status": job.get("status"),
        "pct": int(job.get("pct") or 0),
        "started_at": started,
        "finished_at": finished,
        "elapsed_ms": elapsed_ms,
        "event_count": len(job.get("events") or []),
        "content_preview": (job.get("content_preview") or "")[-800:],
        "route": job.get("route") or {},
        "error": job.get("error") or "",
    }


def list_active_jobs() -> list[dict[str, Any]]:
    with _lock:
        return [
            _job_public(j)
            for j in JOBS.values()
            if j.get("status") == "running"
        ]


def session_job(session_id: str) -> dict[str, Any] | None:
    sid = (session_id or "").strip()
    if not sid:
        return None
    with _lock:
        stream_id = ACTIVE.get(sid)
        if not stream_id:
            for j in JOBS.values():
                if j.get("session_id") == sid and j.get("status") == "running":
                    stream_id = j.get("stream_id")
                    break
        if not stream_id:
            return None
        job = JOBS.get(str(stream_id))
        if not job:
            return None
        return _job_public(job)


def _elapsed_ms_for_stream(stream_id: str | None) -> int | None:
    if not stream_id:
        return None
    with _lock:
        job = JOBS.get(stream_id)
        if not job or job.get("started_at") is None:
            return None
        end = float(job.get("finished_at") or time.time())
        return int(max(0, (end - float(job["started_at"])) * 1000))


def _put(q: queue.Queue, event: str, data: dict[str, Any] | None = None) -> None:
    payload = data if data is not None else {}
    stream_id = QUEUE_STREAM.get(id(q))
    # Durable job buffer is the SSE source of truth. Avoid lock around append —
    # nested acquire under cancel/start historically stalled terminal "done" events.
    if stream_id and event in ("done", "error", "cancelled"):
        job = JOBS.get(stream_id)
        if job is not None:
            _stamp_job_elapsed(job, payload)
    try:
        q.put_nowait({"event": event, "data": payload})
    except Exception:  # noqa: BLE001
        pass
    if stream_id:
        _append_job_event(stream_id, event, payload)


def _think(q: queue.Queue, text: str, *, kind: str = "", quiet: bool = False) -> None:
    """Stream process detail into the thinking channel (not the workflow progress panel)."""
    t = (text or "").strip()
    if not t:
        return
    # Routine ceremony — hide unless caller forces useful content
    if quiet and kind in ("skills", "dispatch", "execute", "summarize"):
        return
    if kind in ("skills", "dispatch") and (
        t.startswith("跳过 Skill") or t.startswith("调度 Agent")
    ):
        return
    payload: dict[str, Any] = {"text": t}
    if kind:
        payload["kind"] = kind
    _put(q, "thinking", payload)


def emit_orchestration_plan(
    q: queue.Queue,
    *,
    goal: str = "",
    agents: list[dict[str, Any]] | None = None,
    mode: str = "parallel",
) -> None:
    """SSE: orchestration_plan — UI renders 任务编排看板 before results."""
    _put(
        q,
        "orchestration_plan",
        {
            "goal": goal or "",
            "mode": mode or "parallel",
            "agents": list(agents or []),
        },
    )


def emit_subagent_status(
    q: queue.Queue,
    *,
    agent_id: str,
    status: str,
    progress: str = "",
    title: str = "",
) -> None:
    """SSE: subagent_status — Pending|Processing|Waiting|Completed heartbeat."""
    _put(
        q,
        "subagent_status",
        {
            "id": agent_id,
            "status": status,
            "progress": progress or "",
            "title": title or "",
        },
    )


def emit_subagent_done(
    q: queue.Queue,
    *,
    agent_id: str,
    content: str = "",
    title: str = "",
    progress: str = "",
) -> None:
    """SSE: subagent_done — lane finished; UI marks Completed + optional body."""
    _put(
        q,
        "subagent_done",
        {
            "id": agent_id,
            "title": title or "",
            "content": content or "",
            "progress": progress or "",
            "status": "completed",
        },
    )


def _progress(q: queue.Queue, step: int, pct: int, label: str = "") -> None:
    """Workflow panel: step index + percent only (no verbose search/heal dumps)."""
    data: dict[str, Any] = {"step": int(step), "pct": int(pct)}
    if label:
        data["label"] = str(label)
    _put(q, "progress", data)


def cancel_stream(session_id: str) -> bool:
    with _lock:
        sid = ACTIVE.get(session_id)
        if not sid:
            return False
        q = STREAMS.get(sid)
        job = JOBS.get(sid)
        if job and job.get("status") == "running":
            job["status"] = "cancelled"
            job["finished_at"] = time.time()
        ACTIVE.pop(session_id, None)
    # Emit outside lock — nested _put + lock previously could stall callers.
    if q is not None:
        _put(q, "cancelled", {"session_id": session_id})
        _put(q, "done", {"session_id": session_id})
    return True



_MODEL_THINK_TAG = r"think(?:ing)?|reasoning|redacted_reasoning|thought"


def strip_model_think_tags(text: str) -> str:
    """Remove <think>…</think> (and common variants) from assistant text.

    Also drops incomplete open tags / trailing tag stubs so streaming buffers
    never leak raw think markup into the user-visible reply.
    """
    import re

    s = text or ""
    open_re = rf"<\s*(?:{_MODEL_THINK_TAG})\b[^>]*>"
    close_re = rf"<\s*/\s*(?:{_MODEL_THINK_TAG})\s*>"
    pair = re.compile(rf"{open_re}[\s\S]*?{close_re}", re.I)
    prev = None
    while prev != s:
        prev = s
        s = pair.sub("", s)
    s = re.sub(rf"{open_re}[\s\S]*$", "", s, flags=re.I)
    stub = re.search(r"<\s*/?\s*[A-Za-z_]{0,32}$", s)
    if stub:
        name = re.sub(r"^<\s*/?\s*", "", stub.group(0), flags=re.I).lower()
        names = ("think", "thinking", "reasoning", "redacted_reasoning", "thought")
        if not name or any(n.startswith(name) for n in names):
            s = s[: stub.start()]
    return s


def sanitize_workflow_output(text: str) -> str:
    """Strip model think tags, reasoning banners, and skill-JSON dumps for UI."""
    import re

    s = strip_model_think_tags(text or "")
    s = re.sub(r"┌─[\s\S]*?┐[\s\S]*?└─+┘", "", s)
    s = re.sub(r"╭─[\s\S]*?╯", "", s)
    s = re.sub(r"```(?:json|javascript|js)?\s*\{[\s\S]*?\"skill\"\s*:[\s\S]*?\}\s*```", "", s, flags=re.I)
    s = re.sub(r"\{\s*\"skill\"\s*:\s*\"[^\"]+\"[\s\S]*?\}", "", s)
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s

def structure_assistant_output(text: str) -> str:
    """Normalize assistant delivery into stable Markdown sections."""
    import re

    s = sanitize_workflow_output(text or "").strip()
    if not s:
        return s
    headings = re.findall(r"^##\s+(.+?)\s*$", s, flags=re.M)
    known = {"结论", "依据与过程", "风险与待确认", "整体汇总", "Conclusion", "Evidence & Process", "Risks & Open Questions", "Overall Summary"}
    required = {"结论", "依据与过程", "风险与待确认", "整体汇总"}
    if not required.issubset({h.strip() for h in headings}):
        first = next((line.strip() for line in s.splitlines() if line.strip()), s[:500])
        s = re.sub(r"^##\s+(整体汇总|Overall Summary)\s*$[\s\S]*$", "", s, flags=re.M).strip()
        s = f"## 结论\n\n{first}\n\n## 依据与过程\n\n{s}\n\n## 风险与待确认\n\n暂无额外待确认项。"
    if not re.search(r"^##\s+(整体汇总|Overall Summary)\s*$", s, flags=re.M):
        plain = re.sub(r"```[\s\S]*?```", "", s).strip()
        plain = re.sub(r"^#{1,6}\s*", "", plain, flags=re.M)
        plain = re.sub(r"\s+", " ", plain)[:700].strip()
        s += f"\n\n## 整体汇总\n\n```text\n{plain}\n```"
    return s.strip()


def _strip_ask_for_research(text: str) -> str:
    """Remove common 'please paste research text' asks after Agent Hub already filled Excel."""
    import re

    s = text or ""
    patterns = [
        r"请您提供[：:].{0,200}教授.{0,80}(?:研究|要点|概况).{0,120}",
        r"请提供[：:].{0,200}(?:教授研究|研究概况|研究要点).{0,120}",
        r"Please (?:provide|paste|send).{0,160}(?:professor|research overview).{0,120}",
        r"我无法(?:自行|直接)?(?:联网|搜索|检索).{0,80}",
    ]
    for p in patterns:
        s = re.sub(p, "", s, flags=re.I)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def start_chat(
    session_id: str,
    message: str,
    model: str = "",
    workspace: str = "",
    route: str = "auto",
    workflow_id: str = "",
    system: str = "",
    display_message: str = "",
    skills: list[str] | None = None,
    execution_mode: str = "workflow",
    soul_role: str = "",
    subagent_id: str = "",
    web_search: bool | None = None,
    thinking_depth: str = "",
) -> dict[str, Any]:
    """Start a background agent run; returns stream_id for SSE."""
    from . import agents as agents_mod, audit, ecosystem, routing, skills as skills_mod, soul as soul_mod
    from .settings import load_campus_config

    session = store.get_session(session_id)
    if session is None:
        raise ValueError("session not found")

    msg = (message or "").strip()
    if not msg:
        raise ValueError("empty message")
    try:
        folder_memory = store.folder_context(session_id, msg).get("context") or ""
        if folder_memory:
            system = (system + "\n\n【同文件夹相关会话摘要】\n" + folder_memory).strip()
    except Exception:  # noqa: BLE001
        pass

    cfg = load_campus_config()
    # Sync selected soul into config before routing/preamble (skip disk SOUL rewrite for speed)
    if (soul_role or "").strip():
        try:
            soul_mod.set_active_role(str(soul_role).strip(), apply_to_soul_file=False)
            cfg = load_campus_config()
        except Exception:  # noqa: BLE001
            pass

    # Resolve connected claw early (fast peek — avoid full list_runtimes version probes)
    from . import runtimes as runtimes_mod

    rt_info = runtimes_mod.peek_runtime()
    runtime_resolved = str(rt_info.get("resolved") or "direct")
    runtime_linked = str(rt_info.get("linked") or runtime_resolved)

    # Subagent: explicit id, else auto-activate when keywords match
    agents_data = agents_mod.get_agents()
    active_sub = None
    sid = (subagent_id or "").strip()
    if sid:
        active_sub = next((s for s in (agents_data.get("subagents") or []) if s.get("id") == sid), None)
    if active_sub is None:
        active_sub = agents_mod.pick_subagent_for_message(msg, agents=agents_data)
    if active_sub and not (soul_role or "").strip():
        try:
            # Don't rewrite SOUL.md on every chat — config role only (speed)
            soul_mod.set_active_role(
                agents_mod.auto_soul_role(msg, active_sub),
                apply_to_soul_file=False,
            )
            cfg = load_campus_config()
        except Exception:  # noqa: BLE001
            pass

    # Soul → claw sync is on connect / Control Center, NOT every chat turn (TTFB)

    agent_route = (
        agents_mod.normalize_agent_route(
            active_sub.get("route")
            if active_sub and active_sub.get("route") is not None
            else (active_sub or {}).get("model_slot")
        )
        if active_sub
        else "auto"
    )
    # A fixed Agent route is a real execution override, not merely a UI label.
    # Auto Agents continue to follow the composer/classified route unchanged.
    effective_route = agent_route if active_sub and agent_route != "auto" else (route or "auto")
    route_info = routing.resolve_route(effective_route, msg, cfg)
    if route_info.get("blocked"):
        raise ValueError(route_info.get("block_reason") or "route blocked by data_policy")

    # Prefer subagent dedicated model (speed/specialization), else UI/route model
    ali = cfg.get("ali") if isinstance(cfg.get("ali"), dict) else {}
    chat_mode = str((ali or {}).get("chat_mode") or "auto").strip()
    depth_raw = (thinking_depth or "").strip() or str((ali or {}).get("thinking_depth") or "medium")
    simple_chat = routing.is_simple_chat(msg)
    if simple_chat:
        # Greetings: keep light depth; avoid nudging into heavy tiers
        depth_raw = "light"
    route_info = routing.apply_thinking_depth(
        route_info, depth_raw, cfg=cfg, chat_mode=chat_mode
    )
    if simple_chat:
        route_info = dict(route_info)
        route_info["simple_chat"] = True
        route_info["quiet_thinking"] = True
    sub_binding = agents_mod.resolve_subagent_binding(active_sub, cfg) if active_sub else {}
    sub_model = str(sub_binding.get("model") or "")
    sub_provider = str(sub_binding.get("provider") or "")
    if active_sub and sub_provider and sub_model:
        route_info = dict(route_info)
        route_info["provider"] = sub_provider
        route_info["backend_type"] = sub_provider
        if str(cfg.get("data_policy") or "internal").lower() == "restricted" and sub_provider in {
            "openai", "anthropic", "nvidia-nim", "nvidia-api", "nvidia-hosted",
            "openrouter", "minimax", "gemini", "deepseek", "kimi", "hybrid",
        }:
            raise ValueError(
                f"data_policy=restricted forbids external provider '{sub_provider}'"
            )
    if active_sub and sub_model:
        resolved_model = sub_model
    else:
        resolved_model = (model or "").strip() or route_info.get("model") or ""
        if chat_mode == "single":
            resolved_model = (
                (model or "").strip()
                or str((ali or {}).get("last_model") or "").strip()
                or route_info.get("model")
                or ""
            )
            route_info = dict(route_info)
            route_info["chat_mode"] = "single"
            route_info["model"] = resolved_model
    # Drop composer model ids that belong to another vendor (e.g. deepseek-ai/* on NVIDIA
    # while backend is official DeepSeek). Always coerce to the active provider.
    try:
        from .providers import coerce_model_for_provider, get_provider

        provider_now = str(route_info.get("provider") or "")
        raw_ui = (resolved_model or "").strip()
        # If UI still has NVIDIA org prefix but provider is DeepSeek, strip / remap
        if provider_now == "deepseek" and ("deepseek-ai/" in raw_ui or "integrate.api.nvidia" in raw_ui):
            raw_ui = raw_ui.split("/")[-1] if "/" in raw_ui else raw_ui
        if provider_now == "deepseek" and raw_ui.startswith(("nvidia/", "meta/", "google/")):
            raw_ui = str(route_info.get("model") or "")
        coerced = coerce_model_for_provider(
            provider_now,
            raw_ui or route_info.get("model") or "",
            route_key=str(route_info.get("route_key") or "office"),
        )
        if coerced:
            resolved_model = coerced
        # Re-pin base_url from catalog for concrete cloud providers
        prov = get_provider(provider_now) if provider_now else None
        if prov and provider_now not in ("", "hybrid", "campus-openai-compatible", "local-ollama"):
            catalog_url = str(prov.get("base_url") or "").strip()
            if catalog_url:
                route_info = dict(route_info)
                route_info["base_url"] = catalog_url
                if prov.get("api_key_env"):
                    route_info["api_key_env"] = prov.get("api_key_env")
    except Exception:  # noqa: BLE001
        pass
    ws = (workspace or "").strip() or (cfg.get("workspace") or "")
    route_info = dict(route_info)
    route_info["workspace"] = ws
    route_info["_user_message"] = msg
    route_info["runtime_active"] = rt_info.get("active")
    route_info["runtime_auto"] = rt_info.get("auto_runtime")
    route_info["runtime_resolved"] = runtime_resolved
    route_info["runtime_linked"] = runtime_linked
    route_info["soul_role"] = str(
        (soul_role or "").strip()
        or agents_mod.auto_soul_role(msg, active_sub)
    )
    if active_sub:
        route_info["subagent_id"] = active_sub.get("id")
        route_info["subagent_label"] = active_sub.get("label")
        route_info["subagent_auto"] = not bool(sid)
        if sub_provider:
            route_info["subagent_provider"] = sub_provider
    if resolved_model:
        route_info["model"] = resolved_model

    # Skills: explicit selection, else auto-suggest only when message implies skills
    skill_ids = [str(s).strip() for s in (skills or []) if str(s).strip()]
    route_info["skills_auto"] = False
    route_info["skills_skipped"] = False
    if simple_chat and not skill_ids:
        skill_ids = []
        route_info["skills_skipped"] = True
        route_info["skills_source"] = "skipped"
    elif skill_ids:
        route_info["skills_source"] = "user"
    elif skills_mod.message_implies_skills(msg):
        try:
            suggested = skills_mod.suggest_skills(msg, limit=3).get("skills") or []
            skill_ids = [s["id"] for s in suggested if s.get("id")]
            route_info["skills_auto"] = bool(skill_ids)
            route_info["skills_source"] = "auto" if skill_ids else "none"
        except Exception:  # noqa: BLE001
            skill_ids = []
            route_info["skills_source"] = "none"
    else:
        skill_ids = []
        route_info["skills_skipped"] = True
        route_info["skills_source"] = "skipped"
    route_info["skills"] = skill_ids
    route_info["hub_loaded_skills"] = skills_mod.get_hub_loaded()
    skill_block = "" if simple_chat else skills_mod.skill_context_block(skill_ids)
    extra_system = str(system or "").strip()
    if active_sub and not simple_chat:
        sub_prompt = agents_mod.subagent_system_prompt(active_sub)
        extra_system = (extra_system + "\n\n" + sub_prompt).strip() if extra_system else sub_prompt
    if skill_block:
        extra_system = (extra_system + "\n\n" + skill_block).strip() if extra_system else skill_block

    # Activated ecosystem packages (OpenSquilla / OpenScience / Obsidian …)
    if not simple_chat:
        try:
            eco_block = ecosystem.ecosystem_context_block(cfg)
            if eco_block:
                extra_system = (extra_system + "\n\n" + eco_block).strip() if extra_system else eco_block
                route_info["ecosystem"] = True
        except Exception:  # noqa: BLE001
            pass

    # External search + Excel web-fill when requested or message implies it
    from . import excel_fill as excel_fill_mod

    session_xlsx = None if simple_chat else excel_fill_mod.find_session_xlsx(session_id)
    has_xlsx = session_xlsx is not None
    # Excel 联网填表 is opt-in only: never force from web_search toggle + leftover xlsx.
    excel_fill_task = (
        False
        if simple_chat
        else excel_fill_mod.looks_like_excel_fill_task(msg, has_xlsx=has_xlsx)
    )

    need_search = False if simple_chat else web_search
    if need_search is None:
        low = msg.lower()
        need_search = any(
            k in low
            for k in (
                "搜索", "检索", "联网", "查一下", "搜一下",
                "web search", "search the web", "google",
            )
        )
        # Explicit spreadsheet fill still implies search, but generic table chatter does not.
        if excel_fill_task:
            need_search = True
        elif has_xlsx and any(
            k in msg for k in ("填写", "填表", "联网填", "表格字段", "excel", "xlsx")
        ):
            need_search = True

    if excel_fill_task:
        try:
            fill_result = excel_fill_mod.run_excel_web_fill(session_id, msg)
            fill_block = excel_fill_mod.prompt_block_for_fill(fill_result)
            extra_system = (extra_system + "\n\n" + fill_block).strip() if extra_system else fill_block
            route_info["excel_fill"] = {
                "ok": bool(fill_result.get("ok")),
                "output": fill_result.get("output"),
                "output_relative": fill_result.get("output_relative"),
                "searched": fill_result.get("searched"),
                "error": fill_result.get("error"),
                "markdown": fill_result.get("markdown") or "",
            }
            need_search = True
            searched_n = fill_result.get("searched") or 0
            route_info.setdefault("_thinking_notes", []).append(
                f"Excel 联网填写：已检索 {searched_n} 行并写回表格"
                + (f"；输出 `{fill_result.get('output_relative') or fill_result.get('output') or ''}`" if fill_result.get("ok") else f"；失败：{fill_result.get('error') or 'unknown'}")
            )
        except Exception as exc:  # noqa: BLE001
            route_info["excel_fill"] = {"ok": False, "error": str(exc)}
            fail_block = excel_fill_mod.prompt_block_for_fill({"ok": False, "error": str(exc)})
            extra_system = (extra_system + "\n\n" + fail_block).strip() if extra_system else fail_block
            route_info.setdefault("_thinking_notes", []).append(f"Excel 联网填写失败：{exc}")

    if need_search and not (excel_fill_task and route_info.get("excel_fill", {}).get("ok")):
        # General web search context (skip duplicate when Excel fill already searched per-row)
        try:
            from . import websearch as websearch_mod

            route_info.setdefault("_thinking_notes", []).append("正在深度联网检索…")
            search_block = websearch_mod.search_context_for_prompt(msg, limit=8, deep=True)
            extra_system = (extra_system + "\n\n" + search_block).strip() if extra_system else search_block
            route_info["web_search"] = True
            route_info["web_search_deep"] = True
            # Soft-parse engines from block header if present
            route_info["web_search_mode"] = "deep"
            # Compact thinking summary (not dumped into workflow progress)
            n_src = search_block.count("\n- [")
            route_info.setdefault("_thinking_notes", []).append(
                f"检索完成 · 深度搜索 · 约 {n_src} 条来源（详情用于模型上下文，不写入工作流进度栏）"
            )
            # Keep a short excerpt for the thinking UI (truncate)
            excerpt = "\n".join(
                ln for ln in search_block.splitlines()
                if ln.startswith("- [") or ln.startswith("Engines:") or ln.startswith("Query:")
            )[:1200]
            if excerpt:
                route_info.setdefault("_thinking_notes", []).append(excerpt)
        except Exception as exc:  # noqa: BLE001
            route_info["web_search"] = False
            route_info["web_search_error"] = str(exc)
            route_info.setdefault("_thinking_notes", []).append(f"联网检索不可用：{exc}")
    elif need_search:
        route_info["web_search"] = True
        if not route_info.get("_thinking_notes"):
            route_info.setdefault("_thinking_notes", []).append("使用 Excel 填写阶段已完成的检索结果")

    # Agent Hub core path: multi-step office workflow (not chit-chat)
    mode = (execution_mode or "workflow").strip() or "workflow"
    if simple_chat:
        mode = "chat"
    route_info["execution_mode"] = mode
    if mode == "workflow":
        wf_rules = (
            "\n\n## Agent Hub workflow mode\n"
            "- You are executing an automated multi-step office/research workflow owned by Agent Hub.\n"
            "- Do NOT chat turn-by-turn. Produce deliverables: gather → apply skills → verify → deliver.\n"
            "- NEVER output raw tool/skill JSON or skill-call fences, or reasoning boxes to the user.\n"
            "- Code/commands MUST use Markdown fenced blocks with language tags "
            "(```python / ```r / ```bash / ```perl / ```markdown / etc.).\n"
            "- When the user asks to search and fill a form: summarize sources, then propose a field→value table.\n"
            "- If Excel web-fill already ran: use those filled cells; do NOT ask the user to paste professor research text; "
            "show the output .xlsx path and a concise summary table.\n"
            "- If web search is offline (SSL/campus): do NOT lead with 「重要说明：网络搜索不可用」; continue the deliverable offline, "
            "footnote at most once at the end.\n"
            "- Execute skills silently; respond with structured results only (Markdown).\n"
            "- Keep the answer concise and actionable for campus office automation.\n"
            "- Match the user's language (Chinese → 简体中文) unless they explicitly request another language.\n"
        )
        extra_system = (extra_system + wf_rules).strip() if extra_system else wf_rules.strip()
    elif simple_chat:
        chat_rules = (
            "\n\n## Simple chat\n"
            "- Reply warmly and briefly to greetings / chit-chat.\n"
            "- Do NOT invent workflows, skills, or tool calls.\n"
            "- Match the user's language.\n"
        )
        extra_system = (extra_system + chat_rules).strip() if extra_system else chat_rules.strip()

    # Persist last used model / thinking depth off the critical path (don't block TTFB)
    if resolved_model or route_info.get("thinking_depth"):
        def _persist_prefs() -> None:
            try:
                from .settings import save_campus_config

                cfg2 = load_campus_config()
                ali2 = cfg2.setdefault("ali", {})
                if not isinstance(ali2, dict):
                    ali2 = {}
                    cfg2["ali"] = ali2
                if resolved_model:
                    ali2["last_model"] = resolved_model
                if chat_mode:
                    ali2["chat_mode"] = chat_mode
                if route_info.get("thinking_depth"):
                    ali2["thinking_depth"] = routing.normalize_thinking_depth(
                        route_info.get("thinking_depth")
                    )
                save_campus_config(cfg2)
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=_persist_prefs, daemon=True, name="ali-persist-prefs").start()

    from . import grounding

    # Engine selection (aligned with hermes-webui): connected claw → real agent tools.
    # - agent (default): Hermes AIAgent / OpenClaw `agent --local` with tool streaming
    # - direct: Hub HTTP chat only (fast chit-chat / fallback)
    # - simple greetings always stay Direct for TTFB
    hub_chat_mode = _resolve_hub_chat_mode(ali if isinstance(ali, dict) else {})
    prefer_agent = hub_chat_mode == "agent"
    chat_engine = _chat_engine_for_runtime(
        hub_chat_mode, runtime_resolved, simple_chat=simple_chat
    )
    route_info["hub_chat_mode"] = hub_chat_mode
    route_info["hub_fast_chat"] = not prefer_agent  # legacy field for older UI
    route_info["chat_engine"] = chat_engine
    route_info["agent_mode"] = chat_engine in ("hermes", "openclaw")

    if simple_chat:
        # Fast path: short preamble, skip workspace snapshot / heavy soul fuse
        role = str(route_info.get("soul_role") or (ali or {}).get("active_soul_role") or "office")
        claw_hint = ""
        if runtime_resolved not in ("", "direct", "auto"):
            claw_hint = f" Connected claw `{runtime_resolved}` (native home); keep its tone."
        preamble = (
            f"You are Agent Hub ({role}). Reply briefly and warmly.{claw_hint} "
            "No skills, tools, or multi-step workflows for this turn.\n"
            + (extra_system or "")
        ).strip()
        ground_meta = {"snapshot": {}, "excerpts": 0}
        route_info["grounding"] = {"workspace": "", "entry_count": 0, "excerpts": 0}
        route_info["_snap_rel"] = []
    elif extra_system:
        preamble, ground_meta = grounding.build_grounded_preamble(
            route_info, cfg, message=msg, session_id=session_id, extra_system=extra_system
        )
    else:
        preamble, ground_meta = grounding.build_grounded_preamble(
            route_info, cfg, message=msg, session_id=session_id
        )
    if not simple_chat:
        route_info["grounding"] = {
            "workspace": (ground_meta.get("snapshot") or {}).get("workspace"),
            "entry_count": (ground_meta.get("snapshot") or {}).get("entry_count"),
            "excerpts": ground_meta.get("excerpts"),
        }
        # Keep snapshot for post-reply verification (small)
        snap = ground_meta.get("snapshot") or {}
        route_info["_snap_rel"] = list(snap.get("relative_paths") or [])[:200]

    stream_id = str(uuid.uuid4())
    q: queue.Queue = queue.Queue()
    route_public = {k: v for k, v in route_info.items() if not str(k).startswith("_")}
    old_q = None
    with _lock:
        old = ACTIVE.get(session_id)
        if old and old in STREAMS:
            old_q = STREAMS.get(old)
            old_job = JOBS.get(old)
            if old_job and old_job.get("status") == "running":
                old_job["status"] = "cancelled"
                old_job["finished_at"] = time.time()
        STREAMS[stream_id] = q
        ACTIVE[session_id] = stream_id
        _register_job(stream_id, session_id, route_public)
        QUEUE_STREAM[id(q)] = stream_id
    if old_q is not None:
        _put(old_q, "cancelled", {"session_id": session_id})
        _put(old_q, "done", {"session_id": session_id})

    shown = (display_message or msg).strip()
    meta = {
        "role": "user",
        "content": shown,
        "route": {k: v for k, v in route_info.items() if not str(k).startswith("_")},
        "workflow_id": workflow_id or None,
        "grounding": route_info.get("grounding"),
    }
    if display_message and display_message != msg:
        meta["expanded"] = True
    store.append_messages(session_id, meta)
    audit.log_event(
        "chat_start",
        {
            "session_id": session_id,
            "stream_id": stream_id,
            "tier": route_info.get("tier"),
            "route_key": route_info.get("route_key"),
            "model": resolved_model,
            "workflow_id": workflow_id or None,
        },
    )

    t = threading.Thread(
        target=_run_agent_streaming,
        args=(session_id, msg, resolved_model, ws, stream_id, route_info, preamble),
        daemon=True,
        name=f"ali-stream-{stream_id[:8]}",
    )
    t.start()
    return {
        "stream_id": stream_id,
        "session_id": session_id,
        "route": {k: v for k, v in route_info.items() if not str(k).startswith("_")},
        "model": resolved_model,
        "grounding": route_info.get("grounding"),
    }


def _run_agent_streaming(
    session_id: str,
    msg_text: str,
    model: str,
    workspace: str,
    stream_id: str,
    route_info: dict[str, Any] | None = None,
    preamble: str = "",
) -> None:
    q = STREAMS.get(stream_id)
    if q is None:
        return

    assistant_parts: list[str] = []
    tools_seen: list[dict[str, Any]] = []
    route_info = route_info or {}
    route_public0 = {k: v for k, v in route_info.items() if not str(k).startswith("_")}
    _put(q, "route", route_public0)

    # Replay pre-stream process notes into thinking channel (search / excel fill)
    quiet = bool(route_info.get("quiet_thinking") or route_info.get("simple_chat"))
    for note in route_info.pop("_thinking_notes", None) or []:
        _think(q, str(note), kind="search", quiet=quiet)

    skills_list = route_info.get("skills") or []
    skipped = bool(route_info.get("skills_skipped"))
    if skills_list or route_info.get("skills_auto"):
        _progress(q, 0, 12, "match-skills")
        _think(
            q,
            "匹配 Skill：" + (", ".join(str(s) for s in skills_list[:6]) or "（自动）"),
            kind="skills",
            quiet=quiet,
        )
    elif skipped:
        # No noisy "跳过 Skill…" line — just advance progress quietly
        _progress(q, 1, 18, "dispatch-agent")
    else:
        _progress(q, 0, 10, "match-skills")

    fill_md = str((route_info.get("excel_fill") or {}).get("markdown") or "").strip()
    if fill_md:
        _progress(q, 1, 22, "dispatch-agent")
        # Deliverable stays in assistant tokens; process narration is thinking
        _think(q, "Excel 填写结果已就绪，写入交付内容…", kind="excel", quiet=quiet)
        _put(q, "token", {"text": fill_md + "\n\n"})
        assistant_parts.append(fill_md + "\n\n")
    _progress(q, 1, 28, "dispatch-agent")
    if not quiet:
        rt = route_info.get("runtime_resolved") or "direct"
        sub = route_info.get("subagent_label") or ""
        if sub:
            _think(q, f"子代理「{sub}」已激活 · 引擎={rt}", kind="dispatch")
        else:
            _think(q, f"调度执行引擎（{rt}）并准备产出", kind="dispatch")

    def on_token(delta: str) -> None:
        if not delta:
            return
        assistant_parts.append(delta)
        _put(q, "token", {"text": delta})

    def _provider_fallback(exc: Exception) -> str:
        """Try a configured healthy provider after an account-level refusal."""
        err = str(exc)
        low = err.lower()
        account_refusal = any(
            marker in low
            for marker in ("overdue", "overdue_payment", "access denied", "account is not in good standing", "余额不足")
        )
        if not account_refusal or provider != "dashscope" or assistant_parts:
            return ""
        candidates = ("zhipu", "deepseek", "kimi", "minimax")
        for fallback_provider in candidates:
            fallback_cfg = get_provider(fallback_provider)
            fallback_key = resolve_api_key(cfg, provider=fallback_provider).get("key") or ""
            if not fallback_cfg or not fallback_key:
                continue
            fallback_model = coerce_model_for_provider(
                fallback_provider, "", route_key=route_key
            )
            try:
                _put(
                    q,
                    "meta",
                    {
                        "mode": "provider-fallback",
                        "from_provider": provider,
                        "provider": fallback_provider,
                        "model": fallback_model,
                        "reason": "primary provider account refusal",
                    },
                )
                fallback_url = str(fallback_cfg.get("base_url") or "")
                if route_info.get("simple_chat"):
                    fallback_text = llm_client._chat_once(
                        fallback_url,
                        fallback_key,
                        model=fallback_model,
                        messages=messages,
                        timeout=timeout,
                        verify_tls=verify_tls,
                        on_token=on_token,
                        temperature=route_info.get("temperature"),
                        max_tokens=route_info.get("max_tokens"),
                    )
                else:
                    fallback_text = llm_client.stream_chat(
                        fallback_url,
                        fallback_key,
                        model=fallback_model,
                        messages=messages,
                        timeout=timeout,
                        verify_tls=verify_tls,
                        on_token=on_token,
                        temperature=route_info.get("temperature"),
                        max_tokens=route_info.get("max_tokens"),
                    )
                if fallback_text:
                    route_info["provider"] = fallback_provider
                    route_info["backend_type"] = fallback_provider
                    route_info["base_url"] = fallback_url
                    route_info["model"] = fallback_model
                    route_info["provider_fallback"] = {
                        "from": provider,
                        "to": fallback_provider,
                        "reason": "account_refusal",
                    }
                    return fallback_text
            except Exception:
                continue
        return ""

    def on_tool(name: str = "", preview: str = "", args: Any = None, **kwargs: Any) -> None:
        payload = {
            "name": name or kwargs.get("tool_name") or "tool",
            "preview": (preview or str(args or kwargs.get("args") or ""))[:120],
        }
        tools_seen.append(payload)
        _put(q, "tool", payload)
        _progress(q, 2, min(88, 45 + 8 * len(tools_seen)), "execute")
        detail = payload["name"]
        if payload.get("preview"):
            detail = f"{payload['name']} — {payload['preview']}"
        _think(q, f"工具/Skill：{detail}", kind="tool")

    try:
        from . import heal as heal_mod
        from . import skills as skills_mod

        def _run_once(active_preamble: str) -> None:
            # Keep excel-fill deliverable if already streamed; only clear model tokens
            kept = "".join(assistant_parts)
            assistant_parts.clear()
            if kept.strip().startswith("## Excel"):
                assistant_parts.append(kept if kept.endswith("\n\n") else kept + "\n\n")
            _progress(q, 2, 45, "execute")
            _think(q, "开始产出交付内容（代码/文档将写入回答）", kind="execute", quiet=quiet)
            AIAgent = get_ai_agent()
            agent_input = msg_text
            if active_preamble:
                agent_input = f"[SYSTEM CONTEXT]\n{active_preamble}\n\n[USER]\n{msg_text}"

            from . import hermes_cli as _hermes_cli
            from . import runtimes as _rt
            from .secrets import resolve_api_key as _resolve_key
            from .settings import load_campus_config

            resolved = _rt.resolved_runtime_id()
            engine = str(route_info.get("chat_engine") or resolved)
            # Prefer route_info engine (set at start_chat); fall back for heal retries
            use_hermes = (
                engine == "hermes"
                and resolved == "hermes"
                and not route_info.get("simple_chat")
            )
            use_openclaw = (
                engine == "openclaw"
                and resolved in ("openclaw", "qqclaw", "aliyun_claw")
                and not route_info.get("simple_chat")
            )

            if use_hermes:
                # Credentials already synced on Connect; light touch only when needed
                if not route_info.get("_hermes_synced"):
                    try:
                        sync_cfg = load_campus_config()
                        sync_provider = str(
                            route_info.get("provider")
                            or (sync_cfg.get("backend") or {}).get("type")
                            or ""
                        )
                        _hermes_cli.sync_hub_to_hermes(
                            sync_cfg,
                            model=model or "",
                            provider_id=sync_provider,
                        )
                        route_info["_hermes_synced"] = True
                    except Exception:  # noqa: BLE001
                        pass

            if use_openclaw:
                oc_input = msg_text
                if active_preamble:
                    oc_input = f"[SYSTEM CONTEXT]\n{active_preamble}\n\n[USER]\n{msg_text}"
                used = _openclaw_cli_reply(
                    q,
                    session_id,
                    oc_input,
                    model,
                    assistant_parts,
                    route_info=route_info,
                )
                if not used:
                    try:
                        from . import claw_cli as _claw

                        active_preamble = _claw.enrich_preamble_with_claw(active_preamble, resolved)
                    except Exception:  # noqa: BLE001
                        pass
                    used = _direct_llm_reply(
                        q,
                        session_id,
                        msg_text,
                        model,
                        assistant_parts,
                        route_info=route_info,
                        preamble=active_preamble,
                    )
                if not used:
                    _demo_reply(q, msg_text, assistant_parts, route_info=route_info, preamble=active_preamble)
            elif not use_hermes:
                # Direct path (greetings / hub_chat_mode=direct / unsupported claws)
                if (
                    not route_info.get("simple_chat")
                    and resolved not in ("", "direct", "auto", "hermes")
                ):
                    try:
                        from . import claw_cli as _claw

                        active_preamble = _claw.enrich_preamble_with_claw(active_preamble, resolved)
                    except Exception:  # noqa: BLE001
                        pass
                used = _direct_llm_reply(
                    q,
                    session_id,
                    msg_text,
                    model,
                    assistant_parts,
                    route_info=route_info,
                    preamble=active_preamble,
                )
                if not used:
                    _demo_reply(q, msg_text, assistant_parts, route_info=route_info, preamble=active_preamble)
            elif AIAgent is not None:
                _think(q, "已接入 Hermes · 工具与 Skill 通道就绪", kind="dispatch", quiet=quiet)
                _put(q, "meta", {"mode": "hermes-inproc", "engine": "hermes", "agent_mode": True})
                session = store.get_session(session_id)
                history = list(session.messages[:-1]) if session else []
                clean_history = []
                for m in history:
                    role = m.get("role")
                    content = m.get("content")
                    if role in ("user", "assistant") and isinstance(content, str):
                        clean_history.append({"role": role, "content": content})

                cfg_now = load_campus_config()
                provider = str(route_info.get("provider") or (cfg_now.get("backend") or {}).get("type") or "")
                key_info = _resolve_key(cfg_now, provider=provider if provider != "hybrid" else "")
                api_key = key_info.get("key") or ""
                base_url = str(route_info.get("base_url") or (cfg_now.get("backend") or {}).get("base_url") or "").strip()
                hermes_provider = _hermes_cli._hermes_provider_name(provider)
                from .settings import resolve_backend_verify_tls

                verify_tls = resolve_backend_verify_tls(cfg_now, route_info)

                import os as _os

                managed = _hermes_cli.hermes_managed_home()
                _os.environ["HERMES_HOME"] = str(managed)
                env_name = str(key_info.get("env_name") or "")
                if env_name and api_key:
                    _os.environ[env_name] = api_key
                if hermes_provider == "custom" and api_key:
                    _os.environ["OPENAI_API_KEY"] = api_key
                    if base_url:
                        _os.environ["OPENAI_BASE_URL"] = base_url
                if hermes_provider == "deepseek" and api_key:
                    _os.environ["DEEPSEEK_API_KEY"] = api_key

                kwargs: dict[str, Any] = {
                    "platform": "cli",
                    "quiet_mode": True,
                    "session_id": session_id,
                    "stream_delta_callback": on_token,
                }
                if model:
                    kwargs["model"] = model
                # Pass Hub credentials when AIAgent accepts them
                for opt_key, opt_val in (
                    ("provider", hermes_provider),
                    ("api_key", api_key),
                    ("base_url", base_url or None),
                ):
                    if opt_val:
                        kwargs[opt_key] = opt_val

                hermes_ok = False
                try:
                    try:
                        agent = AIAgent(**kwargs, tool_progress_callback=on_tool)
                    except TypeError:
                        # Older AIAgent signatures — drop unknown kwargs
                        for drop in ("provider", "api_key", "base_url", "tool_progress_callback"):
                            kwargs.pop(drop, None)
                        try:
                            agent = AIAgent(**kwargs, tool_progress_callback=on_tool)
                        except TypeError:
                            agent = AIAgent(**{k: v for k, v in kwargs.items() if k != "tool_progress_callback"})
                    _apply_hermes_agent_tls(agent, verify_tls)

                    if workspace:
                        try:
                            _os.chdir(workspace)
                        except OSError:
                            pass

                    result = agent.run_conversation(
                        user_message=agent_input,
                        conversation_history=clean_history,
                        task_id=session_id,
                    )
                    if not assistant_parts and result:
                        final = ""
                        if isinstance(result, dict):
                            final = (
                                result.get("final_response")
                                or result.get("response")
                                or result.get("content")
                                or ""
                            )
                        elif isinstance(result, str):
                            final = result
                        failure_text = str(final or "").lower()
                        if "nameerror" in failure_text or "providerfallback" in failure_text:
                            raise RuntimeError(str(final))
                        if final:
                            assistant_parts.append(str(final))
                            _put(q, "token", {"text": str(final)})
                    hermes_ok = True
                except Exception as hermes_exc:  # noqa: BLE001
                    err_s = str(hermes_exc)
                    _put(q, "meta", {"mode": "hermes-inproc", "error": err_s})
                    low = err_s.lower()
                    if "no llm provider" in low or "hermes model" in low or "hermes setup" in low:
                        tip = _hermes_cli.explain_provider_error(err_s)
                        _put(q, "token", {"text": f"\n\n_（{tip.get('zh') or err_s}）_\n\n"})
                    hermes_ok = False

                if not hermes_ok:
                    used = _hermes_cli_reply(
                        q,
                        session_id,
                        agent_input,
                        model,
                        assistant_parts,
                        route_info=route_info,
                        workspace=workspace,
                    )
                    if not used:
                        used = _direct_llm_reply(
                            q,
                            session_id,
                            msg_text,
                            model,
                            assistant_parts,
                            route_info=route_info,
                            preamble=active_preamble,
                        )
                    if not used:
                        _demo_reply(q, msg_text, assistant_parts, route_info=route_info, preamble=active_preamble)
            else:
                # System Python cannot import Hermes (e.g. 3.9 vs 3.11 annotations) — use CLI.
                _think(q, "Hermes CLI 通道（进程内不可用，改用 hermes chat）", kind="dispatch", quiet=quiet)
                used = _hermes_cli_reply(
                    q,
                    session_id,
                    agent_input,
                    model,
                    assistant_parts,
                    route_info=route_info,
                    workspace=workspace,
                )
                if not used:
                    used = _direct_llm_reply(
                        q,
                        session_id,
                        msg_text,
                        model,
                        assistant_parts,
                        route_info=route_info,
                        preamble=active_preamble,
                    )
                if not used:
                    _demo_reply(q, msg_text, assistant_parts, route_info=route_info, preamble=active_preamble)

        def _rebuild_preamble_with_skills(extra_ids: list[str]) -> str:
            ids = list(route_info.get("skills") or [])
            for sid in extra_ids:
                if sid and sid not in ids:
                    ids.append(sid)
            route_info["skills"] = ids
            block = skills_mod.skill_context_block(ids)
            note = (
                "\n\n## Auto-heal\n"
                f"Previous attempt failed. Newly installed skills: {', '.join(extra_ids) or '(none)'}.\n"
                "Continue and complete the original user task with these skills.\n"
            )
            base = preamble or ""
            if block:
                return (base + "\n\n" + block + note).strip()
            return (base + note).strip()

        def _try_heal(err_text: str) -> bool:
            if route_info.get("_heal_attempted"):
                return False
            if route_info.get("simple_chat") or heal_mod.is_provider_api_error(err_text):
                route_info["_heal_attempted"] = True  # mark so we don't loop
                return False
            route_info["_heal_attempted"] = True

            def emit(label: str, extra: dict[str, Any]) -> None:
                _progress(q, 2, 55, "execute")
                bits = [str(label)]
                if extra.get("message"):
                    bits.append(str(extra["message"]))
                if extra.get("candidates"):
                    bits.append("候选：" + ", ".join(str(x) for x in (extra.get("candidates") or [])[:5]))
                if extra.get("installed"):
                    bits.append("已装：" + ", ".join(str(x) for x in (extra.get("installed") or [])[:5]))
                _think(q, " · ".join(bits), kind="heal")
                _put(q, "heal", {"label": label, **extra})

            recovery = heal_mod.auto_recover(msg_text, error=err_text, emit=emit)
            if not recovery.get("ok"):
                note = recovery.get("note_zh") or "自动安装 Skill 未成功"
                _think(q, f"问题解决：{note}", kind="heal")
                return False
            installed = recovery.get("installed") or []
            note = recovery.get("note_zh") or f"已安装：{', '.join(installed)}"
            _think(q, f"问题解决：{note} 正在重试…", kind="heal")
            _progress(q, 1, 40, "dispatch-agent")
            new_preamble = _rebuild_preamble_with_skills([str(x) for x in installed])
            _run_once(new_preamble)
            return True

        _run_once(preamble)
        final_text = "".join(assistant_parts).strip()
        # Ensure Excel fill deliverable is never dropped if the model ignored it
        fill_md = str((route_info.get("excel_fill") or {}).get("markdown") or "").strip()
        if fill_md and fill_md[:40] not in final_text:
            final_text = (fill_md + "\n\n" + final_text).strip()
            _put(q, "token", {"text": "\n\n" + fill_md})
        # Always strip model <think> tags; workflow mode also drops banners / skill dumps
        if route_info.get("execution_mode") == "workflow":
            cleaned = sanitize_workflow_output(final_text)
            if cleaned != final_text:
                final_text = cleaned or final_text
        else:
            final_text = strip_model_think_tags(final_text).strip()
        # Strip LLM "please provide professor text" when fill already succeeded
        if (route_info.get("excel_fill") or {}).get("ok") and final_text:
            final_text = _strip_ask_for_research(final_text)
        if (
            heal_mod.looks_like_failure(final_text)
            and not route_info.get("_heal_attempted")
            and not route_info.get("simple_chat")
            and not heal_mod.is_provider_api_error(text=final_text)
        ):
            healed = _try_heal(final_text[:800])
            if healed:
                final_text = "".join(assistant_parts).strip()
                if route_info.get("execution_mode") == "workflow":
                    cleaned = sanitize_workflow_output(final_text)
                    if cleaned != final_text:
                        final_text = cleaned or final_text
                else:
                    final_text = strip_model_think_tags(final_text).strip()
        if not final_text:
            final_text = "(no response)"
            _put(q, "token", {"text": final_text})
        _progress(q, 3, 95, "summarize")
        _think(q, "整理最终交付（去噪、结构化）", kind="summarize", quiet=quiet)

        route_public = {k: v for k, v in route_info.items() if not str(k).startswith("_")}
        assistant_msg: dict[str, Any] = store.ensure_message_id(
            {
                "role": "assistant",
                "content": final_text,
                "route": route_public,
            }
        )
        if tools_seen:
            assistant_msg["tools"] = tools_seen
        if route_info.get("_heal_attempted"):
            assistant_msg["healed"] = True
        with _lock:
            job = JOBS.get(stream_id)
            if job and job.get("started_at") is not None:
                elapsed_ms = int(max(0, (time.time() - float(job["started_at"])) * 1000))
                assistant_msg["elapsed_ms"] = elapsed_ms
                assistant_msg["started_at"] = job.get("started_at")

        # Soft post-check only — never rewrite/truncate streamed assistant content.
        # Skip filesystem walk on simple chat — it can stall finalize under large workspaces.
        from . import grounding as _g

        if route_info.get("simple_chat"):
            assistant_msg["grounding_check"] = {"ok": True, "soft": True, "skipped": True}
        else:
            try:
                snap = {
                    "workspace": route_info.get("workspace") or "",
                    "relative_paths": route_info.get("_snap_rel") or [],
                }
                if not snap["relative_paths"] and snap["workspace"]:
                    snap = _g.snapshot_workspace(str(snap["workspace"]))
                verify = _g.verify_response_paths(final_text, snap)
                if verify.get("unverified"):
                    assistant_msg["grounding_check"] = {**verify, "soft": True}
                else:
                    assistant_msg["grounding_check"] = {"ok": True, "soft": True}
            except Exception:  # noqa: BLE001
                assistant_msg["grounding_check"] = {"ok": True, "soft": True}

        store.append_messages(session_id, assistant_msg)

        # Keep finalize non-blocking: cheap estimates only (usage tracker side-effects
        # previously stalled the SSE "done" event on some installs).
        usage_data: dict[str, Any] = {
            "inputTokens": max(1, len(msg_text or "") // 4),
            "outputTokens": max(1, len(final_text or "") // 4),
            "cacheReadTokens": 0,
            "cacheWriteTokens": 0,
            "costUsd": 0.0,
            "billedCostUsd": 0.0,
        }
        lean_route = {
            k: route_public.get(k)
            for k in ("tier", "route_key", "model", "provider", "chat_engine", "simple_chat")
            if k in route_public
        }
        done_payload: dict[str, Any] = {
            "session_id": session_id,
            "content": final_text,
            "route": lean_route,
            "message_id": assistant_msg.get("id"),
            "grounding_check": assistant_msg.get("grounding_check") or {"ok": True, "soft": True},
            "healed": bool(route_info.get("_heal_attempted")),
            "usage": usage_data,
        }
        if assistant_msg.get("elapsed_ms") is not None:
            done_payload["elapsed_ms"] = assistant_msg["elapsed_ms"]
            done_payload["started_at"] = assistant_msg.get("started_at")
        # Phase 2: surface queued follow-up so the client can auto-continue
        try:
            queued = drain_queued_after_done(session_id)
            if queued:
                done_payload["queued_message"] = queued
                _put(q, "meta", {"queued_followup": True, "preview": queued[:120]})
        except Exception:  # noqa: BLE001
            pass
        _put(q, "done", done_payload)

    except Exception as exc:  # noqa: BLE001
        err = str(exc)
        # Prefer clean provider messages over urllib class names
        if err.startswith("HTTPError:"):
            err = err.split(":", 1)[-1].strip()
        elif type(exc).__name__ == "HTTPError":
            err = f"HTTP {getattr(exc, 'code', '?')}: {err}"
        else:
            err = f"{type(exc).__name__}: {exc}" if type(exc).__name__ not in ("RuntimeError", "ValueError") else str(exc)

        # Auto problem-solve once: GitHub skill search → install → retry
        # Never heal provider HTTP/auth 404s or simple greetings.
        try:
            from . import heal as heal_mod
            from . import skills as skills_mod

            if (
                not route_info.get("_heal_attempted")
                and not route_info.get("simple_chat")
                and not heal_mod.is_provider_api_error(err)
            ):
                route_info["_heal_attempted"] = True

                def emit(label: str, extra: dict[str, Any]) -> None:
                    _progress(q, 2, 55, "execute")
                    bits = [str(label)]
                    if extra.get("message"):
                        bits.append(str(extra["message"]))
                    if extra.get("candidates"):
                        bits.append("候选：" + ", ".join(str(x) for x in (extra.get("candidates") or [])[:5]))
                    if extra.get("installed"):
                        bits.append("已装：" + ", ".join(str(x) for x in (extra.get("installed") or [])[:5]))
                    _think(q, " · ".join(bits), kind="heal")
                    _put(q, "heal", {"label": label, **extra})

                _think(q, f"任务失败：{err[:200]} — 正在检索并安装 GitHub Skill…", kind="heal")
                recovery = heal_mod.auto_recover(msg_text, error=err, emit=emit)
                if recovery.get("ok"):
                    installed = [str(x) for x in (recovery.get("installed") or [])]
                    ids = list(route_info.get("skills") or [])
                    for sid in installed:
                        if sid not in ids:
                            ids.append(sid)
                    route_info["skills"] = ids
                    block = skills_mod.skill_context_block(ids)
                    note = (
                        f"\n\n## Auto-heal\nPrevious error: {err[:500]}\n"
                        f"Installed skills: {', '.join(installed)}\n"
                        "Retry and complete the original task.\n"
                    )
                    retry_preamble = ((preamble or "") + ("\n\n" + block if block else "") + note).strip()
                    _think(q, f"问题解决：{recovery.get('note_zh') or ''} 正在重试…", kind="heal")
                    _progress(q, 1, 40, "dispatch-agent")
                    assistant_parts.clear()
                    # Re-enter success path via nested call
                    AIAgent = get_ai_agent()
                    agent_input = f"[SYSTEM CONTEXT]\n{retry_preamble}\n\n[USER]\n{msg_text}" if retry_preamble else msg_text

                    engine = str(route_info.get("chat_engine") or "")
                    use_hermes = (
                        engine == "hermes"
                        and not route_info.get("simple_chat")
                    )
                    use_openclaw = (
                        engine == "openclaw"
                        and not route_info.get("simple_chat")
                    )
                    if use_openclaw:
                        oc_input = f"[SYSTEM CONTEXT]\n{retry_preamble}\n\n[USER]\n{msg_text}" if retry_preamble else msg_text
                        used = _openclaw_cli_reply(
                            q, session_id, oc_input, model, assistant_parts, route_info=route_info,
                        )
                        if not used:
                            used = _direct_llm_reply(
                                q, session_id, msg_text, model, assistant_parts,
                                route_info=route_info, preamble=retry_preamble,
                            )
                        if not used:
                            _demo_reply(q, msg_text, assistant_parts, route_info=route_info, preamble=retry_preamble)
                    elif not use_hermes:
                        used = _direct_llm_reply(
                            q, session_id, msg_text, model, assistant_parts,
                            route_info=route_info, preamble=retry_preamble,
                        )
                        if not used:
                            _demo_reply(q, msg_text, assistant_parts, route_info=route_info, preamble=retry_preamble)
                    elif AIAgent is not None:
                        session = store.get_session(session_id)
                        history = list(session.messages[:-1]) if session else []
                        clean_history = [
                            {"role": m["role"], "content": m["content"]}
                            for m in history
                            if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)
                        ]
                        kwargs = {
                            "platform": "cli",
                            "quiet_mode": True,
                            "session_id": session_id,
                            "stream_delta_callback": on_token,
                        }
                        if model:
                            kwargs["model"] = model
                        try:
                            agent = AIAgent(**kwargs, tool_progress_callback=on_tool)
                        except TypeError:
                            agent = AIAgent(**kwargs)
                        result = agent.run_conversation(
                            user_message=agent_input,
                            conversation_history=clean_history,
                            task_id=session_id,
                        )
                        if not assistant_parts and result:
                            final = ""
                            if isinstance(result, dict):
                                final = result.get("final_response") or result.get("response") or result.get("content") or ""
                            elif isinstance(result, str):
                                final = result
                            if final:
                                assistant_parts.append(str(final))
                                _put(q, "token", {"text": str(final)})
                    else:
                        used = _hermes_cli_reply(
                            q, session_id, agent_input, model, assistant_parts,
                            route_info=route_info, workspace=workspace,
                        )
                        if not used:
                            used = _direct_llm_reply(
                                q, session_id, msg_text, model, assistant_parts,
                                route_info=route_info, preamble=retry_preamble,
                            )
                        if not used:
                            _demo_reply(q, msg_text, assistant_parts, route_info=route_info, preamble=retry_preamble)

                    final_text = "".join(assistant_parts).strip() or f"（重试后仍无有效回复。原错误：{err}）"
                    if route_info.get("execution_mode") == "workflow":
                        final_text = sanitize_workflow_output(final_text) or final_text
                    route_public = {k: v for k, v in route_info.items() if not str(k).startswith("_")}
                    assistant_msg = store.ensure_message_id(
                        {
                            "role": "assistant",
                            "content": final_text,
                            "route": route_public,
                            "healed": True,
                        }
                    )
                    with _lock:
                        job = JOBS.get(stream_id)
                        if job and job.get("started_at") is not None:
                            assistant_msg["elapsed_ms"] = int(
                                max(0, (time.time() - float(job["started_at"])) * 1000)
                            )
                            assistant_msg["started_at"] = job.get("started_at")
                    store.append_messages(session_id, assistant_msg)
                    _progress(q, 3, 100, "summarize")
                    _think(q, "Heal 重试完成，汇总交付", kind="heal")
                    done_payload = {
                        "session_id": session_id,
                        "content": final_text,
                        "healed": True,
                        "message_id": assistant_msg.get("id"),
                        "route": route_public,
                        "usage": {
                            "inputTokens": 0,
                            "outputTokens": max(1, len(final_text) // 4),
                            "cacheReadTokens": 0,
                            "cacheWriteTokens": 0,
                            "costUsd": 0.0,
                            "billedCostUsd": 0.0,
                        },
                    }
                    if assistant_msg.get("elapsed_ms") is not None:
                        done_payload["elapsed_ms"] = assistant_msg["elapsed_ms"]
                        done_payload["started_at"] = assistant_msg.get("started_at")
                    _put(q, "done", done_payload)
                    return
        except Exception:  # noqa: BLE001
            pass

        tb = traceback.format_exc()
        _put(q, "error", {"message": err, "traceback": tb})
        err_msg = store.ensure_message_id(
            {"role": "assistant", "content": f"**Error:** {err}", "error": True}
        )
        store.append_messages(session_id, err_msg)
        _put(q, "done", {"session_id": session_id, "error": True, "message_id": err_msg.get("id")})
    finally:
        with _lock:
            if ACTIVE.get(session_id) == stream_id:
                ACTIVE.pop(session_id, None)
            QUEUE_STREAM.pop(id(q), None)
            job = JOBS.get(stream_id)
            if job and job.get("status") == "running":
                job["status"] = "done"
                job["finished_at"] = time.time()

            def _cleanup() -> None:
                time.sleep(_JOB_RETAIN_SEC)
                with _lock:
                    JOBS.pop(stream_id, None)
                    STREAMS.pop(stream_id, None)

            threading.Thread(target=_cleanup, daemon=True).start()


def _openclaw_cli_reply(
    q: queue.Queue,
    session_id: str,
    msg_text: str,
    model: str,
    assistant_parts: list[str],
    *,
    route_info: dict[str, Any] | None = None,
) -> bool:
    """Run OpenClaw ``agent --local`` (tool-capable) when Hub agent mode is on."""
    from . import claw_cli
    from .providers import key_provider_mismatch
    from .secrets import resolve_api_key
    from .settings import load_campus_config

    if not claw_cli.find_openclaw_bin():
        return False

    cfg = load_campus_config()
    route_info = route_info or {}
    provider = str(route_info.get("provider") or (cfg.get("backend") or {}).get("type") or "")
    key_info = resolve_api_key(cfg, provider=provider if provider != "hybrid" else "")
    api_key = key_info.get("key") or ""
    base_url = str(route_info.get("base_url") or (cfg.get("backend") or {}).get("base_url") or "").strip()
    env_name = str(key_info.get("env_name") or "")
    verify_tls = resolve_backend_verify_tls(cfg, route_info)

    if not api_key and provider not in ("local-ollama",):
        return False

    mismatch = key_provider_mismatch(provider, api_key)
    if mismatch:
        raise RuntimeError(mismatch.get("message") or "API key does not match backend provider")

    _think(q, "已接入 OpenClaw · 本地 agent 通道就绪", kind="dispatch")
    _put(
        q,
        "meta",
        {
            "mode": "openclaw-cli",
            "engine": "openclaw",
            "agent_mode": True,
            "bin": str(claw_cli.find_openclaw_bin() or ""),
        },
    )
    timeout = float((cfg.get("backend") or {}).get("timeout_seconds") or 180)
    try:
        result = claw_cli.run_openclaw_chat(
            msg_text,
            session_id=session_id,
            api_key=api_key,
            env_name=env_name,
            base_url=base_url,
            provider_id=provider,
            timeout=timeout,
            verify_tls=verify_tls,
        )
    except Exception as exc:  # noqa: BLE001
        _put(q, "meta", {"mode": "openclaw-cli", "engine": "openclaw", "error": str(exc)})
        return False

    text = str(result.get("text") or "").strip()
    if not text:
        return False
    chunk = 96
    for i in range(0, len(text), chunk):
        piece = text[i : i + chunk]
        assistant_parts.append(piece)
        _put(q, "token", {"text": piece})
    return True


def _apply_hermes_agent_tls(agent: Any, verify_tls: bool) -> None:
    """Rebuild Hermes' in-process OpenAI/httpx client with routed TLS policy."""
    if verify_tls:
        return
    client_kwargs = dict(getattr(agent, "_client_kwargs", {}) or {})
    if not client_kwargs or not hasattr(agent, "_create_openai_client"):
        raise RuntimeError("Hermes Agent does not expose a configurable HTTP client")
    client_kwargs["ssl_verify"] = False
    new_client = agent._create_openai_client(
        dict(client_kwargs),
        reason="agent_hub_tls_policy",
        shared=True,
    )
    old_client = getattr(agent, "client", None)
    agent._client_kwargs = client_kwargs
    agent.client = new_client
    if old_client is not None and old_client is not new_client:
        try:
            agent._close_openai_client(
                old_client,
                reason="agent_hub_tls_policy",
                shared=True,
            )
        except Exception:  # noqa: BLE001
            try:
                old_client.close()
            except Exception:  # noqa: BLE001
                pass


def _hermes_cli_reply(
    q: queue.Queue,
    session_id: str,
    msg_text: str,
    model: str,
    assistant_parts: list[str],
    *,
    route_info: dict[str, Any] | None = None,
    workspace: str = "",
) -> bool:
    """Run Hermes via its CLI when in-process AIAgent cannot be imported."""
    from . import hermes_cli
    from .secrets import resolve_api_key
    from .settings import load_campus_config, resolve_backend_verify_tls
    from .providers import key_provider_mismatch

    if not hermes_cli.find_hermes_bin():
        return False

    cfg = load_campus_config()
    route_info = route_info or {}
    provider = str(route_info.get("provider") or (cfg.get("backend") or {}).get("type") or "")
    key_info = resolve_api_key(cfg, provider=provider if provider != "hybrid" else "")
    api_key = key_info.get("key") or ""
    base_url = str(route_info.get("base_url") or (cfg.get("backend") or {}).get("base_url") or "").strip()
    use_model = (model or route_info.get("model") or "").strip()
    env_name = str(key_info.get("env_name") or (cfg.get("backend") or {}).get("api_key_env") or "")
    verify_tls = resolve_backend_verify_tls(cfg, route_info)

    if not api_key and provider not in ("local-ollama",):
        return False

    mismatch = key_provider_mismatch(provider, api_key)
    if mismatch:
        raise RuntimeError(mismatch.get("message") or "API key does not match backend provider")

    if not route_info.get("_hermes_synced"):
        try:
            hermes_cli.sync_hub_to_hermes(cfg, model=use_model, provider_id=provider)
            route_info["_hermes_synced"] = True
        except Exception:  # noqa: BLE001
            pass

    _put(
        q,
        "meta",
        {
            "mode": "hermes-cli",
            "engine": "hermes",
            "agent_mode": True,
            "provider": provider,
            "model": use_model,
            "bin": hermes_cli.find_hermes_bin() and str(hermes_cli.find_hermes_bin()),
            "key_source": key_info.get("source"),
        },
    )
    try:
        result = hermes_cli.run_hermes_chat(
            msg_text,
            model=use_model,
            provider_id=provider,
            api_key=api_key,
            env_name=env_name,
            base_url=base_url,
            workspace=workspace,
            timeout=float((cfg.get("backend") or {}).get("timeout_seconds") or 180),
            verify_tls=verify_tls,
        )
    except Exception as exc:  # noqa: BLE001
        _put(q, "meta", {"mode": "hermes-cli", "error": str(exc)})
        return False

    text = str(result.get("text") or "").strip()
    if text:
        text = hermes_cli.clean_hermes_text(text)
    # Hermes may exit 0 while returning an internal exception as plain text.
    # Treat it as a failed engine attempt so the configured HTTP provider gets
    # a chance to answer instead of exposing the runtime traceback to users.
    low_text = text.lower()
    if "nameerror" in low_text or "providerfallback" in low_text:
        _put(q, "meta", {"mode": "hermes-cli", "error": text[:500]})
        return False
    if not text:
        return False
    assistant_parts.append(text)
    _put(q, "token", {"text": text})
    return True


def _direct_llm_reply(
    q: queue.Queue,
    session_id: str,
    msg_text: str,
    model: str,
    assistant_parts: list[str],
    *,
    route_info: dict[str, Any] | None = None,
    preamble: str = "",
) -> bool:
    """Use OpenAI-compatible HTTP when Hermes Agent is absent but API is configured."""
    from . import llm_client
    from .providers import coerce_model_for_provider, get_provider, key_provider_mismatch
    from .secrets import resolve_api_key
    from .settings import load_campus_config, resolve_backend_verify_tls

    cfg = load_campus_config()
    route_info = route_info or {}
    backend = cfg.get("backend") or {}
    provider = str(route_info.get("provider") or backend.get("type") or "").strip()
    if provider == "hybrid":
        provider = str(backend.get("type") or "").strip()

    # Pin cloud provider endpoints from catalog — never drift back to NVIDIA NIM
    # when the user selected official DeepSeek / OpenAI / etc.
    prov = get_provider(provider) if provider else None
    base_url = str(route_info.get("base_url") or backend.get("base_url") or "").strip()
    if prov and provider not in ("", "hybrid", "campus-openai-compatible", "local-ollama"):
        catalog_url = str(prov.get("base_url") or "").strip()
        if catalog_url:
            base_url = catalog_url

    key_info = resolve_api_key(cfg, provider=provider if provider != "hybrid" else "")
    api_key = key_info.get("key") or ""
    route_key = str(route_info.get("route_key") or "office")
    use_model = coerce_model_for_provider(
        provider,
        (model or route_info.get("model") or "").strip(),
        route_key=route_key,
    )
    verify_tls = resolve_backend_verify_tls(cfg, route_info)
    timeout = float(backend.get("timeout_seconds") or 120)
    if route_info.get("simple_chat"):
        timeout = min(timeout, 25.0)

    if not base_url or not use_model:
        return False
    # Ollama often needs no key; others need a key
    if not api_key and provider not in ("local-ollama",):
        return False

    mismatch = key_provider_mismatch(provider, api_key)
    if mismatch:
        # Never silently switch OpenRouter ↔ NVIDIA — surface a clear error.
        raise RuntimeError(mismatch.get("message") or "API key does not match backend provider")

    # Refuse NVIDIA model ids against non-NVIDIA backends (and vice versa)
    low_model = use_model.lower()
    if provider == "deepseek" and ("integrate.api.nvidia" in base_url.lower() or low_model.startswith("deepseek-ai/")):
        base_url = str((prov or {}).get("base_url") or "https://api.deepseek.com/v1")
        use_model = coerce_model_for_provider(provider, use_model, route_key=route_key)

    session = store.get_session(session_id)
    history = list(session.messages[:-1]) if session else []
    messages: list[dict[str, str]] = []
    if preamble:
        messages.append({"role": "system", "content": preamble})
    # Workspace path is already embedded in grounded preamble; avoid a weak one-liner that invites invention.
    for m in history:
        role = m.get("role")
        content = m.get("content")
        if role in ("user", "assistant", "system") and isinstance(content, str):
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": msg_text})

    _put(
        q,
        "meta",
        {
            "mode": "direct-llm",
            "agent_mode": False,
            "provider": provider,
            "model": use_model,
            "base_url": base_url,
            "key_source": key_info.get("source"),
        },
    )

    def on_token(delta: str) -> None:
        if not delta:
            return
        assistant_parts.append(delta)
        _put(q, "token", {"text": delta})

    def _provider_fallback(exc: Exception) -> str:
        """Fallback for direct HTTP calls after an account-level refusal."""
        low = str(exc).lower()
        if (
            provider != "dashscope"
            or assistant_parts
            or not any(
                marker in low
                for marker in (
                    "overdue",
                    "overdue_payment",
                    "access denied",
                    "account is not in good standing",
                    "余额不足",
                )
            )
        ):
            return ""
        for fallback_provider in ("zhipu", "deepseek", "kimi", "minimax"):
            fallback_cfg = get_provider(fallback_provider)
            fallback_key = resolve_api_key(cfg, provider=fallback_provider).get("key") or ""
            if not fallback_cfg or not fallback_key:
                continue
            fallback_model = coerce_model_for_provider(
                fallback_provider, "", route_key=route_key
            )
            fallback_url = str(fallback_cfg.get("base_url") or "")
            try:
                _put(
                    q,
                    "meta",
                    {
                        "mode": "provider-fallback",
                        "from_provider": provider,
                        "provider": fallback_provider,
                        "model": fallback_model,
                    },
                )
                fallback_text = llm_client._chat_once(
                    fallback_url,
                    fallback_key,
                    model=fallback_model,
                    messages=messages,
                    timeout=timeout,
                    verify_tls=verify_tls,
                    on_token=on_token,
                    temperature=route_info.get("temperature"),
                    max_tokens=route_info.get("max_tokens"),
                )
                if fallback_text:
                    route_info["provider"] = fallback_provider
                    route_info["backend_type"] = fallback_provider
                    route_info["base_url"] = fallback_url
                    route_info["model"] = fallback_model
                    route_info["provider_fallback"] = {
                        "from": provider,
                        "to": fallback_provider,
                        "reason": "account_refusal",
                    }
                    return fallback_text
            except Exception:
                continue
        return ""

    # Simple chats: non-stream JSON — MiniMax SSE often stalls without `[DONE]`.
    if route_info.get("simple_chat"):
        try:
            text = llm_client._chat_once(
                base_url,
                api_key,
                model=use_model,
                messages=messages,
                timeout=timeout,
                verify_tls=verify_tls,
                on_token=on_token,
                temperature=route_info.get("temperature"),
                max_tokens=route_info.get("max_tokens"),
            )
        except Exception as exc:  # noqa: BLE001
            route_info["_direct_error"] = str(exc)[:500]
            fallback_text = _provider_fallback(exc)
            if fallback_text:
                if not assistant_parts:
                    assistant_parts.append(fallback_text)
                    _put(q, "token", {"text": fallback_text})
                return True
            _put(q, "meta", {"mode": "direct-llm", "error": str(exc)[:240]})
            return False
    else:
        try:
            text = llm_client.stream_chat(
                base_url,
                api_key,
                model=use_model,
                messages=messages,
                timeout=timeout,
                verify_tls=verify_tls,
                on_token=on_token,
                temperature=route_info.get("temperature"),
                max_tokens=route_info.get("max_tokens"),
            )
        except Exception as exc:  # noqa: BLE001
            route_info["_direct_error"] = str(exc)[:500]
            text = _provider_fallback(exc)
            if not text:
                raise
    if text and not assistant_parts:
        assistant_parts.append(text)
        _put(q, "token", {"text": text})
    return bool("".join(assistant_parts).strip())


def _demo_reply(
    q: queue.Queue,
    msg_text: str,
    assistant_parts: list[str],
    route_info: dict[str, Any] | None = None,
    preamble: str = "",
) -> None:
    """Fallback when Hermes Agent is not installed."""
    from . import workflows
    from .settings import load_campus_config

    status = agent_status()
    cfg = load_campus_config()
    health = workflows.health_snapshot()
    route_info = route_info or {}
    direct_ready = bool(status.get("direct_llm"))
    direct_error = str(route_info.get("_direct_error") or "").strip()
    if direct_ready:
        # Direct LLM is a valid production path. Never tell a user to install
        # Hermes merely because the optional tool-capable Agent path failed.
        lines = [
            "Agent 通道暂时不可用，已检测到 Direct LLM 配置，但本次模型请求未返回内容。\n\n",
            f"**路由**: {route_info.get('tier', '?')} → `{route_info.get('route_key', '')}` model=`{route_info.get('model') or '(未配置)'}`\n",
            f"**后端**: `{((cfg.get('backend') or {}).get('type'))}` · **建议**: 重试一次或在控制中心切换为 Direct LLM。\n",
        ]
        if direct_error:
            lines.append(f"**错误摘要**: `{direct_error}`\n\n")
    else:
        lines = [
            "Agent Hub **Campus Office** demo mode（未检测到本地 Agent 运行时）。\n\n",
        ]
        lines.extend([
        f"**路由**: {route_info.get('tier', '?')} → `{route_info.get('route_key', '')}` "
        f"model=`{route_info.get('model') or '(未配置)'}`\n",
        f"**数据策略**: `{cfg.get('data_policy')}` | **后端**: `{((cfg.get('backend') or {}).get('type'))}`\n\n",
        f"你的输入摘要: _{msg_text[:240]}_\n\n",
        "### 控制中心检查\n",
        ])
    for c in health.get("checks") or []:
        mark = "✅" if c.get("ok") else "⚠️"
        lines.append(f"- {mark} **{c['id']}**: {c.get('detail')}\n")
    if not direct_ready:
        lines.extend(
            [
            "\n### 启用完整 Agent\n",
            "1. 安装 Hermes Agent 运行时（可选）: https://hermes-agent.nousresearch.com/\n",
            "2. 在控制中心配置模型与 API Key\n",
            "3. 选择 Soul 角色并保存\n",
            "4. 重启 Agent Hub\n\n",
            f"Agent Hub home: `~/.agent-cli`\n",
            ]
        )
    if status.get("import_error"):
        lines.append(f"Import: `{status['import_error']}`\n")
    text = "".join(lines)
    chunk = 28
    for i in range(0, len(text), chunk):
        part = text[i : i + chunk]
        assistant_parts.append(part)
        _put(q, "token", {"text": part})
        time.sleep(0.015)




def inject_steer(session_id: str, text: str) -> bool:
    """Deliver mid-run steer as a thinking (+ optional token note) on the active stream."""
    msg = (text or "").strip()
    if not msg:
        return False
    with _lock:
        sid = ACTIVE.get(session_id)
        q = STREAMS.get(sid) if sid else None
    if q is None:
        return False
    note = f"【用户中途指引 / Steer】{msg}"
    _think(q, note, kind="steer")
    _put(q, "meta", {"steer": msg, "session_id": session_id})
    return True


def drain_queued_after_done(session_id: str) -> str | None:
    """Pop queued follow-up after a run ends (caller may auto-start next turn)."""
    try:
        from . import pending_intent

        pending_intent.clear_run(session_id)
        return pending_intent.pop_queue(session_id)
    except Exception:  # noqa: BLE001
        return None

def iter_sse(stream_id: str, timeout: float = 900.0, from_seq: int = 0):
    """Generator yielding SSE-formatted strings; polls durable job buffer (reconnect-safe)."""
    sid = (stream_id or "").strip()
    sent = max(0, int(from_seq or 0))
    deadline = time.time() + max(30.0, float(timeout))
    while time.time() < deadline:
        with _lock:
            job = JOBS.get(sid)
            if job is None:
                events: list[Any] = []
                status = "missing"
            else:
                events = list(job.get("events") or [])
                status = str(job.get("status") or "running")
        if status == "missing":
            # Phase 2: replay from disk journal if memory JOB expired
            try:
                from . import run_journal

                rows = run_journal.read_events(sid, from_seq=sent)
            except Exception:  # noqa: BLE001
                rows = []
            if rows:
                for row in rows:
                    event = row.get("event") or "message"
                    data = row.get("data") or {}
                    sent = max(sent, int(row.get("seq") or sent) + 0)
                    yield _sse(event, data)
                    if event == "done":
                        return
                return
            yield _sse("error", {"message": "unknown stream"})
            yield _sse("done", {})
            return
        while sent < len(events):
            item = events[sent]
            sent += 1
            event = item.get("event", "message")
            data = item.get("data") or {}
            yield _sse(event, data)
            if event == "done":
                return
        if status in ("done", "error", "cancelled"):
            # Race: status flipped after our event snapshot missed the terminal
            # event — always emit done so clients don't hang on keepalives.
            yield _sse("done", {"session_id": (job or {}).get("session_id"), "reconciled": True})
            return
        yield ": keepalive\n\n"
        time.sleep(0.04)
    yield _sse("error", {"message": "stream timeout"})
    yield _sse("done", {})


def _sse(event: str, data: dict[str, Any]) -> str:
    import json

    try:
        payload = json.dumps(data, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        payload = json.dumps({"error": "unserializable_event_data", "event": event}, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"
