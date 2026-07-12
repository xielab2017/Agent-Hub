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

# stream_id -> Queue of SSE event dicts
STREAMS: dict[str, queue.Queue] = {}
# session_id -> stream_id currently running
ACTIVE: dict[str, str] = {}
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


def agent_status() -> dict[str, Any]:
    cls = get_ai_agent()
    dirs = [str(p) for p in discover_agent_dirs()]
    return {
        "available": cls is not None,
        "agent_dir": str(_agent_dir) if _agent_dir else (dirs[0] if dirs else None),
        "hermes_home": str(hermes_home()),
        "import_error": _import_error,
        "candidates": dirs,
    }


def _put(q: queue.Queue, event: str, data: dict[str, Any] | None = None) -> None:
    q.put({"event": event, "data": data or {}})


def cancel_stream(session_id: str) -> bool:
    with _lock:
        sid = ACTIVE.get(session_id)
        if not sid:
            return False
        q = STREAMS.get(sid)
        if q is not None:
            _put(q, "cancelled", {"session_id": session_id})
            _put(q, "done", {"session_id": session_id})
        ACTIVE.pop(session_id, None)
        return True


def start_chat(
    session_id: str,
    message: str,
    model: str = "",
    workspace: str = "",
    route: str = "auto",
    workflow_id: str = "",
    system: str = "",
    display_message: str = "",
) -> dict[str, Any]:
    """Start a background agent run; returns stream_id for SSE."""
    from . import audit, routing
    from .settings import load_campus_config

    session = store.get_session(session_id)
    if session is None:
        raise ValueError("session not found")

    msg = (message or "").strip()
    if not msg:
        raise ValueError("empty message")

    cfg = load_campus_config()
    route_info = routing.resolve_route(route or "auto", msg, cfg)
    if route_info.get("blocked"):
        raise ValueError(route_info.get("block_reason") or "route blocked by data_policy")

    # Prefer explicit model, else routed model
    resolved_model = (model or "").strip() or route_info.get("model") or ""
    ws = (workspace or "").strip() or (cfg.get("workspace") or "")
    preamble = system or routing.system_preamble(route_info, cfg)

    stream_id = str(uuid.uuid4())
    q: queue.Queue = queue.Queue()
    with _lock:
        old = ACTIVE.get(session_id)
        if old and old in STREAMS:
            _put(STREAMS[old], "cancelled", {"session_id": session_id})
            _put(STREAMS[old], "done", {"session_id": session_id})
        STREAMS[stream_id] = q
        ACTIVE[session_id] = stream_id

    shown = (display_message or msg).strip()
    meta = {
        "role": "user",
        "content": shown,
        "route": route_info,
        "workflow_id": workflow_id or None,
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
        "route": route_info,
        "model": resolved_model,
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
    _put(q, "route", route_info)

    def on_token(delta: str) -> None:
        if not delta:
            return
        assistant_parts.append(delta)
        _put(q, "token", {"text": delta})

    def on_tool(name: str = "", preview: str = "", args: Any = None, **kwargs: Any) -> None:
        payload = {
            "name": name or kwargs.get("tool_name") or "tool",
            "preview": preview or str(args or kwargs.get("args") or "")[:500],
        }
        tools_seen.append(payload)
        _put(q, "tool", payload)

    try:
        AIAgent = get_ai_agent()
        agent_input = msg_text
        if preamble:
            agent_input = f"[SYSTEM CONTEXT]\n{preamble}\n\n[USER]\n{msg_text}"

        if AIAgent is None:
            _demo_reply(q, msg_text, assistant_parts, route_info=route_info, preamble=preamble)
        else:
            session = store.get_session(session_id)
            history = list(session.messages[:-1]) if session else []
            clean_history = []
            for m in history:
                role = m.get("role")
                content = m.get("content")
                if role in ("user", "assistant") and isinstance(content, str):
                    clean_history.append({"role": role, "content": content})

            kwargs: dict[str, Any] = {
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

            if workspace:
                try:
                    import os

                    os.chdir(workspace)
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
                if final:
                    assistant_parts.append(str(final))
                    _put(q, "token", {"text": str(final)})

        final_text = "".join(assistant_parts).strip()
        if not final_text:
            final_text = "(no response)"
            _put(q, "token", {"text": final_text})

        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": final_text,
            "route": route_info,
        }
        if tools_seen:
            assistant_msg["tools"] = tools_seen
        store.append_messages(session_id, assistant_msg)
        _put(q, "done", {"session_id": session_id, "content": final_text, "route": route_info})

    except Exception as exc:  # noqa: BLE001
        err = f"{type(exc).__name__}: {exc}"
        tb = traceback.format_exc()
        _put(q, "error", {"message": err, "traceback": tb})
        store.append_messages(
            session_id,
            {"role": "assistant", "content": f"**Error:** {err}", "error": True},
        )
        _put(q, "done", {"session_id": session_id, "error": True})
    finally:
        with _lock:
            if ACTIVE.get(session_id) == stream_id:
                ACTIVE.pop(session_id, None)

            def _cleanup() -> None:
                time.sleep(60)
                with _lock:
                    STREAMS.pop(stream_id, None)

            threading.Thread(target=_cleanup, daemon=True).start()


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
    lines = [
        "Hermes-ALI **Campus Office** demo mode（未检测到 Hermes Agent）。\n\n",
        f"**路由**: {route_info.get('tier', '?')} → `{route_info.get('route_key', '')}` "
        f"model=`{route_info.get('model') or '(未配置)'}`\n",
        f"**数据策略**: `{cfg.get('data_policy')}` | **后端**: `{((cfg.get('backend') or {}).get('type'))}`\n\n",
        f"你的输入摘要: _{msg_text[:240]}_\n\n",
        "### 控制中心检查\n",
    ]
    for c in health.get("checks") or []:
        mark = "✅" if c.get("ok") else "⚠️"
        lines.append(f"- {mark} **{c['id']}**: {c.get('detail')}\n")
    lines.extend(
        [
            "\n### 启用完整 Agent\n",
            "1. 安装 Hermes Agent: https://hermes-agent.nousresearch.com/\n",
            "2. `hermes model` 配置校园 OpenAI-compatible / NVIDIA NIM\n",
            "3. 在控制中心填写 campus-office-ai 模型 ID 与 Vault 路径\n",
            "4. 重启 Hermes-ALI\n\n",
            f"HERMES_HOME: `{status['hermes_home']}`\n",
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


def iter_sse(stream_id: str, timeout: float = 300.0):
    """Generator yielding SSE-formatted strings."""
    q = STREAMS.get(stream_id)
    if q is None:
        yield _sse("error", {"message": "unknown stream"})
        yield _sse("done", {})
        return

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            item = q.get(timeout=1.0)
        except queue.Empty:
            yield ": keepalive\n\n"
            continue
        event = item.get("event", "message")
        data = item.get("data") or {}
        yield _sse(event, data)
        if event == "done":
            break


def _sse(event: str, data: dict[str, Any]) -> str:
    import json

    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"
