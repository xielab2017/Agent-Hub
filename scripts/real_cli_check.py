#!/usr/bin/env python3
"""Check the real Claude Code / Codex CLIs against the flags ali/agent_cli.py uses (CLI drift guard).

    python scripts/real_cli_check.py --claude "$(npm prefix -g)/bin/claude" --codex "$(npm prefix -g)/bin/codex"
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run(cmd: list[str]) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return (out.stdout or "") + (out.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"(failed: {exc})"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--claude", required=True)
    ap.add_argument("--codex", required=True)
    ap.add_argument("--out", default=str(ROOT / "outputs" / "agents_demo" / "real-cli-check.json"))
    a = ap.parse_args()
    from ali import agent_cli

    report = {}
    for rid, binpath in (("claude-code", a.claude), ("codex", a.codex)):
        version = run([binpath, "--version"]).strip().splitlines()[:1]
        help_text = agent_cli.cli_help(rid, binpath)
        extra = run([binpath, "exec", "resume", "--help"]) if rid == "codex" else run([binpath, "setup-token", "--help"])
        login = run([binpath, "login", "--help"]) if rid == "codex" else ""
        report[rid] = {"bin": binpath, "version": version[0] if version else "", "missing": agent_cli.check_flags(
            rid, help_text=help_text), "help": help_text[:30000], "extra_help": extra[:2500], "login_help": login[:2500]}
        print(rid, report[rid]["version"], "missing:", report[rid]["missing"] or "none")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if not any(r["missing"] for r in report.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
