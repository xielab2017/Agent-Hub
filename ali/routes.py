"""HTTP route handlers for Hermes-ALI."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import audit, auth, obsidian, routing, sessions as store, streaming, workflows
from .config import REPO_ROOT, RUNTIME, STATIC_DIR, VERSION, local_ips
from .settings import import_campus_config, load_campus_config, public_settings_view, save_campus_config


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
    if path.endswith((".css", ".js", ".svg", ".png", ".ico", ".woff2", ".json")):
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

    if path.startswith("/assets/"):
        return _serve_file(handler, REPO_ROOT / "assets" / path[len("/assets/") :], root=REPO_ROOT / "assets")

    if path in ("/health", "/api/health"):
        return _json(handler, 200, {"ok": True, "version": VERSION})

    if path == "/api/status":
        st = streaming.agent_status()
        health = workflows.health_snapshot()
        ali = load_campus_config().get("ali") or {}
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
                "agent": st,
                "health": health,
                "default_route": ali.get("default_route") or "auto",
                "ui": {
                    "language": ali.get("language") or "zh",
                    "theme": ali.get("theme") or "dark",
                    "accent": ali.get("accent") or "ocean",
                },
            },
        )

    if path == "/api/settings":
        return _json(handler, 200, public_settings_view())

    if path == "/api/providers":
        from .providers import catalog_payload

        return _json(handler, 200, catalog_payload())

    if path == "/api/routing":
        return _json(handler, 200, {"matrix": routing.routing_matrix(), "tiers": routing.TIERS})

    if path == "/api/workflows":
        return _json(handler, 200, {"presets": workflows.list_presets()})

    if path == "/api/health/office":
        return _json(handler, 200, workflows.health_snapshot())

    if path == "/api/audit":
        limit = int((qs.get("limit") or ["50"])[0])
        return _json(handler, 200, {"events": audit.recent(limit)})

    if path == "/api/obsidian":
        return _json(handler, 200, obsidian.vault_status())

    if path == "/api/obsidian/notes":
        limit = int((qs.get("limit") or ["40"])[0])
        root = (qs.get("root") or [""])[0]
        return _json(handler, 200, obsidian.list_notes(limit=limit, root_filter=root))

    if len(parts) == 4 and parts[0] == "api" and parts[1] == "obsidian" and parts[2] == "note":
        # /api/obsidian/note?path=
        rel = (qs.get("path") or [""])[0]
        return _json(handler, 200, obsidian.read_note(rel))

    if path == "/api/sessions":
        return _json(handler, 200, {"sessions": store.list_sessions()})

    if len(parts) == 3 and parts[0] == "api" and parts[1] == "sessions":
        session = store.get_session(parts[2])
        if session is None:
            return _json(handler, 404, {"error": "not found"})
        return _json(handler, 200, session.to_dict())

    if len(parts) == 3 and parts[0] == "api" and parts[1] == "stream":
        return _sse_stream(handler, parts[2])

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
        saved = save_campus_config(cfg)
        audit.log_event("settings_save", {"keys": list(saved.keys())})
        view = public_settings_view()
        if saved.get("_warning"):
            view["warning"] = saved["_warning"]
        return _json(handler, 200, {"ok": True, "config": {k: v for k, v in saved.items() if not str(k).startswith("_")}, **view})

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
            view = public_settings_view()
            if saved.get("_warning"):
                view["warning"] = saved["_warning"]
            audit.log_event("apply_provider", {"provider": provider_id, "hybrid_preset": hybrid_preset or None})
            return _json(handler, 200, {"ok": True, **view})
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})

    if path == "/api/settings/api-key":
        body = _read_json(handler)
        from .secrets import set_api_key
        from .providers import looks_like_secret

        raw_key = str(body.get("api_key") or body.get("key") or "").strip()
        provider = str(body.get("provider") or (load_campus_config().get("backend") or {}).get("type") or "default").strip()
        env_name = str(body.get("api_key_env") or (load_campus_config().get("backend") or {}).get("api_key_env") or "").strip()

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

        # Save under provider id and env name slot
        info = set_api_key(provider, raw_key)
        if env_name and not looks_like_secret(env_name):
            set_api_key(env_name, raw_key)
            # persist correct env name in config
            cfg = load_campus_config()
            cfg.setdefault("backend", {})["api_key_env"] = env_name
            save_campus_config(cfg)
        elif provider:
            from .providers import get_provider

            prov = get_provider(provider)
            if prov and prov.get("api_key_env"):
                cfg = load_campus_config()
                cfg.setdefault("backend", {})["api_key_env"] = prov["api_key_env"]
                if provider != "hybrid":
                    cfg["backend"]["type"] = provider
                save_campus_config(cfg)
                set_api_key(str(prov["api_key_env"]), raw_key)

        audit.log_event("api_key_save", {"provider": provider, "present": True})
        view = public_settings_view()
        view["api_key_saved"] = {"provider": provider, "masked": info.get("masked")}
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
            verify_tls=bool((cfg.get("backend") or {}).get("verify_tls", True)),
        )
        if not result.get("ok"):
            return _json(handler, 400, {"error": result.get("error") or "list models failed", **result})

        models = result.get("models") or []
        suggested = llm_client.suggest_slots(models)
        apply_suggest = body.get("apply_suggestions", True)
        if apply_suggest and suggested:
            m = dict(cfg.get("models") or {})
            m.update({k: v for k, v in suggested.items() if v})
            cfg["models"] = m
            cfg = save_campus_config(cfg)

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
                **view,
            },
        )

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
        s = store.create_session(title=str(body.get("title") or "New chat"), model=str(body.get("model") or ""))
        return _json(handler, 201, s.to_dict())

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
            )
            return _json(handler, 200, result)
        except ValueError as exc:
            return _json(handler, 400, {"error": str(exc)})

    if len(parts) == 4 and parts[0] == "api" and parts[1] == "sessions" and parts[3] == "cancel":
        ok = streaming.cancel_stream(parts[2])
        return _json(handler, 200, {"ok": ok})

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
        )
        if s is None:
            return _json(handler, 404, {"error": "not found"})
        return _json(handler, 200, s.to_dict())

    _json(handler, 404, {"error": "not found"})


def handle_delete(handler) -> None:
    path, parts, _qs = _path_parts(handler.path)
    if requires_auth(path) and not auth.is_authenticated(handler):
        return _json(handler, 401, {"error": "unauthorized"})

    if len(parts) == 3 and parts[0] == "api" and parts[1] == "sessions":
        ok = store.delete_session(parts[2])
        return _json(handler, 200 if ok else 404, {"ok": ok})

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


def _sse_stream(handler, stream_id: str) -> None:
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "keep-alive")
    handler.send_header("X-Accel-Buffering", "no")
    handler.end_headers()
    try:
        for chunk in streaming.iter_sse(stream_id):
            handler.wfile.write(chunk.encode("utf-8"))
            handler.wfile.flush()
    except (BrokenPipeError, ConnectionResetError):
        return
