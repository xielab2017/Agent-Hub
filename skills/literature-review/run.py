#!/usr/bin/env python3
"""Agent Hub skill entry: write an evidence-grounded critical review on any topic.

    python run.py --topic "…"                         # the Hub model plans the profile for the topic
    python run.py --profile multiomics-emp            # a profile from profiles/ (or a path to .yaml / .json)
    python run.py --profile thbs4 --smoke             # every stage on a small scale (~5 min)

The skill uses the host Agent Hub's configured model (Settings → backend / models) and its network layer; it
holds no key of its own, so it runs unchanged on any Agent Hub it is installed on.  Output (Word, Markdown,
reviewer reports, response letter, citation audit, evidence cards, checkpoints) goes to --out; a re-run with the
same arguments resumes at the stage that failed.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def find_profile(name: str) -> Path:
    for cand in (Path(name), HERE / "profiles" / name, HERE / "profiles" / f"{name}.yaml",
                 HERE / "profiles" / f"{name}.json"):
        if cand.is_file():
            return cand
    raise SystemExit(f"profile not found: {name} (available: "
                     + ", ".join(sorted(p.stem for p in (HERE / "profiles").glob("*.y*ml"))) + ")")


def read_profile(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        import yaml

        return yaml.safe_load(text) or {}
    return json.loads(text)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--topic", default="", help="review topic (English); overrides the profile's topic")
    ap.add_argument("--profile", default="", help="profile name in profiles/ or a path")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--min-refs", type=int, default=40)
    ap.add_argument("--max-cards", type=int, default=60)
    ap.add_argument("--smoke", action="store_true", help="small scale: 4 queries × 8 papers, 12 cards, 2 sections")
    ap.add_argument("--fresh", action="store_true", help="ignore saved checkpoints")
    args = ap.parse_args(argv)

    from ali import review_writer as rw

    profile = read_profile(find_profile(args.profile)) if args.profile else {}
    if args.topic:
        profile["topic"] = args.topic
    if not profile.get("topic"):
        raise SystemExit("give --topic or a --profile with a topic")
    limits = {"retmax": 25, "max_queries": 0, "max_sections": 0}
    if args.smoke:
        args.min_refs, args.max_cards = 8, 12
        limits = {"retmax": 8, "max_queries": 4, "max_sections": 2}
    out = Path(args.out)
    if args.fresh and (out / "checkpoints").exists():
        shutil.rmtree(out / "checkpoints")
    t0 = time.time()
    summary = rw.run(profile["topic"], out, profile=profile, min_refs=args.min_refs, max_cards=args.max_cards,
                     log=lambda m: print(f"[{time.time() - t0:6.0f}s] {m}", flush=True), **limits)
    chk = summary["citation_check"]
    ok = chk["cited"] >= args.min_refs and not chk["out_of_range"] and not chk["uncited"]
    print("RESULT:", "PASS" if ok else "CHECK", json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
