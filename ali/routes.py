"""HTTP route handlers for Hermes-ALI."""

from __future__ import annotations

import json
import importlib
import inspect
import mimetypes
import tempfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import (
    agents,
    audit,
    auth,
    brand_logo,
    digest,
    ecosystem,
    evolution,
    excel_fill,
   feedback,
    folders,
    fsutil,
    hermes_cli,
    home,
    mcp_hub,
    model_intelligence,
    nightly_maintenance,
    multipart,
    obsidian,
    routing,
    runtimes,
    schedule,
    sessions as store,
    skills,
    skills_hub,
    soul,
    pending_intent,
    run_journal,
    streaming,
    subagent_planner,
    uploads,
    websearch,
    workflows,
)
from .config import APP_NAME, PUBLIC_URL, REPO_ROOT, RUNTIME, STATIC_DIR, VERSION, local_ips, public_ip
from .settings import (
    import_campus_config,
    load_campus_config,
    public_model_governance_view,
    public_settings_view,
    resolve_backend_verify_tls,
    save_campus_config,
)


_COUNTRY_CACHE = {"value": "", "expires": 0.0, "refreshing": False}
_COUNTRY_CACHE_LOCK = threading.Lock()
_COUNTRY_CACHE_TTL = 24 * 60 * 60
_COUNTRY_HEADERS = (
    "CF-IPCountry",
    "CloudFront-Viewer-Country",
    "X-Vercel-IP-Country",
)
_ZH_COUNTRIES = frozenset({"CN", "HK", "MO", "TW"})


def _country_code(value: Any) -> str:
    code = str(value or "").strip().upper()
    return code if len(code) == 2 and code.isascii() and code.isalpha() else ""


def _proxy_country_hint(headers: Any) -> str:
    """Read only provider-owned country headers, never forwarded client IPs."""
    for name in _COUNTRY_HEADERS:
        code = _country_code(headers.get(name) if headers is not None else "")
        if code:
            return code
    return ""


def _refresh_server_country() -> None:
    value = ""
    try:
        request = urllib.request.Request(
            "https://ipapi.co/country/",
            headers={"User-Agent": "Agent-Hub/locale-hint"},
        )
        with urllib.request.urlopen(request, timeout=2.0) as response:  # noqa: S310
            value = _country_code(response.read(16).decode("ascii", errors="ignore"))
    except (OSError, ValueError):
        pass
    with _COUNTRY_CACHE_LOCK:
        _COUNTRY_CACHE.update({
            "value": value,
            "expires": time.monotonic() + (_COUNTRY_CACHE_TTL if value else 10 * 60),
            "refreshing": False,
        })


def _cached_server_country_hint() -> str:
    """Return cached country immediately and refresh it off the request thread."""
    now = time.monotonic()
    with _COUNTRY_CACHE_LOCK:
        value = str(_COUNTRY_CACHE.get("value") or "")
        if now < float(_COUNTRY_CACHE.get("expires") or 0):
            return value
        if not _COUNTRY_CACHE.get("refreshing"):
            _COUNTRY_CACHE["refreshing"] = True
            threading.Thread(target=_refresh_server_country, daemon=True).start()
        return value


def _resolve_locale_hint(
    language_mode: Any,
    headers: Any,
    *,
    server_country: str = "",
) -> dict[str, str]:
    mode = str(language_mode or "zh").strip().lower()
    mode = mode if mode in ("zh", "en", "auto") else "zh"
    if mode != "auto":
        return {"mode": mode, "resolved": mode, "source": "setting", "country": ""}

    country = _proxy_country_hint(headers)
    source = "proxy_country" if country else ""
    if not country:
        country = _country_code(server_country)
        source = "server_country" if country else ""
    if country:
        return {
            "mode": "auto",
            "resolved": "zh" if country in _ZH_COUNTRIES else "en",
            "source": source,
            "country": country,
        }

    accepted = str(headers.get("Accept-Language") if headers is not None else "").lower()
    resolved = "zh" if any(part.strip().startswith("zh") for part in accepted.split(",")) else "en"
    if not accepted.strip():
        resolved = "zh"
    return {"mode": "auto", "resolved": resolved, "source": "accept_language", "country": ""}


def _build_fusion_plan(body: dict[str, Any]) -> dict[str, Any]:
    """Call the fusion planner while tolerating adjacent branch signatures."""
    prompt = str(body.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("prompt required")
    cfg = load_campus_config()
    mode = str(body.get("fusion_mode") or cfg.get("fusion_mode") or "auto").strip().lower()
    if mode not in ("fast", "auto", "deep"):
        raise ValueError("fusion_mode must be fast, auto, or deep")

    request = {
        "prompt": prompt,
        "task_type": str(body.get("task_type") or "auto"),
        "fusion_mode": mode,
        "thinking_depth": str(body.get("thinking_depth") or "medium"),
    }
    module = importlib.import_module("ali.fusion")
    build_plan = getattr(module, "build_plan", None) or getattr(module, "build_fusion_plan", None)
    if not callable(build_plan):
        raise RuntimeError("ali.fusion.build_plan/build_fusion_plan is unavailable")

    signature = inspect.signature(build_plan)
    parameters = signature.parameters
    request_names = ("request", "payload", "body", "options")
    if any(name in parameters for name in request_names):
        kwargs = {next(name for name in request_names if name in parameters): request}
        if "config" in parameters:
            kwargs["config"] = cfg
        elif "cfg" in parameters:
            kwargs["cfg"] = cfg
        result = build_plan(**kwargs)
    else:
        profiles = cfg.get("model_profiles")
        profiles = list(profiles.values()) if isinstance(profiles, dict) else []
        budget = cfg.get("fusion_token_budget")
        total_budget = budget.get("total_budget") if isinstance(budget, dict) else budget
        candidates = {
            **request,
            "cfg": cfg,
            "models": profiles,
            "total_budget": total_budget,
        }
        if "config" in parameters:
            candidates["config"] = cfg
        accepts_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in parameters.values())
        kwargs = candidates if accepts_kwargs else {key: value for key, value in candidates.items() if key in parameters}
        result = build_plan(**kwargs)
    if not isinstance(result, dict):
        raise TypeError("fusion plan must be a JSON object")
    judge_model = str(cfg.get("fusion_judge_model") or "").strip()
    if judge_model and isinstance(result.get("judge"), dict):
        result = dict(result)
        result["judge"] = {**result["judge"], "model": judge_model, "source": "configured"}
    return result


def _sync_hermes_safe(cfg: dict | None = None) -> dict:
    """Best-effort Hub → Hermes provider sync (never raises to callers)."""
    try:
        return hermes_cli.sync_hub_to_hermes(cfg)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": str(exc),
            "error_zh": f"同步 Hermes 失败：{exc}",
            "error_en": f"Hermes sync failed: {exc}",
        }


def _sync_runtime_llm_safe(runtime: str = "", cfg: dict | None = None) -> dict:
    """Sync Hub LLM credentials into the selected runtime / claw home."""
    try:
        return runtimes.sync_hub_llm(runtime or "auto", cfg)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": str(exc),
            "error_zh": f"同步运行时 LLM 失败：{exc}",
            "error_en": f"Runtime LLM sync failed: {exc}",
            "runtime": runtime or "auto",
        }


def _json(handler, status: int, payload: Any) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    try:
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}


def _optional_bool(value: Any) -> bool | None:
    """Decode JSON booleans without treating the string ``"false"`` as true."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("true", "1", "yes", "on"):
            return True
        if normalized in ("false", "0", "no", "off", ""):
            return False
    raise ValueError("boolean value required")


def _path_parts(path: str) -> tuple[str, list[str], dict[str, list[str]]]:
    parsed = urlparse(path)
    parts = [p for p in parsed.path.split("/") if p]
    return parsed.path, parts, parse_qs(parsed.query)


PUBLIC_PATHS = {
    "/",
    "/index.html",
    "/health",
    "/api/health",
    "/api/login",
    "/api/status",
}


def requires_auth(path: str) -> bool:
    if not auth.auth_required():
        return False
    if path in PUBLIC_PATHS:
        return False
    if path.startswith("/static/") or path.startswith("/assets/"):
        return False
    if path.startswith("/brand/"):
        return False
    if path.endswith((".css", ".js", ".svg", ".png", ".ico", ".woff2", ".json", ".jpg", ".jpeg", ".webp")):
        return False
    return path.startswith("/api/")


def handle_get(handler) -> None:
    path, parts, qs = _path_parts(handler.path)

    if requires_auth(path) and not auth.is_authenticated(handler):
        _json(handler, 401, {"error": "unauthorized"})
        return

    if path in ("/", "/index.html"):
        return _serve_file(handler, STATIC_DIR / "index.html")

    if path.startswith("/static/"):
        return _serve_file(handler, STATIC_DIR / path[len("/static/") :])

    if path in ("/app.js", "/style.css"):
        return _serve_file(handler, STATIC_DIR / path.lstrip("/"))

    if path.startswith("/brand/custom/"):
        custom = brand_logo.resolve_custom_file(path[len("/brand/custom/") :])
        if custom is None:
            return _json(handler, 404, {"error": "not found"})
        return _serve_file(handler, custom, root=brand_logo.brand_custom_dir())

    if path.startswith("/brand/"):
        return _serve_file(handler, STATIC_DIR / "brand" / path[len("/brand/") :], root=STATIC_DIR / "brand")

    if path.startswith("/assets/"):
        return _serve_file(handler, REPO_ROOT / "assets" / path[len("/assets/") :], root=REPO_ROOT / "assets")

    if path in ("/health", "/api/health"):
        st = streaming.agent_status()
        return _json(
            handler,
            200,
            {
                "ok": True,
                "version": VERSION,
                "gateway": "online",
                "agent": {
                    "available": bool(st.get("available") or st.get("agent_mode") or st.get("direct_llm")),
                    "chat_engine": st.get("chat_engine") or "",
                    "runtime_resolved": st.get("runtime_resolved") or st.get("runtime_active") or "",
                    "hub_chat_mode": st.get("hub_chat_mode") or "",
                },
                "note_zh": "Hub 网关在线。关闭浏览器不会停止网关或 Claw；请用 ctl.sh stop 显式停止。",
                "note_en": "Hub gateway online. Closing the browser does not stop the gateway or Claw; use ctl.sh stop.",
            },
        )

    if path == "/api/status":
        st = streaming.agent_status()
        health = workflows.health_snapshot()
        ali = load_campus_config().get("ali") or {}
        detected_public_ip = public_ip()
        proxy_country = _proxy_country_hint(handler.headers)
        language_mode = str(ali.get("language_mode") or ali.get("language") or "zh").strip().lower()
        server_country = ""
        if language_mode == "auto" and not proxy_country:
            server_country = _cached_server_country_hint()
        locale_hint = _resolve_locale_hint(
            language_mode,
            handler.headers,
            server_country=server_country,
        )
        return _json(
            handler,
            200,
            {
                "version": VERSION,
                "auth_required": auth.auth_required(),
                "authenticated": auth.is_authenticated(handler),
                "host": RUNTIME.get("host"),
                "port": RUNTIME.get("port"),
                "local_ips": local_ips(),
                "public_url": PUBLIC_URL,
                "public_ip": detected_public_ip,
                "public_access": {
                    "configured": bool(PUBLIC_URL),
                    "detected": bool(detected_public_ip),
                    "https": PUBLIC_URL.lower().startswith("https://"),
                    "auth_required": auth.auth_required(),
                    "ready": bool(
                        PUBLIC_URL
                        and PUBLIC_URL.lower().startswith("https://")
                        and auth.auth_required()
                    ),
                },
                "locale_hint": locale_hint,
                "agent": st,
                "health": health,
                "default_route": "auto" if (ali.get("default_route") in (None, "", "office")) else ali.get("default_route"),
                "ui": {
                    "language": ali.get("language") or "zh",
                    "language_mode": ali.get("language_mode") or ali.get("language") or "zh",
                    "theme": ali.get("theme") or "auto",
                    "accent": ali.get("accent") or "suat",
                    "bg": ali.get("bg") or "auto",
                    "chat_mode": ali.get("chat_mode") or "auto",
                    "last_model": ali.get("last_model") or "",
                    "thinking_depth": ali.get("thinking_depth") or "medium",
                    "hub_chat_mode": ali.get("hub_chat_mode") or "agent",
                    **brand_logo.public_logo_state({"ali": ali}),
                },
                "app_name": APP_NAME,
                "models": (load_campus_config().get("models") or {}),
                "runtime": {
                    "active": ali.get("agent_runtime") or "auto",
                    "auto_runtime": ali.get("auto_runtime") or "hermes",
                },
            },
        )

    if path == "/api/settings":
        return _json(handler, 200, public_settings_view())

    if path == "/api/models/governance":
        view = public_model_governance_view()
        view["jobs"] = model_intelligence.governance_job()
        return _json(handler, 200, view)

    if path == "/api/ui/logo":
        return _json(handler, 200, brand_logo.public_logo_state())

    if path == "/api/providers":
        from .providers import catalog_payload

        return _json(handler, 200, catalog_payload())

    if path == "/api/usage":
        # ── Token usage summary (OpenSquilla) ───────────────────────────────
        tracker = streaming.get_usage_tracker()
        has_squilla = streaming.get_has_squilla()
        if tracker is None:
            return _json(handler, 200, {
                "ok": False,
                "available": False,
                "message": "OpenSquilla UsageTracker not available",
            })
        all_sessions = tracker.all_sessions()
        rows = []
        total_input = total_output = total_cost = total_cache_read = total_cache_write = 0
        for sid, usage in all_sessions.items():
            rows.append({
                "sessionKey": sid,
                "inputTokens": usage.input_tokens,
                "outputTokens": usage.output_tokens,
                "cacheReadTokens": usage.cache_read_tokens,
                "cacheWriteTokens": usage.cache_write_tokens,
                "costUsd": round(usage.total_cost, 8),
                "billedCostUsd": round(usage.billed_cost, 8),
                "model": usage.model_id,
                "provider": getattr(usage, "provider", ""),
            })
            total_input += usage.input_tokens
            total_output += usage.output_tokens
            total_cost += usage.total_cost
            total_cache_read += usage.cache_read_tokens
            total_cache_write += usage.cache_write_tokens
        return _json(handler, 200, {
            "ok": True,
            "available": True,
            "totalSessions": len(rows),
            "totalInputTokens": total_input,
            "totalOutputTokens": total_output,
            "totalCacheReadTokens": total_cache_read,
            "totalCacheWriteTokens": total_cache_write,
            "totalCostUsd": round(total_cost, 8),
            "sessions": rows,
        })

    if path == "/api/routing":
        from .providers import model_options_payload

        cfg = load_campus_config()
        return _json(
            handler,
            200,
            {
                "matrix": routing.routing_matrix(),
                "tiers": routing.TIERS,
                "model_options": model_options_payload(cfg),
            },
        )

    if path == "/api/workflows":
        return _json(handler, 200, {"presets": workflows.list_presets()})

    if path == "/api/health/office":
        return _json(handler, 200, workflows.health_snapshot())

    if path == "/api/audit":
        limit = int((qs.get("limit") or ["50"])[0])
        return _json(handler, 200, {"events": audit.recent(limit)})

    if path == "/api/obsidian":
        return _json(handler, 200, obsidian.vault_status())

    if path == "/api/fs/list":
        target = (qs.get("path") or [""])[0]
        return _json(handler, 200, fsutil.list_dir(target))

    if path == "/api/obsidian/notes":
        limit = int((qs.get("limit") or ["40"])[0])
        root = (qs.get("root") or [""])[0]
        return _json(handler, 200, obsidian.list_notes(limit=limit, root_filter=root))

    if len(parts) == 4 and parts[0] == "api" and parts[1] == "obsidian" and parts[2] == "note":
        # /api/obsidian/note?path=
        rel = (qs.get("path") or [""])[0]
        return _json(handler, 200, obsidian.read_note(rel))

    if path == "/api/sessions":
        include_archived = (qs.get("archived") or ["0"])[0] in ("1", "true", "yes")
        return _json(handler, 200, {"sessions": store.list_sessions(include_archived=include_archived)})

    if path == "/api/folders":
        return _json(handler, 200, {"folders": folders.list_folders()})

    if path == "/api/sessions/context":
        sid = (qs.get("session_id") or [""])[0]
        query = (qs.get("query") or [""])[0]
        return _json(handler, 200, store.folder_context(sid, query))

    if path == "/api/feedback":
        limit = int((qs.get("limit") or ["50"])[0])
        return _json(handler, 200, feedback.summary(limit=limit))

    if path == "/api/uploads":
        sid = (qs.get("session_id") or [""])[0]
        return _json(handler, 200, uploads.list_uploads(sid))

    if path == "/api/skills":
        return _json(handler, 200, skills.list_skills())

    if path == "/api/skills/catalog":
        return _json(handler, 200, skills.skill_catalog())

    if path == "/api/skills/suggest":
        q = (qs.get("q") or qs.get("message") or [""])[0]
        return _json(handler, 200, skills.suggest_skills(q))

    if path == "/api/skills/hub-loaded":
        return _json(handler, 200, {"ok": True, "hub_loaded_skills": skills.get_hub_loaded()})

    if path == "/api/search":
        q = (qs.get("q") or qs.get("query") or [""])[0]
        try:
            limit = int((qs.get("limit") or ["8"])[0])
        except ValueError:
            limit = 8
        deep = (qs.get("deep") or ["1"])[0] not in ("0", "false", "False", "no")
        if deep:
            return _json(handler, 200, websearch.deep_search(q, limit=max(1, min(limit, 16))))
        structured = websearch.search_structured(q, limit=max(1, min(limit, 16)), deep=False)
        return _json(handler, 200, {
            **structured,
            "results": structured.get("sources") or [],
            "offline": not bool(structured.get("ok")),
        })

    if path == "/api/search/status":
        return _json(handler, 200, websearch.search_status())

    if path == "/api/soul":
        return _json(handler, 200, soul.get_soul())

    if path == "/api/schedule":
        return _json(handler, 200, schedule.list_tasks())

    if path == "/api/schedule/notifications":
        # Default unread-only for morning tips; ?all=1 for history
        all_flag = (qs.get("all") or [""])[0].lower() in ("1", "true", "yes")
        return _json(
            handler,
            200,
            schedule.list_notifications(unread_only=not all_flag, limit=40),
        )

    if path == "/api/agents":
        return _json(handler, 200, agents.get_agents())

    if path == "/api/agents/parallel-plan":
        # GET?count=&message= also accepted via query for debugging
        count = int((qs.get("count") or ["3"])[0] or 3)
        message = (qs.get("message") or [""])[0]
        prefer = qs.get("prefer") or []
        if isinstance(prefer, str):
            prefer = [prefer]
        lanes = agents.pick_subagents_for_parallel(count, message, prefer_ids=list(prefer))
        return _json(handler, 200, {"ok": True, "lanes": lanes, "count": len(lanes)})

    if path == "/api/runtimes":
        return _json(handler, 200, runtimes.list_runtimes())

    if path == "/api/home":
        return _json(handler, 200, home.home_status())

    if path == "/api/ecosystem":
        return _json(handler, 200, ecosystem.list_ecosystem())

    if path == "/api/evolution":
        return _json(handler, 200, evolution.list_targets())

    if path == "/api/evolution/runs":
        tid = (qs.get("target_id") or [""])[0]
        try:
            limit = int((qs.get("limit") or ["30"])[0])
        except ValueError:
            limit = 30
        return _json(handler, 200, evolution.list_runs(limit=limit, target_id=tid))

    if len(parts) == 4 and parts[0] == "api" and parts[1] == "evolution" and parts[2] == "runs":
        try:
            return _json(handler, 200, evolution.get_run(parts[3]))
        except FileNotFoundError:
            return _json(handler, 404, {"error": "run not found"})

    if len(parts) == 4 and parts[0] == "api" and parts[1] == "evolution" and parts[2] == "jobs":
        try:
            return _json(handler, 200, evolution.job_status(parts[3]))
        except FileNotFoundError:
            return _json(handler, 404, {"error": "job not found"})

    if path == "/api/mcp":
        return _json(handler, 200, mcp_hub.list_mcp())

    if path == "/api/skills/hub":
        return _json(handler, 200, skills_hub.list_skill_packs())

    if path == "/api/recommend/daily":
        refresh = (qs.get("refresh") or ["0"])[0] in ("1", "true", "yes")
        return _json(handler, 200, digest.daily_recommend(refresh=refresh))

    if path == "/api/digests":
        return _json(handler, 200, digest.latest_digests())

    if len(parts) == 4 and parts[0] == "api" and parts[1] == "runtimes" and parts[2] == "jobs":
        try:
            return _json(handler, 200, runtimes.install_job_status(parts[3]))
        except FileNotFoundError:
            return _json(handler, 404, {"error": "job not found"})

    if len(parts) == 4 and parts[0] == "api" and parts[1] == "ecosystem" and parts[2] == "jobs":
        try:
            return _json(handler, 200, ecosystem.job_status(parts[3]))
        except FileNotFoundError:
            return _json(handler, 404, {"error": "job not found"})

    if path == "/api/workspace/snapshot":
        from . import grounding

        target = (qs.get("path") or [""])[0]
        sid = (qs.get("session_id") or [""])[0]
        snap = grounding.snapshot_workspace(target, session_id=sid)
        return _json(handler, 200, snap)

    if path == "/api/workspace/verify":
        # GET with query is awkward for long text — use POST
        return _json(handler, 405, {"error": "use POST"})

    if path == "/api/jobs/active":
        return _json(handler, 200, {"jobs": streaming.list_active_jobs()})

    if len(parts) == 4 and parts[0] == "api" and parts[1] == "sessions" and parts[3] == "pending":
        return _json(handler, 200, {"ok": True, "session_id": parts[2], **pending_intent.get(parts[2])})

    if len(parts) == 4 and parts[0] == "api" and parts[1] == "sessions" and parts[3] == "journal":
        # ?stream_id= optional; else active job stream
        qs = parse_qs(urlparse(handler.path).query)
        sid = (qs.get("stream_id") or [""])[0].strip()
        if not sid:
            job = streaming.session_job(parts[2]) or {}
            sid = str(job.get("stream_id") or "")
        if not sid:
            return _json(handler, 404, {"error": "no journal / active stream"})
        return _json(handler, 200, run_journal.status(sid))

    if len(parts) == 4 and parts[0] == "api" and parts[1] == "sessions" and parts[3] == "job":
        job = streaming.session_job(parts[2])
        if not job:
            return _json(handler, 200, {"active": False})
        return _json(handler, 200, {"active": True, "job": job})

    if len(parts) == 3 and parts[0] == "api" and parts[1] == "sessions":
        session = store.get_session(parts[2])
        if session is None:
            return _json(handler, 404, {"error": "not found"})
        out = session.to_dict()
        job = streaming.session_job(parts[2])
        if job:
            out["active_job"] = job
        return _json(handler, 200, out)

    if len(parts) == 3 and parts[0] == "api" and parts[1] == "stream":
        try:
            from_seq = int((qs.get("from") or ["0"])[0])
        except ValueError:
            from_seq = 0
        return _sse_stream(handler, parts[2], from_seq=from_seq)

    _json(handler, 404, {"error": "not found"})


def handle_post(handler) -> None:
    path, parts, _qs = _path_parts(handler.path)

    if path == "/api/login":
        body = _read_json(handler)
        if not auth.verify_password(str(body.get("password") or "")):
            return _json(handler, 403, {"error": "invalid password"})
        token = auth.issue_token()
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header(
            "Set-Cookie",
            f"{auth.COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={7*24*3600}",
        )
        payload = json.dumps({"ok": True, "token": token}).encode("utf-8")
        handler.send_header("Content-Length", str(len(payload)))
        handler.end_headers()
        handler.wfile.write(payload)
        return

    if requires_auth(path) and not auth.is_authenticated(handler):
        return _json(handler, 401, {"error": "unauthorized"})

    if path == "/api/settings":
        body = _read_json(handler)
        cfg = body.get("config") if isinstance(body.get("config"), dict) else body
        # Backend changes require an explicit intent flag. Older/stale browser
        # tabs POST a complete cached config when saving appearance/routes and
        # must never switch provider or re-enable TLS as a side effect.
        if not bool(body.get("backend_update")):
            current_backend = (load_campus_config().get("backend") or {})
            if isinstance(current_backend, dict):
                cfg = dict(cfg)
                cfg["backend"] = dict(current_backend)
        saved = save_campus_config(cfg)
        audit.log_event("settings_save", {"keys": list(saved.keys())})
        hermes_sync = _sync_hermes_safe(saved)
        view = public_settings_view()
        if saved.get("_warning"):
            view["warning"] = saved["_warning"]
        return _json(
            handler,
            200,
            {
                "ok": True,
                "config": {k: v for k, v in saved.items() if not str(k).startswith("_")},
                "hermes_sync": hermes_sync,
                **view,
            },
        )

    if path == "/api/fusion/plan":
        body = _read_json(handler)
        try:
            plan = _build_fusion_plan(body)
            return _json(handler, 200, plan)
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})
        except (ImportError, RuntimeError) as exc:
            return _json(handler, 503, {"error": str(exc), "available": False})
        except TypeError as exc:
            return _json(handler, 500, {"error": str(exc)})

    if path == "/api/ui/logo":
        try:
            ctype = handler.headers.get("Content-Type") or ""
            if "multipart/form-data" in ctype:
                parsed = multipart.parse_multipart(handler)
                fields = parsed.get("fields") or {}
                slot = str(fields.get("slot") or "both")
                files = parsed.get("files") or []
                if not files:
                    return _json(handler, 400, {"error": "file required"})
                upload = files[0]
                result = brand_logo.save_upload(
                    upload.get("data") or b"",
                    filename=str(upload.get("filename") or "logo.png"),
                    slot=slot,
                )
                audit.log_event("ui_logo_upload", {"slot": slot, "filename": upload.get("filename")})
                return _json(handler, 200, result)
            body = _read_json(handler)
            action = str(body.get("action") or "").strip().lower()
            slot = str(body.get("slot") or "both")
            if action == "reset":
                result = brand_logo.reset_logos(slot)
                audit.log_event("ui_logo_reset", {"slot": slot})
                return _json(handler, 200, result)
            if action == "preset":
                result = brand_logo.apply_preset(str(body.get("preset") or body.get("id") or ""), slot)
                audit.log_event("ui_logo_preset", {"slot": slot, "preset": body.get("preset") or body.get("id")})
                return _json(handler, 200, result)
            return _json(handler, 400, {"error": "use multipart upload, or action=preset|reset"})
        except (OSError, ValueError) as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/maintenance/run":
        try:
            return _json(handler, 200, nightly_maintenance.run())
        except Exception as exc:  # noqa: BLE001
            return _json(handler, 500, {"ok": False, "error": str(exc)})

    if path == "/api/ui/logo/preset":
        body = _read_json(handler)
        try:
            result = brand_logo.apply_preset(
                str(body.get("preset") or body.get("id") or ""),
                str(body.get("slot") or "both"),
            )
            audit.log_event("ui_logo_preset", {"slot": body.get("slot"), "preset": body.get("preset") or body.get("id")})
            return _json(handler, 200, result)
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/ui/logo/reset":
        body = _read_json(handler)
        try:
            result = brand_logo.reset_logos(str(body.get("slot") or "both"))
            audit.log_event("ui_logo_reset", {"slot": body.get("slot")})
            return _json(handler, 200, result)
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/settings/sync-hermes":
        # Always Hermes homes (dedicated button). Use /api/runtimes/sync-llm for other claws.
        result = _sync_hermes_safe()
        try:
            mcp_hub.sync_to_hermes()
        except Exception:  # noqa: BLE001
            pass
        status = 200 if result.get("ok") else 400
        return _json(handler, status, result)

    if path == "/api/settings/apply-provider":
        body = _read_json(handler)
        from .providers import apply_hybrid_preset, apply_provider_preset

        try:
            current = load_campus_config()
            provider_id = str(body.get("provider") or "")
            hybrid_preset = str(body.get("hybrid_preset") or "")
            fill_models = body.get("fill_models", True)
            if hybrid_preset:
                next_cfg = apply_hybrid_preset(current, hybrid_preset)
            else:
                next_cfg = apply_provider_preset(current, provider_id, fill_models=bool(fill_models))
            saved = save_campus_config(next_cfg)
            hermes_sync = _sync_hermes_safe(saved)
            view = public_settings_view()
            if saved.get("_warning"):
                view["warning"] = saved["_warning"]
            audit.log_event("apply_provider", {"provider": provider_id, "hybrid_preset": hybrid_preset or None})
            return _json(handler, 200, {"ok": True, "hermes_sync": hermes_sync, **view})
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/recommend/apply-model":
        body = _read_json(handler)
        from .providers import apply_recommended_model

        try:
            current = load_campus_config()
            next_cfg = apply_recommended_model(
                current,
                model_id=str(body.get("model_id") or body.get("id") or ""),
                provider=str(body.get("provider") or ""),
                role=str(body.get("role") or "main"),
                apply_provider=bool(body.get("apply_provider", True)),
            )
            meta = next_cfg.pop("_apply_meta", {})
            saved = save_campus_config(next_cfg)
            hermes_sync = _sync_hermes_safe(saved)
            view = public_settings_view()
            if saved.get("_warning"):
                view["warning"] = saved["_warning"]
            audit.log_event("apply_recommended_model", meta)
            return _json(
                handler,
                200,
                {
                    "ok": True,
                    "applied": meta,
                    "hermes_sync": hermes_sync,
                    "note_zh": "已写入模型配置并设为当前模型；请确认后端 Provider / API Key 已就绪。",
                    "note_en": "Model written into config and set as current; ensure provider + API key are ready.",
                    **view,
                },
            )
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/settings/api-key":
        body = _read_json(handler)
        from .secrets import set_api_key
        from .providers import (
            apply_provider_preset,
            detect_provider_from_key,
            key_provider_mismatch,
            looks_like_secret,
            get_provider,
        )

        raw_key = str(body.get("api_key") or body.get("key") or "").strip()
        provider = str(body.get("provider") or (load_campus_config().get("backend") or {}).get("type") or "default").strip()
        env_name = str(body.get("api_key_env") or (load_campus_config().get("backend") or {}).get("api_key_env") or "").strip()
        # Default OFF: never silently switch OpenRouter ↔ NVIDIA backends.
        auto_switch = bool(body.get("auto_switch", False))

        # If user pasted key into env_name by mistake, treat as key
        if looks_like_secret(env_name) and not raw_key:
            raw_key = env_name
            env_name = ""

        if not raw_key and body.get("clear"):
            set_api_key(provider, "")
            if env_name:
                set_api_key(env_name, "")
            return _json(handler, 200, {"ok": True, "present": False, **public_settings_view()})

        if not raw_key:
            return _json(handler, 400, {"error": "api_key required"})

        detected = detect_provider_from_key(raw_key)
        switched = None
        mismatch = key_provider_mismatch(provider, raw_key)
        if mismatch and auto_switch and detected and get_provider(detected):
            cfg = apply_provider_preset(load_campus_config(), detected, fill_models=True)
            save_campus_config(cfg)
            switched = {"from": provider, "to": detected}
            provider = detected
            env_name = str((cfg.get("backend") or {}).get("api_key_env") or "")
            mismatch = None
        elif mismatch:
            return _json(
                handler,
                400,
                {
                    "error": mismatch.get("message") or "API key does not match selected backend",
                    "mismatch": mismatch,
                    "hint": "先在后端类型中选择匹配的厂商，再保存对应密钥（OpenRouter=sk-or-…，NVIDIA=nvapi-…）。",
                },
            )

        # Save under provider id and THAT provider's env name only (no cross-write).
        info = set_api_key(provider, raw_key)
        prov = get_provider(provider) if provider else None
        if not env_name and prov and prov.get("api_key_env"):
            env_name = str(prov["api_key_env"])
        if env_name and not looks_like_secret(env_name):
            set_api_key(env_name, raw_key)
            cfg = load_campus_config()
            cfg.setdefault("backend", {})["api_key_env"] = env_name
            if provider != "hybrid":
                cfg["backend"]["type"] = provider
            save_campus_config(cfg)
        elif provider and prov and prov.get("api_key_env"):
            cfg = load_campus_config()
            cfg.setdefault("backend", {})["api_key_env"] = prov["api_key_env"]
            if provider != "hybrid":
                cfg["backend"]["type"] = provider
            save_campus_config(cfg)
            set_api_key(str(prov["api_key_env"]), raw_key)

        audit.log_event("api_key_save", {"provider": provider, "present": True, "switched": switched})
        hermes_sync = _sync_hermes_safe()
        view = public_settings_view()
        view["api_key_saved"] = {
            "provider": provider,
            "masked": info.get("masked"),
            "detected": detected,
            "switched": switched,
            "mismatch": mismatch,
        }
        view["hermes_sync"] = hermes_sync
        if switched:
            view["warning"] = (
                f"密钥格式匹配 {switched['to']}，已自动将后端从 {switched['from']} 切换为 {switched['to']}。"
            )
        return _json(handler, 200, {"ok": True, **view})

    if path == "/api/settings/refresh-models":
        body = _read_json(handler)
        from . import llm_client
        from .secrets import resolve_api_key

        cfg = load_campus_config()
        # optionally update base_url/type from body first
        if body.get("base_url") or body.get("provider"):
            backend = dict(cfg.get("backend") or {})
            if body.get("provider"):
                backend["type"] = str(body["provider"])
            if body.get("base_url"):
                backend["base_url"] = str(body["base_url"]).strip()
            cfg["backend"] = backend
            cfg = save_campus_config(cfg)

        provider = str((cfg.get("backend") or {}).get("type") or "")
        key_info = resolve_api_key(cfg, provider=provider)
        base_url = str((cfg.get("backend") or {}).get("base_url") or "").strip()
        if not base_url:
            return _json(handler, 400, {"error": "base_url missing — set Backend Base URL first"})
        if not key_info.get("present") and provider not in ("local-ollama",):
            return _json(handler, 400, {"error": "API key missing — paste key in Control Center and Save key"})

        result = llm_client.list_models(
            base_url,
            key_info.get("key") or "",
            timeout=float((cfg.get("backend") or {}).get("timeout_seconds") or 30),
            verify_tls=resolve_backend_verify_tls(cfg, {"provider": provider}),
        )
        if not result.get("ok"):
            return _json(handler, 400, {"error": result.get("error") or "list models failed", **result})

        models = result.get("models") or []
        catalogs = dict(cfg.get("available_models") or {})
        # Replace only this provider after a successful fetch. Failed fetches
        # return above and therefore preserve the last known-good catalog.
        catalogs[provider] = [str(model) for model in models if str(model).strip()]
        cfg["available_models"] = catalogs
        suggested = llm_client.suggest_slots(models)
        apply_suggest = body.get("apply_suggestions", True)
        if apply_suggest and suggested:
            m = dict(cfg.get("models") or {})
            m.update({k: v for k, v in suggested.items() if v})
            cfg["models"] = m
        cfg = save_campus_config(cfg)

        governance_job = None
        if provider == "nvidia-nim":
            governance_job = model_intelligence.start_governance_analysis(
                provider=provider,
                models=models,
                base_url=base_url,
                api_key=key_info.get("key") or "",
                verify_tls=resolve_backend_verify_tls(cfg, {"provider": provider}),
                deep=False,
                force=False,
            )

        audit.log_event("refresh_models", {"count": len(models), "provider": provider})
        view = public_settings_view()
        return _json(
            handler,
            200,
            {
                "ok": True,
                "models": models,
                "count": len(models),
                "suggested": suggested,
                "applied": bool(apply_suggest),
                "governance_job": governance_job,
                **view,
            },
        )

    if path == "/api/models/governance/refresh":
        body = _read_json(handler)
        from .secrets import resolve_api_key

        cfg = load_campus_config()
        provider = str(body.get("provider") or (cfg.get("backend") or {}).get("type") or "").strip()
        catalogs = cfg.get("available_models") if isinstance(cfg.get("available_models"), dict) else {}
        models = body.get("models") if isinstance(body.get("models"), list) else catalogs.get(provider) or []
        key_info = resolve_api_key(cfg, provider=provider)
        base_url = str(body.get("base_url") or (cfg.get("backend") or {}).get("base_url") or "").strip()
        if not base_url or (not key_info.get("present") and provider != "local-ollama"):
            return _json(handler, 400, {"error": "Provider Base URL and API key are required"})
        job = model_intelligence.start_governance_analysis(
            provider=provider,
            models=models,
            base_url=base_url,
            api_key=key_info.get("key") or "",
            verify_tls=resolve_backend_verify_tls(cfg, {"provider": provider}),
            deep=bool(body.get("deep")),
            force=bool(body.get("force", True)),
        )
        return _json(handler, 202, {"ok": True, "job": job})

    if path == "/api/settings/import":
        body = _read_json(handler)
        try:
            saved = import_campus_config(str(body.get("path") or ""))
            return _json(handler, 200, {"ok": True, "config": saved})
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/routing/resolve":
        body = _read_json(handler)
        info = routing.resolve_route(
            str(body.get("route") or "auto"),
            str(body.get("message") or ""),
        )
        return _json(handler, 200, info)

    if path == "/api/workflows/run":
        body = _read_json(handler)
        preset_id = str(body.get("preset_id") or "")
        session_id = str(body.get("session_id") or "")
        user_input = str(body.get("input") or "")
        try:
            built = workflows.build_workflow_message(preset_id, user_input)
            if not session_id:
                s = store.create_session(title=built["preset"]["name"])
                session_id = s.id
            result = streaming.start_chat(
                session_id=session_id,
                message=built["message"],
                route=built["preset"].get("route") or built["route"].get("route_key") or "office",
                workflow_id=preset_id,
                system=built["system"],
                display_message=f"[{built['preset']['name']}] {user_input[:200] or '(使用工作流模板)'}",
                workspace=str(body.get("workspace") or ""),
                skills=list(body.get("skills") or []),
                execution_mode=str(body.get("execution_mode") or "workflow"),
                thinking_depth=str(body.get("thinking_depth") or ""),
            )
            workflows.record_run(preset_id, session_id, built["route"], "started")
            result["preset"] = built["preset"]
            result["session_id"] = session_id
            return _json(handler, 200, result)
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/obsidian/write":
        body = _read_json(handler)
        result = obsidian.write_candidate(
            title=str(body.get("title") or "AI_Note"),
            content=str(body.get("content") or ""),
            approved=bool(body.get("approved")),
            tags=list(body.get("tags") or ["ai-candidate"]),
        )
        audit.log_event("obsidian_write", {"ok": result.get("ok"), "path": result.get("path"), "needs_approval": result.get("needs_approval")})
        return _json(handler, 200 if result.get("ok") or result.get("needs_approval") else 400, result)

    if path == "/api/sessions":
        body = _read_json(handler)
        s = store.create_session(
            title=str(body.get("title") or "New chat"),
            model=str(body.get("model") or ""),
            hidden=bool(body.get("hidden")),
            parent_id=str(body.get("parent_id") or ""),
            folder_id=str(body.get("folder_id") or ""),
        )
        return _json(handler, 201, s.to_dict())

    if path == "/api/folders":
        body = _read_json(handler)
        return _json(handler, 201, folders.create_folder(str(body.get("name") or "新文件夹")))

    if len(parts) == 4 and parts[0] == "api" and parts[1] == "sessions" and parts[3] == "messages":
        body = _read_json(handler)
        msgs = body.get("messages") if isinstance(body.get("messages"), list) else []
        if not msgs and (body.get("role") or body.get("content")):
            msgs = [{"role": body.get("role") or "assistant", "content": body.get("content") or ""}]
        try:
            cleaned: list[dict] = []
            for m in msgs:
                if not isinstance(m, dict):
                    continue
                role = str(m.get("role") or "assistant")
                content = m.get("content")
                if not isinstance(content, str):
                    content = str(content or "")
                if role == "assistant":
                    content = streaming.sanitize_workflow_output(content)
                entry: dict = {"role": role, "content": content}
                if isinstance(m.get("route"), dict):
                    entry["route"] = m["route"]
                if m.get("elapsed_ms") is not None:
                    entry["elapsed_ms"] = m.get("elapsed_ms")
                cleaned.append(entry)
            if not cleaned:
                return _json(handler, 400, {"error": "no messages"})
            s = store.append_messages(parts[2], *cleaned)
            if s is None:
                return _json(handler, 404, {"error": "not found"})
            return _json(handler, 200, s.to_dict())
        except Exception as exc:  # noqa: BLE001
            return _json(handler, 400, {"error": str(exc)})

    if len(parts) == 4 and parts[0] == "api" and parts[1] == "sessions" and parts[3] == "backup":
        try:
            result = store.backup_session(parts[2])
            audit.log_event("session_backup", {"session_id": parts[2], "path": result.get("path")})
            return _json(handler, 200, result)
        except FileNotFoundError:
            return _json(handler, 404, {"error": "not found"})
        except Exception as exc:  # noqa: BLE001
            return _json(handler, 400, {"error": str(exc)})

    if len(parts) == 4 and parts[0] == "api" and parts[1] == "sessions" and parts[3] == "chat":
        body = _read_json(handler)
        try:
            result = streaming.start_chat(
                session_id=parts[2],
                message=str(body.get("message") or ""),
                model=str(body.get("model") or ""),
                workspace=str(body.get("workspace") or ""),
                route=str(body.get("route") or "auto"),
                workflow_id=str(body.get("workflow_id") or ""),
                system=str(body.get("system") or ""),
                display_message=str(body.get("display_message") or ""),
                skills=list(body.get("skills") or []),
                execution_mode=str(body.get("execution_mode") or "workflow"),
                soul_role=str(body.get("soul_role") or ""),
                subagent_id=str(body.get("subagent_id") or ""),
                web_search=body.get("web_search") if "web_search" in body else None,
                thinking_depth=str(body.get("thinking_depth") or ""),
                max_tokens_override=body.get("max_tokens_override", body.get("max_tokens")),
            )
            return _json(handler, 200, result)
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})

    if len(parts) == 4 and parts[0] == "api" and parts[1] == "sessions" and parts[3] == "queue":
        body = _read_json(handler)
        result = pending_intent.enqueue(parts[2], str(body.get("message") or body.get("text") or ""))
        audit.log_event("session_queue", {"session_id": parts[2], "ok": result.get("ok")})
        return _json(handler, 200 if result.get("ok") else 400, result)

    if len(parts) == 4 and parts[0] == "api" and parts[1] == "sessions" and parts[3] == "steer":
        body = _read_json(handler)
        result = pending_intent.steer(parts[2], str(body.get("message") or body.get("text") or ""))
        audit.log_event("session_steer", {"session_id": parts[2], "ok": result.get("ok")})
        return _json(handler, 200 if result.get("ok") else 400, result)

    if len(parts) == 4 and parts[0] == "api" and parts[1] == "sessions" and parts[3] == "busy-mode":
        body = _read_json(handler)
        result = pending_intent.set_busy_mode(parts[2], str(body.get("mode") or "queue"))
        return _json(handler, 200, {"ok": True, **result})

    if len(parts) == 4 and parts[0] == "api" and parts[1] == "sessions" and parts[3] == "cancel":
        body = {}
        try:
            body = _read_json(handler)
        except Exception:  # noqa: BLE001
            body = {}
        stop_and_send = bool(body.get("stop_and_send") or body.get("drain_queue"))
        queued = None
        if stop_and_send:
            queued = pending_intent.pop_queue(parts[2])
        ok = streaming.cancel_stream(parts[2])
        return _json(handler, 200, {
            "ok": ok,
            "stop_and_send": stop_and_send,
            "queued_message": queued,
        })

    if path == "/api/feedback":
        body = _read_json(handler)
        try:
            result = feedback.rate_message(
                str(body.get("session_id") or ""),
                str(body.get("message_id") or ""),
                rating=int(body.get("rating")),
                note=str(body.get("note") or ""),
                model=str(body.get("model") or ""),
                content_preview=str(body.get("content_preview") or ""),
            )
            audit.log_event("feedback", {"rating": body.get("rating"), "session_id": body.get("session_id")})
            return _json(handler, 200, result)
        except (TypeError, ValueError) as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/uploads":
        try:
            ctype = handler.headers.get("Content-Type") or ""
            if "multipart/form-data" in ctype:
                parsed = multipart.parse_multipart(handler)
                fields = parsed["fields"]
                sid = fields.get("session_id") or ""
                into_ws = (fields.get("into_workspace") or "").lower() in ("1", "true", "yes")
                saved = []
                for f in parsed["files"]:
                    rel = fields.get("relative_path") or f.get("filename") or ""
                    # webkitdirectory sends full relative path in filename
                    if "/" in (f.get("filename") or "") or "\\" in (f.get("filename") or ""):
                        rel = f["filename"]
                    saved.append(
                        uploads.save_bytes(
                            f["data"],
                            filename=f.get("filename") or "file",
                            session_id=sid,
                            relative_path=rel,
                            into_workspace=into_ws,
                        )
                    )
                audit.log_event("upload", {"count": len(saved), "session_id": sid})
                return _json(handler, 200, {"ok": True, "files": saved, "count": len(saved)})
            body = _read_json(handler)
            import base64

            data = base64.b64decode(str(body.get("data") or ""))
            result = uploads.save_bytes(
                data,
                filename=str(body.get("filename") or "upload.bin"),
                session_id=str(body.get("session_id") or ""),
                relative_path=str(body.get("relative_path") or ""),
                into_workspace=bool(body.get("into_workspace")),
            )
            return _json(handler, 200, result)
        except (OSError, ValueError) as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/skills/install":
        body = _read_json(handler)
        try:
            src = Path(str(body.get("path") or "")).expanduser()
            result = skills.install_skill_dir(src, name=str(body.get("name") or ""))
            audit.log_event("skill_install", {"id": result.get("id"), "path": str(src)})
            return _json(handler, 200, result)
        except (OSError, ValueError, FileNotFoundError) as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/skills/upload":
        try:
            parsed = multipart.parse_multipart(handler)
            name = (parsed["fields"].get("name") or "").strip()
            files = parsed.get("files") or []
            zips = [f for f in files if multipart.is_zip_upload(f)]
            if not zips:
                return _json(
                    handler,
                    400,
                    {
                        "error": "zip file required",
                        "hint": "请上传包含 SKILL.md 的 Skill ZIP（字段名 file）",
                        "fields": list((parsed.get("fields") or {}).keys()),
                        "file_names": [f.get("filename") for f in files],
                    },
                )
            upload = zips[0]
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp.write(upload["data"])
                tmp_path = Path(tmp.name)
            try:
                result = skills.install_skill_zip(tmp_path, name=name)
            finally:
                tmp_path.unlink(missing_ok=True)
            audit.log_event("skill_upload", {"id": result.get("id"), "path": result.get("path")})
            return _json(handler, 200, result)
        except (OSError, ValueError, FileNotFoundError, zipfile.BadZipFile) as exc:
            return _json(handler, 400, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            return _json(handler, 400, {"error": f"upload failed: {exc}"})

    if path == "/api/soul":
        body = _read_json(handler)
        try:
            if body.get("seed"):
                result = soul.save_soul("", seed_if_missing=True)
            else:
                result = soul.save_soul(str(body.get("content") or ""))
            audit.log_event("soul_save", {"path": result.get("path")})
            return _json(handler, 200, {**result, **soul.get_soul()})
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/soul/role":
        body = _read_json(handler)
        try:
            return _json(handler, 200, soul.set_active_role(str(body.get("role") or "")))
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/soul/roles":
        body = _read_json(handler)
        try:
            return _json(handler, 200, soul.upsert_role(body))
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/soul/generate":
        body = _read_json(handler)
        try:
            return _json(
                handler,
                200,
                soul.generate_soul_draft(
                    str(body.get("brief") or ""),
                    role_label=str(body.get("role_label") or body.get("label") or ""),
                ),
            )
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/schedule":
        body = _read_json(handler)
        try:
            if body.get("defaults") is not None or "nightly_hour" in body or "maintenance_hour" in body or "morning_hour" in body:
                return _json(
                    handler,
                    200,
                    schedule.save_defaults(
                        nightly_hour=body.get("nightly_hour"),
                        morning_hour=body.get("morning_hour"),
                        maintenance_hour=body.get("maintenance_hour"),
                    ),
                )
            return _json(handler, 200, schedule.upsert_task(body))
        except (ValueError, TypeError) as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/schedule/notifications/read":
        body = _read_json(handler)
        ids = body.get("ids") if isinstance(body.get("ids"), list) else None
        all_read = bool(body.get("all") or body.get("all_read"))
        return _json(handler, 200, schedule.mark_notifications_read(ids, all_read=all_read or not ids))

    if path == "/api/agents":
        body = _read_json(handler)
        return _json(handler, 200, agents.save_agents(body))

    if path == "/api/agents/parallel-plan":
        body = _read_json(handler)
        count = int(body.get("count") or 3)
        message = str(body.get("message") or "")
        prefer = body.get("prefer_ids") or body.get("prefer") or []
        if not isinstance(prefer, list):
            prefer = []
        lanes = agents.pick_subagents_for_parallel(
            count,
            message,
            prefer_ids=[str(x) for x in prefer if str(x).strip()],
        )
        return _json(handler, 200, {"ok": True, "lanes": lanes, "count": len(lanes)})

    if path == "/api/agents/auto-plan":
        body = _read_json(handler)
        message = str(body.get("message") or body.get("text") or "").strip()
        session_context = str(body.get("session_context") or body.get("context") or "").strip()
        session_id = str(body.get("session_id") or "").strip()
        if session_id and not session_context:
            try:
                sess = store.get_session(session_id)
                if sess and getattr(sess, "messages", None):
                    bits = []
                    for m in list(sess.messages)[-6:]:
                        role = m.get("role") if isinstance(m, dict) else ""
                        content = m.get("content") if isinstance(m, dict) else ""
                        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
                            bits.append(f"{role}: {content.strip()[:240]}")
                    session_context = "\n".join(bits)
            except Exception:  # noqa: BLE001
                session_context = ""
        web_search = body.get("web_search")
        if isinstance(web_search, str):
            if web_search.lower() in ("0", "false", "no"):
                web_search = False
            elif web_search.lower() in ("1", "true", "yes"):
                web_search = True
            else:
                web_search = None
        force_parallel = bool(body.get("force_parallel"))
        try:
            force_count = int(body.get("force_count") or body.get("count") or 0)
        except (TypeError, ValueError):
            force_count = 0
        run_search = body.get("run_search", True)
        if isinstance(run_search, str):
            run_search = run_search.lower() not in ("0", "false", "no")
        result = subagent_planner.plan_lanes(
            message,
            session_context=session_context,
            web_search_enabled=web_search,
            force_parallel=force_parallel,
            force_count=force_count,
            run_search=bool(run_search),
        )
        audit.log_event(
            "agents_auto_plan",
            {
                "need_parallel": result.get("need_parallel"),
                "lanes": len(result.get("lanes") or []),
                "source": result.get("source"),
                "needs_search": result.get("needs_search"),
            },
        )
        return _json(handler, 200, result)

    if path == "/api/agents/upsert":
        # Catalog upsert retired — return current built-in view
        return _json(handler, 200, agents.get_agents())

    if path == "/api/runtimes/active":
        body = _read_json(handler)
        try:
            result = runtimes.set_active_runtime(str(body.get("runtime") or "auto"))
            rt = str(body.get("runtime") or "auto")
            llm_sync = _sync_runtime_llm_safe(rt)
            return _json(handler, 200, {**result, "hermes_sync": llm_sync, "llm_sync": llm_sync})
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/runtimes/auto":
        body = _read_json(handler)
        try:
            prefer = str(body.get("runtime") or body.get("auto_runtime") or "")
            result = runtimes.set_auto_runtime(prefer)
            audit.log_event("runtime_auto", {"auto_runtime": result.get("auto_runtime")})
            return _json(handler, 200, result)
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/runtimes/connect":
        body = _read_json(handler)
        try:
            rt = str(body.get("runtime") or body.get("id") or "")
            result = runtimes.connect_runtime(rt)
            llm_sync = _sync_runtime_llm_safe(rt)
            audit.log_event("runtime_connect", {"runtime": rt})
            return _json(handler, 200, {**result, "llm_sync": llm_sync})
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/runtimes/disconnect":
        body = _read_json(handler)
        try:
            rt = str(body.get("runtime") or body.get("id") or "")
            result = runtimes.disconnect_runtime(rt or None)
            audit.log_event("runtime_disconnect", {"runtime": rt or result.get("linked")})
            return _json(handler, 200, result)
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/ecosystem/activate":
        body = _read_json(handler)
        try:
            active = body.get("active", True)
            if isinstance(active, str):
                active = active.lower() not in ("0", "false", "no")
            result = ecosystem.activate(str(body.get("id") or ""), active=bool(active))
            audit.log_event("ecosystem_activate", {"id": body.get("id"), "active": bool(active)})
            return _json(handler, 200, result)
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/mcp/enable":
        body = _read_json(handler)
        try:
            tid = str(body.get("id") or body.get("template") or "")
            overrides = body.get("overrides") if isinstance(body.get("overrides"), dict) else None
            result = mcp_hub.enable_template(tid, overrides=overrides)
            audit.log_event("mcp_enable", {"id": tid})
            return _json(handler, 200, result)
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/mcp/toggle":
        body = _read_json(handler)
        try:
            result = mcp_hub.set_enabled(str(body.get("id") or ""), bool(body.get("enabled", True)))
            return _json(handler, 200, result)
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/mcp/sync-hermes":
        try:
            result = mcp_hub.sync_to_hermes()
            audit.log_event("mcp_sync_hermes", {"servers": result.get("servers")})
            return _json(handler, 200, result)
        except Exception as exc:  # noqa: BLE001
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/runtimes/sync-llm":
        body = _read_json(handler)
        try:
            result = _sync_runtime_llm_safe(str(body.get("runtime") or body.get("id") or ""))
            audit.log_event(
                "runtime_sync_llm",
                {"runtime": result.get("runtime"), "ok": result.get("ok"), "provider": result.get("provider")},
            )
            if "error" not in result and not result.get("ok"):
                result = {
                    **result,
                    "error": result.get("error_zh") or result.get("error_en") or "sync failed",
                }
            return _json(handler, 200, result)
        except Exception as exc:  # noqa: BLE001
            return _json(
                handler,
                500,
                {
                    "ok": False,
                    "error": str(exc),
                    "error_zh": f"同步 LLM 失败：{exc}",
                    "error_en": f"Sync LLM failed: {exc}",
                },
            )

    if path == "/api/runtimes/optimize":
        body = _read_json(handler)
        try:
            result = runtimes.apply_optimize(str(body.get("runtime") or ""))
            audit.log_event("runtime_optimize", {"runtime": body.get("runtime")})
            return _json(handler, 200, result)
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/runtimes/install":
        body = _read_json(handler)
        try:
            result = runtimes.start_install(str(body.get("runtime") or ""))
            audit.log_event("runtime_install", {"runtime": body.get("runtime"), "job": (result.get("job") or {}).get("id")})
            return _json(handler, 200, result)
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/runtimes/upgrade":
        body = _read_json(handler)
        try:
            result = runtimes.start_upgrade(str(body.get("runtime") or ""))
            audit.log_event("runtime_upgrade", {"runtime": body.get("runtime"), "job": (result.get("job") or {}).get("id")})
            return _json(handler, 200, result)
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/ecosystem/install":
        body = _read_json(handler)
        try:
            result = ecosystem.start_install(str(body.get("id") or ""))
            audit.log_event("ecosystem_install", {"id": body.get("id")})
            return _json(handler, 200, result)
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/evolution/start":
        body = _read_json(handler)
        try:
            kind = str(body.get("kind") or body.get("target_kind") or "claw")
            tid = str(body.get("id") or body.get("target_id") or body.get("runtime") or "")
            focus = str(body.get("focus") or body.get("skill") or "")
            result = evolution.start_review(
                kind=kind,
                target_id=tid,
                focus=focus,
                auto_apply=bool(body.get("auto_apply")),
                mode=str(body.get("mode") or "auto"),
            )
            audit.log_event("evolution_start", {"kind": kind, "id": tid, "run_id": result.get("run_id")})
            return _json(handler, 200, result)
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            return _json(handler, 500, {"error": str(exc)})

    if path == "/api/evolution/apply":
        body = _read_json(handler)
        try:
            indices = body.get("indices")
            if indices is not None and not isinstance(indices, list):
                raise ValueError("indices must be a list of ints")
            idx_list = [int(x) for x in indices] if isinstance(indices, list) else None
            result = evolution.apply_proposals(
                str(body.get("run_id") or body.get("id") or ""),
                indices=idx_list,
                confirm=bool(body.get("confirm")),
            )
            return _json(handler, 200, result)
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})
        except FileNotFoundError:
            return _json(handler, 404, {"error": "run not found"})

    if path == "/api/evolution/rollback":
        body = _read_json(handler)
        try:
            result = evolution.rollback_run(str(body.get("run_id") or body.get("id") or ""))
            return _json(handler, 200, result)
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})
        except FileNotFoundError:
            return _json(handler, 404, {"error": "run not found"})

    if path == "/api/ecosystem/activate":
        body = _read_json(handler)
        try:
            result = ecosystem.activate(
                str(body.get("id") or ""),
                active=bool(body.get("active", True)),
            )
            audit.log_event("ecosystem_activate", {"id": body.get("id"), "active": body.get("active", True)})
            return _json(handler, 200, result)
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/mcp/enable":
        body = _read_json(handler)
        try:
            result = mcp_hub.enable_template(
                str(body.get("id") or body.get("template") or ""),
                overrides=body.get("overrides") if isinstance(body.get("overrides"), dict) else None,
            )
            try:
                mcp_hub.sync_to_hermes()
            except Exception:  # noqa: BLE001
                pass
            audit.log_event("mcp_enable", {"id": body.get("id")})
            return _json(handler, 200, result)
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/mcp/toggle":
        body = _read_json(handler)
        try:
            result = mcp_hub.set_enabled(
                str(body.get("id") or ""),
                bool(body.get("enabled", True)),
            )
            try:
                mcp_hub.sync_to_hermes()
            except Exception:  # noqa: BLE001
                pass
            return _json(handler, 200, result)
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/mcp/upsert":
        body = _read_json(handler)
        try:
            entry = body.get("entry") if isinstance(body.get("entry"), dict) else body
            if "command" not in entry and "url" not in entry:
                entry = {k: body[k] for k in ("command", "args", "env", "url", "headers") if k in body}
            result = mcp_hub.upsert_server(
                str(body.get("id") or ""),
                entry if isinstance(entry, dict) else {},
                enable=bool(body.get("enable", True)),
            )
            try:
                mcp_hub.sync_to_hermes()
            except Exception:  # noqa: BLE001
                pass
            return _json(handler, 200, result)
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/mcp/sync-hermes":
        try:
            result = mcp_hub.sync_to_hermes()
            return _json(handler, 200, result)
        except Exception as exc:  # noqa: BLE001
            return _json(handler, 400, {"ok": False, "error": str(exc)})

    if path == "/api/skills/hub/install":
        body = _read_json(handler)
        try:
            result = skills_hub.start_install_pack(str(body.get("id") or ""))
            audit.log_event("skill_hub_install", {"id": body.get("id")})
            return _json(handler, 200, result)
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/skills/suggest":
        body = _read_json(handler)
        return _json(handler, 200, skills.suggest_skills(str(body.get("message") or body.get("q") or "")))

    if path == "/api/skills/hub-loaded":
        body = _read_json(handler)
        action = str(body.get("action") or "").strip().lower()
        sid = str(body.get("id") or body.get("skill_id") or "").strip()
        try:
            if action == "load" or body.get("load"):
                return _json(handler, 200, skills.load_skill_to_hub(sid))
            if action == "unload" or body.get("unload"):
                return _json(handler, 200, skills.unload_skill_from_hub(sid))
            if "hub_loaded_skills" in body or "skills" in body:
                ids = body.get("hub_loaded_skills")
                if ids is None:
                    ids = body.get("skills")
                return _json(handler, 200, skills.set_hub_loaded(list(ids or [])))
            return _json(handler, 400, {"error": "action must be load|unload, or pass hub_loaded_skills"})
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/search":
        body = _read_json(handler)
        q = str(body.get("query") or body.get("q") or body.get("message") or "")
        try:
            limit = int(body.get("limit") or 8)
        except (TypeError, ValueError):
            limit = 8
        deep = body.get("deep")
        if deep is None:
            deep = True
        if deep:
            return _json(handler, 200, websearch.deep_search(q, limit=max(1, min(limit, 16))))
        structured = websearch.search_structured(q, limit=max(1, min(limit, 16)), deep=False)
        return _json(handler, 200, {
            **structured,
            "results": structured.get("sources") or [],
            "offline": not bool(structured.get("ok")),
        })

    if path == "/api/search/keys":
        body = _read_json(handler)
        from .secrets import set_api_key

        out: dict = {"ok": True, "saved": []}
        cse = str(body.get("google_cse_key") or body.get("google_cse") or "").strip()
        serp = str(body.get("serpapi_key") or body.get("serpapi") or "").strip()
        if cse or body.get("clear_google_cse"):
            set_api_key("google_cse", "" if body.get("clear_google_cse") else cse)
            out["saved"].append("google_cse")
        if serp or body.get("clear_serpapi"):
            set_api_key("serpapi", "" if body.get("clear_serpapi") else serp)
            out["saved"].append("serpapi")
        # Persist non-secret search config
        cfg = load_campus_config()
        search_cfg = dict(cfg.get("search") or {})
        if "google_cse_cx" in body:
            search_cfg["google_cse_cx"] = str(body.get("google_cse_cx") or "").strip()
        if "proxy" in body:
            search_cfg["proxy"] = str(body.get("proxy") or "").strip()
        if "provider" in body:
            search_cfg["provider"] = str(body.get("provider") or "auto").strip() or "auto"
        if "deep" in body:
            search_cfg["deep"] = bool(body.get("deep"))
        if "enabled" in body:
            search_cfg["enabled"] = bool(body.get("enabled"))
        if "verify_tls" in body:
            search_cfg["verify_tls"] = bool(body.get("verify_tls"))
        cfg["search"] = search_cfg
        save_campus_config(cfg)
        out.update(public_settings_view())
        return _json(handler, 200, out)

    if path == "/api/search/fill":
        body = _read_json(handler)
        q = str(body.get("query") or body.get("q") or "")
        fields = body.get("fields") or []
        if not isinstance(fields, list):
            fields = []
        try:
            limit = int(body.get("limit") or 6)
        except (TypeError, ValueError):
            limit = 6
        return _json(handler, 200, websearch.fill_form_from_search(q, fields, limit=max(1, min(limit, 12))))

    if path == "/api/excel/fill":
        body = _read_json(handler)
        sid = str(body.get("session_id") or "")
        message = str(body.get("message") or body.get("query") or "")
        prefer = body.get("prefer_names") or body.get("prefer") or []
        if not isinstance(prefer, list):
            prefer = [str(prefer)] if prefer else []
        try:
            max_rows = int(body.get("max_rows") or 40)
        except (TypeError, ValueError):
            max_rows = 40
        if not sid:
            return _json(handler, 400, {"ok": False, "error": "session_id required"})
        result = excel_fill.run_excel_web_fill(
            sid,
            message,
            max_rows=max(1, min(max_rows, 80)),
            prefer_names=[str(n) for n in prefer if str(n).strip()],
        )
        return _json(handler, 200 if result.get("ok") else 400, result)

    if path == "/api/digests/nightly":
        return _json(handler, 200, digest.run_nightly())

    if path == "/api/digests/morning":
        return _json(handler, 200, digest.run_morning())

    if path == "/api/maintenance/status":
        return _json(handler, 200, nightly_maintenance.status())

    if path == "/api/workspace/verify":
        from . import grounding

        body = _read_json(handler)
        ws = str(body.get("workspace") or "")
        snap = grounding.snapshot_workspace(ws, session_id=str(body.get("session_id") or ""))
        result = grounding.verify_response_paths(str(body.get("text") or ""), snap)
        return _json(handler, 200, {**result, "snapshot_count": snap.get("entry_count")})

    _json(handler, 404, {"error": "not found"})


def handle_patch(handler) -> None:
    path, parts, _qs = _path_parts(handler.path)
    if requires_auth(path) and not auth.is_authenticated(handler):
        return _json(handler, 401, {"error": "unauthorized"})

    if len(parts) == 3 and parts[0] == "api" and parts[1] == "sessions":
        body = _read_json(handler)
        s = store.update_session(
            parts[2],
            title=body.get("title"),
            model=body.get("model"),
            pinned=body.get("pinned"),
            archived=body.get("archived"),
            folder_id=body.get("folder_id"),
        )
        if s is None:
            return _json(handler, 404, {"error": "not found"})
        return _json(handler, 200, s.to_dict())

    if len(parts) == 3 and parts[0] == "api" and parts[1] == "folders":
        body = _read_json(handler)
        try:
            archived = _optional_bool(body.get("archived"))
            pinned = _optional_bool(body.get("pinned"))
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})
        item = folders.update_folder(
            parts[2],
            name=body.get("name"),
            sort_order=body.get("sort_order"),
            archived=archived,
            pinned=pinned,
        )
        if item is not None and archived is not None:
            for session in store.list_sessions(include_archived=True):
                if session.get("folder_id") == parts[2]:
                    store.update_session(session["id"], archived=archived)
        return _json(handler, 200 if item else 404, item or {"error": "not found"})

    _json(handler, 404, {"error": "not found"})


def handle_delete(handler) -> None:
    path, parts, qs = _path_parts(handler.path)
    if requires_auth(path) and not auth.is_authenticated(handler):
        return _json(handler, 401, {"error": "unauthorized"})

    if path == "/api/ui/logo":
        try:
            slot = (qs.get("slot") or ["both"])[0]
            result = brand_logo.reset_logos(slot)
            audit.log_event("ui_logo_reset", {"slot": slot})
            return _json(handler, 200, result)
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})

    if len(parts) == 3 and parts[0] == "api" and parts[1] == "sessions":
        ok = store.delete_session(parts[2])
        return _json(handler, 200 if ok else 404, {"ok": ok})

    if len(parts) == 3 and parts[0] == "api" and parts[1] == "folders":
        folder_id = parts[2]
        for item in store.list_sessions(include_archived=True):
            if item.get("folder_id") == folder_id:
                store.update_session(item["id"], folder_id="")
        ok = folders.delete_folder(folder_id)
        return _json(handler, 200 if ok else 404, {"ok": ok})

    if len(parts) == 3 and parts[0] == "api" and parts[1] == "soul" and parts[2] == "roles":
        # DELETE /api/soul/roles?id=
        return _json(handler, 400, {"error": "use DELETE /api/soul/roles/<id>"})

    if len(parts) == 4 and parts[0] == "api" and parts[1] == "soul" and parts[2] == "roles":
        try:
            return _json(handler, 200, soul.delete_role(parts[3]))
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})

    if len(parts) == 3 and parts[0] == "api" and parts[1] == "schedule":
        try:
            return _json(handler, 200, schedule.delete_task(parts[2]))
        except Exception as exc:  # noqa: BLE001
            return _json(handler, 400, {"error": str(exc)})

    if len(parts) == 3 and parts[0] == "api" and parts[1] == "skills":
        sid = parts[2]
        try:
            # Delete by skill id across all roots (handles nested + duplicates)
            result = skills.uninstall_skill(sid)
            try:
                skills_hub.uninstall_pack(sid)
            except FileNotFoundError:
                pass
            return _json(handler, 200, result)
        except FileNotFoundError:
            return _json(handler, 404, {"error": f"skill not found: {sid}"})
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            return _json(handler, 400, {"error": str(exc)})

    _json(handler, 404, {"error": "not found"})


def _serve_file(handler, filepath: Path, root: Path | None = None) -> None:
    try:
        filepath = filepath.resolve()
        static_root = (root or STATIC_DIR).resolve()
        if not str(filepath).startswith(str(static_root)) or not filepath.is_file():
            return _json(handler, 404, {"error": "not found"})
        data = filepath.read_bytes()
    except OSError:
        return _json(handler, 404, {"error": "not found"})

    ctype, _ = mimetypes.guess_type(str(filepath))
    if filepath.suffix == ".js":
        ctype = "application/javascript; charset=utf-8"
    elif filepath.suffix == ".css":
        ctype = "text/css; charset=utf-8"
    elif filepath.suffix == ".html":
        ctype = "text/html; charset=utf-8"
    elif filepath.suffix == ".json":
        ctype = "application/json; charset=utf-8"
    else:
        ctype = ctype or "application/octet-stream"

    handler.send_response(200)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-cache")
    handler.end_headers()
    handler.wfile.write(data)


def _sse_stream(handler, stream_id: str, *, from_seq: int = 0) -> None:
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "keep-alive")
    handler.send_header("X-Accel-Buffering", "no")
    handler.end_headers()
    try:
        for chunk in streaming.iter_sse(stream_id, from_seq=from_seq):
            handler.wfile.write(chunk.encode("utf-8"))
            handler.wfile.flush()
    except (BrokenPipeError, ConnectionResetError):
        return
