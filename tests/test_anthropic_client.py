"""Anthropic Messages API client (MiniMax …/anthropic and other compatible gateways)."""

from __future__ import annotations

import contextlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


class _Messages(BaseHTTPRequestHandler):
    mode = "stream"
    last: dict = {}

    def log_message(self, *a):
        pass

    def do_GET(self):
        body = json.dumps({"data": [{"id": "MiniMax-M2", "type": "model"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        type(self).last = {"path": self.path, "body": req, "x-api-key": self.headers.get("x-api-key"),
                           "version": self.headers.get("anthropic-version")}
        if self.mode == "error":
            body = json.dumps({"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}}).encode()
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if not req.get("stream"):
            body = json.dumps({"type": "message", "content": [{"type": "thinking", "thinking": "hmm"},
                                                              {"type": "text", "text": "plain answer"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        events = [
            {"type": "message_start", "message": {"id": "m1"}},
            {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking"}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "secret reasoning"}},
            {"type": "content_block_start", "index": 1, "content_block": {"type": "text"}},
            {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "Hello "}},
            {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "from MiniMax"}},
        ]
        if self.mode != "cut":
            events += [{"type": "message_delta", "delta": {"stop_reason": "end_turn"}}, {"type": "message_stop"}]
        for e in events:
            self.wfile.write(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n".encode())
        self.wfile.flush()
        self.close_connection = True


@contextlib.contextmanager
def _server(mode="stream"):
    _Messages.mode = mode
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Messages)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}/anthropic"
    finally:
        srv.shutdown()


def test_anthropic_bases_are_detected():
    from ali.anthropic_client import is_anthropic_base, messages_url

    assert is_anthropic_base("https://api.minimax.cn/anthropic")
    assert is_anthropic_base("https://api.minimaxi.com/anthropic/")
    assert not is_anthropic_base("https://api.minimaxi.com/v1")
    assert messages_url("https://api.minimax.cn/anthropic") == "https://api.minimax.cn/anthropic/v1/messages"
    assert messages_url("https://api.minimax.cn/anthropic/v1/messages") == "https://api.minimax.cn/anthropic/v1/messages"


def test_openai_style_history_becomes_system_plus_alternating_turns():
    from ali.anthropic_client import to_anthropic

    system, turns = to_anthropic([
        {"role": "system", "content": "rules"}, {"role": "system", "content": "sources"},
        {"role": "assistant", "content": "earlier"}, {"role": "user", "content": "a"}, {"role": "user", "content": "b"},
    ])
    assert system == "rules\n\nsources"
    assert [t["role"] for t in turns] == ["user", "assistant", "user"] and turns[-1]["content"] == "a\n\nb"


def test_stream_chat_routes_to_messages_api_and_hides_thinking():
    from ali import llm_client

    tokens: list[str] = []
    with _server() as base:
        meta: dict = {}
        text = llm_client.stream_chat(base, "sk-cp-test", model="MiniMax-M2",
                                      messages=[{"role": "system", "content": "be brief"}, {"role": "user", "content": "hi"}],
                                      on_token=tokens.append, meta=meta)
        sent = _Messages.last
    assert text == "Hello from MiniMax" and "secret" not in "".join(tokens)
    assert sent["path"] == "/anthropic/v1/messages" and sent["x-api-key"] == "sk-cp-test" and sent["version"]
    assert sent["body"]["system"] == "be brief" and sent["body"]["max_tokens"] > 0
    assert not meta.get("truncated")


def test_cut_stream_is_flagged_and_errors_are_clear():
    from ali import llm_client

    with _server("cut") as base:
        meta: dict = {}
        llm_client.stream_chat(base, "k", model="m", messages=[{"role": "user", "content": "hi"}], meta=meta)
        assert meta.get("truncated") is True
    with _server("error") as base:
        with pytest.raises(RuntimeError, match="401"):
            llm_client.stream_chat(base, "k", model="m", messages=[{"role": "user", "content": "hi"}], sleep=lambda s: None)


def test_non_stream_and_model_list():
    from ali import llm_client

    with _server() as base:
        assert llm_client._chat_once(base, "k", model="m", messages=[{"role": "user", "content": "hi"}]) == "plain answer"
        listed = llm_client.list_models(base, "k")
    assert listed["ok"] and listed["models"] == ["MiniMax-M2"]
