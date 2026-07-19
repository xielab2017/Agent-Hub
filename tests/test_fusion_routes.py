from __future__ import annotations

import io
import importlib
import json
import sys
from types import SimpleNamespace

from ali import routes


class _Handler:
    def __init__(self, path: str, payload: dict):
        raw = json.dumps(payload).encode()
        self.path = path
        self.headers = {"Content-Length": str(len(raw))}
        self.rfile = io.BytesIO(raw)
        self.wfile = io.BytesIO()
        self.status = None

    def send_response(self, status):
        self.status = status

    def send_header(self, *_args):
        pass

    def end_headers(self):
        pass

    def json(self):
        return json.loads(self.wfile.getvalue())


def test_auto_locale_prefers_proxy_country_without_exposing_ip():
    headers = {
        "CF-IPCountry": "CN",
        "CF-Connecting-IP": "203.0.113.42",
        "Accept-Language": "en-US,en;q=0.9",
    }
    hint = routes._resolve_locale_hint("auto", headers, server_country="US")
    assert hint == {"mode": "auto", "resolved": "zh", "source": "proxy_country", "country": "CN"}
    assert "203.0.113.42" not in json.dumps(hint)


def test_auto_locale_uses_cached_server_country_then_accept_language():
    assert routes._resolve_locale_hint(
        "auto", {"Accept-Language": "zh-CN,zh;q=0.9"}, server_country="DE"
    ) == {"mode": "auto", "resolved": "en", "source": "server_country", "country": "DE"}
    assert routes._resolve_locale_hint(
        "auto", {"Accept-Language": "zh-CN,zh;q=0.9"}, server_country=""
    )["resolved"] == "zh"


def test_explicit_locale_preserves_legacy_choice():
    hint = routes._resolve_locale_hint("en", {"CF-IPCountry": "CN"}, server_country="CN")
    assert hint == {"mode": "en", "resolved": "en", "source": "setting", "country": ""}


def test_status_exposes_resolved_locale_hint(monkeypatch):
    monkeypatch.setattr(routes.streaming, "agent_status", lambda: {})
    monkeypatch.setattr(routes.workflows, "health_snapshot", lambda: {})
    monkeypatch.setattr(routes, "load_campus_config", lambda: {"ali": {"language": "auto"}, "models": {}})
    monkeypatch.setattr(routes, "public_ip", lambda: "")
    monkeypatch.setattr(routes, "local_ips", lambda: [])
    monkeypatch.setattr(routes, "_cached_server_country_hint", lambda: "")
    monkeypatch.setattr(routes.auth, "auth_required", lambda: False)
    monkeypatch.setattr(routes.auth, "is_authenticated", lambda _handler: True)
    monkeypatch.setattr(routes.brand_logo, "public_logo_state", lambda _cfg=None: {})
    handler = _Handler("/api/status", {})
    handler.headers["Accept-Language"] = "zh-CN,zh;q=0.9"

    routes.handle_get(handler)

    assert handler.status == 200
    assert handler.json()["locale_hint"] == {
        "mode": "auto",
        "resolved": "zh",
        "source": "accept_language",
        "country": "",
    }


def test_fusion_plan_route_wires_keyword_signature(monkeypatch):
    calls = []

    def build_plan(prompt, task_type, fusion_mode, thinking_depth, config):
        calls.append((prompt, task_type, fusion_mode, thinking_depth, config))
        return {"enabled": True, "mode": fusion_mode, "lanes": []}

    monkeypatch.setitem(sys.modules, "ali.fusion", SimpleNamespace(build_plan=build_plan))
    monkeypatch.setattr(routes, "load_campus_config", lambda: {"fusion_mode": "auto"})
    handler = _Handler("/api/fusion/plan", {
        "prompt": "compare models",
        "task_type": "C3",
        "fusion_mode": "deep",
        "thinking_depth": "high",
    })

    routes.handle_post(handler)

    assert handler.status == 200
    assert handler.json()["mode"] == "deep"
    assert calls[0][:4] == ("compare models", "C3", "deep", "high")


def test_fusion_plan_route_supports_request_adapter(monkeypatch):
    def build_plan(request, cfg):
        return {"enabled": False, "mode": request["fusion_mode"], "configured": bool(cfg)}

    monkeypatch.setitem(sys.modules, "ali.fusion", SimpleNamespace(build_plan=build_plan))
    monkeypatch.setattr(routes, "load_campus_config", lambda: {"fusion_mode": "fast"})
    handler = _Handler("/api/fusion/plan", {"prompt": "hello", "fusion_mode": "fast"})

    routes.handle_post(handler)

    assert handler.status == 200
    assert handler.json() == {"enabled": False, "mode": "fast", "configured": True}


def test_fusion_plan_route_validates_before_import():
    handler = _Handler("/api/fusion/plan", {"prompt": "", "fusion_mode": "auto"})
    routes.handle_post(handler)
    assert handler.status == 400
    assert handler.json()["error"] == "prompt required"


def test_fusion_plan_route_reports_missing_module(monkeypatch):
    real_import = routes.importlib.import_module

    def missing(name):
        if name == "ali.fusion":
            raise ImportError("fusion module not installed")
        return real_import(name)

    monkeypatch.setattr(routes.importlib, "import_module", missing)
    handler = _Handler("/api/fusion/plan", {"prompt": "hello"})

    routes.handle_post(handler)

    assert handler.status == 503
    assert handler.json()["available"] is False


def test_fusion_plan_adapter_uses_real_compatibility_alias(monkeypatch):
    import ali

    monkeypatch.delitem(sys.modules, "ali.fusion", raising=False)
    monkeypatch.delattr(ali, "fusion", raising=False)
    real_fusion = importlib.import_module("ali.fusion")
    monkeypatch.setattr(routes.importlib, "import_module", lambda name: real_fusion if name == "ali.fusion" else importlib.import_module(name))
    monkeypatch.setattr(routes, "load_campus_config", lambda: {
        "fusion_mode": "deep",
        "fusion_token_budget": {"total_budget": 5000},
        "fusion_judge_model": "configured-judge",
        "model_profiles": {
            "primary": {
                "model": "primary",
                "provider": "offline",
                "healthy": True,
                "recommended_categories": ["C3"],
            },
            "second": {
                "model": "second",
                "provider": "offline",
                "healthy": True,
                "recommended_categories": ["C3"],
            },
        },
    })

    plan = routes._build_fusion_plan({"prompt": "研究并比较两个复杂方案"})

    assert plan["mode"] == "deep"
    assert plan["budget"]["total_budget"] == 5000
    assert plan["judge"]["model"] == "configured-judge"
    assert plan["judge"]["source"] == "configured"


def test_chat_route_forwards_fusion_token_budget(monkeypatch):
    captured = {}

    def fake_start_chat(**kwargs):
        captured.update(kwargs)
        return {"stream_id": "stream-test", "route": {"max_tokens": 2048}}

    monkeypatch.setattr(routes.streaming, "start_chat", fake_start_chat)
    handler = _Handler("/api/sessions/session-1/chat", {
        "message": "analyze",
        "max_tokens_override": 2048,
    })

    routes.handle_post(handler)

    assert handler.status == 200
    assert captured["max_tokens_override"] == 2048


def test_folder_pin_route_accepts_false_string_without_repinning(monkeypatch):
    captured = {}

    def fake_update(folder_id, **kwargs):
        captured["folder_id"] = folder_id
        captured.update(kwargs)
        return {"id": folder_id, "pinned": kwargs["pinned"]}

    monkeypatch.setattr(routes.folders, "update_folder", fake_update)
    handler = _Handler("/api/folders/folder-1", {"pinned": "false"})

    routes.handle_patch(handler)

    assert handler.status == 200
    assert captured == {"folder_id": "folder-1", "name": None, "sort_order": None, "archived": None, "pinned": False}
