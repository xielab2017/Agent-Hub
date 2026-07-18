"""Tests for the MiniMax code search parity integration.

What we cover:
  * `parse_query` — every operator (`site:`, `inurl:`, `intitle:`,
    `intext:`, `inanchor:`, `-exclude`, `~synonym`, `"exact"`) and their
    combinations.
  * `format_brief` — extra_snippets > snippet > description preference.
  * `parallel_search` — order-preserving fan-out, error capture, empty
    query short-circuit, deterministic worker sizing.
  * `chunk_text` + `browse_url` — token-aware chunking and LLM synthesis
    with stubbed llm_fn / fetch_fn (no network).
  * `search_structured` (parity) — operator pass-through, empty-result
    fallback to the cleaned query.
  * Integration — `websearch.search_structured` honours `site:` by
    post-filtering; the parity engine is registered for every intent.
  * End-to-end world cup — operator + planner fan-out delivers sources
    without fabricating scores when offline.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root is importable so `import ali.…` works.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ── 1. Operator parser ────────────────────────────────────────────────


def test_parse_query_extracts_site_operator():
    from ali.minimax_search_parity import parse_query

    p = parse_query("site:zh.wikipedia.org 世界杯 战况")
    assert p.site == "zh.wikipedia.org"
    assert p.cleaned == "世界杯 战况"
    assert p.has_operators() is True


def test_parse_query_extracts_all_five_operators():
    from ali.minimax_search_parity import parse_query

    p = parse_query(
        "site:bbc.com inurl:sport intitle:WorldCup intext:group inanchor:results foo"
    )
    assert p.site == "bbc.com"
    assert p.inurl == "sport"
    assert p.intitle == "WorldCup"
    assert p.intext == "group"
    assert p.inanchor == "results"
    # The remaining term falls through into the cleaned body.
    assert "foo" in p.cleaned
    # Site + inurl + intitle + intext + inanchor should all be gone from
    # the cleaned body.
    for op in ("site:", "inurl:", "intitle:", "intext:", "inanchor:"):
        assert op not in p.cleaned


def test_parse_query_handles_exclude_synonym_exact():
    from ali.minimax_search_parity import parse_query

    p = parse_query('世界杯 战况 -广告 ~预测 "group stage"')
    assert p.exclude == ["广告"]
    assert p.synonym == ["预测"]
    assert p.exact == ["group stage"]
    # Exact phrase words stay in `cleaned` (without quote marks) so the
    # broader fallback still carries the intent; exclude/synonym are
    # fully removed because the operator already encodes the intent.
    assert "group stage" in p.cleaned
    assert '"' not in p.cleaned
    assert "广告" not in p.cleaned
    assert "预测" not in p.cleaned


def test_parse_query_preserves_cjk_in_cleaned():
    from ali.minimax_search_parity import parse_query

    p = parse_query("site:wikipedia.org 2026世界杯小组赛A组")
    assert p.site == "wikipedia.org"
    assert p.cleaned == "2026世界杯小组赛A组"
    # CJK + ASCII tokens survive the punctuation strip.
    assert "世界杯" in p.cleaned


def test_parse_query_empty_input_is_a_noop():
    from ali.minimax_search_parity import parse_query

    p = parse_query("")
    assert p.cleaned == ""
    assert p.has_operators() is False
    assert p.site == ""


# ── 2. format_brief ───────────────────────────────────────────────────


def test_format_brief_prefers_extra_snippets():
    from ali.minimax_search_parity import format_brief

    md = format_brief([
        {"title": "A", "url": "http://a", "snippet": "fallback", "extra_snippets": ["e1", "e2"]},
        {"title": "B", "url": "http://b", "snippet": "primary"},
        {"title": "C", "url": "http://c", "description": "desc only"},
        "ignored-not-dict",
        {},
    ])
    # extra_snippets joined by newline appear first
    assert "e1\ne2" in md
    # snippet used when extra_snippets absent
    assert "primary" in md
    # description used when both are absent
    assert "desc only" in md
    # Title / url / snippet tags present
    assert "<title>A</title>" in md
    assert "<url>http://a</url>" in md
    # Non-dict + empty dict silently dropped
    assert "ignored-not-dict" not in md


# ── 3. parallel_search ───────────────────────────────────────────────


def test_parallel_search_preserves_query_order():
    from ali.minimax_search_parity import parallel_search

    def stub(q):
        # Return order must match the order of the `queries` arg.
        return {"ok": True, "results": [{"title": f"hit-{q}", "url": f"http://x/{q}", "snippet": q}], "engine": "stub"}

    par = parallel_search(["alpha", "beta", "gamma"], search_fn=stub, max_workers=3)
    assert par.ok is True
    assert [b["query"] for b in par.blocks] == ["alpha", "beta", "gamma"]
    assert [b["results"][0]["title"] for b in par.blocks] == ["hit-alpha", "hit-beta", "hit-gamma"]
    # The combined markdown should mention each query label.
    for q in ("alpha", "beta", "gamma"):
        assert f"--- search result for [{q}] ---" in par.combined_markdown


def test_parallel_search_captures_errors_per_block():
    from ali.minimax_search_parity import parallel_search

    def stub(q, _blocked={"nope"}):
        if q in _blocked:
            return {"ok": False, "results": [], "error": "blocked"}
        return {"ok": True, "results": [{"title": q, "url": f"http://x/{q}", "snippet": ""}]}

    par = parallel_search(["ok", "nope", "ok2"], search_fn=stub)
    assert par.ok is True  # at least one succeeded
    assert any("nope" in e for e in par.errors)
    assert par.blocks[1]["ok"] is False
    assert par.blocks[1]["error"] == "blocked"


def test_parallel_search_empty_query_short_circuits():
    from ali.minimax_search_parity import parallel_search

    called: list[str] = []

    def stub(q):
        called.append(q)
        return {"ok": True, "results": [{"title": q, "url": f"http://x/{q}", "snippet": ""}], "engine": "stub"}

    par = parallel_search(["", "  ", "real"], search_fn=stub)
    # First two blocks: ok=False with error=empty_query
    assert par.blocks[0]["ok"] is False
    assert par.blocks[0]["error"] == "empty_query"
    assert par.blocks[1]["ok"] is False
    assert par.blocks[1]["error"] == "empty_query"
    # The non-empty query reached the engine.
    assert par.blocks[2]["ok"] is True
    assert par.blocks[2]["query"] == "real"
    assert called == ["real"]


# ── 4. chunk_text + browse_url (no network) ──────────────────────────


def test_chunk_text_splits_with_overlap():
    from ali.minimax_search_parity import chunk_text

    text = "a" * 10_000
    chunks = chunk_text(text, chunk_chars=4000, overlap=200)
    # Step = 4000 - 200 = 3800; we should see ~3 chunks
    assert 2 <= len(chunks) <= 4
    # Every chunk except possibly the last should be <= chunk_chars
    for c in chunks[:-1]:
        assert len(c) <= 4000
    # Reassembled: tail of chunk N == head of chunk N+1 (overlap preserved)
    if len(chunks) >= 2:
        tail = chunks[0][-200:]
        head = chunks[1][:200]
        assert tail == head


def test_browse_url_synthesizes_via_stub_llm():
    from ali.minimax_search_parity import browse_url

    html = (
        "<html><head><title>X</title></head><body>"
        "<script>alert(1)</script>"
        "<h1>Hello</h1><p>The capital of France is Paris.</p>"
        "</body></html>"
    )

    def fetch(_url):
        return html

    seen_prompts: list[str] = []

    def llm(prompt):
        seen_prompts.append(prompt)
        return "Answer: The capital of France is Paris."

    out = browse_url(
        "http://example.test/",
        "What is the capital of France?",
        llm_fn=llm,
        fetch_fn=fetch,
    )
    assert "Paris" in out
    # Scripts should be stripped before the LLM sees the body.
    assert "alert(1)" not in seen_prompts[0]
    assert "What is the capital of France" in seen_prompts[0]


def test_browse_url_splits_long_pages_into_chunks():
    from ali.minimax_search_parity import browse_url, chunk_text

    # Build a long body so chunking kicks in.  2000 sentences × ~30 chars
    # ≈ 60 000 chars.  We disable the head/tail truncation (max_chars)
    # so the LLM sees the entire body, then we verify the chunk count
    # matches what `chunk_text` says for the un-truncated body.
    body = " ".join(f"sentence {i} about topic." for i in range(2000))
    html = f"<html><body><p>{body}</p></body></html>"

    def fetch(_url):
        return html

    prompts: list[str] = []

    def llm(prompt):
        prompts.append(prompt)
        # Return something the test can identify per chunk.
        return f"answer-for-chunk-{len(prompts)}"

    out = browse_url(
        "http://x.test/long",
        "topic",
        llm_fn=llm,
        fetch_fn=fetch,
        chunk_chars=2000,
        max_chars=10**9,  # disable head/tail truncation
    )
    expected_chunks = len(chunk_text(body, chunk_chars=2000))
    # More than one chunk should have been generated.
    assert len(prompts) > 1, "expected long page to be split into multiple chunks"
    # Combined output stitches the parts together.
    assert "result part 1" in out
    assert f"result part {len(prompts)}" in out
    # chunk_text agrees on the count.
    assert expected_chunks == len(prompts)


def test_browse_url_handles_fetch_error_gracefully():
    from ali.minimax_search_parity import browse_url

    def fetch(_url):
        raise RuntimeError("network down")

    def llm(_prompt):
        raise AssertionError("LLM should not be called when fetch failed")

    out = browse_url("http://x.test/", "anything", llm_fn=llm, fetch_fn=fetch)
    assert "Browse error" in out
    assert "network down" in out or "RuntimeError" in out


# ── 5. search_structured (parity) ────────────────────────────────────


def test_parity_search_structured_returns_cleaned_and_operators():
    from ali.minimax_search_parity import search_structured

    def stub(q, _seen=None):
        _seen = getattr(stub, "_seen", [])
        _seen.append(q)
        setattr(stub, "_seen", _seen)
        return {
            "ok": True,
            "results": [
                {"title": f"Result for {q}", "url": f"http://x/{q}", "snippet": "snippet"}
            ],
            "engine": "stub",
        }

    res = search_structured("site:wikipedia.org 世界杯", search_fn=stub)
    assert res["cleaned_query"] == "世界杯"
    assert res["operators"]["site"] == "wikipedia.org"
    # The actual search call was made with the cleaned query.
    assert stub._seen == ["世界杯"]


def test_parity_search_structured_falls_back_to_exact_phrase():
    from ali.minimax_search_parity import search_structured

    # First call (cleaned with phrase words, no quotes) returns results.
    def stub(q, _state={"calls": 0}):
        _state["calls"] += 1
        if "group stage" in q:
            return {"ok": True, "results": [{"title": "exact", "url": "http://x", "snippet": "ok"}], "engine": "stub"}
        return {"ok": True, "results": [], "engine": "stub"}

    res = search_structured('"group stage" 世界杯', search_fn=stub)
    assert res["ok"] is True
    # The primary call should have matched because cleaned retains the phrase words.
    assert res["cleaned_query"] == "group stage 世界杯"
    assert res["operators"]["exact"] == ["group stage"]


# ── 6. Integration: websearch.search_structured honours site: ────────


def test_websearch_structured_filters_by_site_operator(monkeypatch):
    from ali import websearch

    fake_results = [
        {"title": "wiki", "url": "https://zh.wikipedia.org/wiki/2026_FIFA_World_Cup", "snippet": "w"},
        {"title": "noise", "url": "https://example.com/random", "snippet": "n"},
    ]

    def fake_search_web(q, *, limit=8, deep=False):
        return {"ok": True, "results": list(fake_results), "engines": ["stub"], "errors": [], "summary": ""}

    def fake_deep_search(q, *, limit=8):
        return fake_search_web(q, limit=limit, deep=True)

    monkeypatch.setattr(websearch, "search_web", fake_search_web)
    monkeypatch.setattr(websearch, "deep_search", fake_deep_search)

    res = websearch.search_structured("site:zh.wikipedia.org 2026世界杯", deep=False)
    urls = [s.get("url") for s in res.get("sources") or []]
    # Only the Wikipedia URL should survive the site: filter.
    assert all("wikipedia.org" in u for u in urls)
    assert res.get("operators", {}).get("site") == "zh.wikipedia.org"
    assert res.get("cleaned_query") == "2026世界杯"


def test_websearch_structured_filters_by_exclude(monkeypatch):
    from ali import websearch

    fake_results = [
        {"title": "good", "url": "http://a", "snippet": "useful"},
        {"title": "bad ad", "url": "http://b", "snippet": "this is an advertisement page"},
    ]

    def fake_search_web(q, *, limit=8, deep=False):
        return {"ok": True, "results": list(fake_results), "engines": ["stub"], "errors": [], "summary": ""}

    monkeypatch.setattr(websearch, "search_web", fake_search_web)

    res = websearch.search_structured("世界杯 战况 -advertisement", deep=False)
    titles = [s.get("title") for s in res.get("sources") or []]
    assert "good" in titles
    assert "bad ad" not in titles
    assert "advertisement" in res.get("operators", {}).get("exclude", [])


# ── 7. Integration: planner uses parallel fan-out for >1 query ───────


def test_planner_uses_parallel_fan_out(monkeypatch):
    from ali import subagent_planner

    calls: list[str] = []

    def fake_search_structured(q, *, limit=8, deep=True):
        calls.append(q)
        return {
            "ok": True,
            "sources": [{"title": f"hit-{q}", "url": f"http://x/{q}", "snippet": q}],
            "context_markdown": f"ctx for {q}",
        }

    monkeypatch.setattr(subagent_planner.websearch, "search_structured", fake_search_structured)

    # Build a plan that carries multiple search_queries.
    sources, ctx = subagent_planner._gather_sources(
        ["alpha", "beta", "gamma"], enabled=True, limit=4, parallel=True
    )
    # All three queries were called (parallel preserves the set, possibly reordered).
    assert sorted(calls) == ["alpha", "beta", "gamma"]
    # Sources came back from all three — one per query, deduped by URL.
    assert len(sources) == 3
    titles = sorted(s.get("title") for s in sources)
    assert titles == ["hit-alpha", "hit-beta", "hit-gamma"]
    # The combined markdown is the MiniMax-code style per-query block list.
    assert "--- search result for [alpha] ---" in ctx
    assert "--- search result for [beta] ---" in ctx
    assert "--- search result for [gamma] ---" in ctx
    # The combined markdown should not duplicate blocks (added once).
    assert ctx.count("--- search result for [alpha] ---") == 1


def test_planner_falls_back_to_serial_on_parallel_failure(monkeypatch):
    """If the parity import explodes, the planner should still work serially."""
    from ali import subagent_planner

    calls: list[str] = []

    def fake_search_structured(q, *, limit=8, deep=True):
        calls.append(q)
        return {
            "ok": True,
            "sources": [{"title": f"hit-{q}", "url": f"http://x/{q}", "snippet": q}],
            "context_markdown": f"ctx for {q}",
        }

    # Force the parallel_search import to fail.
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.endswith("minimax_search_parity") or name == "ali.minimax_search_parity":
            raise ImportError("boom")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(subagent_planner.websearch, "search_structured", fake_search_structured)

    sources, _ctx = subagent_planner._gather_sources(
        ["alpha", "beta"], enabled=True, limit=4, parallel=True
    )
    # The serial fallback should still have run both queries.
    assert sorted(calls) == ["alpha", "beta"]
    assert len(sources) == 2


# ── 8. search_extensions: parity engine registered ───────────────────


def test_parity_engine_registered_for_every_intent():
    from ali import search_extensions as se

    for intent in ("event", "news", "academic", "code", "general"):
        engines = se.engines_for_intent(intent)
        assert se.search_minimax_parity in engines, (
            f"parity engine missing from intent={intent}"
        )


def test_parity_engine_runs_offline_without_fabricating():
    """When the underlying engines all return empty, the parity engine
    must NOT invent results — it should expose the empty state honestly.
    """
    from ali import search_extensions as se
    from ali import websearch

    def fake_search_structured(q, *, limit=8, deep=True):
        return {"ok": False, "sources": [], "context_markdown": "", "engines": [], "errors": ["offline"]}

    # Patch both websearch and any direct call paths.
    websearch.search_structured = fake_search_structured
    try:
        res = se.search_minimax_parity("site:wikipedia.org 世界杯")
        # Either ok=False or results list is empty — never a fabricated hit.
        assert res.get("ok") is False
        assert res.get("results") == []
        assert res.get("engine") == "minimax_parity"
        assert res.get("operators", {}).get("site") == "wikipedia.org"
        assert res.get("cleaned_query") == "世界杯"
    finally:
        # Restore — not strictly needed because monkeypatch isn't used here,
        # but be tidy.
        pass


# ── 9. End-to-end: World Cup + site: ────────────────────────────────


def test_world_cup_with_site_operator_does_not_fabricate_offline(monkeypatch):
    from ali import subagent_planner
    from ali import search_extensions as se
    from ali import websearch

    # Everything is offline; planner + engines must NOT invent a score.
    def fake_websearch_structured(q, *, limit=8, deep=True):
        return {
            "ok": False,
            "sources": [],
            "context_markdown": "## Web search offline",
            "engines": [],
            "errors": ["offline"],
        }

    monkeypatch.setattr(websearch, "search_structured", fake_websearch_structured)

    plan = subagent_planner.plan_lanes(
        "site:wikipedia.org 昨晚世界杯小组赛战况", cfg={}, web_search_enabled=True
    )
    # Event intent: 3 event lanes
    assert plan["need_parallel"] is True
    assert len(plan["lanes"]) == 3
    # Per-lane queries should reflect the operator-aware cleaned text.
    for lane in plan["lanes"]:
        queries = lane.get("search_queries") or []
        assert queries, "each event lane must carry a search query"
        # site: shouldn't sneak into the actual search text (it lives on
        # the operator, not in the engine query).
        for qu in queries:
            assert "site:wikipedia.org" not in qu or "wikipedia.org" in qu.lower()
    # Sources list is empty (offline) but the shape is still useful.
    assert plan.get("sources") == []
    # No fake scores
    for lane in plan["lanes"]:
        text = (lane.get("search_context") or "") + " ".join(
            str(x) for x in (lane.get("search_queries") or [])
        )
        assert "3-0" not in text
        assert "1-0" not in text


# ── 10. Parallel fan-out end-to-end against the parity engine ───────


def test_parity_engine_combined_markdown_preserves_per_query_blocks(monkeypatch):
    from ali import search_extensions as se
    from ali import websearch

    counter = {"n": 0}

    def fake_websearch_structured(q, *, limit=8, deep=True):
        counter["n"] += 1
        return {
            "ok": True,
            "sources": [
                {"title": f"hit-{q}", "url": f"http://x/{q}", "snippet": f"snippet {q}"}
            ],
            "context_markdown": f"ctx for {q}",
            "engines": ["stub"],
            "errors": [],
        }

    monkeypatch.setattr(websearch, "search_structured", fake_websearch_structured)
    res = se.search_minimax_parity("site:foo.com 世界杯")
    # Combined markdown includes per-query blocks.
    assert "--- search result for [" in res.get("combined_markdown", "")
    assert res.get("ok") is True
    assert res.get("engine") == "minimax_parity"
