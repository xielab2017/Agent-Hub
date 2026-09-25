#!/usr/bin/env python3
"""Write an evidence-grounded literature review with Agent Hub (one command).

    MINIMAX_KEY='sk-...' python scripts/review_pipeline.py --out outputs/thbs4_review

Configures a throw-away Agent Hub state directory for MiniMax (region probed,
MiniMax-M3 preferred), then runs ``ali.review_writer.run``: PubMed search →
abstract screening → evidence cards → outline → drafted sections (Hub reviewer
checks) → three Agent Hub reviewer subagents → revision → Word document.
The key is never printed; every log line is masked.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEY = (os.environ.get("MINIMAX_KEY") or os.environ.get("MINIMAX_CN_API_KEY") or os.environ.get("MINIMAX_API_KEY") or "").strip()

TOPIC = ("Thrombospondin-4 (THBS4) as a skeletal muscle-derived secreted factor: regulatory mechanisms in ageing "
         "and metabolism")
SEED_QUERIES = [
    "THBS4 skeletal muscle",
    "thrombospondin-4 muscle",
    "thrombospondin-4 ATF6 endoplasmic reticulum stress",
    "thrombospondin-4 sarcolemma muscular dystrophy",
    "thrombospondin-4 heart hypertrophy",
    "thrombospondin-4 aging OR ageing",
    "THBS4 obesity OR adipose OR insulin OR diabetes",
    "THBS4 liver fibrosis OR NAFLD OR MASLD",
    "thrombospondin-4 exercise OR mechanical load",
    "thrombospondin-4 tendon extracellular matrix",
    "THBS4 fibroblast TGF-beta fibrosis",
    "THBS4 proteomics plasma",
    "thrombospondin-4 angiogenesis inflammation",
    "thrombospondin family matricellular review",
    "myokines skeletal muscle endocrine organ review",
    "muscle secretome aging sarcopenia",
]
FOCUS = r"\bTHBS-?4\b|\bTSP-?4\b|thrombospondin[- ]?4\b"
SEED_PMIDS = ["27669143", "30622267", "34168130", "29712757", "26459760", "24573206", "23287452", "29138119",
              "32795101", "37582915", "24589453", "28481870", "39373248", "38876442", "39154161", "41873540"]


def mask(text: object) -> str:
    s = str(text)
    if KEY:
        s = s.replace(KEY, KEY[:6] + "…" + KEY[-4:])
    return re.sub(r"sk-[A-Za-z0-9_\-]{16,}", lambda m: m.group(0)[:6] + "…" + m.group(0)[-4:], s)


def say(*parts: object) -> None:
    print(mask(" ".join(str(p) for p in parts)), flush=True)


def configure(model_pref: str) -> str:
    from ali.providers import get_provider, probe_minimax_region
    from ali.secrets import set_api_key
    from ali.settings import load_campus_config, save_campus_config

    probe = probe_minimax_region(KEY, timeout=15.0)
    region = probe["region"]
    if not region:
        raise SystemExit("neither MiniMax region accepted the key")
    models = probe["results"].get(region, {}).get("models") or []
    model = model_pref if (not models or model_pref in models) else (models[0] if models else model_pref)
    base_url = (probe["results"].get(region) or {}).get("base_url") or get_provider(region)["base_url"]
    cfg = load_campus_config()
    prov = get_provider(region)
    cfg["backend"] = {**(cfg.get("backend") or {}), "type": region, "base_url": base_url, "model": model,
                      "api_key_env": prov["api_key_env"], "verify_tls": True}
    cfg["models"] = {**(cfg.get("models") or {}), "fast": model, "main": model, "reasoning": model}
    save_campus_config(cfg)
    set_api_key(region, KEY)
    return f"{region} {base_url} {model}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "outputs" / "thbs4_review"))
    ap.add_argument("--model", default="MiniMax-M3")
    ap.add_argument("--min-refs", type=int, default=40)
    ap.add_argument("--max-cards", type=int, default=60)
    args = ap.parse_args()
    if not KEY:
        say("Set MINIMAX_KEY first.")
        return 2

    tmp = Path(tempfile.mkdtemp(prefix="agenthub-review-"))
    for var, sub in (("HERMES_ALI_STATE_DIR", "state"), ("AGENT_CLI_HOME", "cli"), ("HERMES_HOME", "hermes"),
                     ("HERMES_ALI_AGENT_DIR", "no-agent")):
        os.environ[var] = str(tmp / sub)
    os.environ["HOME"] = str(tmp)
    sys.path.insert(0, str(ROOT))

    say("backend:", configure(args.model))
    from ali import review_writer

    t0 = time.time()
    out = Path(args.out)
    summary = review_writer.run(TOPIC, out, seed_queries=SEED_QUERIES, seed_pmids=SEED_PMIDS,
                                focus=FOCUS, min_refs=args.min_refs, max_cards=args.max_cards,
                                log=lambda m: say(f"[{time.time() - t0:6.0f}s]", m))
    say(json.dumps(summary, ensure_ascii=False, indent=1))
    chk = summary["citation_check"]
    ok = chk["cited"] >= args.min_refs and not chk["out_of_range"] and not chk["uncited"]
    say("RESULT:", "PASS" if ok else "CHECK", f"— {chk['cited']} distinct references cited")
    for f in sorted(out.iterdir()):  # nothing written may contain the key
        if f.is_file() and KEY in f.read_bytes().decode("utf-8", "ignore"):
            f.unlink()
            say("removed (contained the key):", f.name)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
