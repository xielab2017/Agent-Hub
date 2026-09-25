#!/usr/bin/env python3
"""Live check of Agent Hub against a real MiniMax account (one command).

    MINIMAX_KEY='sk-...' python scripts/minimax_live_check.py [--region auto|minimax-cn|minimax] [--quick]

(The Claude Code style ANTHROPIC_BASE_URL=https://api.minimax.cn/anthropic +
ANTHROPIC_API_KEY='sk-...' is picked up too.)

What it does, in a throw-away state directory (your real Agent Hub settings are
never touched, the key is never printed — every line of output is masked):

 1. region   — which MiniMax region accepts the key (China api.minimaxi.com /
               global api.minimax.io) and which models it lists
 2. chat     — one direct streamed reply through the Hub pipeline
               (review + sealed provenance record)
 3. search   — a research question with web search + page reading + evidence
 4. memory   — a follow-up that needs the previous turn
 5. task     — a 3-step scientific task, auto-advancing (skipped with --quick)
 6. errors   — a wrong model name must come back as a clear error

Exit code 0 when every step passed.  Needs network access to the MiniMax host
(and to search engines / PubMed for step 3).
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
_ANTHROPIC_BASE = (os.environ.get("ANTHROPIC_BASE_URL") or "").strip()
KEY = (os.environ.get("MINIMAX_KEY") or os.environ.get("MINIMAX_CN_API_KEY") or os.environ.get("MINIMAX_API_KEY")
       or (os.environ.get("ANTHROPIC_API_KEY") if "minimax" in _ANTHROPIC_BASE.lower() else "") or "").strip()


def mask(text: object) -> str:
    s = str(text)
    if KEY:
        s = s.replace(KEY, KEY[:6] + "…" + KEY[-4:])
    return re.sub(r"sk-[A-Za-z0-9_\-]{16,}", lambda m: m.group(0)[:6] + "…" + m.group(0)[-4:], s)


def say(*parts: object) -> None:
    print(mask(" ".join(str(p) for p in parts)), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--region", default="auto", choices=("auto", "minimax-cn", "minimax"))
    ap.add_argument("--model", default="", help="model id (default: MiniMax-M2, or the first listed)")
    ap.add_argument("--quick", action="store_true", help="skip the multi-step task")
    args = ap.parse_args()
    if not KEY:
        say("Set MINIMAX_KEY (or MINIMAX_CN_API_KEY / MINIMAX_API_KEY) first.")
        return 2
    if KEY.startswith("cp-"):
        say("⚠ The key starts with 'cp-': a ${sk-cp-…} shell expansion drops 'sk-'. "
            "Use quotes instead: export MINIMAX_KEY='sk-cp-…'")

    tmp = Path(tempfile.mkdtemp(prefix="agenthub-minimax-"))
    for var, sub in (("HERMES_ALI_STATE_DIR", "state"), ("AGENT_CLI_HOME", "cli"), ("HERMES_HOME", "hermes"),
                     ("HERMES_ALI_AGENT_DIR", "no-agent")):
        os.environ[var] = str(tmp / sub)
    os.environ["HOME"] = str(tmp)
    sys.path.insert(0, str(ROOT))

    from ali import provenance, streaming, task_runner
    from ali import sessions as store
    from ali.providers import get_provider, probe_minimax_region
    from ali.secrets import set_api_key
    from ali.settings import load_campus_config, save_campus_config

    results: dict[str, object] = {}

    # 1. region ---------------------------------------------------------
    say("== 1. region / models")
    from ali import providers as providers_mod

    if _ANTHROPIC_BASE and "minimax" in _ANTHROPIC_BASE.lower():
        # try the endpoint the user already uses (e.g. Claude Code) first
        for pid in providers_mod.MINIMAX_REGIONS:
            urls = providers_mod.PROVIDERS[pid].setdefault("base_urls", [providers_mod.PROVIDERS[pid]["base_url"]])
            if ("minimax.io" in _ANTHROPIC_BASE) == (pid == "minimax"):
                urls[:] = [_ANTHROPIC_BASE.rstrip("/")] + [u for u in urls if u.rstrip("/") != _ANTHROPIC_BASE.rstrip("/")]
    probe = probe_minimax_region(KEY, timeout=15.0)
    for pid, r in probe["results"].items():
        for e in r.get("endpoints") or []:
            say(f"   {pid:11s} {e['base_url']:38s} ok={e['ok']} via={e['via']} {('error: ' + e['error'][:140]) if e['error'] else ''}")
        say(f"   {pid:11s} models={r['count']} {r['models'][:8]}")
    region = probe["region"] if args.region == "auto" else args.region
    if not region:
        say("   ✗ neither region accepted the key — check the key, or network access to api.minimaxi.com / api.minimax.io")
        return 1
    models = probe["results"].get(region, {}).get("models") or []
    model = args.model or ("MiniMax-M2" if not models or "MiniMax-M2" in models else models[0])
    base_url = (probe["results"].get(region) or {}).get("base_url") or get_provider(region)["base_url"]
    say(f"   ✓ region={region} endpoint={base_url} model={model}")
    results["region"] = region
    results["endpoint"] = base_url

    cfg = load_campus_config()
    prov = get_provider(region)
    cfg["backend"] = {**(cfg.get("backend") or {}), "type": region, "base_url": base_url, "model": model,
                      "api_key_env": prov["api_key_env"], "verify_tls": True}
    cfg["models"] = {**(cfg.get("models") or {}), "fast": model, "main": model, "reasoning": model}
    cfg.setdefault("ali", {})["hub_chat_mode"] = "direct"
    save_campus_config(cfg)
    set_api_key(region, KEY)

    def run(sid: str, message: str, **kw: object) -> dict:
        t0 = time.time()
        res = streaming.start_chat(sid, message, model=model, **kw)
        deadline = t0 + 240
        while time.time() < deadline:
            job = streaming.JOBS.get(res["stream_id"]) or {}
            if any(e.get("event") == "done" for e in job.get("events") or []):
                break
            time.sleep(0.3)
        msg = [m for m in store.get_session(sid).messages if m.get("role") == "assistant"][-1]
        rec = provenance.load_record(sid, msg["id"]) or {}
        return {"msg": msg, "secs": round(time.time() - t0, 1), "verified": bool(rec) and provenance.verify_record(rec),
                "notes": [str(e["data"].get("text", ""))[:120] for e in (streaming.JOBS.get(res["stream_id"]) or {}).get("events", [])
                          if e.get("event") == "thinking"]}

    def show(label: str, out: dict, ok: bool) -> bool:
        m = out["msg"]
        rv = m.get("review") or {}
        cov = (m.get("evidence") or {}).get("coverage") or {}
        say(f"   {'✓' if ok else '✗'} {label}: {out['secs']}s error={bool(m.get('error'))} "
            f"review ok={rv.get('ok')} warn={rv.get('warn')} provenance={out['verified']}"
            + (f" sources={cov.get('sources')} read={cov.get('pages_read')} conflicts={len((m.get('evidence') or {}).get('conflicts') or [])}" if cov else ""))
        say("     reply:", re.sub(r"\s+", " ", str(m.get("content") or ""))[:400])
        results[label] = ok
        return ok

    all_ok = True
    sid = store.create_session(title="minimax live check").id

    say("== 2. chat")
    out = run(sid, "用三句话解释什么是肌肉因子（myokine），并举一个例子。", web_search=False)
    all_ok &= show("chat", out, not out["msg"].get("error") and len(out["msg"].get("content") or "") > 20 and out["verified"])

    say("== 3. search + evidence")
    out = run(sid, "搜索：人血浆中鸢尾素（irisin）的浓度是多少？质谱和 ELISA 的结果为什么不一致？", web_search=True, deep_search=True)
    for n in out["notes"][:4]:
        say("     ·", n)
    all_ok &= show("search", out, not out["msg"].get("error") and bool(re.search(r"\[\d+\]", out["msg"].get("content") or "")))

    say("== 4. memory")
    out = run(sid, "我上一个问题问的是什么？只用一句话回答。", web_search=False)
    all_ok &= show("memory", out, not out["msg"].get("error") and ("鸢尾素" in (out["msg"].get("content") or "") or "irisin" in (out["msg"].get("content") or "").lower()))

    if not args.quick:
        say("== 5. multi-step task")
        tsid = store.create_session(title="minimax task").id
        q = ("研究问题：运动能否提高人体循环鸢尾素水平？1. 检索关键文献并列出测量方法 "
             "2. 比较质谱与 ELISA 的结果并指出分歧 3. 设计一个验证实验（样本量、对照、测量方法）")
        created = task_runner.create_task(tsid, q, mode="auto")
        tid, nxt, steps_ok = created["task"]["id"], created["next"], True
        while True:
            o = run(tsid, nxt["prompt"], task_id=tid, task_step=nxt["step"], display_message=nxt["display"],
                    web_search=True if nxt["web_search"] else None, deep_search=True if nxt["web_search"] else None)
            m = o["msg"]
            say(f"   step {nxt['step']}/{nxt['total']} {nxt['title']}: {o['secs']}s error={bool(m.get('error'))} "
                f"warn={(m.get('review') or {}).get('warn')}")
            adv = task_runner.advance(tid, message_id=m["id"])
            if adv["status"] == "blocked" and adv.get("reason") == "review":
                say("     reviewer paused the task:", adv.get("issues"), "→ continuing")
                adv = task_runner.advance(tid, force=True)
            if adv["status"] == "blocked":
                steps_ok = False
                say("     ✗ task blocked:", adv.get("reason"))
                break
            if adv["status"] != "next":
                break
            nxt = adv
        final = task_runner.get_task(tid) or {}
        done = sum(1 for s in final.get("steps") or [] if s.get("status") in ("done", "skipped"))
        say(f"   {'✓' if steps_ok else '✗'} task: {final.get('status')} {done}/{len(final.get('steps') or [])} steps, "
            f"{len(final.get('sources') or [])} task sources")
        results["task"] = steps_ok
        all_ok &= steps_ok

    say("== 6. errors")
    cfg = load_campus_config()
    cfg["models"] = {**cfg["models"], "fast": "no-such-model", "main": "no-such-model", "reasoning": "no-such-model"}
    cfg["backend"]["model"] = "no-such-model"
    save_campus_config(cfg)
    esid = store.create_session(title="error").id
    res = streaming.start_chat(esid, "你好，请介绍一下你自己。", model="no-such-model", web_search=False)
    for _ in range(200):
        if any(e.get("event") == "done" for e in (streaming.JOBS.get(res["stream_id"]) or {}).get("events") or []):
            break
        time.sleep(0.3)
    em = [m for m in store.get_session(esid).messages if m.get("role") == "assistant"][-1]
    ok = bool(em.get("error"))
    say(f"   {'✓' if ok else '✗'} wrong model → error={em.get('error')}:", re.sub(r"\s+", " ", str(em.get("content")))[:300])
    results["errors"] = ok
    all_ok &= ok

    say("== summary", json.dumps(results, ensure_ascii=False), "→", "PASS" if all_ok else "FAIL")
    say(f"   (state kept in {tmp} — delete it when done; it holds the key)")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
