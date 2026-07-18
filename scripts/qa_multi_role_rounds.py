#!/usr/bin/env python3
"""Multi-role Hub QA harness: user / engineer / supervisor test loops."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

# Local Hub must bypass HTTP(S)_PROXY (e.g. Clash :7890) or requests hang.
os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
os.environ.setdefault("no_proxy", "127.0.0.1,localhost")

BASE = "http://127.0.0.1:8765"
OUT = Path.home() / ".hermes" / "ali" / "qa-round-report.jsonl"
OUT.parent.mkdir(parents=True, exist_ok=True)

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def req(method: str, path: str, body: dict | None = None, timeout: float = 180) -> tuple[int, Any, float]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    t0 = time.perf_counter()
    try:
        with _OPENER.open(r, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            elapsed = time.perf_counter() - t0
            try:
                payload = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                payload = {"_raw": raw[:500]}
            return int(resp.status), payload, elapsed
    except urllib.error.HTTPError as e:
        elapsed = time.perf_counter() - t0
        raw = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {"error": str(e)}
        except json.JSONDecodeError:
            payload = {"error": raw[:500] or str(e)}
        return int(e.code), payload, elapsed
    except Exception as e:  # noqa: BLE001
        elapsed = time.perf_counter() - t0
        return 0, {"error": f"{type(e).__name__}: {e}"}, elapsed


def log_row(row: dict[str, Any]) -> None:
    with OUT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    role = row.get("role", "?")
    round_id = row.get("round", "?")
    verdict = row.get("verdict", "?")
    title = row.get("title", "")
    print(f"[R{round_id}|{role}|{verdict}] {title}", flush=True)
    if row.get("issues"):
        for issue in row["issues"]:
            print(f"    ! {issue}", flush=True)
    if row.get("metrics"):
        print(f"    metrics={row['metrics']}", flush=True)


def create_session(title: str) -> str:
    code, data, _ = req("POST", "/api/sessions", {"title": title})
    if code >= 400:
        raise RuntimeError(f"create session failed: {code} {data}")
    sid = data.get("id") or (data.get("session") or {}).get("id") or data.get("session_id")
    if not sid:
        # list and pick newest
        code2, lst, _ = req("GET", "/api/sessions")
        sessions = lst if isinstance(lst, list) else (lst.get("sessions") or [])
        if sessions:
            sid = sessions[0].get("id")
    if not sid:
        raise RuntimeError(f"no session id: {data}")
    return str(sid)


def drain_stream(stream_id: str, timeout: float = 90) -> tuple[str, float, list[str]]:
    t0 = time.perf_counter()
    headers = {"Accept": "text/event-stream"}
    r = urllib.request.Request(
        f"{BASE}/api/stream/{urllib.request.quote(stream_id)}?from=0",
        headers=headers,
        method="GET",
    )
    text_parts: list[str] = []
    events: list[str] = []
    # IMPORTANT: do not set a short socket timeout and then continue — after the
    # first timeout macOS/python sockets often become permanently unreadable.
    with _OPENER.open(r, timeout=timeout) as resp:
        while True:
            if time.perf_counter() - t0 > timeout:
                return "".join(text_parts), time.perf_counter() - t0, events + ["timeout"]
            try:
                # SSE responses are line-framed and often smaller than 4 KiB.
                # read(4096) waits for a full block on some macOS urllib
                # sockets, falsely turning a valid short reply into an empty
                # stream timeout.
                line = resp.readline()
            except TimeoutError:
                return "".join(text_parts), time.perf_counter() - t0, events + ["timeout"]
            except Exception as exc:  # noqa: BLE001
                return "".join(text_parts), time.perf_counter() - t0, events + [f"read_error:{type(exc).__name__}"]
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace").rstrip("\r\n")
            if decoded.startswith(":") or not decoded:
                continue
            if decoded.startswith("event:"):
                events.append(decoded[6:].strip())
                continue
            if not decoded.startswith("data:"):
                continue
            data_line = decoded[5:].strip()
            try:
                payload = json.loads(data_line)
            except json.JSONDecodeError:
                continue
            event = events[-1] if events else "message"
            if event == "token" and isinstance(payload.get("text"), str):
                text_parts.append(payload["text"])
            elif event in ("done", "error", "cancelled"):
                elapsed = time.perf_counter() - t0
                if event == "error":
                    return "".join(text_parts), elapsed, events + [f"error:{payload}"]
                return "".join(text_parts), elapsed, events
    return "".join(text_parts), time.perf_counter() - t0, events


def chat_once(session_id: str, message: str, **extra: Any) -> dict[str, Any]:
    body = {"message": message, **extra}
    code, data, start_ms = req("POST", f"/api/sessions/{session_id}/chat", body, timeout=60)
    if code >= 400 or not data.get("stream_id"):
        return {
            "ok": False,
            "http": code,
            "error": data,
            "plan_ms": start_ms,
            "stream_ms": 0,
            "total_ms": start_ms,
            "text": "",
            "events": [],
        }
    text, stream_ms, events = drain_stream(str(data["stream_id"]), timeout=45)
    timed_out = "timeout" in events
    has_done = "done" in events
    # Some providers stream tokens but never close SSE; treat substantial text as success.
    ok = bool((text or "").strip()) and (has_done or len((text or "").strip()) >= 8)
    err = None
    if not ok:
        if timed_out and not (text or "").strip():
            err = "stream timeout with empty reply"
        elif timed_out:
            err = "stream timeout before done"
        else:
            err = data.get("error") or "empty reply"
    return {
        "ok": ok,
        "http": code,
        "stream_id": data.get("stream_id"),
        "model": data.get("model") or (data.get("route") or {}).get("model"),
        "plan_ms": start_ms,
        "stream_ms": stream_ms,
        "total_ms": start_ms + stream_ms,
        "text": text,
        "events": events,
        "route": data.get("route"),
        "timed_out": timed_out,
        "error": err,
    }


def auto_plan(message: str, **kw: Any) -> tuple[dict[str, Any], float]:
    code, data, elapsed = req("POST", "/api/agents/auto-plan", {"message": message, **kw}, timeout=120)
    data = data if isinstance(data, dict) else {"error": data}
    data["_http"] = code
    return data, elapsed


def main() -> None:
    if OUT.exists():
        OUT.write_text("", encoding="utf-8")
    report: list[dict[str, Any]] = []
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"=== Hub QA start {stamp} ===", flush=True)
    code, health, _ = req("GET", "/api/health", timeout=10)
    print(f"health http={code} ok={health.get('ok') if isinstance(health, dict) else health}", flush=True)
    if code != 200:
        raise SystemExit("Hub not healthy; abort QA")

    # ---------- Round 1: User — greeting single session ----------
    issues: list[str] = []
    plan, plan_ms = auto_plan("你好", run_search=False)
    if plan.get("need_parallel"):
        issues.append("greeting incorrectly planned as parallel")
    sid = create_session("qa-r1-greet")
    chat = chat_once(sid, "你好")
    if not chat["ok"]:
        issues.append(f"chat failed: {chat.get('error')}")
    elif len(chat["text"].strip()) < 2:
        issues.append("empty greeting reply")
    row = {
        "round": 1,
        "role": "user",
        "title": "单一会话问候",
        "verdict": "PASS" if not issues else "FAIL",
        "issues": issues,
        "metrics": {
            "plan_ms": round(plan_ms, 3),
            "chat_total_ms": round(chat.get("total_ms", 0), 3),
            "need_parallel": plan.get("need_parallel"),
            "reply_chars": len(chat.get("text") or ""),
        },
        "output_preview": (chat.get("text") or "")[:240],
    }
    log_row(row)
    report.append(row)

    # ---------- Round 2: User — single session factual Q ----------
    issues = []
    sid = create_session("qa-r2-single-fact")
    q2 = "用三句话解释 CRISPR 是什么，不要编造论文编号。"
    t0 = time.perf_counter()
    chat = chat_once(sid, q2, web_search=False)
    single_ms = time.perf_counter() - t0
    if not chat["ok"]:
        issues.append(f"single fact chat failed: {chat.get('error')}")
    if "CRISPR" not in (chat.get("text") or "").upper() and "基因" not in (chat.get("text") or ""):
        issues.append("reply missing CRISPR/gene keywords")
    row = {
        "round": 2,
        "role": "user",
        "title": "单 Agent 事实问答（无强制搜索）",
        "verdict": "PASS" if not issues else "FAIL",
        "issues": issues,
        "metrics": {"total_ms": round(single_ms, 3), "chat_total_ms": round(chat.get("total_ms", 0), 3), "reply_chars": len(chat.get("text") or "")},
        "output_preview": (chat.get("text") or "")[:300],
        "baseline_single_ms": single_ms,
    }
    log_row(row)
    report.append(row)
    baseline_single_ms = single_ms

    # ---------- Round 3: User — news search summary ----------
    issues = []
    q3 = "请联网检索并总结今天关于人工智能的3条重要新闻，每条附来源URL。"
    plan, plan_ms = auto_plan(q3, web_search=True, run_search=True)
    if not plan.get("needs_search") and not plan.get("search_enabled"):
        issues.append("planner did not enable search for news request")
    if plan.get("_http", 200) >= 400:
        issues.append(f"auto-plan http {plan.get('_http')}: {plan.get('error')}")
    sources = plan.get("sources") or []
    if plan.get("search_enabled") and len(sources) < 1:
        issues.append("search enabled but zero sources returned")
    # Prefer single session with web_search if not parallel, else still measure plan+optional chat
    sid = create_session("qa-r3-news")
    t0 = time.perf_counter()
    if plan.get("need_parallel") and len(plan.get("lanes") or []) >= 2:
        # Use first lane system context + single chat for speed in this round
        chat = chat_once(
            sid,
            q3,
            web_search=True,
            system=(plan.get("search_context") or "")[:4000],
        )
    else:
        chat = chat_once(sid, q3, web_search=True, system=(plan.get("search_context") or "")[:4000])
    news_ms = time.perf_counter() - t0
    text = chat.get("text") or ""
    if "http" not in text.lower() and not sources:
        issues.append("news reply has no URL and no plan sources")
    row = {
        "round": 3,
        "role": "user",
        "title": "实时新闻搜索总结",
        "verdict": "PASS" if not issues else "FAIL",
        "issues": issues,
        "metrics": {
            "plan_ms": round(plan_ms, 3),
            "chat_total_ms": round(chat.get("total_ms", 0), 3),
            "wall_ms": round(news_ms, 3),
            "sources": len(sources),
            "need_parallel": plan.get("need_parallel"),
            "reply_chars": len(text),
        },
        "output_preview": text[:400],
        "source_urls": [s.get("url") for s in sources[:5]],
    }
    log_row(row)
    report.append(row)

    # ---------- Round 4: User — force 3 parallel via NL ----------
    issues = []
    q4 = "请分成三个子代理：1)检索本周AI安全政策要点 2)写一封给导师的汇报邮件草稿 3)审阅邮件语气是否得体；最后由主代理深度综合。"
    plan, plan_ms = auto_plan(q4, force_parallel=True, force_count=3, web_search=True, run_search=True)
    lanes = plan.get("lanes") or []
    if not plan.get("need_parallel") or len(lanes) < 3:
        issues.append(f"expected ≥3 lanes, got need={plan.get('need_parallel')} n={len(lanes)}")
    row = {
        "round": 4,
        "role": "user",
        "title": "强制3子代理规划（含搜索）",
        "verdict": "PASS" if not issues else "FAIL",
        "issues": issues,
        "metrics": {
            "plan_ms": round(plan_ms, 3),
            "lanes": len(lanes),
            "roles": [l.get("role") for l in lanes],
            "sources": len(plan.get("sources") or []),
            "source": plan.get("source"),
        },
        "output_preview": json.dumps({"lanes": [{"role": l.get("role"), "goal": l.get("goal")} for l in lanes]}, ensure_ascii=False)[:500],
    }
    log_row(row)
    report.append(row)
    plan3 = plan

    # ---------- Round 5: Engineer — execute 3 parallel lanes + synth timing ----------
    issues = []
    parent = create_session("qa-r5-multi-parent")
    lanes3 = (plan3.get("lanes") or [])[:3]

    def _run_lane(i: int, lane: dict[str, Any]) -> dict[str, Any]:
        child = create_session(f"qa-r5-lane-{i}")
        prompt = (
            f"【角色】{lane.get('role')}\n【目标】{lane.get('goal')}\n"
            f"【用户任务】{q4}\n请只完成本车道目标，输出简洁要点。"
        )
        system = lane.get("system") or plan3.get("search_context") or ""
        chat = chat_once(
            child,
            prompt,
            route=lane.get("route_hint") or "auto",
            model=lane.get("model") or lane.get("resolved_model") or "",
            soul_role=lane.get("soul_role") or "",
            subagent_id=lane.get("id") or "",
            system=system[:5000],
            web_search=bool(plan3.get("search_enabled")),
            execution_mode="workflow",
        )
        return {
            "i": i,
            "role": lane.get("role"),
            "ok": chat.get("ok"),
            "chars": len(chat.get("text") or ""),
            "text": (chat.get("text") or "")[:500],
            "total_s": float(chat.get("total_ms") or 0),
            "error": chat.get("error"),
        }

    t_multi0 = time.perf_counter()
    lane_results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(len(lanes3), 1)) as pool:
        futs = [pool.submit(_run_lane, i, lane) for i, lane in enumerate(lanes3)]
        for fut in as_completed(futs):
            lane_results.append(fut.result())
    parallel_wall = time.perf_counter() - t_multi0
    lane_results.sort(key=lambda x: x["i"])
    lane_times = [float(x["total_s"]) for x in lane_results]
    lane_texts = [
        {"role": x["role"], "ok": x["ok"], "chars": x["chars"], "text": x["text"]}
        for x in lane_results
    ]
    for x in lane_results:
        if not x.get("ok"):
            issues.append(f"lane {x['i']} failed: {x.get('error')}")
    # synthesis (after all lanes complete)
    matrix = "\n\n".join(
        f"### 来自 {x['role']}\n{x['text'] or '（无产出）'}" for x in lane_texts
    )
    synth_prompt = (
        "你是主代理。综合以下三路子代理结果，输出：1)总述 2)分节要点 3)风险与未证实处。\n"
        f"【用户任务】\n{q4}\n\n【矩阵】\n{matrix}"
    )
    t_synth0 = time.perf_counter()
    synth = chat_once(parent, synth_prompt, route="C2", execution_mode="workflow")
    synth_wall = time.perf_counter() - t_synth0
    multi_wall = time.perf_counter() - t_multi0
    if not synth.get("ok"):
        issues.append(f"synthesis failed: {synth.get('error')}")
    elif len(synth.get("text") or "") < 80:
        issues.append("synthesis too short")
    parallel_effective = max(lane_times) if lane_times else 0
    row = {
        "round": 5,
        "role": "engineer",
        "title": "3子代理并行执行 + 主代理合成",
        "verdict": "PASS" if not issues else "FAIL",
        "issues": issues,
        "metrics": {
            "lane_times_s": [round(x, 3) for x in lane_times],
            "max_lane_s": round(parallel_effective, 3),
            "sum_lane_s": round(sum(lane_times), 3),
            "parallel_wall_s": round(parallel_wall, 3),
            "synth_s": round(synth_wall, 3),
            "multi_wall_s": round(multi_wall, 3),
            "speedup_vs_sum": round(sum(lane_times) / parallel_wall, 3) if parallel_wall else None,
        },
        "output_preview": (synth.get("text") or "")[:500],
        "lane_previews": lane_texts,
    }
    log_row(row)
    report.append(row)

    # ---------- Round 6: Supervisor — single vs multi comparison ----------
    issues = []
    q6 = "调研本周AI安全政策要点，写导师汇报邮件，并审阅语气；请一次性完成。"
    sid = create_session("qa-r6-single-all")
    t0 = time.perf_counter()
    single_all = chat_once(sid, q6, web_search=True, route="auto")
    single_all_ms = time.perf_counter() - t0
    m5 = report[4]["metrics"]
    multi_s = float(m5.get("multi_wall_s") or m5.get("multi_wall_ms") or 0)
    single_s = single_all_ms
    if not single_all.get("ok"):
        issues.append(f"single-all failed: {single_all.get('error')}")
    verdict_note = (
        f"multi_wall={multi_s:.2f}s vs single_all={single_s:.2f}s; "
        f"delta={multi_s - single_s:.2f}s; "
        f"parallel_wall={float(m5.get('parallel_wall_s') or 0):.2f}s; "
        f"multi_sum_lanes={float(m5.get('sum_lane_s') or m5.get('sum_lane_ms') or 0):.2f}s; "
        f"speedup_vs_sum={m5.get('speedup_vs_sum')}"
    )
    row = {
        "round": 6,
        "role": "supervisor",
        "title": "多Agent vs 单Agent 耗时与质量对比",
        "verdict": "PASS" if not issues else "FAIL",
        "issues": issues,
        "metrics": {
            "multi_wall_s": round(multi_s, 3),
            "parallel_wall_s": round(float(m5.get("parallel_wall_s") or 0), 3),
            "single_all_s": round(single_s, 3),
            "delta_s": round(multi_s - single_s, 3),
            "multi_sum_lane_s": round(float(m5.get("sum_lane_s") or m5.get("sum_lane_ms") or 0), 3),
            "speedup_vs_sum": m5.get("speedup_vs_sum"),
            "single_reply_chars": len(single_all.get("text") or ""),
            "multi_synth_chars": len(report[4].get("output_preview") or ""),
            "note": verdict_note,
        },
        "output_preview": {
            "single": (single_all.get("text") or "")[:350],
            "multi_synth": (report[4].get("output_preview") or "")[:350],
        },
    }
    log_row(row)
    report.append(row)

    # ---------- Round 7: Engineer — find bugs from prior rounds ----------
    eng_issues: list[str] = []
    for r in report:
        for iss in r.get("issues") or []:
            eng_issues.append(f"R{r['round']}: {iss}")
    # Structural API checks
    code, _, _ = req("GET", "/api/webui/status")
    if code != 404:
        eng_issues.append(f"/api/webui/status expected 404 got {code}")
    code, agents_view, _ = req("GET", "/api/agents")
    ui = (agents_view or {}).get("ui") or {}
    if "auto_parallel" not in ui and "max_lanes" not in ui:
        eng_issues.append("agents.ui missing auto_parallel/max_lanes")
    # 5-lane force
    plan5, p5ms = auto_plan(
        "分成五个子代理分别做：背景、数据、分析、可视化、审阅；主题：校园节能减碳方案。",
        force_parallel=True,
        force_count=5,
        run_search=False,
    )
    n5 = len(plan5.get("lanes") or [])
    if n5 < 5:
        eng_issues.append(f"force 5 lanes got {n5}")
    row = {
        "round": 7,
        "role": "engineer",
        "title": "缺陷汇总 + 5车道规划冒烟",
        "verdict": "PASS" if not eng_issues else "FAIL",
        "issues": eng_issues,
        "metrics": {"plan5_ms": round(p5ms, 3), "lanes5": n5, "roles5": [l.get("role") for l in (plan5.get("lanes") or [])]},
        "fix_backlog": eng_issues,
    }
    log_row(row)
    report.append(row)

    # ---------- Round 8: Engineer — 5 parallel micro-benchmark (lighter prompts) ----------
    issues = []
    plan5b, _ = auto_plan(
        "分成五个子代理：拆解、检索要点、起草、质检、风险清单。主题：新能源校园班车。",
        force_parallel=True,
        force_count=5,
        run_search=False,
    )
    lanes5 = (plan5b.get("lanes") or [])[:5]
    if len(lanes5) < 5:
        issues.append(f"need 5 lanes got {len(lanes5)}")

    def _run_lane5(i: int, lane: dict[str, Any]) -> tuple[int, float, bool]:
        child = create_session(f"qa-r8-lane-{i}")
        chat = chat_once(
            child,
            f"角色:{lane.get('role')} 目标:{lane.get('goal')} 主题:新能源校园班车。用5条要点回答。",
            route=lane.get("route_hint") or "C0",
            system=lane.get("system") or "",
            execution_mode="workflow",
        )
        return i, float(chat.get("total_ms") or 0), bool(chat.get("ok"))

    times5: list[float] = [0.0] * len(lanes5)
    t50 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(len(lanes5), 1)) as pool:
        futs = [pool.submit(_run_lane5, i, lane) for i, lane in enumerate(lanes5)]
        for fut in as_completed(futs):
            i, tot, ok = fut.result()
            times5[i] = tot
            if not ok:
                issues.append(f"lane{i} fail")
    wall5 = time.perf_counter() - t50
    row = {
        "round": 8,
        "role": "engineer",
        "title": "5子代理并行耗时基准",
        "verdict": "PASS" if not issues else "FAIL",
        "issues": issues,
        "metrics": {
            "lane_times_s": [round(x, 3) for x in times5],
            "max_lane_s": round(max(times5) if times5 else 0, 3),
            "sum_lane_s": round(sum(times5), 3),
            "wall_s": round(wall5, 3),
            "parallel_efficiency": round(sum(times5) / wall5, 3) if wall5 else None,
        },
    }
    log_row(row)
    report.append(row)

    # ---------- Round 9: Supervisor — regression on greeting + webui gone + agents UI ----------
    issues = []
    plan, _ = auto_plan("早上好", run_search=False)
    if plan.get("need_parallel"):
        issues.append("早上好 still parallel")
    code, _, _ = req("GET", "/api/webui/open")
    # GET may 404/405
    if code not in (404, 405):
        # try POST
        code2, _, _ = req("POST", "/api/webui/stop", {})
        if code2 != 404:
            issues.append(f"webui stop expected 404 got {code2}")
    code3, _, _ = req("POST", "/api/webui/start", {})
    if code3 != 404:
        issues.append(f"webui start expected 404 got {code3}")
    html_code, html_body, _ = req("GET", "/")
    raw_html = html_body.get("_raw") if isinstance(html_body, dict) else ""
    if not raw_html:
        # root returns html not json — already handled
        pass
    # re-fetch root as text
    r = urllib.request.Request(BASE + "/", method="GET")
    with _OPENER.open(r, timeout=10) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    for bad in ("deep-webui", "webui-overlay", "Hermes 深度会话", "subagent-picker"):
        if bad in html:
            issues.append(f"UI still contains {bad}")
    row = {
        "round": 9,
        "role": "supervisor",
        "title": "回归抽检：问候非并行 + WebUI拆除 + UI洁净",
        "verdict": "PASS" if not issues else "FAIL",
        "issues": issues,
        "metrics": {"html_bytes": len(html), "root_http": html_code or 200},
    }
    log_row(row)
    report.append(row)

    # ---------- Round 10: Multi-user simulation (2 users interleaved) ----------
    issues = []
    u1 = create_session("qa-r10-userA")
    u2 = create_session("qa-r10-userB")
    c1 = chat_once(u1, "用一句话介绍 Agent Hub")
    c2 = chat_once(u2, "用一句话介绍并行子代理")
    c1b = chat_once(u1, "上一问的产品名称是什么？")
    if not c1.get("ok") or not c2.get("ok") or not c1b.get("ok"):
        issues.append("multi-user chat failure")
    if "Hub" not in (c1b.get("text") or "") and "hub" not in (c1b.get("text") or "").lower() and "代理" not in (c1b.get("text") or ""):
        # soft — context may not persist perfectly
        issues.append("userA follow-up may lack session continuity keyword")
    row = {
        "round": 10,
        "role": "user",
        "title": "双用户交错会话",
        "verdict": "PASS" if not issues else "WARN" if len(issues) == 1 and "continuity" in issues[0] else "FAIL",
        "issues": issues,
        "metrics": {
            "userA_ms": round(float(c1.get("total_ms") or 0), 3),
            "userB_ms": round(float(c2.get("total_ms") or 0), 3),
            "userA_follow_ms": round(float(c1b.get("total_ms") or 0), 3),
        },
        "output_preview": {
            "A": (c1.get("text") or "")[:160],
            "B": (c2.get("text") or "")[:160],
            "A2": (c1b.get("text") or "")[:160],
        },
    }
    log_row(row)
    report.append(row)

    # ---------- Round 11: Engineer fix pass checklist (extra) ----------
    issues = []
    # ensure auto-plan single specialty for email-only
    plan, _ = auto_plan("帮我写一封请假邮件，语气正式", run_search=False)
    if plan.get("need_parallel"):
        issues.append("simple email task should not need parallel")
    # news should prefer search
    plan_n, _ = auto_plan("今天有什么科技新闻？请检索后总结", web_search=True, run_search=False)
    # run_search false still can set needs_search
    if not plan_n.get("needs_search") and not plan_n.get("need_parallel"):
        # soft
        issues.append("tech news did not flag needs_search")
    row = {
        "round": 11,
        "role": "engineer",
        "title": "规划精度抽检（邮件非并行 / 新闻需搜索）",
        "verdict": "PASS" if not issues else "FAIL",
        "issues": issues,
        "metrics": {
            "email_parallel": plan.get("need_parallel"),
            "email_single": bool(plan.get("single_role")),
            "news_needs_search": plan_n.get("needs_search"),
        },
    }
    log_row(row)
    report.append(row)

    # ---------- Round 12: Supervisor final gate ----------
    fails = [r for r in report if r.get("verdict") == "FAIL"]
    warns = [r for r in report if r.get("verdict") == "WARN"]
    row = {
        "round": 12,
        "role": "supervisor",
        "title": "最终监管门禁",
        "verdict": "PASS" if not fails else "FAIL",
        "issues": [f"R{r['round']} {r['title']}: {r['issues']}" for r in fails],
        "metrics": {
            "rounds": len(report) + 1,
            "fails": len(fails),
            "warns": len(warns),
            "passes": len([r for r in report if r.get("verdict") == "PASS"]),
        },
        "summary": {
            "multi_vs_single": report[5]["metrics"] if len(report) > 5 else {},
            "five_lane_eff": report[7]["metrics"] if len(report) > 7 else {},
        },
    }
    log_row(row)
    report.append(row)

    summary_path = OUT.with_name("qa-round-summary.json")
    summary_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== DONE fails={len(fails)} warns={len(warns)} report={summary_path} ===", flush=True)


if __name__ == "__main__":
    main()
