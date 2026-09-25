"""Per-output provenance records (auditable history, modelled on Claude Science).

Every assistant reply gets a record answering: which model / route / engine
produced it, from which prompt, sources, skills, tools and workspace context,
in which environment, and when.  A compact summary lives on the session
message; the full record is written to ``STATE_DIR/provenance/<session>/<msg>.json``
and carries a SHA-256 over its canonical JSON so edits are detectable.

Everything here is best-effort: callers wrap it so provenance can never break
the chat path.  Secrets are never recorded (keys dropped, key-like strings
masked, ``base_url`` reduced to its host).
"""

from __future__ import annotations

import hashlib
import io
import json
import platform
import re
import sys
import time
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .config import REPO_ROOT, STATE_DIR, VERSION

SCHEMA = "agent-hub.provenance/1"
PROV_DIR = STATE_DIR / "provenance"

_SECRET_KEY_PARTS = (
    "api_key", "apikey", "secret", "password", "passwd", "authorization", "cookie",
    "access_token", "refresh_token", "auth_token", "bearer",
)
_SECRET_KEY_EXACT = {"key", "token", "api-key", "x-api-key"}
_SECRET_VALUE_RE = re.compile(
    r"(?:\bsk-[A-Za-z0-9_\-]{16,}|\bnvapi-[A-Za-z0-9_\-]{16,}|\bgh[pousr]_[A-Za-z0-9]{20,}"
    r"|\bAIza[0-9A-Za-z_\-]{30,}|\bBearer\s+[A-Za-z0-9._\-]{16,})"
)
_MAX_PROMPT_CHARS = 200_000
_SNIPPET_CHARS = 280

_env_cache: dict[str, Any] | None = None


# ── helpers ───────────────────────────────────────────────────────────


def sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _iso(ts: float | None) -> str:
    if not ts:
        return ""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(ts)))


def _safe_id(raw: str) -> str:
    return "".join(c for c in (raw or "") if c.isalnum() or c in "-_") or "unknown"


def mask_secrets(text: str) -> tuple[str, int]:
    """Mask API-key-looking substrings; returns (text, number of masks)."""
    count = 0

    def _sub(m: re.Match) -> str:
        nonlocal count
        count += 1
        return m.group(0)[:4] + "***"

    return _SECRET_VALUE_RE.sub(_sub, text or ""), count


def _redact(value: Any) -> Any:
    """Drop secret-named keys and mask key-like strings, recursively."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            lk = str(k).lower()
            if lk in _SECRET_KEY_EXACT or any(s in lk for s in _SECRET_KEY_PARTS):
                out[k] = "***"
            else:
                out[k] = _redact(v)
        return out
    if isinstance(value, (list, tuple)):
        return [_redact(v) for v in value]
    if isinstance(value, str):
        return mask_secrets(value)[0]
    return value


def _host(url: str) -> str:
    try:
        return urlparse(str(url or "")).netloc or ""
    except ValueError:
        return ""


def _git_commit() -> dict[str, str]:
    """Read the checkout's HEAD without spawning git (works on any platform)."""
    git_dir = REPO_ROOT / ".git"
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return {}
    if not head.startswith("ref:"):
        return {"commit": head}
    ref = head.split(":", 1)[1].strip()
    branch = ref.rsplit("/", 1)[-1]
    try:
        return {"commit": (git_dir / ref).read_text(encoding="utf-8").strip(), "branch": branch}
    except OSError:
        pass
    try:
        for line in (git_dir / "packed-refs").read_text(encoding="utf-8").splitlines():
            parts = line.strip().split(" ", 1)
            if len(parts) == 2 and parts[1] == ref:
                return {"commit": parts[0], "branch": branch}
    except OSError:
        pass
    return {"branch": branch}


def environment() -> dict[str, Any]:
    global _env_cache
    if _env_cache is None:
        _env_cache = {
            "app": "Agent Hub",
            "app_version": VERSION,
            "python": sys.version.split()[0],
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "git": _git_commit(),
        }
    return dict(_env_cache)


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def compute_record_hash(record: dict[str, Any]) -> str:
    body = {k: v for k, v in record.items() if k != "integrity"}
    return sha256_text(canonical_json(body))


def verify_record(record: dict[str, Any]) -> bool:
    claimed = str(((record or {}).get("integrity") or {}).get("record_sha256") or "")
    return bool(claimed) and claimed == compute_record_hash(record)


# ── record construction ───────────────────────────────────────────────


def compact_search(search: dict[str, Any] | None) -> dict[str, Any]:
    """Keep the auditable part of a ``websearch.search_structured`` result.

    Sources are numbered in the same order they were listed in the prompt.
    """
    if not isinstance(search, dict):
        return {}
    sources = []
    for i, s in enumerate(search.get("sources") or [], start=1):
        if not isinstance(s, dict):
            continue
        url = str(s.get("url") or "")
        sources.append(
            {
                "n": i,
                "title": str(s.get("title") or "")[:300],
                "url": url,
                "domain": _host(url),
                "engine": str(s.get("source") or ""),
                "snippet": str(s.get("snippet") or "")[:_SNIPPET_CHARS],
            }
        )
    return {
        "query": str(search.get("query") or ""),
        "ok": bool(search.get("ok")),
        "engines": [str(e) for e in (search.get("engines") or [])],
        "quality": search.get("quality") if isinstance(search.get("quality"), dict) else {},
        "warnings": [str(w) for w in (search.get("warnings") or [])],
        "errors": [str(e) for e in (search.get("errors") or [])][:5],
        "retrieved_at": _iso(time.time()),
        "sources": sources,
    }


def describe(record: dict[str, Any]) -> dict[str, str]:
    """Deterministic plain-language 'how this was made' sentence (zh + en)."""
    m = record.get("model") or {}
    a = record.get("agent") or {}
    c = record.get("context") or {}
    t = record.get("timing") or {}
    model = "/".join(x for x in (m.get("provider"), m.get("model") or m.get("model_slot")) if x) or "unknown model"
    route = "·".join(x for x in (m.get("tier"), m.get("route_key")) if x)
    engine = a.get("chat_engine") or "direct"
    secs = (t.get("elapsed_ms") or 0) / 1000.0
    skills = c.get("skills") or []
    n_src = len((record.get("search") or {}).get("sources") or [])
    n_tools = len(record.get("tools") or [])
    ws_entries = (c.get("grounding") or {}).get("entry_count") or 0

    zh = [f"由 {model}" + (f"（{route} 路由，{engine} 引擎）" if route else f"（{engine} 引擎）") + "生成"]
    en = [f"Generated by {model}" + (f" ({route} route, {engine} engine)" if route else f" ({engine} engine)")]
    if secs:
        zh[0] += f"，用时 {secs:.1f}s"
        en[0] += f" in {secs:.1f}s"
    if skills:
        zh.append("使用技能 " + "、".join(skills))
        en.append("skills: " + ", ".join(skills))
    if n_src:
        zh.append(f"检索 {n_src} 条来源")
        en.append(f"{n_src} retrieved sources")
    if n_tools:
        zh.append(f"调用工具 {n_tools} 次")
        en.append(f"{n_tools} tool calls")
    if ws_entries:
        zh.append(f"参考工作区 {ws_entries} 个条目")
        en.append(f"{ws_entries} workspace entries in context")
    rv = record.get("review") or {}
    if rv and not rv.get("skipped"):
        if rv.get("warn"):
            zh.append(f"审查发现 {rv.get('warn')} 项待核实")
            en.append(f"reviewer flagged {rv.get('warn')} item(s) to verify")
        else:
            zh.append("审查未发现问题")
            en.append("reviewer found no issues")
    if record.get("healed"):
        zh.append("经自愈重试")
        en.append("after a self-heal retry")
    return {"zh": "；".join(zh) + "。", "en": "; ".join(en) + "."}


def build_record(
    *,
    session_id: str,
    message_id: str,
    stream_id: str = "",
    user_message: str = "",
    preamble: str = "",
    final_text: str = "",
    route_info: dict[str, Any] | None = None,
    tools: list[dict[str, Any]] | None = None,
    grounding_check: dict[str, Any] | None = None,
    elapsed_ms: int | None = None,
    started_at: float | None = None,
    healed: bool = False,
    history_messages: int | None = None,
    review: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ri = route_info or {}
    finished = time.time()
    prompt_text, masked = mask_secrets(preamble or "")
    excel = ri.get("excel_fill") if isinstance(ri.get("excel_fill"), dict) else {}
    try:
        from .run_journal import journal_path

        journal = str(journal_path(stream_id)) if stream_id else ""
    except Exception:  # noqa: BLE001
        journal = ""

    record: dict[str, Any] = {
        "schema": SCHEMA,
        "session_id": session_id,
        "message_id": message_id,
        "stream_id": stream_id,
        "request": {
            "sha256": sha256_text(user_message),
            "chars": len(user_message or ""),
            "text": mask_secrets(user_message or "")[0][:4000],
            "workflow_id": ri.get("_workflow_id") or ri.get("workflow_id") or None,
            "execution_mode": ri.get("execution_mode") or "",
            "history_messages": history_messages,
        },
        "model": {
            "provider": str(ri.get("provider") or ri.get("backend_type") or ""),
            "model": str(ri.get("model") or ""),
            "model_slot": str(ri.get("model_slot") or ""),
            "base_url_host": _host(str(ri.get("base_url") or "")),
            "tier": str(ri.get("tier") or ""),
            "route_key": str(ri.get("route_key") or ""),
            "thinking_depth": str(ri.get("thinking_depth") or ""),
            "temperature": ri.get("temperature"),
            "max_tokens": ri.get("max_tokens"),
            "chat_mode": str(ri.get("chat_mode") or ri.get("hub_chat_mode") or ""),
            "provider_fallback": _redact(ri.get("provider_fallback")) if ri.get("provider_fallback") else None,
        },
        "agent": {
            "chat_engine": str(ri.get("chat_engine") or ""),
            "runtime_resolved": str(ri.get("runtime_resolved") or ""),
            "soul_role": str(ri.get("soul_role") or ""),
            "subagent_id": ri.get("subagent_id") or None,
            "subagent_auto": ri.get("subagent_auto") if ri.get("subagent_id") else None,
            "hermes_session_id": ri.get("hermes_session_id") or None,
        },
        "context": {
            "skills": [str(s) for s in (ri.get("skills") or [])],
            "skills_source": str(ri.get("skills_source") or ""),
            "ecosystem": bool(ri.get("ecosystem")),
            "grounding": _redact(ri.get("grounding") or {}),
            "web_search": bool(ri.get("web_search")),
            "excel_fill_output": excel.get("output_relative") or excel.get("output") or None,
            "system_prompt": {
                "sha256": sha256_text(preamble or ""),
                "chars": len(preamble or ""),
                "masked_secrets": masked,
                "truncated": len(prompt_text) > _MAX_PROMPT_CHARS,
                "text": prompt_text[:_MAX_PROMPT_CHARS],
            },
        },
        "search": ri.get("_search") if isinstance(ri.get("_search"), dict) else {},
        "tools": _redact([
            {"name": str(t.get("name") or ""), "preview": str(t.get("preview") or ""),
             **({"ok": bool(t["ok"])} if "ok" in t else {}),
             **({"duration_ms": t["duration_ms"]} if t.get("duration_ms") is not None else {})}
            for t in (tools or []) if isinstance(t, dict)
        ]),
        "output": {
            "sha256": sha256_text(final_text),
            "chars": len(final_text or ""),
            "grounding_check": _redact(grounding_check or {}),
        },
        "timing": {
            "started_at": _iso(started_at),
            "finished_at": _iso(finished),
            "elapsed_ms": elapsed_ms,
        },
        "healed": bool(healed),
        "review": _redact(review) if isinstance(review, dict) else {},
        "evidence": _redact(evidence) if isinstance(evidence, dict) else {},
        "task": {"id": ri.get("task_id"), "step": ri.get("task_step")} if ri.get("task_id") else {},
        "steer": str(ri.get("steer_applied") or "")[:500],
        "environment": environment(),
        "journal": journal,
    }
    record["description"] = describe(record)
    record["integrity"] = {"algorithm": "sha256", "record_sha256": compute_record_hash(record)}
    return record


def summary(record: dict[str, Any]) -> dict[str, Any]:
    """Compact form stored on the session message and sent in SSE ``done``."""
    m = record.get("model") or {}
    return {
        "schema": record.get("schema"),
        "description": record.get("description") or {},
        "provider": m.get("provider") or "",
        "model": m.get("model") or "",
        "tier": m.get("tier") or "",
        "chat_engine": (record.get("agent") or {}).get("chat_engine") or "",
        "sources": len((record.get("search") or {}).get("sources") or []),
        "tools": len(record.get("tools") or []),
        "skills": list((record.get("context") or {}).get("skills") or []),
        "review": {
            k: (record.get("review") or {}).get(k)
            for k in ("ok", "skipped", "warn", "info")
            if k in (record.get("review") or {})
        },
        "output_sha256": (record.get("output") or {}).get("sha256") or "",
        "record_sha256": (record.get("integrity") or {}).get("record_sha256") or "",
        "finished_at": (record.get("timing") or {}).get("finished_at") or "",
    }


# ── storage ───────────────────────────────────────────────────────────


def record_path(session_id: str, message_id: str) -> Path:
    return Path(PROV_DIR) / _safe_id(session_id) / f"{_safe_id(message_id)}.json"


def save_record(record: dict[str, Any]) -> Path:
    path = record_path(str(record.get("session_id") or ""), str(record.get("message_id") or ""))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)
    return path


def load_record(session_id: str, message_id: str) -> dict[str, Any] | None:
    path = record_path(session_id, message_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def list_records(session_id: str) -> list[dict[str, Any]]:
    d = Path(PROV_DIR) / _safe_id(session_id)
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("*.json")):
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(rec, dict):
            out.append(rec)
    out.sort(key=lambda r: str((r.get("timing") or {}).get("finished_at") or ""))
    return out


def record_reply(**kwargs: Any) -> dict[str, Any]:
    """Build + persist a record and log it to the audit trail; returns the summary."""
    record = build_record(**kwargs)
    save_record(record)
    try:
        from . import audit

        audit.log_event(
            "provenance_recorded",
            {
                "session_id": record.get("session_id"),
                "message_id": record.get("message_id"),
                "record_sha256": (record.get("integrity") or {}).get("record_sha256"),
            },
        )
    except Exception:  # noqa: BLE001
        pass
    return summary(record)


# ── human-readable report & reproducibility bundle ────────────────────


def _md_cell(value: Any) -> str:
    return str(value if value not in (None, "") else "—").replace("|", "\\|").replace("\n", " ")


def render_markdown(record: dict[str, Any]) -> str:
    m = record.get("model") or {}
    a = record.get("agent") or {}
    c = record.get("context") or {}
    t = record.get("timing") or {}
    env = record.get("environment") or {}
    git = env.get("git") or {}
    search = record.get("search") or {}
    desc = record.get("description") or {}
    verified = verify_record(record)
    lines = [
        "# 溯源报告 · Provenance report",
        "",
        f"> {desc.get('zh') or ''}",
        f"> {desc.get('en') or ''}",
        "",
        f"- Session: `{record.get('session_id')}` · Message: `{record.get('message_id')}`",
        f"- Stream: `{record.get('stream_id') or '—'}` · Journal: `{record.get('journal') or '—'}`",
        f"- Time: {t.get('started_at') or '—'} → {t.get('finished_at') or '—'} ({t.get('elapsed_ms') or '—'} ms)",
        f"- Schema: `{record.get('schema')}`",
        "",
        "## 模型与路由 · Model & route",
        "",
        "| Field | Value |",
        "|---|---|",
    ]
    for label, val in (
        ("Provider", m.get("provider")),
        ("Model", m.get("model")),
        ("Model slot", m.get("model_slot")),
        ("Endpoint host", m.get("base_url_host")),
        ("Tier / route", " · ".join(x for x in (m.get("tier"), m.get("route_key")) if x)),
        ("Thinking depth", m.get("thinking_depth")),
        ("Temperature", m.get("temperature")),
        ("Engine", a.get("chat_engine")),
        ("Runtime", a.get("runtime_resolved")),
        ("Soul role", a.get("soul_role")),
        ("Subagent", a.get("subagent_id")),
        ("Provider fallback", json.dumps(m.get("provider_fallback"), ensure_ascii=False) if m.get("provider_fallback") else ""),
    ):
        lines.append(f"| {label} | {_md_cell(val)} |")

    lines += ["", "## 上下文 · Context", ""]
    lines.append(f"- Skills ({_md_cell(c.get('skills_source'))}): {', '.join(c.get('skills') or []) or '—'}")
    g = c.get("grounding") or {}
    lines.append(f"- Workspace: `{g.get('workspace') or '—'}` · entries {g.get('entry_count') or 0} · excerpts {g.get('excerpts') or 0}")
    lines.append(f"- Ecosystem packages active: {'yes' if c.get('ecosystem') else 'no'}")
    if c.get("excel_fill_output"):
        lines.append(f"- Excel fill output: `{c.get('excel_fill_output')}`")
    sp = c.get("system_prompt") or {}
    lines.append(f"- System prompt: {sp.get('chars') or 0} chars · sha256 `{sp.get('sha256') or ''}`")

    lines += ["", "## 来源 · Sources", ""]
    srcs = search.get("sources") or []
    if srcs:
        lines.append(f"Query: `{search.get('query') or ''}` · engines: {', '.join(search.get('engines') or []) or '—'}")
        if search.get("warnings"):
            lines.append("Warnings: " + "；".join(search.get("warnings") or []))
        lines += ["", "| # | Title | Domain | Engine |", "|---|---|---|---|"]
        for s in srcs:
            title = _md_cell(s.get("title"))
            url = str(s.get("url") or "")
            link = f"[{title}]({url})" if url else title
            lines.append(f"| {s.get('n')} | {link} | {_md_cell(s.get('domain'))} | {_md_cell(s.get('engine'))} |")
    else:
        lines.append("No web sources were retrieved for this reply. · 本次回复未使用联网来源。")

    ev = record.get("evidence") or {}
    if ev.get("sources"):
        cov = ev.get("coverage") or {}
        lines += ["", "## 证据核对 · Evidence", ""]
        lines.append(
            f"- Authoritative {cov.get('authoritative', 0)}/{cov.get('sources', 0)} · pages read {cov.get('pages_read', 0)}"
            f" · corroborated numbers {cov.get('corroborated_facts', 0)} · conflicts {len(ev.get('conflicts') or [])}"
            + (f" · latest {cov['latest_date']}" if cov.get("latest_date") else "")
        )
        lines += ["", "| # | Tier | Date | Domain |", "|---|---|---|---|"]
        for s_ in ev.get("sources") or []:
            lines.append(f"| {s_.get('n')} | {_md_cell(s_.get('tier_label'))} | {_md_cell(s_.get('date'))} | {_md_cell(s_.get('domain'))} |")
        facts = ev.get("facts") or []
        if facts:
            lines += ["", "| Metric | Value | Sources | Agreement |", "|---|---|---|---|"]
            for f in facts[:12]:
                agree = "conflict" if f.get("conflict") else (f"{f.get('domains')} domains" if (f.get("domains") or 0) >= 2 else "single source")
                lines.append(f"| {_md_cell(f.get('key'))} | {_md_cell(f.get('display'))} | {''.join(f'[{n}]' for n in f.get('sources') or [])} | {agree} |")

    lines += ["", "## 工具调用 · Tool calls", ""]
    tools = record.get("tools") or []
    if tools:
        lines += ["| # | Tool | Preview |", "|---|---|---|"]
        for i, tl in enumerate(tools, start=1):
            lines.append(f"| {i} | `{_md_cell(tl.get('name'))}` | {_md_cell(tl.get('preview'))} |")
    else:
        lines.append("None · 无")

    out = record.get("output") or {}
    gc = out.get("grounding_check") or {}
    lines += ["", "## 输出与校验 · Output & checks", ""]
    lines.append(f"- Output: {out.get('chars') or 0} chars · sha256 `{out.get('sha256') or ''}`")
    if gc.get("unverified"):
        lines.append("- ⚠ Unverified file paths: " + ", ".join(f"`{p}`" for p in gc.get("unverified") or []))
    else:
        lines.append("- Workspace path check: OK")
    lines.append(f"- Record sha256: `{(record.get('integrity') or {}).get('record_sha256') or ''}` · {'✓ verified' if verified else '✗ MISMATCH'}")

    rv = record.get("review") or {}
    lines += ["", "## 审查 · Review", ""]
    if not rv or rv.get("skipped"):
        lines.append("Skipped (chit-chat) · 已跳过（闲聊）" if rv.get("skipped") else "Not reviewed · 未审查")
    else:
        st = rv.get("stats") or {}
        lines.append(
            f"- {'✓ No issues' if rv.get('ok') else '⚠ ' + str(rv.get('warn')) + ' warning(s)'} · "
            f"{rv.get('info') or 0} note(s) · citations {st.get('citations', 0)} · "
            f"numbers traced {st.get('traced_numbers', 0)}/{st.get('numbers', 0)}"
        )
        for it in rv.get("issues") or []:
            lines.append(f"- [{it.get('severity')}] `{it.get('kind')}` {_md_cell(it.get('text'))} — {_md_cell(it.get('detail'))}")

    lines += ["", "## 环境 · Environment", ""]
    lines.append(
        f"- {env.get('app')} v{env.get('app_version')} · Python {env.get('python')} ({env.get('implementation')}) · {env.get('platform')}"
    )
    if git:
        lines.append(f"- Git: `{git.get('commit') or '?'}` ({git.get('branch') or 'detached'})")
    lines.append("")
    return "\n".join(lines)


def export_session_bundle(session_id: str) -> tuple[bytes, str]:
    """Zip session + provenance records + run journals + report + manifest.

    Returns ``(zip_bytes, filename)``. Raises ``FileNotFoundError`` for an
    unknown session.
    """
    from . import sessions as store

    session = store.get_session(session_id)
    if session is None:
        raise FileNotFoundError(f"session not found: {session_id}")
    records = list_records(session_id)
    files: dict[str, bytes] = {}
    files["session.json"] = json.dumps(_redact(session.to_dict()), ensure_ascii=False, indent=2).encode("utf-8")
    report = [
        f"# 复现包 · Reproducibility bundle — {session.title}",
        "",
        f"- Session: `{session.id}` · exported {_iso(time.time())}",
        f"- Records: {len(records)} · environment at export: {canonical_json(environment())}",
        "",
    ]
    for rec in records:
        mid = _safe_id(str(rec.get("message_id") or ""))
        files[f"provenance/{mid}.json"] = json.dumps(rec, ensure_ascii=False, indent=2).encode("utf-8")
        journal = str(rec.get("journal") or "")
        if journal:
            jp = Path(journal)
            if jp.is_file():
                try:
                    files[f"runs/{jp.name}"] = jp.read_bytes()
                except OSError:
                    pass
        report += ["---", "", render_markdown(rec)]
    files["REPORT.md"] = "\n".join(report).encode("utf-8")
    manifest = {
        "schema": SCHEMA + "#bundle",
        "session_id": session.id,
        "title": session.title,
        "exported_at": _iso(time.time()),
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
        "records": [
            {
                "message_id": r.get("message_id"),
                "record_sha256": (r.get("integrity") or {}).get("record_sha256"),
                "verified": verify_record(r),
            }
            for r in records
        ],
    }
    files["MANIFEST.json"] = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return buf.getvalue(), f"agent-hub-repro_{_safe_id(session.id)[:8]}_{stamp}.zip"
