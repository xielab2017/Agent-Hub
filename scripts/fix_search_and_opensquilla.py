"""Apply two fixes to Agent Hub's campus config in one shot:

  (1) Search repair — fill missing `search.*` knobs so the intent router
      in ali/search_extensions.py actually fires. Today the default
      campus-office-ai.json has no `search` block, so any *_no_key search
      degrades to noisy homepage scrape with zero campus filter.

  (2) OpenSquilla token-saving — turn on the engine by toggling
      `routing.use_opensquilla = true` AND activating the ecosystem flag
      `ecosystem.activated.opensquilla.active = true`. The routing
      resolver in ali/routing.py:412-417 reads these and will then
      select C0–C3 auto tiers and the cheaper ensemble lineup.

Both edits are additive and idempotent. Re-running this script is safe.

Run:
    python3 scripts/fix_search_and_opensquilla.py
    ./ctl.sh restart

Optional flags:
    --config PATH      override config path (default ~/.hermes/ali/campus-office-ai.json)
    --no-opensquilla   only repair search, leave routing engine alone
    --no-search        only flip OpenSquilla on, leave search section alone
    --dry-run          print diff without writing
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_CONFIG = Path.home() / ".hermes/ali/campus-office-ai.json"

SEARCH_DEFAULTS = {
    "engine": "auto",            # classify_intent → academic/news/event/code/general
    "verify_tls": True,
    "proxy": "",                 # empty → use system proxy bypass
    "max_results": 8,
    "fallback_policy": "off",
    "diagnostics": False,
}

OPENSQUILLA_ECO = {
    "path": "/Users/liweixie/.agent-cli/ecosystem/opensquilla",
    "active": True,
    "description": (
        "OpenSquilla token-saving routing (C0–C3 + ensemble). "
        "Cheapest-capable model per turn."
    ),
}


def _ensure_block(cfg: dict, key: str, defaults: dict) -> tuple[dict, bool]:
    block = cfg.get(key)
    if not isinstance(block, dict):
        cfg[key] = dict(defaults)
        return cfg[key], True
    changed = False
    for k, v in defaults.items():
        if k not in block:
            block[k] = v
            changed = True
    cfg[key] = block
    return block, changed


def _activate_opensquilla(cfg: dict) -> tuple[dict, list[str]]:
    notes: list[str] = []
    routing = cfg.get("routing") or {}
    if not routing.get("use_opensquilla") and not routing.get("token_saving"):
        routing["use_opensquilla"] = True
        notes.append("routing.use_opensquilla=true")
    cfg["routing"] = routing

    eco = cfg.get("ecosystem") or {}
    activated = eco.get("activated") or {}
    osq = activated.get("opensquilla") or {}
    if not osq.get("active"):
        for k, v in OPENSQUILLA_ECO.items():
            osq.setdefault(k, v)
        osq["active"] = True
        activated["opensquilla"] = osq
        eco["activated"] = activated
        cfg["ecosystem"] = eco
        notes.append("ecosystem.activated.opensquilla.active=true")

    # Bind each tier to a cheap default if no per-tier model is set yet.
    tier_models = routing.get("tier_models") or {}
    cheap = {
        "C0": "deepseek-v4-flash",
        "C1": "deepseek-v4-pro",
        "C2": "kimi-k2.7-code",
        "C3": "deepseek-v4-pro",
    }
    if not tier_models:
        routing["tier_models"] = cheap
        notes.append("routing.tier_models seeded (C0–C3)")
    return cfg, notes


def repair_search(cfg: dict) -> tuple[dict, list[str]]:
    notes: list[str] = []
    search, changed = _ensure_block(cfg, "search", SEARCH_DEFAULTS)
    if changed:
        notes.append("search block seeded with campus-safe defaults")
    cfg["search"] = search
    return cfg, notes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--no-opensquilla", action="store_true")
    ap.add_argument("--no-search", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    path: Path = args.config.expanduser()
    if not path.exists():
        print(f"[fix] config not found: {path}", file=sys.stderr)
        return 2

    raw = path.read_text(encoding="utf-8")
    cfg = json.loads(raw)
    before = json.dumps(cfg, ensure_ascii=False, sort_keys=True)

    notes: list[str] = []
    if not args.no_search:
        cfg, n = repair_search(cfg)
        notes += n
    if not args.no_opensquilla:
        cfg, n = _activate_opensquilla(cfg)
        notes += n

    after = json.dumps(cfg, ensure_ascii=False, sort_keys=True)
    if before == after:
        print("[fix] nothing to change — config already matches target state")
        return 0

    if args.dry_run:
        print("[fix] dry-run — would apply:")
        for line in notes:
            print(f"  - {line}")
        return 0

    path.write_text(after + "\n", encoding="utf-8")
    print(f"[fix] wrote {path}")
    for line in notes:
        print(f"  + {line}")
    print("[fix] next: cd /Users/liweixie/Projects/Agent-Hub-3.0 && ./ctl.sh restart")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())