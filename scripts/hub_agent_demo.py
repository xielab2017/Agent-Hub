#!/usr/bin/env python3
"""Live check of the Hub agent through the UI: a configured model understands plain requests and acts.

    MINIMAX_KEY=… python scripts/hub_agent_demo.py --out outputs/hub_agent_demo

Three plain-language requests (no slash commands) to a Hub whose only "agent" is the configured model:
  1. a literature question            → the model should search PubMed itself and answer with citations
  2. "写一篇…综述（先小规模试跑）"   → the model should start the literature-review skill (progress card)
  3. "工作区里有哪些文件？…"          → the model should list / read the workspace
Each turn's tool steps are read back from the session and written to <out>/demo.json; screenshots to
<out>/screens/.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import skill_demo as sd  # noqa: E402

TURNS = [
    ("pubmed", "THBS4 在骨骼肌衰老中有哪些研究证据？请查一下文献，简要总结并给出 PMID。", ["pubmed_search"]),
    ("skill", "帮我写一篇关于 GDF15 与衰老和代谢的英文综述，先小规模试跑一下看看效果。", ["run_skill"]),
    ("files", "工作区里有哪些文件？读一下 notes.md 并告诉我下一步该做什么。", ["list_files", "read_file"]),
]


def api(hub: sd.Hub, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(hub.url + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "outputs" / "hub_agent_demo"))
    ap.add_argument("--skill-timeout-min", type=int, default=20)
    ap.add_argument("--stub", action="store_true", help="offline rehearsal with scripts/stub_llm.py")
    args = ap.parse_args()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    import shutil

    for old in ("screens", "skill_run"):  # one run = one record (earlier runs stay in git history)
        shutil.rmtree(out / old, ignore_errors=True)
    report: dict = {"run_url": sd.RUN_URL, "turns": []}
    from playwright.sync_api import sync_playwright

    stub = None
    if args.stub:  # offline rehearsal: the stub model speaks the agent protocol
        import subprocess

        stub = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "stub_llm.py"), "--port", "9911"])
        time.sleep(1)
    hub = sd.Hub("A", 8765, "http://127.0.0.1:9911/v1" if args.stub else "", setup_args=[] if args.stub else ["--agent"])
    if args.stub:
        cfg_agent = {"ali": {"hub_chat_mode": "agent"}}
        api(hub, "/api/settings", cfg_agent)
    ws = hub.home / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "notes.md").write_text("# 项目笔记\n\n- 目标：投稿一篇 GDF15 与衰老代谢的综述\n- 已完成：文献检索草案\n"
                                 "- 待办：请导师审阅提纲；补充人群队列证据\n", encoding="utf-8")
    (ws / "outline.txt").write_text("1. Introduction\n2. GDF15 biology\n3. Ageing\n4. Metabolism\n", encoding="utf-8")
    cfg_body = {"workspace": str(ws)}
    try:
        api(hub, "/api/settings", cfg_body)
    except Exception as exc:  # noqa: BLE001
        report["workspace_error"] = str(exc)
    # the runnable skill the agent may choose
    report["skill_install"] = api(hub, "/api/skills/install", {"path": str(ROOT / "skills" / "literature-review")}).get("id")
    shots = sd.Shots(out)
    ok_all = True
    try:
        with sync_playwright() as pw:
            exe = os.environ.get("CHROMIUM_PATH")
            browser = pw.chromium.launch(**({"executable_path": exe} if exe else {}))
            page = sd.open_ui(browser, hub)
            shots.take(page, "A", "home", note="Hub with MiniMax-M3 only, chat mode Agent — no external agent")
            for key, text, expect in TURNS:
                page.click("#btn-new")
                page.wait_for_timeout(1200)
                sd.command(page, text)
                page.wait_for_timeout(2500)
                shots.take(page, "A", f"{key}-running", note=f"typed (plain language): {text[:60]}")
                page.wait_for_function("() => !((state.sessionRuns || {})[state.currentId] || {}).streaming",
                                       timeout=300000)
                page.wait_for_timeout(1500)
                sid = page.evaluate("() => state.currentId")
                sess = api(hub, f"/api/sessions/{sid}")
                msgs = (sess.get("session") or sess).get("messages") or []
                last = next((m for m in reversed(msgs) if m.get("role") == "assistant" and not m.get("skill_run")), {})
                route = last.get("route") or {}
                steps = route.get("agent_steps") or []
                used = [s["tool"] for s in steps]
                turn = {"turn": key, "engine": route.get("chat_engine"), "provider": route.get("provider"),
                        "model": route.get("model"), "tools": used, "expected": expect,
                        "steps": [{k: s.get(k) for k in ("tool", "args", "ok", "error")} for s in steps],
                        "ok": all(t in used for t in expect), "answer": (last.get("content") or "")[:600],
                        "skill_runs": route.get("skill_runs") or []}
                if key == "skill":  # the skill must actually have started, not just been attempted
                    turn["ok"] = turn["ok"] and bool(turn["skill_runs"])
                ok_all &= turn["ok"]
                page.locator("#messages .msg.assistant").last.scroll_into_view_if_needed()
                shots.take(page, "A", f"{key}-answer", note=f"agent used {', '.join(used) or 'no tools'}")
                if key == "skill" and turn["skill_runs"]:
                    run_id = turn["skill_runs"][0]
                    t0 = time.time()
                    while time.time() - t0 < args.skill_timeout_min * 60:
                        info = api(hub, f"/api/skill-runs/{run_id}")
                        if info.get("status") != "running":
                            break
                        if int(time.time() - t0) % 60 < 4:
                            page.locator(".msg.skill-run").last.scroll_into_view_if_needed()
                            shots.take(page, "A", "skill-progress", keep=False, note=f"skill run: {info.get('stage')}")
                        time.sleep(4)
                    info = api(hub, f"/api/skill-runs/{run_id}")
                    turn["skill_result"] = {k: info.get(k) for k in ("status", "stage", "summary", "outputs", "error")}
                    keep = out / "skill_run"  # the deliverable itself, so it can be opened from the branch
                    keep.mkdir(exist_ok=True)
                    for name in ("review.docx", "review_final.md", "citation_audit.json", "response_to_reviewers.md"):
                        src = Path(info.get("out") or "") / name
                        if src.is_file():
                            shutil.copy2(src, keep / name)
                    page.wait_for_timeout(3000)
                    page.locator(".msg.skill-run").last.scroll_into_view_if_needed()
                    shots.take(page, "A", "skill-finished", note=f"skill run {info.get('status')}")
                    ok_all &= info.get("status") == "done"
                report["turns"].append(turn)
                (out / "demo.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
            # 4. the stop button on a running skill card (a full run, so it is still going when clicked)
            turn = {"turn": "stop", "expected": ["stopped"], "ok": False}
            try:
                page.click("#btn-new")
                page.wait_for_timeout(1200)
                if args.stub:  # offline the review fails in seconds; a slow stand-in skill exercises the button
                    slow = out / "slow-demo"
                    slow.mkdir(exist_ok=True)
                    (slow / "SKILL.md").write_text("---\nname: slow-demo\ndescription: slow stand-in for the stop "
                                                   "check\nentry: run.py\n---\n\n# Slow demo\n", encoding="utf-8")
                    (slow / "run.py").write_text(
                        "import argparse, pathlib, time\nap = argparse.ArgumentParser(); ap.add_argument('--out'); "
                        "ap.add_argument('--topic', default='')\na = ap.parse_args()\n"
                        "pathlib.Path(a.out, 'evidence_cards.json').write_text('[]')\n"
                        "for i in range(600):\n    print(f'[{i:6d}s] working', flush=True); time.sleep(1)\n",
                        encoding="utf-8")
                    api(hub, "/api/skills/install", {"path": str(slow)})
                    sd.command(page, "/skill slow-demo GDF15")
                else:
                    sd.command(page, "/skill literature-review GDF15 and exercise adaptation in skeletal muscle")
                card = page.locator(".msg.skill-run").last
                stop = card.locator(".skill-run-stop")
                stop.wait_for(state="visible", timeout=120000)
                page.wait_for_timeout(15000)
                card.scroll_into_view_if_needed()
                shots.take(page, "A", "stop-running", note="skill running — ■ 停止 button on the card")
                stop.click()
                page.wait_for_function("() => { const c = [...document.querySelectorAll('.msg.skill-run')].pop();"
                                       " return c && c.classList.contains('stopped'); }", timeout=60000)
                page.wait_for_timeout(1000)
                card.scroll_into_view_if_needed()
                shots.take(page, "A", "stop-done", note="clicked ■ 停止 — run stopped, partial files kept")
                info = api(hub, f"/api/skill-runs/{card.get_attribute('data-run')}")
                turn.update(ok=info.get("status") == "stopped", status=info.get("status"), stage=info.get("stage"),
                            outputs=[o["name"] for o in info.get("outputs") or []])
            except Exception as exc:  # noqa: BLE001 — recorded, the screenshots show where it stopped
                turn["error"] = f"{type(exc).__name__}: {exc}"[:300]
                shots.take(page, "A", "stop-error", note=turn["error"][:120])
            ok_all &= turn["ok"]
            report["turns"].append(turn)
            browser.close()
    finally:
        hub.stop()
        if stub:
            stub.terminate()
        (out / "demo.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    for t in report["turns"]:
        if t["turn"] == "stop":
            print(f"stop    status={t.get('status')} outputs={t.get('outputs')} ok={t['ok']} {t.get('error', '')}",
                  flush=True)
            continue
        print(f"{t['turn']:7s} engine={t['engine']} tools={t['tools']} ok={t['ok']}", flush=True)
    print("RESULT:", "PASS" if ok_all else "CHECK", flush=True)
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
