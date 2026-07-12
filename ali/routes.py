"""HTTP route handlers for Hermes-ALI."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import auth, sessions as store, streaming
from .config import STATIC_DIR, VERSION, local_ips, RUNTIME


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
    # Allow CSS/JS at root of static served paths
    if path.endswith((".css", ".js", ".svg", ".png", ".ico", ".woff2")):
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
        rel = path[len("/static/") :]
        return _serve_file(handler, STATIC_DIR / rel)

    # Convenience: /app.js /style.css
    if path in ("/app.js", "/style.css"):
        return _serve_file(handler, STATIC_DIR / path.lstrip("/"))

    if path in ("/health", "/api/health"):
        return _json(handler, 200, {"ok": True, "version": VERSION})

    if path == "/api/status":
        st = streaming.agent_status()
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
            },
        )

    if path == "/api/sessions":
        return _json(handler, 200, {"sessions": store.list_sessions()})

    if len(parts) == 2 and parts[0] == "api" and parts[1] == "sessions":
        return _json(handler, 200, {"sessions": store.list_sessions()})

    if len(parts) == 3 and parts[0] == "api" and parts[1] == "sessions":
        session = store.get_session(parts[2])
        if session is None:
            return _json(handler, 404, {"error": "not found"})
        return _json(handler, 200, session.to_dict())

    if len(parts) == 3 and parts[0] == "api" and parts[1] == "stream":
        stream_id = parts[2]
        return _sse_stream(handler, stream_id)

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


def _serve_file(handler, filepath: Path) -> None:
    try:
        filepath = filepath.resolve()
        static_root = STATIC_DIR.resolve()
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
