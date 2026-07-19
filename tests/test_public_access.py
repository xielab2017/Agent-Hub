from __future__ import annotations

from types import SimpleNamespace

from ali import config


def _clear_public_ip_cache() -> None:
    config._PUBLIC_IP_CACHE.update({"value": "", "expires": 0.0})


def test_public_ip_uses_curl_and_caches_result(monkeypatch):
    _clear_public_ip_cache()
    calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="8.8.8.8\n")

    monkeypatch.setattr(config.shutil, "which", lambda _name: "/usr/bin/curl")
    monkeypatch.setattr(config.subprocess, "run", fake_run)

    assert config.public_ip() == "8.8.8.8"
    assert config.public_ip() == "8.8.8.8"
    assert len(calls) == 1


def test_public_ip_rejects_non_global_addresses(monkeypatch):
    _clear_public_ip_cache()

    def fake_run(_command, **_kwargs):
        return SimpleNamespace(returncode=0, stdout="192.168.1.10\n")

    monkeypatch.setattr(config.shutil, "which", lambda _name: "/usr/bin/curl")
    monkeypatch.setattr(config.subprocess, "run", fake_run)

    assert config.public_ip() == ""


def test_public_url_requires_http_scheme_and_hostname(monkeypatch):
    monkeypatch.setenv("HERMES_ALI_PUBLIC_URL", "javascript:alert(1)")
    assert config._public_url() == ""
    monkeypatch.setenv("HERMES_ALI_PUBLIC_URL", "https://agent.example.edu/")
    assert config._public_url() == "https://agent.example.edu"
