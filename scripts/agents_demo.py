#!/usr/bin/env python3
"""Drive Agent Hub's UI through multi-vendor model APIs and the Claude Code / Codex agents, with screenshots.

    python scripts/agents_demo.py --out outputs/agents_demo [--fakes tests/fakes]

1. 多模型 API: several vendors connected at once (MiniMax from $MINIMAX_KEY when set, plus an OpenAI-compatible
   stub standing in for a campus endpoint), tier routing bound per vendor, routing test, then a chat answered by
   the office-tier vendor.
2. Claws → Claude Code: 外部链接登录 — the sign-in link appears, a code is pasted back, the token is stored.
3. Claws → Codex: 设备码登录 — link + device code.
4. Connect each agent and chat: streamed text and tool use.

With --fakes the login and chat use the fake CLIs in tests/fakes (CI has no real accounts); the real CLIs'
--help is checked separately by the workflow.  Screens: <out>/screens/NNN_<step>.png (+ live.png).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import skill_demo as sd  # noqa: E402  (Hub / Shots / open_ui / command helpers)


def api(hub: sd.Hub, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(hub.url + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def wait_reply(page, timeout_s: int = 240) -> None:
    page.wait_for_timeout(1500)
    page.wait_for_function("() => !((state.sessionRuns || {})[state.currentId] || {}).streaming",
                           timeout=timeout_s * 1000)
    page.wait_for_timeout(800)


def open_tab(page, tab: str) -> None:
    if page.locator("#control-overlay").is_hidden():
        page.click("#btn-control")
    page.click(f"[data-ctab={tab}]")
    page.wait_for_timeout(1500)


def close_control(page) -> None:
    if not page.locator("#control-overlay").is_hidden():
        page.click("#btn-control-close")
        page.wait_for_timeout(500)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "outputs" / "agents_demo"))
    ap.add_argument("--fakes", default="", help="directory with fake claude / codex / cursor-agent CLIs to put first on PATH")
    args = ap.parse_args()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    report: dict = {"run_url": sd.RUN_URL, "steps": []}
    if args.fakes:
        os.environ["PATH"] = f"{Path(args.fakes).resolve()}{os.pathsep}{os.environ['PATH']}"
        os.environ["FAKE_LOGIN_WAIT"] = "4"
    stub = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "stub_llm.py"), "--port", "9911"])
    time.sleep(1)
    key = (os.environ.get("MINIMAX_KEY") or "").strip()
    from playwright.sync_api import sync_playwright

    hub = sd.Hub("A", 8765, "http://127.0.0.1:9911/v1")  # starts on the stub (campus-openai-compatible)
    shots = sd.Shots(out)
    try:
        # ── 1. multi-vendor connections + tier routing ─────────────────
        if key:
            api(hub, "/api/connections/minimax-cn", {"api_key": key})
            test = api(hub, "/api/connections/minimax-cn/test", {})
            report["steps"].append({"step": "minimax-test", "ok": test.get("ok"), "count": test.get("count"),
                                    "via": test.get("via")})
            api(hub, "/api/connections/tier", {"route_key": "office", "provider": "minimax-cn", "model": "MiniMax-M3"})
        api(hub, "/api/connections/tier", {"route_key": "simple", "provider": "campus-openai-compatible",
                                           "model": "stub-model"})
        routes = api(hub, "/api/connections/route-test")["routes"]
        report["steps"].append({"step": "routes", "routes": routes})

        with sync_playwright() as pw:
            exe = os.environ.get("CHROMIUM_PATH")
            browser = pw.chromium.launch(**({"executable_path": exe} if exe else {}))
            page = sd.open_ui(browser, hub)
            open_tab(page, "connections")
            page.click("#conn-route-test")
            page.wait_for_timeout(1000)
            shots.take(page, "A", "connections", note="多模型 API: vendors connected side by side + tier routing test")
            page.locator(".conn-grid").scroll_into_view_if_needed()
            shots.take(page, "A", "vendor-cards", note="vendor cards: own key (masked), endpoint, TLS, test status")
            close_control(page)
            if key:
                sd.command(page, "请写一段简短的实验室组会通知，时间周五下午三点。")
                wait_reply(page)
                shots.take(page, "A", "office-chat", note="office-tier chat answered by MiniMax-M3 (hybrid routing)")

            # ── 2. Claude Code: external-link login ─────────────────────
            open_tab(page, "runtimes")
            box = page.locator('.agent-login[data-rid="claude-code"]')
            box.scroll_into_view_if_needed()
            shots.take(page, "A", "claws-agents", note="Claws: Claude Code and Codex rows with sign-in controls")
            box.locator('[data-login="link"]').click()
            page.wait_for_selector('.agent-login[data-rid="claude-code"] .agent-login-url', timeout=30000)
            page.wait_for_timeout(1500)
            box.scroll_into_view_if_needed()
            shots.take(page, "A", "claude-link", note="Claude Code: external sign-in link shown, code box ready")
            url = box.locator(".agent-login-url").get_attribute("href")
            report["steps"].append({"step": "claude-link", "url": url})
            box.locator(".agent-login-input").fill("demo-authorisation-code")
            box.locator(".agent-login-send").click()
            page.wait_for_function("""() => /已登录|signed in/.test(document.querySelector('.agent-login[data-rid="claude-code"] .agent-login-head')?.textContent || '')""",
                                   timeout=30000)
            box.scroll_into_view_if_needed()
            shots.take(page, "A", "claude-signed-in", note="Claude Code signed in — token stored by Agent Hub, never shown")
            report["steps"].append({"step": "claude-auth", **api(hub, "/api/runtimes/claude-code/auth")})

            # ── 3. Codex: device-code login ─────────────────────────────
            cbox = page.locator('.agent-login[data-rid="codex"]')
            cbox.scroll_into_view_if_needed()
            cbox.locator('[data-login="device"]').click()
            page.wait_for_selector('.agent-login[data-rid="codex"] .agent-login-code', timeout=30000)
            cbox.scroll_into_view_if_needed()
            shots.take(page, "A", "codex-device", note="Codex: device-code sign-in (link + one-time code)")
            page.wait_for_function("""() => /已登录|signed in/.test(document.querySelector('.agent-login[data-rid="codex"] .agent-login-head')?.textContent || '')""",
                                   timeout=40000)
            cbox.scroll_into_view_if_needed()
            shots.take(page, "A", "codex-signed-in", note="Codex signed in")
            report["steps"].append({"step": "codex-auth", **api(hub, "/api/runtimes/codex/auth")})

            # ── 3b. Cursor: external-link login ─────────────────────────
            ubox = page.locator('.agent-login[data-rid="cursor"]')
            ubox.scroll_into_view_if_needed()
            ubox.locator('[data-login="link"]').click()
            page.wait_for_selector('.agent-login[data-rid="cursor"] .agent-login-url', timeout=30000)
            ubox.scroll_into_view_if_needed()
            shots.take(page, "A", "cursor-link", note="Cursor: external sign-in link (cursor-agent login)")
            page.wait_for_function("""() => /已登录|signed in/.test(document.querySelector('.agent-login[data-rid="cursor"] .agent-login-head')?.textContent || '')""",
                                   timeout=40000)
            ubox.scroll_into_view_if_needed()
            shots.take(page, "A", "cursor-signed-in", note="Cursor signed in (account shown by cursor-agent status)")
            report["steps"].append({"step": "cursor-auth", **api(hub, "/api/runtimes/cursor/auth")})

            # ── 4. chat through each agent ──────────────────────────────
            for rid, text in (("claude-code", "请读一下工作区并总结项目结构"), ("codex", "列出工作区里的文件"),
                              ("cursor", "读一下 notes.md 并总结")):
                api(hub, "/api/runtimes/connect", {"runtime": rid})
                close_control(page)
                page.reload(wait_until="domcontentloaded")
                page.wait_for_selector("#input", timeout=60000)
                page.wait_for_function("() => typeof state !== 'undefined' && !!state.currentId", timeout=60000)
                page.click("#btn-new")
                page.wait_for_timeout(1200)
                sd.command(page, text)
                wait_reply(page)
                last = page.locator("#messages .msg.assistant").last
                reply = last.inner_text()[:300]
                report["steps"].append({"step": f"chat-{rid}", "reply": reply})
                shots.take(page, "A", f"chat-{rid}", note=f"chat through {rid}: streamed reply + tool use")
            browser.close()
    finally:
        hub.stop()
        stub.terminate()
        (out / "demo.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = all(s.get("reply", "x") for s in report["steps"]) and all(
        any(s["step"] == f"chat-{rid}" for s in report["steps"]) for rid in ("codex", "cursor"))
    print("RESULT:", "PASS" if ok else "CHECK", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
