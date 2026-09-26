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
            page.locator(".conn-grid:not(.agent-grid)").scroll_into_view_if_needed()
            shots.take(page, "A", "vendor-cards", note="vendor cards: own key (masked), endpoint, TLS, test status")
            close_control(page)
            if key:
                sd.command(page, "请写一段简短的实验室组会通知，时间周五下午三点。")
                wait_reply(page)
                shots.take(page, "A", "office-chat", note="office-tier chat answered by MiniMax-M3 (hybrid routing)")

            # ── 2. accounts live in 多模型 API: quick sign-in (several at once) ─────────
            open_tab(page, "connections")
            page.locator(".quick-login-bar").scroll_into_view_if_needed()
            shots.take(page, "A", "accounts", note="多模型 API: quick sign-in bar + Claude / ChatGPT(Codex) / Cursor accounts")
            # Claude subscription: one click → the official sign-in page opens in a new tab by itself
            with page.context.expect_page() as tab:
                page.click('.quick-login[data-rid="claude-code"]')
            box = page.locator('.agent-login[data-rid="claude-code"]')
            page.wait_for_selector('.agent-login[data-rid="claude-code"] .agent-login-url', timeout=30000)
            page.wait_for_timeout(1500)
            box.scroll_into_view_if_needed()
            shots.take(page, "A", "claude-quick", note="⚡ Claude 一键登录: sign-in page opened in a new tab, code box ready")
            report["steps"].append({"step": "claude-link", "url": box.locator(".agent-login-url").get_attribute("href"),
                                    "auth_tab": tab.value.url})
            box.locator(".agent-login-input").fill("demo-authorisation-code")
            box.locator(".agent-login-send").click()
            page.wait_for_function("""() => /已登录|signed in/.test(document.querySelector('.agent-login[data-rid="claude-code"] .agent-login-head')?.textContent || '')""",
                                   timeout=40000)
            report["steps"].append({"step": "claude-auth", **api(hub, "/api/runtimes/claude-code/auth")})
            # ChatGPT via Codex: device code inside its account card
            page.wait_for_timeout(1500)
            cbox = page.locator('.agent-login[data-rid="codex"]')
            cbox.scroll_into_view_if_needed()
            cbox.locator('[data-login="device"]').click()
            page.wait_for_selector('.agent-login[data-rid="codex"] .agent-login-code', timeout=30000)
            cbox.scroll_into_view_if_needed()
            shots.take(page, "A", "codex-device", note="ChatGPT (Codex): device-code sign-in in its account card")
            page.wait_for_function("""() => /已登录|signed in/.test(document.querySelector('.agent-login[data-rid="codex"] .agent-login-head')?.textContent || '')""",
                                   timeout=40000)
            report["steps"].append({"step": "codex-auth", **api(hub, "/api/runtimes/codex/auth")})
            # Cursor: one click, the sign-in page opens by itself; done when the browser authorises
            page.wait_for_timeout(1500)
            with page.context.expect_page() as tab2:
                page.click('.quick-login[data-rid="cursor"]')
            page.wait_for_function("""() => /已登录|signed in/.test(document.querySelector('.agent-login[data-rid="cursor"] .agent-login-head')?.textContent || '')""",
                                   timeout=40000)
            report["steps"].append({"step": "cursor-auth", **api(hub, "/api/runtimes/cursor/auth"),
                                    "auth_tab": tab2.value.url})
            page.wait_for_timeout(1500)
            page.locator(".quick-login-bar").scroll_into_view_if_needed()
            shots.take(page, "A", "accounts-signed-in", note="three accounts signed in at the same time")

            # ── 3. tier routing to accounts: reasoning → Claude, office → Cursor (buttons on the cards) ──
            page.locator('.agent-card[data-rid="claude-code"] .agent-bind[data-tiers="reasoning"]').click()
            page.wait_for_timeout(2500)
            page.locator('.agent-card[data-rid="cursor"] .agent-bind[data-tiers="office"]').click()
            page.wait_for_timeout(2500)
            page.click("#conn-route-test")
            page.wait_for_timeout(1500)
            page.locator(".conn-tiers").scroll_into_view_if_needed()
            shots.take(page, "A", "tiers-accounts", note="tier routing: reasoning → Claude subscription, office → Cursor")
            report["steps"].append({"step": "routes-accounts", "routes": api(hub, "/api/connections/route-test")["routes"]})
            # Claws now lists claws only
            open_tab(page, "runtimes")
            report["steps"].append({"step": "claws-clean", "agent_rows": page.locator('#ctab-runtimes .agent-login').count()})
            shots.take(page, "A", "claws", note="Claws: claws only — agent accounts moved to 多模型 API")

            # ── 4. chat: each account answers the tier it is bound to ────────────────
            for rid, tiers, text in (("claude-code", "reasoning", "证明根号二是无理数，并说明思路"),
                                     ("cursor", "office", "写一封实验室组会通知，时间周五下午三点"),
                                     ("codex", "all", "列出工作区里的文件并说明用途")):
                if tiers == "all":
                    for rk in ("simple", "office", "reasoning", "vision"):
                        api(hub, "/api/connections/tier", {"route_key": rk, "provider": rid, "model": ""})
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
                report["steps"].append({"step": f"chat-{rid}", "tier": tiers, "reply": reply})
                shots.take(page, "A", f"chat-{rid}", note=f"{tiers} tier → {rid} account answers")
            # ── 5. one model picker for every source: tick several → fused answer ─────────
            close_control(page)
            page.reload(wait_until="domcontentloaded")
            page.wait_for_selector("#input", timeout=60000)
            page.wait_for_function("() => typeof state !== 'undefined' && !!state.currentId", timeout=60000)
            page.click("#btn-new")
            page.wait_for_timeout(1200)
            api_src = "minimax-cn::MiniMax-M3" if key else "campus-openai-compatible::stub-model"
            if not key:
                api(hub, "/api/connections/campus-openai-compatible/test", {})
            picks = [api_src, "claude-code::opus", "cursor::"]
            page.click("#model-pick-btn")
            page.wait_for_selector(".model-pick-row", timeout=60000)
            for sid in picks:
                page.locator(f'.model-pick-row[data-id="{sid}"] input').check()
            page.wait_for_timeout(600)
            shots.take(page, "A", "picker", note="模型按钮: API models + signed-in accounts in one list, three ticked")
            report["steps"].append({"step": "picker", "button": page.inner_text("#model-pick-btn")})
            page.click("#input")
            sd.command(page, "比较 CRISPR-Cas9 与碱基编辑在脱靶风险上的差异，给出简明结论。")
            page.wait_for_timeout(4000)
            shots.take(page, "A", "fusion-running", note="fusion: each model answering (progress per model)")
            wait_reply(page, timeout_s=420)
            last = page.locator("#messages .msg.assistant").last
            box = last.locator(".fusion-box")
            if box.count():
                box.locator("summary").click()
                page.wait_for_timeout(600)
            last.scroll_into_view_if_needed()
            shots.take(page, "A", "fusion-answer", note="fused answer + each model's own answer (expanded)")
            sid_now = page.evaluate("() => state.currentId")
            sess = api(hub, f"/api/sessions/{sid_now}")
            msgs = (sess.get("session") or sess).get("messages") or []
            fm = next((m for m in reversed(msgs) if m.get("role") == "assistant"), {})
            fus = (fm.get("route") or {}).get("fusion") or {}
            report["steps"].append({"step": "fusion", "engine": (fm.get("route") or {}).get("chat_engine"),
                                    "synthesizer": fus.get("synthesizer"), "reply": (fm.get("content") or "")[:400],
                                    "members": [{k: x.get(k) for k in ("label", "ok", "seconds", "error")}
                                                for x in fus.get("members") or []]})
            browser.close()
    finally:
        hub.stop()
        stub.terminate()
        (out / "demo.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    steps = {s["step"]: s for s in report["steps"]}
    ok = (all(s.get("reply", "x") for s in report["steps"])
          and all(steps.get(f"{name}-auth", {}).get("logged_in") for name in ("claude", "codex", "cursor"))
          and all(rid in (steps.get(f"chat-{rid}") or {}).get("reply", "").replace("Claude Code", "claude-code")
                  .replace("OpenAI Codex", "codex").replace("Cursor", "cursor") for rid in ("claude-code", "codex", "cursor"))
          and steps.get("claws-clean", {}).get("agent_rows") == 0
          and steps.get("fusion", {}).get("engine") == "fusion"
          and sum(1 for m in steps.get("fusion", {}).get("members", []) if m.get("ok")) >= 3)
    print("RESULT:", "PASS" if ok else "CHECK", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
