"""Shared test setup: no test may reach the real network or real claw homes.

Every outbound search / connector / page request goes through
``websearch._http``; tests that need responses stub a higher-level function
(``_fetch``, an engine, ``search_structured`` …).  Blocking the bottom layer
keeps CI deterministic even where the network is open.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    from ali import websearch

    def _blocked(url, *a, **k):
        raise OSError(f"network disabled in tests: {url}")

    monkeypatch.setattr(websearch, "_http", _blocked)
    # Never link test skills into a developer's real ~/.hermes / ~/.openclaw skills dir.
    from ali import skills

    monkeypatch.setattr(skills, "sync_active_claw", lambda: {"ok": True, "synced": False, "reason": "tests"})
    yield
