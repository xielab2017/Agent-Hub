#!/usr/bin/env python3
"""A tiny OpenAI-compatible model for offline rehearsal of the skill demo (no network, no key).

    python scripts/stub_llm.py --port 9911

``/v1/models`` lists ``stub-model``; ``/v1/chat/completions`` streams a canned SKILL.md for skill-authoring
prompts and a short reply otherwise.  Rehearsal only — the real demo uses the configured MiniMax model.
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SKILL_MD = """---
name: literature-review
description: Evidence-grounded critical review (stub rehearsal text).
triggers: literature review, 综述
entry: run.py
---

# Literature review (rehearsal)

## When to use
Rehearsal of the skill demo with a stub model.

## Steps
1. Plan the profile. 2. Search PubMed. 3. Screen. 4. Draft. 5. Review. 6. Revise. 7. Audit. 8. Word.
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path.rstrip("/").endswith("/models"):
            return self._send(200, json.dumps({"data": [{"id": "stub-model", "object": "model"}]}).encode())
        self._send(404, b"{}")

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        req = json.loads(self.rfile.read(n) or b"{}")
        text = json.dumps(req.get("messages") or [])
        reply = SKILL_MD if "SKILL.md" in text else "Stub reply."
        if not req.get("stream"):
            return self._send(200, json.dumps({"choices": [{"message": {"role": "assistant", "content": reply},
                                                            "finish_reason": "stop"}]}).encode())
        chunks = [reply[i:i + 200] for i in range(0, len(reply), 200)]
        body = "".join(f"data: {json.dumps({'choices': [{'delta': {'content': c}}]})}\n\n" for c in chunks)
        body += f"data: {json.dumps({'choices': [{'delta': {}, 'finish_reason': 'stop'}]})}\n\ndata: [DONE]\n\n"
        self._send(200, body.encode(), "text/event-stream")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9911)
    a = ap.parse_args()
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
