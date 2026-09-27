#!/usr/bin/env python3
"""Screenshot helper for UI review: open the running Hub and shoot a few states.

    python scripts/ui_shots.py --url http://127.0.0.1:8765 --out /tmp/shots [--lang en]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8765")
    ap.add_argument("--out", default="/tmp/shots")
    ap.add_argument("--lang", default="zh")
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--height", type=int, default=900)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_context(viewport={"width": args.width, "height": args.height}).new_page()
        page.goto(args.url, wait_until="networkidle")
        page.evaluate("(l) => localStorage.setItem('hermes_ali_lang', l)", args.lang)
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(2500)
        page.screenshot(path=str(out / f"01_home_{args.lang}.png"))
        page.fill("#input", "请写一段简短的实验室组会通知")
        page.wait_for_timeout(300)
        page.screenshot(path=str(out / f"02_composer_{args.lang}.png"))
        page.click("#btn-composer-adv")
        page.wait_for_timeout(400)
        page.screenshot(path=str(out / f"03_advanced_{args.lang}.png"))
        page.click("#btn-control")
        page.wait_for_timeout(1500)
        page.screenshot(path=str(out / f"04_control_{args.lang}.png"))
        for tab in ("connections", "runtimes", "appearance", "agents"):
            try:
                page.click(f'.ctab[data-ctab="{tab}"]')
                page.wait_for_timeout(2000)
                page.screenshot(path=str(out / f"05_{tab}_{args.lang}.png"), full_page=False)
            except Exception as exc:  # noqa: BLE001
                print("tab failed", tab, exc)
        browser.close()
    print("shots in", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
