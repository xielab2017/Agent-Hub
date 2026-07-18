"""Regression tests for the Hub → Hermes LLM sync.

These tests cover the "Routing tab binding vs. legacy Models slot"
chokepoint. The original bug: the user sets dashscope · qwen3.7-max-preview
in the Routing tab (per-tier binding), but Hermes' ``.env`` ends up with
``model=deepseek-r1-distill-llama-70b`` because ``sync_hub_to_hermes``
falls through to the stale ``models.main`` slot.

Two layers are exercised:
  * ``ali.hermes_cli._hermes_provider_name`` maps ``dashscope`` → ``custom``
    (because Hermes speaks OpenAI-compat when given the right base_url).
  * ``ali.hermes_cli.sync_hub_to_hermes`` honours the Routing tab's
    ``routing.tier_models.C1`` binding ahead of the legacy slot.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).parent.parent.resolve()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ── provider mapping ────────────────────────────────────────────────────


def test_dashscope_maps_to_custom_so_hermes_uses_openai_compat():
    from ali.hermes_cli import _hermes_provider_name
    # DashScope / Qwen / Aliyun all surface through Hermes' OpenAI
    # compatibility layer; the .env therefore gets OPENAI_BASE_URL +
    # DASHSCOPE_API_KEY rather than a native vendor block.
    assert _hermes_provider_name("dashscope") == "custom"
    assert _hermes_provider_name("qwen") == "custom"
    assert _hermes_provider_name("aliyun") == "custom"
    # Existing mappings stay put
    assert _hermes_provider_name("deepseek") == "deepseek"
    assert _hermes_provider_name("openai") == "openai"


def test_routing_tier_wins_over_legacy_models_slot():
    """The Routing tab's per-tier binding must beat the legacy models.main."""
    from unittest import mock as _mock
    from ali import runtimes as _runtimes
    from ali import secrets as _secrets
    cfg = {
        "backend": {
            "type": "dashscope",
            "api_key_env": "DASHSCOPE_API_KEY",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        },
        "routing": {
            "tier_models": {
                "C1": {"provider": "dashscope", "model": "qwen3.7-max-preview"},
            },
        },
        "models": {"main": "deepseek-r1-distill-llama-70b"},  # stale
    }
    with _mock.patch.object(_secrets, "resolve_api_key",
                            return_value={"key": "sk-test-1234",
                                          "env_name": "DASHSCOPE_API_KEY",
                                          "masked": "sk-…-1234",
                                          "tried": ["env:DASHSCOPE_API_KEY"]}):
        cred = _runtimes._resolve_hub_llm(cfg)
    assert cred["provider_id"] == "dashscope"
    assert cred["env_name"] == "DASHSCOPE_API_KEY"
    assert cred["base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    # The binding wins over the legacy slot — this is the regression
    # that was producing "model=deepseek-r1-distill-llama-70b".
    assert cred["model"] == "qwen3.7-max-preview"
    # Claw provider slug for OpenClaw / NanoBot config — dashscope has
    # no native block there, falls through to openai (OpenAI-compat).
    assert cred["claw_provider"] == "openai"


def test_routing_tier_falls_through_to_models_when_unbound():
    """If the Routing tab is on "follow route / auto" the legacy slot wins."""
    from ali.runtimes import _resolve_hub_llm
    cfg = {
        "backend": {"type": "dashscope"},
        "routing": {
            "tier_models": {
                "C1": {"provider": "auto", "model": ""},  # UI "follow" sentinel
            },
        },
        "models": {"main": "qwen-flash"},
    }
    cred = _resolve_hub_llm(cfg)
    assert cred["model"] == "qwen-flash"
    assert cred["provider_id"] == "dashscope"


def test_routing_tier_provider_switch_with_key():
    """If C1 names a different provider, the new provider's key must be used."""
    from unittest import mock as _mock
    from ali import runtimes as _runtimes
    from ali import secrets as _secrets
    cfg = {
        "backend": {"type": "deepseek", "api_key_env": "DEEPSEEK_API_KEY"},
        "routing": {
            "tier_models": {
                "C1": {"provider": "dashscope", "model": "qwen3.7-max-preview"},
            },
        },
        "models": {},
    }
    # Stub resolve_api_key at its source module so the local imports
    # inside _resolve_hub_llm pick up the mock.
    with _mock.patch.object(_secrets, "resolve_api_key",
                            side_effect=lambda c, provider="": {
                                "deepseek": {"key": "sk-deepseek-xxx", "env_name": "DEEPSEEK_API_KEY",
                                             "masked": "sk-…-xxx", "tried": ["env:DEEPSEEK_API_KEY"]},
                                "dashscope": {"key": "sk-dashscope-xxx", "env_name": "DASHSCOPE_API_KEY",
                                              "masked": "sk-…-xxx", "tried": ["env:DASHSCOPE_API_KEY"]},
                            }[provider]):
        cred = _runtimes._resolve_hub_llm(cfg)
    assert cred["provider_id"] == "dashscope"
    assert cred["env_name"] == "DASHSCOPE_API_KEY"
    assert cred["api_key"] == "sk-dashscope-xxx"
    assert cred["model"] == "qwen3.7-max-preview"


def test_routing_tier_provider_switch_blocked_when_no_key():
    """If the named provider has no key, keep the backend's existing one."""
    from unittest import mock as _mock
    from ali import runtimes as _runtimes
    from ali import secrets as _secrets
    cfg = {
        "backend": {"type": "deepseek", "api_key_env": "DEEPSEEK_API_KEY"},
        "routing": {
            "tier_models": {
                "C1": {"provider": "dashscope", "model": "qwen3.7-max-preview"},
            },
        },
        "models": {},
    }
    with _mock.patch.object(_secrets, "resolve_api_key",
                            side_effect=lambda c, provider="": {
                                "deepseek": {"key": "sk-deepseek-xxx", "env_name": "DEEPSEEK_API_KEY",
                                             "masked": "sk-…-xxx", "tried": ["env:DEEPSEEK_API_KEY"]},
                                "dashscope": {"key": "", "env_name": "DASHSCOPE_API_KEY",
                                              "masked": "", "tried": ["env:DASHSCOPE_API_KEY"]},
                            }[provider]):
        cred = _runtimes._resolve_hub_llm(cfg)
    assert cred["provider_id"] == "deepseek"
    assert cred["api_key"] == "sk-deepseek-xxx"


# ── end-to-end sync ─────────────────────────────────────────────────────


def _make_cfg():
    return {
        "backend": {
            "type": "dashscope",
            "api_key_env": "DASHSCOPE_API_KEY",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "verify_tls": True,
        },
        "routing": {
            "tier_models": {
                "C0": {"provider": "dashscope", "model": "qwen3.7-max"},
                "C1": {"provider": "dashscope", "model": "qwen3.7-max-preview"},
                "C2": {"provider": "dashscope", "model": "qwen3.7-max-preview"},
                "C3": {"provider": "dashscope", "model": "qwen3.7-text-embedding"},
                "Vision": {"provider": "dashscope", "model": "qwen3.7-plus-2026-05-26"},
            },
        },
        "models": {"main": "deepseek-r1-distill-llama-70b"},
    }


def test_sync_hub_to_hermes_writes_dashscope_key_and_routing_model():
    from unittest import mock as _mock
    from ali import hermes_cli
    from ali import secrets as _secrets
    cfg = _make_cfg()
    with tempfile.TemporaryDirectory() as tmp:
        hermes_home = Path(tmp) / ".hermes"
        hermes_home.mkdir()
        managed_home = hermes_home / "agent-cli"
        managed_home.mkdir()
        (managed_home / ".env").write_text("# stub\n")
        # Stable stub: dashscope key is the only one resolve_api_key sees.
        with _mock.patch.object(_secrets, "resolve_api_key",
                                return_value={"key": "sk-test-dashscope-key-1234",
                                              "env_name": "DASHSCOPE_API_KEY",
                                              "masked": "sk-…-1234",
                                              "tried": ["env:DASHSCOPE_API_KEY"]}), \
             _mock.patch.object(hermes_cli, "hermes_managed_home", return_value=managed_home), \
             _mock.patch.object(hermes_cli, "hermes_home", return_value=hermes_home), \
             _mock.patch.object(hermes_cli, "hermes_config_homes", return_value=[managed_home, hermes_home]):
            result = hermes_cli.sync_hub_to_hermes(cfg)
    assert result["ok"] is True
    assert result["model"] == "qwen3.7-max-preview"
    assert result["provider"] == "dashscope"
    assert result["hermes_provider"] == "custom"


def test_sync_hub_to_hermes_writes_dashscope_api_key_to_env():
    from unittest import mock as _mock
    from ali import hermes_cli
    from ali import secrets as _secrets
    cfg = _make_cfg()
    with tempfile.TemporaryDirectory() as tmp:
        hermes_home = Path(tmp) / ".hermes"
        hermes_home.mkdir()
        managed_home = hermes_home / "agent-cli"
        managed_home.mkdir()
        (managed_home / ".env").write_text("# stub\n")
        with _mock.patch.object(_secrets, "resolve_api_key",
                                return_value={"key": "sk-test-dashscope-key-1234",
                                              "env_name": "DASHSCOPE_API_KEY",
                                              "masked": "sk-…-1234",
                                              "tried": ["env:DASHSCOPE_API_KEY"]}), \
             _mock.patch.object(hermes_cli, "hermes_managed_home", return_value=managed_home), \
             _mock.patch.object(hermes_cli, "hermes_home", return_value=hermes_home), \
             _mock.patch.object(hermes_cli, "hermes_config_homes", return_value=[managed_home, hermes_home]):
            hermes_cli.sync_hub_to_hermes(cfg)
        env_text = (managed_home / ".env").read_text()
    assert "DASHSCOPE_API_KEY=sk-test-dashscope-key-1234" in env_text
    assert "OPENAI_API_KEY=sk-test-dashscope-key-1234" in env_text
    assert "OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1" in env_text
