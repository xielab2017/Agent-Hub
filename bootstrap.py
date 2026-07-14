#!/usr/bin/env python3
"""One-shot launcher for Agent Hub (Mac / Linux / Windows)."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def find_python() -> str:
    # Prefer current interpreter
    return sys.executable or "python3"


def maybe_hint_hermes() -> None:
    hermes = shutil.which("hermes")
    if hermes:
        print(f"  Found hermes CLI: {hermes}")
    else:
        print("  Tip: install Hermes Agent for full agent mode:")
        print("    curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash")
        if sys.platform == "win32":
            print("    PowerShell: iex (irm https://hermes-agent.nousresearch.com/install.ps1)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap & start Agent Hub")
    parser.add_argument("--host", default=os.environ.get("HERMES_ALI_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("HERMES_ALI_PORT", "8765")))
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--password", default=os.environ.get("HERMES_ALI_PASSWORD", ""), help="Optional access password")
    args = parser.parse_args()

    if args.password:
        os.environ["HERMES_ALI_PASSWORD"] = args.password

    print()
    print("  Agent Hub bootstrap")
    print("  ────────────────────")
    print(f"  Python: {find_python()} ({sys.version.split()[0]})")
    maybe_hint_hermes()
    print()

    cmd = [find_python(), str(ROOT / "server.py"), "--host", args.host, "--port", str(args.port)]
    if args.no_browser:
        cmd.append("--no-browser")
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
