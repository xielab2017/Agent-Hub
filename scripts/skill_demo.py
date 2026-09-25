#!/usr/bin/env python3
"""Drive two Agent Hub instances through their web UI (Playwright) and screenshot every step.

Hub A  : `/skill-author literature-review` — the Hub's model writes SKILL.md for the pipeline and installs it;
         `/skill-export literature-review` — the skill bundle is downloaded.
Hub B  : a fresh state directory ("another machine"): the bundle is uploaded in Control Center → Skills, then
         `/skill literature-review profile=… out=…` runs the full review while screenshots are taken.

    MINIMAX_KEY=… python scripts/skill_demo.py --profile multiomics-emp [--smoke] --out outputs/skill_demo
    python scripts/skill_demo.py --stub --smoke --out /tmp/demo      # offline rehearsal (stub model, no PubMed)

Screenshots go to <out>/screens/NNN_<step>.png, the latest one also to <out>/screens/live.png, with a banner
naming the run (GitHub Actions run id when present) and the UTC time; <out>/live-log.txt mirrors the run log.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
RUN_URL = (f"{os.environ.get('GITHUB_SERVER_URL', '')}/{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/"
           f"{os.environ.get('GITHUB_RUN_ID', '')}") if os.environ.get("GITHUB_RUN_ID") else "local"


def say(*a: object) -> None:
    print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)


class Hub:
    """One Agent Hub server with its own state / home directories."""

    def __init__(self, name: str, port: int, stub: str = "") -> None:
        self.name, self.port = name, port
        self.url = f"http://127.0.0.1:{port}"
        self.home = Path(tempfile.mkdtemp(prefix=f"agenthub-{name}-"))
        self.env = {**os.environ, "HOME": str(self.home), "HERMES_ALI_STATE_DIR": str(self.home / "state"),
                    "AGENT_CLI_HOME": str(self.home / "cli"), "HERMES_HOME": str(self.home / "hermes"),
                    "HERMES_ALI_AGENT_DIR": str(self.home / "no-agent"), "HERMES_ALI_PASSWORD": "",
                    "PYTHONUNBUFFERED": "1"}
        setup = [PY, str(ROOT / "scripts" / "hub_setup.py")] + (["--stub", stub] if stub else [])
        out = subprocess.run(setup, env=self.env, capture_output=True, text=True, timeout=120)
        say(f"hub {name}:", (out.stdout or out.stderr).strip().splitlines()[-1:] or "")
        if out.returncode != 0:
            raise SystemExit(f"hub {name} setup failed: {out.stdout} {out.stderr}")
        self.log = open(self.home / "server.log", "w", encoding="utf-8")
        self.proc = subprocess.Popen([PY, str(ROOT / "server.py"), "--host", "127.0.0.1", "--port", str(port),
                                      "--no-browser"], env=self.env, cwd=str(ROOT), stdout=self.log,
                                     stderr=subprocess.STDOUT)
        for _ in range(120):
            try:
                with urllib.request.urlopen(self.url + "/api/health", timeout=2) as r:
                    if r.status == 200:
                        break
            except OSError:
                time.sleep(0.5)
        else:
            raise SystemExit(f"hub {name} did not start: {(self.home / 'server.log').read_text()[-2000:]}")
        say(f"hub {name} up at {self.url} (state {self.home})")

    def get(self, path: str) -> dict:
        with urllib.request.urlopen(self.url + path, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))

    def stop(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.log.close()


class Shots:
    def __init__(self, out: Path) -> None:
        self.dir = out / "screens"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.n = len(list(self.dir.glob("[0-9][0-9][0-9]_*.png")))
        self.index = self.dir / "index.md"

    def banner(self, page, hub: str, note: str = "") -> None:
        text = f"Agent Hub {hub} · {note} · {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} UTC · {RUN_URL}"
        page.evaluate("""(t) => { let b = document.getElementById('demo-banner');
            if (!b) { b = document.createElement('div'); b.id = 'demo-banner'; document.body.appendChild(b);
              b.style.cssText = 'position:fixed;left:0;right:0;bottom:0;z-index:99999;padding:4px 10px;font:12px monospace;' +
                'background:#111c;color:#fff;pointer-events:none'; }
            b.textContent = 'screenshot by scripts/skill_demo.py — ' + t; }""", text)

    def take(self, page, hub: str, step: str, *, keep: bool = True, note: str = "") -> Path:
        self.banner(page, hub, note or step)
        mask = [page.locator("input[type=password]"), page.locator(".key-masked")]  # no key fragments in shots
        live = self.dir / "live.png"
        page.screenshot(path=str(live), mask=mask)
        if not keep:
            return live
        self.n += 1
        dest = self.dir / f"{self.n:03d}_{hub}_{step}.png"
        shutil.copyfile(live, dest)
        with open(self.index, "a", encoding="utf-8") as fh:
            fh.write(f"- {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} UTC — `{dest.name}` — {note or step}\n")
        say("screenshot", dest.name)
        return dest


def open_ui(browser, hub: Hub):
    page = browser.new_page(viewport={"width": 1440, "height": 960}, accept_downloads=True)
    page.goto(hub.url + "/", wait_until="domcontentloaded")
    page.wait_for_selector("#input", timeout=60000)
    page.wait_for_function("() => typeof state !== 'undefined' && !!state.currentId", timeout=60000)
    page.wait_for_timeout(1500)
    return page


def command(page, text: str) -> None:
    page.fill("#input", text)
    page.press("#input", "Control+Enter")


def last_card(page):
    return page.locator(".msg.skill-run").last


def wait_card(page, shots: Shots, hub: str, step: str, timeout_s: int, *, every_s: int = 60,
              keep_every_s: int = 300, on_tick=None) -> str:
    """Wait until the newest skill card leaves the running state; screenshot periodically."""
    t0 = last = kept = time.time()
    while time.time() - t0 < timeout_s:
        status = last_card(page).locator(".skill-run-status").inner_text(timeout=10000)
        if status.startswith(("✓", "✗")):
            return status
        if time.time() - last >= every_s:
            last_card(page).scroll_into_view_if_needed()
            keep = time.time() - kept >= keep_every_s
            shots.take(page, hub, step, keep=keep, note=f"{step}: {status}")
            kept = time.time() if keep else kept
            last = time.time()
        if on_tick:
            on_tick()
        page.wait_for_timeout(3000)
    return "timeout"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", default="multiomics-emp")
    ap.add_argument("--out", default=str(ROOT / "outputs" / "skill_demo"))
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--author-run", default=str(ROOT / "outputs" / "thbs4_review"),
                    help="a finished run the Hub's model may learn from when authoring the skill")
    ap.add_argument("--stub", action="store_true", help="offline rehearsal with scripts/stub_llm.py")
    ap.add_argument("--timeout-min", type=int, default=140)
    args = ap.parse_args()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    review_out = out / ("smoke" if args.smoke else "review")
    report: dict = {"run_url": RUN_URL, "profile": args.profile, "smoke": args.smoke, "steps": []}

    stub_proc = None
    stub = ""
    if args.stub:
        stub_proc = subprocess.Popen([PY, str(ROOT / "scripts" / "stub_llm.py"), "--port", "9911"])
        stub = "http://127.0.0.1:9911/v1"
        time.sleep(1)

    from playwright.sync_api import sync_playwright

    hubs: list[Hub] = []
    shots = Shots(out)
    try:
        with sync_playwright() as pw:
            exe = os.environ.get("CHROMIUM_PATH")
            browser = pw.chromium.launch(**({"executable_path": exe} if exe else {}))

            # ── Hub A: author + export ─────────────────────────────────
            a = Hub("A", 8765, stub)
            hubs.append(a)
            page = open_ui(browser, a)
            shots.take(page, "A", "home", note="Hub A started (fresh state, model configured)")
            ar = Path(args.author_run).resolve()
            author_cmd = "/skill-author literature-review" + (f" run={ar.relative_to(ROOT) if ar.is_relative_to(ROOT) else ar}"
                                                              if ar.exists() else "")
            command(page, author_cmd)
            page.wait_for_timeout(2000)
            shots.take(page, "A", "authoring", note=f"typed: {author_cmd}")
            status = wait_card(page, shots, "A", "authoring", 20 * 60, every_s=30, keep_every_s=90)
            card = last_card(page)
            card.scroll_into_view_if_needed()
            shots.take(page, "A", "authored", note=f"skill authored: {status}")
            report["steps"].append({"hub": "A", "step": "author", "status": status})
            if not status.startswith("✓"):
                (out / "SKILL.rejected.md").write_text(card.locator(".skill-run-log").inner_text(), encoding="utf-8")
                raise SystemExit(f"authoring failed: {status}")
            md = card.locator(".skill-run-log").inner_text()
            (out / "SKILL.authored.md").write_text(md, encoding="utf-8")
            with page.expect_download(timeout=60000) as dl:
                command(page, "/skill-export literature-review")
            bundle = out / "literature-review.zip"
            dl.value.save_as(str(bundle))
            page.wait_for_timeout(1000)
            shots.take(page, "A", "exported", note=f"skill exported: {bundle.name} ({bundle.stat().st_size} bytes)")
            report["steps"].append({"hub": "A", "step": "export", "bytes": bundle.stat().st_size})
            page.close()
            a.stop()

            # ── Hub B: import + run ───────────────────────────────────
            b = Hub("B", 8766, stub)
            hubs.append(b)
            page = open_ui(browser, b)
            shots.take(page, "B", "home", note="Hub B started — fresh state, no literature-review skill")
            page.click("#btn-control")
            page.click("[data-ctab=skills]")
            page.wait_for_selector("#skill-zip-input", state="attached", timeout=30000)
            page.set_input_files("#skill-zip-input", str(bundle))
            page.wait_for_function("() => /literature-review/.test(document.getElementById('settings-status')?.textContent"
                                   " || '')", timeout=60000)
            page.wait_for_timeout(1500)
            page.evaluate("""() => { const el = [...document.querySelectorAll('#ctab-skills *')].find(e =>
                e.children.length === 0 && /literature-review/.test(e.textContent));
                if (el) { el.scrollIntoView({block: 'center'}); el.style.outline = '3px solid #e33'; } }""")
            shots.take(page, "B", "imported", note="bundle uploaded in Control Center → Skills and installed")
            installed = [s for s in b.get("/api/skills")["skills"] if s["id"] == "literature-review"]
            report["steps"].append({"hub": "B", "step": "import", "installed": bool(installed),
                                    "entry": installed[0].get("entry") if installed else None,
                                    "origin": installed[0].get("origin") if installed else None})
            page.click("#btn-control-close")

            shown = review_out.relative_to(ROOT) if review_out.is_relative_to(ROOT) else review_out
            run_cmd = f"/skill literature-review profile={args.profile} out={shown}" + (" smoke" if args.smoke else "") \
                + (" fresh" if args.fresh else "")
            command(page, run_cmd)
            page.wait_for_timeout(3000)
            shots.take(page, "B", "run-started", note=f"typed: {run_cmd}")

            def mirror_log() -> None:
                try:
                    runs = b.get("/api/skill-runs")["runs"]
                    if runs:
                        info = b.get(f"/api/skill-runs/{runs[0]['id']}")
                        (out / "live-log.txt").write_text("\n".join(info.get("lines") or []), encoding="utf-8")
                        report["run"] = {k: info.get(k) for k in ("id", "status", "stage", "returncode", "outputs",
                                                                   "summary", "error")}
                        (out / "demo.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
                except OSError:
                    pass

            status = wait_card(page, shots, "B", "running", args.timeout_min * 60, on_tick=mirror_log)
            mirror_log()
            last_card(page).scroll_into_view_if_needed()
            page.wait_for_timeout(1000)
            shots.take(page, "B", "finished", note=f"skill run finished: {status}")
            report["steps"].append({"hub": "B", "step": "run", "status": status})
            page.close()
            browser.close()
    finally:
        for h in hubs:
            try:
                h.stop()
            except Exception:  # noqa: BLE001
                pass
        if stub_proc:
            stub_proc.terminate()
        (out / "demo.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = bool(report.get("run", {}).get("status") == "done")
    say("RESULT:", "PASS" if ok else "CHECK", json.dumps(report.get("run", {}).get("summary") or {}, ensure_ascii=False)[:400])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
