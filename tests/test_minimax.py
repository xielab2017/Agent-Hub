"""MiniMax provider: regions, key detection, Hermes / claw mapping, region probe."""

from __future__ import annotations

from unittest import mock

FAKE_KEY = "sk-cp-" + "A1b2C3d4" * 10  # shape of a MiniMax Coding / Token Plan key (not a real key)


def test_presets_for_both_regions():
    from ali.providers import get_provider

    g, cn = get_provider("minimax"), get_provider("minimax-cn")
    assert g["base_url"] == "https://api.minimax.io/v1" and g["api_key_env"] == "MINIMAX_API_KEY"
    assert cn["base_url"] == "https://api.minimaxi.com/v1" and cn["api_key_env"] == "MINIMAX_CN_API_KEY"
    for p in (g, cn):
        assert p["openai_compatible"] and p["models"]["main"].startswith("MiniMax-M")
        assert "MiniMax-M2" in p["suggestions"]["main"]
    assert "minimax.chat" not in g["base_url"] + cn["base_url"]  # retired host


def test_catalog_regions_and_short_model_names():
    from ali.providers import catalog_payload, coerce_model_for_provider

    regions = {p["id"]: p.get("region") for p in catalog_payload()["providers"] if "minimax" in p["id"]}
    assert regions == {"minimax": "global", "minimax-cn": "cn"}
    assert coerce_model_for_provider("minimax-cn", "minimax/MiniMax-M2", route_key="office") == "MiniMax-M2"


def test_coding_plan_key_detected_as_minimax_not_openai():
    from ali.providers import detect_provider_from_key, key_provider_mismatch

    assert detect_provider_from_key(FAKE_KEY) == "minimax"
    assert key_provider_mismatch("minimax-cn", FAKE_KEY) is None
    assert key_provider_mismatch("minimax", FAKE_KEY) is None


def test_hermes_mapping_and_env_per_region(tmp_path):
    from ali import hermes_cli

    assert hermes_cli._hermes_provider_name("minimax") == "minimax"
    assert hermes_cli._hermes_provider_name("minimax-cn") == "minimax-cn"
    with mock.patch.object(hermes_cli, "hermes_home", return_value=tmp_path), \
            mock.patch("ali.mcp_hub.active_servers_for_hermes", return_value={}):
        env = hermes_cli.build_hermes_env(env_name="MINIMAX_CN_API_KEY", api_key=FAKE_KEY, provider_id="minimax-cn",
                                          model="MiniMax-M2")
        assert env["MINIMAX_CN_API_KEY"] == FAKE_KEY and env["HERMES_HOME"] == str(tmp_path)
        dotenv = (tmp_path / ".env").read_text()
        assert f"MINIMAX_CN_API_KEY={FAKE_KEY}" in dotenv
        cfg = (tmp_path / "config.yaml").read_text()
        assert "minimax-cn" in cfg and "MiniMax-M2" in cfg
        assert "base_url" not in cfg  # native provider: Hermes uses its own MiniMax endpoint
        env_g = hermes_cli.build_hermes_env(env_name="MINIMAX_API_KEY", api_key=FAKE_KEY, provider_id="minimax")
        assert env_g["MINIMAX_API_KEY"] == FAKE_KEY and "MINIMAX_CN_API_KEY" not in env_g


def test_stale_vendor_keys_do_not_bleed_into_hermes(tmp_path, monkeypatch):
    from ali import hermes_cli

    monkeypatch.setenv("MINIMAX_API_KEY", "sk-stale")
    with mock.patch.object(hermes_cli, "hermes_home", return_value=tmp_path), \
            mock.patch("ali.mcp_hub.active_servers_for_hermes", return_value={}):
        env = hermes_cli.build_hermes_env(env_name="DEEPSEEK_API_KEY", api_key="sk-deepseek-xyz", provider_id="deepseek")
    assert "MINIMAX_API_KEY" not in env


def test_openclaw_and_restricted_policy_cover_china_region():
    from ali import claw_cli, routing

    env = claw_cli.build_openclaw_env(provider_id="minimax-cn", api_key=FAKE_KEY) if hasattr(claw_cli, "build_openclaw_env") else None
    if env is not None:
        assert env.get("MINIMAX_API_KEY") == FAKE_KEY
    cfg = {"data_policy": "restricted", "backend": {"type": "minimax-cn"}}
    info = routing.resolve_route("auto", "写一份周报", cfg)
    assert info.get("blocked") is True


def test_probe_minimax_region_picks_the_region_that_accepts_the_key():
    from ali.providers import probe_minimax_region

    calls = []

    def fake_list(base, key, timeout=6.0, verify_tls=True):
        calls.append(base)
        if "minimaxi.com" in base:
            return {"ok": True, "models": ["MiniMax-M2", "MiniMax-M2.5"], "count": 2}
        return {"ok": False, "error": f"HTTP 401: invalid api key {key}", "models": []}

    res = probe_minimax_region(FAKE_KEY, list_fn=fake_list)
    assert res["region"] == "minimax-cn" and res["base_url"] == "https://api.minimaxi.com/v1"
    # the China region stops at its first working endpoint; the global one tries each endpoint
    assert calls == ["https://api.minimaxi.com/v1", "https://api.minimax.io/v1", "https://api.minimax.io/anthropic"]
    assert res["results"]["minimax-cn"]["models"] == ["MiniMax-M2", "MiniMax-M2.5"]
    assert FAKE_KEY not in res["results"]["minimax"]["error"]  # never echo the key back

    none = probe_minimax_region(FAKE_KEY, list_fn=lambda *a, **k: {"ok": False, "error": "HTTP 403", "models": []})
    assert none["region"] is None


def test_probe_falls_back_to_a_chat_when_the_model_list_is_unavailable():
    from ali.providers import probe_minimax_region

    pings = []

    def no_models(base, key, timeout=6.0, verify_tls=True):
        return {"ok": False, "error": "HTTP 404: not found", "models": []}

    def chat(base, key, timeout=15.0, verify_tls=True):
        pings.append(base)
        if "minimaxi.com" in base:
            return {"ok": True, "models": [], "count": 0, "via": "chat"}
        return {"ok": False, "error": "HTTP 401 Unauthorized", "models": [], "via": "chat"}

    res = probe_minimax_region(FAKE_KEY, list_fn=no_models, chat_fn=chat)
    assert res["region"] == "minimax-cn" and res["results"]["minimax-cn"]["via"] == "chat"
    assert pings == ["https://api.minimaxi.com/v1", "https://api.minimax.io/v1", "https://api.minimax.io/anthropic"]
    # an auth failure on the model list is final for that region: no extra chat request
    pings.clear()
    probe_minimax_region(FAKE_KEY, list_fn=lambda *a, **k: {"ok": False, "error": "HTTP 401: bad key", "models": []}, chat_fn=chat)
    assert pings == []


def test_minimax_error_envelope_in_a_200_reply_is_an_error():
    from ali.llm_client import provider_error

    assert provider_error({"choices": [{"message": {"content": "hi"}}], "base_resp": {"status_code": 0}}) == ""
    msg = provider_error({"base_resp": {"status_code": 1004, "status_msg": "login fail"}})
    assert "1004" in msg and "api.minimaxi.com" in msg
    assert provider_error({"base_resp": {"status_code": 2013, "status_msg": "invalid params"}}).startswith("MiniMax error 2013")


def test_coding_plan_key_that_only_works_on_the_anthropic_endpoint():
    from ali.providers import probe_minimax_region

    def lister(base, key, timeout=6.0, verify_tls=True):
        if base == "https://api.minimax.cn/anthropic":
            return {"ok": True, "models": ["MiniMax-M2"], "count": 1}
        return {"ok": False, "error": "HTTP 401: invalid api key", "models": []}

    res = probe_minimax_region(FAKE_KEY, list_fn=lister, chat_fn=lambda *a, **k: {"ok": False, "error": "x"})
    assert res["region"] == "minimax-cn" and res["base_url"] == "https://api.minimax.cn/anthropic"
    assert [e["base_url"] for e in res["results"]["minimax-cn"]["endpoints"]] == [
        "https://api.minimaxi.com/v1", "https://api.minimax.cn/anthropic"]


def test_chosen_alternative_endpoint_is_not_overridden_by_the_catalog(monkeypatch):
    from ali import streaming

    seen = {}

    def fake_stream(base_url, api_key, **kw):
        seen["base"] = base_url
        return "ok"

    cfg = {"backend": {"type": "minimax-cn", "base_url": "https://api.minimax.cn/anthropic", "model": "MiniMax-M2"},
           "models": {}}
    monkeypatch.setattr("ali.settings.load_campus_config", lambda: cfg)
    monkeypatch.setattr("ali.secrets.resolve_api_key", lambda *a, **k: {"key": FAKE_KEY, "present": True})
    monkeypatch.setattr("ali.llm_client.stream_chat", fake_stream)
    monkeypatch.setattr(streaming.store, "get_session", lambda sid: None)
    import queue

    parts = []
    assert streaming._direct_llm_reply(queue.Queue(), "s", "hi", "MiniMax-M2", parts, route_info={"route_key": "office"})
    assert seen["base"] == "https://api.minimax.cn/anthropic"
    cfg["backend"]["base_url"] = "https://evil.example.com/v1"  # anything else still snaps to the catalog URL
    streaming._direct_llm_reply(queue.Queue(), "s", "hi", "MiniMax-M2", [], route_info={"route_key": "office"})
    assert seen["base"] == "https://api.minimaxi.com/v1"


def test_routing_keeps_a_chosen_minimax_endpoint_but_not_foreign_urls():
    from ali import routing
    from ali.providers import pick_base_url, get_provider

    cfg = {"backend": {"type": "minimax-cn", "base_url": "https://api.minimax.cn/anthropic", "model": "MiniMax-M2"},
           "models": {"main": "MiniMax-M2"}, "data_policy": "open"}
    assert routing.resolve_route("office", "写一段总结", cfg)["base_url"] == "https://api.minimax.cn/anthropic"
    cfg["backend"]["base_url"] = "https://integrate.api.nvidia.com/v1"  # stale URL from another vendor
    assert routing.resolve_route("office", "写一段总结", cfg)["base_url"] == "https://api.minimaxi.com/v1"
    assert pick_base_url(get_provider("minimax"), "https://api.minimax.io/anthropic/") == "https://api.minimax.io/anthropic/"
