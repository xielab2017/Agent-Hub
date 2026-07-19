#!/usr/bin/env python3
"""Hermes-ALI server — lightweight cross-platform Hermes Agent terminal."""

from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Ensure repo root is importable when run as script
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ali import auth, routes  # noqa: E402
from ali.config import (  # noqa: E402
    APP_NAME,
    DEFAULT_HOST,
    DEFAULT_PORT,
    RUNTIME,
    VERSION,
    ensure_state_dirs,
    local_ips,
)
from ali.streaming import agent_status  # noqa: E402
from ali.digest import start_scheduler  # noqa: E402
from ali.home import ensure_home  # noqa: E402


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_GET(self) -> None:
        routes.handle_get(self)

    def do_POST(self) -> None:
        routes.handle_post(self)

    def do_PATCH(self) -> None:
        routes.handle_patch(self)

    def do_DELETE(self) -> None:
        routes.handle_delete(self)


def print_banner(host: str, port: int) -> None:
    ips = local_ips()
    status = agent_status()
    print()
    print(f"  {APP_NAME} v{VERSION}")
    print("  " + "─" * 42)
    print(f"  Local:   http://127.0.0.1:{port}")
    if host in ("0.0.0.0", "::"):
        if ips:
            for ip in ips:
                print(f"  LAN:     http://{ip}:{port}")
        else:
            print(f"  LAN:     http://<your-ip>:{port}")
    else:
        print(f"  Bind:    http://{host}:{port}")
    if auth.auth_required():
        print("  Auth:    password required (HERMES_ALI_PASSWORD)")
    else:
        print("  Auth:    off  (set HERMES_ALI_PASSWORD to protect remote access)")
    if status.get("available") or (status.get("hermes_cli") or {}).get("available"):
        engine = status.get("chat_engine") or "hermes"
        print(f"  Agent:   ready ({engine}) · {status.get('agent_dir') or (status.get('hermes_cli') or {}).get('bin')}")
        if status.get("import_error") and engine == "hermes-cli":
            print("  Note:    in-process import failed; using Hermes CLI (venv)")
    else:
        print("  Agent:   demo mode — install Hermes Agent for full power")
    print("  " + "─" * 42)
    print("  Open any of the URLs above from phone / other PCs.")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} — lightweight Hermes terminal")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bind host (default 0.0.0.0 for LAN access)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Bind port (default 8765)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser")
    parser.add_argument("--open", action="store_true", help="Force-open browser")
    args = parser.parse_args(argv)

    ensure_state_dirs()
    ensure_home()
    try:
        from ali.ecosystem import ensure_auto_activated

        ensure_auto_activated()
    except Exception:  # noqa: BLE001
        pass
    start_scheduler()
    try:
        from ali.model_intelligence import start_startup_governance_refresh

        start_startup_governance_refresh()
    except Exception:  # noqa: BLE001
        pass
    RUNTIME["host"] = args.host
    RUNTIME["port"] = args.port
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print_banner(args.host, args.port)

    open_browser = args.open or (not args.no_browser and sys.stdin.isatty())
    if open_browser:
        url = f"http://127.0.0.1:{args.port}"

        def _open() -> None:
            try:
                webbrowser.open(url)
            except Exception:  # noqa: BLE001
                pass

        threading.Timer(0.6, _open).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down…")
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
