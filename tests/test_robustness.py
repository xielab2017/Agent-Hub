"""Regressions found by the offline end-to-end runs (search, errors, science tasks, continuity)."""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parent.parent

JEDRYCHOWSKI = (
    "In this paper we have identified and quantitated human irisin in plasma using mass spectrometry. "
    "This precise method shows that human irisin circulates at ∼ 3.6 ng/ml in sedentary individuals; "
    "this level is increased to ∼ 4.3 ng/ml in individuals undergoing aerobic interval training."
)


# ── search ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("raw,clean", [
    ("搜索一下：人血浆中鸢尾素（irisin）的浓度是多少？", "人血浆中鸢尾素（irisin）的浓度是多少"),
    ("帮我查一下明天深圳天气", "明天深圳天气"),
    ("请联网搜索 TP53 突变频率", "TP53 突变频率"),
    ("search the web for irisin plasma level?", "irisin plasma level"),
    ("TP53 突变频率", "TP53 突变频率"),
    ("搜索", "搜索"),  # nothing left: keep the original
])
def test_clean_search_query_drops_the_chat_command(raw, clean):
    from ali.websearch import clean_search_query

    assert clean_search_query(raw) == clean


def test_chinese_research_questions_route_to_literature():
    from ali.search_extensions import classify_intent

    assert classify_intent("人血浆中鸢尾素（irisin）的浓度是多少") == "academic"
    assert classify_intent("运动后小鼠血清 FGF21 水平变化") == "academic"
    assert classify_intent("明天深圳天气") == "general"
    assert classify_intent("写一份周报") == "general"


def test_english_only_literature_apis_get_the_english_terms(monkeypatch):
    from ali import search_extensions as se

    urls: list[str] = []

    def fake_fetch(url, **k):
        urls.append(url)
        return json.dumps({"esearchresult": {"idlist": []}, "results": []})

    monkeypatch.setattr(se, "_fetch", fake_fetch)
    se.search_pubmed("人血浆中鸢尾素（irisin）的浓度")
    assert "term=irisin" in urls[-1]
    urls.clear()
    out = se.search_openalex("鸢尾素的浓度是多少")  # no English term at all: no request
    assert urls == [] and out["ok"] is False


def test_same_paper_from_several_indexes_is_listed_once_and_papers_are_not_capped_at_two():
    from ali.websearch import _structure_sources

    title = "Detection and Quantitation of Circulating Human Irisin by Tandem Mass Spectrometry."
    rows = [
        {"title": title, "url": "https://doi.org/10.1016/j.cmet.2015.08.001", "source": "openalex"},
        {"title": title, "url": "https://pubmed.ncbi.nlm.nih.gov/26278051/", "source": "pubmed"},
    ] + [{"title": f"Irisin paper number {i} with a long enough title", "url": f"https://pubmed.ncbi.nlm.nih.gov/{i}/",
          "source": "pubmed"} for i in range(1, 6)]
    rows += [{"title": f"Forum post {i}", "url": f"https://bbs.example.com/{i}", "source": "bing"} for i in range(3)]
    out = _structure_sources(rows, limit=20)
    urls = [r["url"] for r in out]
    assert urls.count("https://pubmed.ncbi.nlm.nih.gov/26278051/") == 0  # duplicate title dropped
    assert sum("pubmed" in u for u in urls) == 5  # literature hosts are not capped at 2
    assert sum("bbs.example.com" in u for u in urls) == 2  # ordinary hosts still are


def test_sources_are_numbered_by_credibility(monkeypatch):
    from ali import websearch

    results = [
        {"title": "Irisin ELISA kit plasma", "url": "https://www.example-reagents.com/kit", "snippet": "irisin kit", "source": "bing"},
        {"title": "鸢尾素 irisin 知乎", "url": "https://www.zhihu.com/question/1", "snippet": "irisin", "source": "bing"},
        {"title": "Irisin by mass spectrometry", "url": "https://pubmed.ncbi.nlm.nih.gov/26278051/", "snippet": "irisin", "source": "pubmed"},
    ]
    monkeypatch.setattr(websearch, "deep_search", lambda q, limit=8: {"ok": True, "results": results, "engines": ["bing"]})
    res = websearch.search_structured("irisin plasma", limit=8)
    assert [s["tier"] for s in res["sources"]] == ["academic", "other", "ugc"]
    assert "- [1] [Irisin by mass spectrometry]" in res["context_markdown"]


def test_cross_language_results_are_not_flagged_irrelevant(monkeypatch):
    from ali import websearch

    results = [{"title": f"Irisin study {i}", "url": f"https://pubmed.ncbi.nlm.nih.gov/{i}/",
                "snippet": "irisin plasma", "source": "pubmed"} for i in range(1, 4)]
    monkeypatch.setattr(websearch, "deep_search", lambda q, limit=8: {"ok": True, "results": results, "engines": ["pubmed"]})
    res = websearch.search_structured("人血浆中鸢尾素（irisin）的浓度是多少", limit=8)
    assert res["quality"]["verified"] is True
    assert not any("相关性偏低" in w for w in res["warnings"])


def test_cascade_deadline_stops_slow_engines(monkeypatch):
    from ali import websearch

    calls = []

    def slow(q, limit=8):
        calls.append(q)
        time.sleep(0.3)
        return {"engine": "slow", "results": []}

    monkeypatch.setattr(websearch, "_engine_cascade", lambda p, i: [slow] * 10)
    out = websearch._search_once("irisin", limit=8, deadline=time.monotonic() + 0.5)
    assert len(calls) <= 3 and "search deadline exceeded" in out["errors"]


# ── evidence: concentrations ───────────────────────────────────────────


def test_concentrations_keep_units_ranges_and_blood_matrix():
    from ali.evidence import extract_facts, subject_terms

    sub = subject_terms("人血浆中鸢尾素（irisin）的浓度是多少？ELISA 和质谱结果为什么不一致")
    assert sub[0] == "irisin" and "ELISA" not in sub  # an assay is not an analyte
    facts = extract_facts(JEDRYCHOWSKI, sub)
    assert [(f["kind"], f["key"], f["display"]) for f in facts] == [
        ("concentration", "irisin@blood", "3.6 ng/ml"), ("concentration", "irisin@blood", "4.3 ng/ml")]
    csf = extract_facts("irisin concentration was approximately 0.26-1.86 ng/ml in cerebrospinal fluid", sub)
    assert csf[0]["value"] == "0.26-1.86" and csf[0]["key"] == "irisin@csf"
    zh = extract_facts("用 ELISA 试剂盒测到人血浆鸢尾素浓度约 100 ng/ml", sub)
    assert zh[0]["key"] == "irisin@blood" and zh[0]["amount"] == 100.0  # Chinese name → the English analyte
    assert extract_facts("serum level 0.5 µg/mL", ["level"])[0]["amount"] == 500.0  # normalised to ng/mL


def test_order_of_magnitude_disagreement_is_a_conflict_but_cohort_variation_is_not():
    from ali.evidence import build_evidence

    q = "人血浆中鸢尾素（irisin）的浓度"
    srcs = [
        {"title": "MS study", "url": "https://pubmed.ncbi.nlm.nih.gov/26278051/", "snippet": JEDRYCHOWSKI},
        {"title": "Vendor", "url": "https://www.example-reagents.com/kit", "snippet": "Typical human plasma irisin concentration 100 ng/ml."},
    ]
    ev = build_evidence(q, srcs)
    assert len(ev["conflicts"]) == 1 and ev["conflicts"][0]["key"] == "irisin@blood"
    assert {v["display"] for v in ev["conflicts"][0]["values"]} == {"3.6 ng/ml", "100 ng/ml"}
    calm = build_evidence(q, srcs[:1])  # 3.6 vs 4.3 ng/ml in one study: no conflict
    assert calm["conflicts"] == []


def test_reviewer_traces_ranges_and_accepts_reported_conflicts():
    from ali.evidence import build_evidence
    from ali.reviewer import review_reply

    srcs = [{"title": "CSF", "url": "https://pubmed.ncbi.nlm.nih.gov/29574076/",
             "snippet": "irisin concentration was approximately 0.26-1.86 ng/ml in CSF"}]
    rv = review_reply("脑脊液中鸢尾素约 0.26–1.86 ng/ml [1]。", sources=srcs, evidence=build_evidence("irisin", srcs))
    assert not any(i["kind"] == "untraceable_number" for i in rv["issues"])
    rv2 = review_reply("约 0.26–9.9 ng/ml [1]。", sources=srcs)
    assert any(i["kind"] == "untraceable_number" for i in rv2["issues"])


# ── LLM client: retries and truncation ─────────────────────────────────


class _Stub(BaseHTTPRequestHandler):
    plan: list = []
    hits = 0

    def log_message(self, *a):
        pass

    def do_POST(self):
        type(self).hits += 1
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        step = self.plan.pop(0) if self.plan else "ok"
        if isinstance(step, int):
            body = json.dumps({"error": {"message": f"status {step}"}}).encode()
            self.send_response(step)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            if step == 429:
                self.send_header("Retry-After", "0")
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        for piece in ("Hello ", "world"):
            chunk = {"choices": [{"delta": {"content": piece}, "finish_reason": None}]}
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
        if step == "ok":
            self.wfile.write(b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
        self.wfile.flush()
        self.close_connection = True


@contextlib.contextmanager
def _stub_server(plan):
    _Stub.plan, _Stub.hits = list(plan), 0
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}/v1"
    finally:
        srv.shutdown()


def test_rate_limit_and_server_errors_are_retried_before_anything_streams():
    from ali import llm_client

    with _stub_server([429, 503, "ok"]) as base:
        meta: dict = {}
        text = llm_client.stream_chat(base, "k", model="m", messages=[{"role": "user", "content": "hi"}],
                                      meta=meta, sleep=lambda s: None)
    assert text == "Hello world" and meta["retries"] == [429, 503] and meta["attempts"] == 3
    with _stub_server([500, 500, 500]) as base:
        with pytest.raises(RuntimeError, match="HTTP 500"):
            llm_client.stream_chat(base, "k", model="m", messages=[{"role": "user", "content": "hi"}], sleep=lambda s: None)
        assert _Stub.hits == 3
    with _stub_server([401]) as base:
        with pytest.raises(RuntimeError, match="401"):
            llm_client.stream_chat(base, "k", model="m", messages=[{"role": "user", "content": "hi"}], sleep=lambda s: None)
        assert _Stub.hits == 1  # a bad key is never retried


def test_connection_refused_is_retried_but_timeouts_are_not(monkeypatch):
    import urllib.error

    from ali import llm_client

    calls = []

    def once(*a, **k):
        calls.append(1)
        raise exc

    monkeypatch.setattr(llm_client, "_stream_chat_once", once)
    exc = urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))
    with pytest.raises(urllib.error.URLError):
        llm_client.stream_chat("http://x/v1", "k", model="m", messages=[], sleep=lambda s: None)
    assert len(calls) == 3
    calls.clear()
    exc = urllib.error.URLError(TimeoutError("timed out"))
    with pytest.raises(urllib.error.URLError):
        llm_client.stream_chat("http://x/v1", "k", model="m", messages=[], sleep=lambda s: None)
    assert len(calls) == 1


def test_stream_that_ends_without_finish_marker_is_flagged_truncated():
    from ali import llm_client

    with _stub_server(["cut"]) as base:
        meta: dict = {}
        text = llm_client.stream_chat(base, "k", model="m", messages=[{"role": "user", "content": "hi"}], meta=meta)
    assert text == "Hello world" and meta.get("truncated") is True


def test_401_hint_names_the_minimax_region_not_other_vendors():
    import io
    import urllib.error

    from ali.llm_client import _format_http_error

    exc = urllib.error.HTTPError("u", 401, "Unauthorized", {}, io.BytesIO(b'{"error":{"message":"invalid api key"}}'))
    msg = _format_http_error(exc, url="https://api.minimaxi.com/v1/chat/completions", model="MiniMax-M2")
    assert "api.minimaxi.com" in msg and "中国大陆区" in msg and "nvapi-" not in msg


# ── chat pipeline: history, cancellation ───────────────────────────────


def test_model_history_skips_failed_replies_and_fits_the_budget():
    from ali.streaming import model_history

    msgs = [{"role": "user", "content": "q1"}, {"role": "assistant", "content": "**Error:** HTTP 500", "error": True}]
    msgs += [{"role": "user" if i % 2 == 0 else "assistant", "content": f"{i} " + "x" * 1000} for i in range(40)]
    kept, dropped = model_history(msgs, budget_chars=10_000)
    assert all("Error" not in m["content"] for m in kept)
    assert sum(len(m["content"]) for m in kept) <= 10_000 and dropped == 41 - len(kept)
    assert kept[-1]["content"].startswith("39 ")  # newest turns are the ones kept


def test_cancel_is_sticky_and_superseded_runs_are_dropped():
    from ali import streaming

    with tempfile.TemporaryDirectory() as tmp, \
            mock.patch.object(streaming.store, "SESSIONS_DIR", Path(tmp)), \
            mock.patch.object(streaming.store, "ensure_state_dirs", lambda: None):
        s = streaming.store.create_session(title="t")
        streaming.store.append_messages(s.id, {"role": "user", "content": "long question"})
        streaming._register_job("sX", s.id)
        streaming.ACTIVE[s.id] = "sX"
        assert streaming.cancel_stream(s.id)
        streaming._append_job_event("sX", "done", {})  # the done that follows a cancel
        assert streaming._job_cancelled("sX")
        route = {"_user_turns": 1}
        assert streaming._store_final(s.id, "sX", route, {"role": "assistant", "content": "partial"})
        assert streaming.store.get_session(s.id).messages[-1]["cancelled"] is True
        # a newer message arrived: the stopped run must not land after it
        streaming.store.append_messages(s.id, {"role": "user", "content": "newer"})
        assert not streaming._store_final(s.id, "sX", route, {"role": "assistant", "content": "late"})
        assert streaming.store.get_session(s.id).messages[-1]["content"] == "newer"
        streaming.JOBS.pop("sX", None)


def test_gateway_restart_marks_the_unanswered_turn():
    from ali import streaming

    with tempfile.TemporaryDirectory() as tmp, \
            mock.patch.object(streaming.store, "SESSIONS_DIR", Path(tmp)), \
            mock.patch.object(streaming.store, "ensure_state_dirs", lambda: None):
        s = streaming.store.create_session(title="t")
        streaming.store.append_messages(s.id, {"role": "user", "content": "q", "route": {"tier": "C1"}})
        done = streaming.store.create_session(title="ok")
        streaming.store.append_messages(done.id, {"role": "user", "content": "q", "route": {}},
                                        {"role": "assistant", "content": "a"})
        assert streaming.recover_interrupted_runs() == 1
        last = streaming.store.get_session(s.id).messages[-1]
        assert last["interrupted"] and last["error"] and "中断" in last["content"]
        assert streaming.recover_interrupted_runs() == 0  # idempotent


# ── tasks: one source numbering, resume, planning ──────────────────────


def test_task_sources_keep_one_numbering_across_steps():
    from ali import task_runner
    from ali.reviewer import review_reply

    from test_task_runner import sandbox

    with sandbox() as store:
        sid = store.create_session(title="t").id
        t = task_runner.create_task(sid, "1. 检索文献 2. 比较结果")["task"]
        a = task_runner.register_sources(t["id"], [{"url": "https://pubmed.ncbi.nlm.nih.gov/1/", "title": "A"},
                                                   {"url": "https://pubmed.ncbi.nlm.nih.gov/2/", "title": "B"}])
        b = task_runner.register_sources(t["id"], [{"url": "https://pubmed.ncbi.nlm.nih.gov/2", "title": "B again"},
                                                   {"url": "https://doi.org/10.1/x", "title": "C"}])
        assert [s["n"] for s in a] == [1, 2] and [s["n"] for s in b] == [2, 3]
        reg = task_runner.task_sources(t["id"])
        assert [s["n"] for s in reg] == [1, 2, 3]
        assert "- [3] [C](https://doi.org/10.1/x)" in task_runner.sources_block(reg)
        rv = review_reply("见 [2][3]，另见 [7]。", sources=b)
        assert [i["text"] for i in rv["issues"] if i["kind"] == "citation_out_of_range"] == ["[7]"]


def test_numbered_steps_after_a_fullwidth_question_mark():
    from ali.task_runner import plan_steps

    plan = plan_steps("研究问题：运动能否提高鸢尾素水平？1. 检索关键文献 2. 比较质谱与 ELISA 结果 3. 设计验证实验")
    assert plan["source"] == "numbered"
    assert [s["title"] for s in plan["steps"]][:3] == ["检索关键文献", "比较质谱与 ELISA 结果", "设计验证实验"]


# ── end to end: search runs after the request returns ──────────────────

E2E = r"""
import json, sys, time
sys.path.insert(0, sys.argv[1])
from ali import sessions as store, streaming, websearch, task_runner

SEARCH = {"ok": True, "query": "q", "sources": [{"title": "Irisin by MS", "url": "https://pubmed.ncbi.nlm.nih.gov/26278051/",
          "snippet": "irisin circulates at 3.6 ng/ml", "source": "pubmed"}], "context_markdown": "## Deep information search results\n- [1] [Irisin by MS](https://pubmed.ncbi.nlm.nih.gov/26278051/) (pubmed) — irisin",
          "engines": ["pubmed"], "errors": [], "quality": {}, "warnings": []}
def slow_search(q, limit=8, deep=True):
    time.sleep(1.5)
    return SEARCH
websearch.search_structured = slow_search
import ali.page_fetch as pf
pf.fetch_pages = lambda *a, **k: []
seen = {}
def fake_direct(q, session_id, msg_text, model, parts, *, route_info=None, preamble=""):
    seen["preamble"] = preamble
    parts.append("结论见 [1]。")
    streaming._put(q, "token", {"text": parts[-1]})
    return True
streaming._direct_llm_reply = fake_direct

s = store.create_session(title="t")
t0 = time.time()
res = streaming.start_chat(s.id, "搜索 irisin 血浆浓度", web_search=True)
returned = time.time() - t0
while time.time() - t0 < 30:
    msgs = [m for m in store.get_session(s.id).messages if m.get("role") == "assistant"]
    if msgs:
        break
    time.sleep(0.1)
events = [e["event"] for e in streaming.JOBS[res["stream_id"]]["events"]]
notes = [e["data"].get("text", "") for e in streaming.JOBS[res["stream_id"]]["events"] if e["event"] == "thinking"]
# a task: the step's source gets the task number, later steps see it
task = task_runner.create_task(s.id, "1. 检索文献 2. 比较")
tid = task["task"]["id"]
task_runner.register_sources(tid, [{"url": "https://example.org/earlier", "title": "Earlier"}])
res2 = streaming.start_chat(s.id, task["next"]["prompt"], task_id=tid, task_step=1, web_search=True)
while time.time() - t0 < 30:
    msgs = [m for m in store.get_session(s.id).messages if m.get("role") == "assistant"]
    if len(msgs) >= 2:
        break
    time.sleep(0.1)
print(json.dumps({"returned": returned, "has_block": "Irisin by MS" in seen.get("preamble", ""),
                  "marker_left": "agent-hub:search-results" in seen.get("preamble", ""),
                  "notes": notes, "task_block_n2": "- [2] [Irisin by MS]" in seen.get("preamble", ""),
                  "review": msgs[-1].get("review", {}).get("warn")}, ensure_ascii=False))
"""


def test_search_runs_in_the_stream_and_task_steps_share_source_numbers():
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ)
        env.update({
            "HERMES_ALI_STATE_DIR": str(Path(tmp) / "state"),
            "AGENT_CLI_HOME": str(Path(tmp) / "agent-cli"),
            "HERMES_HOME": str(Path(tmp) / "hermes"),
            "HOME": tmp,
            "HERMES_ALI_AGENT_DIR": str(Path(tmp) / "no-agent"),
        })
        proc = subprocess.run([sys.executable, "-c", E2E, str(ROOT)], env=env, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    assert out["returned"] < 1.0  # the chat request does not wait for the 1.5 s search
    assert out["has_block"] and not out["marker_left"]
    assert any("正在深度联网检索" in n for n in out["notes"]) and any("检索完成" in n for n in out["notes"])
    assert out["task_block_n2"]  # the step's source was numbered after the task's earlier source
    assert out["review"] == 0
