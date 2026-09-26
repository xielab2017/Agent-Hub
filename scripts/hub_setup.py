#!/usr/bin/env python3
"""Configure the Agent Hub in the current state directory (HERMES_ALI_STATE_DIR / AGENT_CLI_HOME / HOME).

    MINIMAX_KEY='sk-…' python scripts/hub_setup.py            # MiniMax (region probed, MiniMax-M3 preferred)
    python scripts/hub_setup.py --stub http://127.0.0.1:9911/v1  # an OpenAI-compatible stub (offline rehearsal)

The key is stored with the Hub's own secret store and never printed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stub", default="", help="base URL of an OpenAI-compatible stub model")
    ap.add_argument("--model", default="MiniMax-M3")
    ap.add_argument("--agent", action="store_true", help="agent chat mode (the Hub agent answers with tools)")
    args = ap.parse_args()
    if args.stub:
        from ali.secrets import set_api_key
        from ali.settings import load_campus_config, save_campus_config

        cfg = load_campus_config()
        cfg["backend"] = {**(cfg.get("backend") or {}), "type": "campus-openai-compatible", "base_url": args.stub,
                          "model": "stub-model", "api_key_env": "CAMPUS_LLM_API_KEY", "verify_tls": False}
        cfg["models"] = {**(cfg.get("models") or {}), "fast": "stub-model", "main": "stub-model",
                         "reasoning": "stub-model"}
        cfg.setdefault("ali", {})["hub_chat_mode"] = "direct"
        save_campus_config(cfg)
        set_api_key("campus-openai-compatible", "stub-key")
        print("backend: stub", args.stub)
        return 0
    import review_pipeline

    if not review_pipeline.KEY:
        print("Set MINIMAX_KEY first.")
        return 2
    print(review_pipeline.mask("backend: " + review_pipeline.configure(args.model)))
    if args.agent:
        from ali.settings import load_campus_config, save_campus_config

        cfg = load_campus_config()
        cfg.setdefault("ali", {})["hub_chat_mode"] = "agent"
        cfg["ali"].pop("hub_fast_chat", None)
        save_campus_config(cfg)
        print("chat mode: agent (Hub agent)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
