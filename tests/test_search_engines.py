"""Tests for the extra search engines, the engine cascade and the fetch layer."""

from __future__ import annotations

import json
import ssl
from unittest import mock

import pytest

DDG_HTML = """
<div class="result results_links results_links_deep web-result ">
  <h2 class="result__title"><a rel="nofollow" class="result__a"
     href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.who.int%2Fnews%2Fitem%2F1&amp;rut=abc">WHO <b>report</b> 2024</a></h2>
  <a class="result__snippet" href="x">Global cases rose by <b>12%</b> in 2024.</a>
</div>
<div class="result result--ad"><a class="result__a" href="https://ads.example/">Ad</a></div>
<div class="result results_links"><h2><a class="result__a" href="https://example.org/b">Second</a></h2>
  <div class="result__snippet">Another snippet</div></div>
"""

BAIDU_HTML = """
<div class="result c-container new-pmd" id="1" mu="https://www.gov.cn/zhengce/2024/content_1.htm">
  <h3 class="t"><a href="http://www.baidu.com/link?url=AAA" target="_blank">国务院 <em>政策</em> 解读</a></h3>
  <span class="content-right_8Zs40">2024年发布的政策要点……</span>
</div>
<div class="result c-container" id="2">
  <h3 class="t"><a href="http://www.baidu.com/link?url=BBB">没有 mu 的结果</a></h3>
  <div class="c-abstract">摘要文字</div>
</div>
"""


def _route_http(mapping):
    def fake(url, *, data=None, headers=None, timeout=8.0, relaxed_tls=False, max_timeout=4.0):
        for key, val in mapping.items():
            if key in url:
                if callable(val):
                    return val(url, data, headers)
                return val
        raise OSError(f"unexpected {url}")
    return fake


def _cfg(**search):
    return mock.patch("ali.websearch._search_cfg", return_value=dict(search))


def _secrets(**keys):
    return mock.patch("ali.websearch._secret", side_effect=lambda slot: keys.get(slot, ""))


# ── engines ────────────────────────────────────────────────────────────


def test_duckduckgo_parses_results_decodes_redirects_skips_ads(monkeypatch):
    from ali import search_engines as se2, websearch

    monkeypatch.setattr(websearch, "_http", _route_http({"html.duckduckgo.com": DDG_HTML}))
    r = se2.search_ddg("who report")
    assert r["ok"] and [x["url"] for x in r["results"]] == ["https://www.who.int/news/item/1", "https://example.org/b"]
    assert r["results"][0]["title"] == "WHO report 2024" and "12%" in r["results"][0]["snippet"]
    assert all(x["source"] == "duckduckgo" for x in r["results"])


def test_baidu_prefers_mu_real_url_and_detects_captcha(monkeypatch):
    from ali import search_engines as se2, websearch

    monkeypatch.setattr(websearch, "_http", _route_http({"www.baidu.com": BAIDU_HTML}))
    r = se2.search_baidu("政策")
    assert r["results"][0]["url"] == "https://www.gov.cn/zhengce/2024/content_1.htm"
    assert r["results"][0]["title"] == "国务院 政策 解读" and "2024年" in r["results"][0]["snippet"]
    assert r["results"][1]["url"].startswith("http://www.baidu.com/link")
    monkeypatch.setattr(websearch, "_http", _route_http({"www.baidu.com": "<title>百度安全验证</title>"}))
    r2 = se2.search_baidu("政策")
    assert r2["ok"] is False and "captcha" in r2["errors"][0]


def test_searxng_needs_url_and_parses_json(monkeypatch):
    from ali import search_engines as se2, websearch

    with _cfg():
        assert se2.search_searxng("x")["errors"] == ["searxng_url not configured"]
    body = json.dumps({"results": [{"url": "https://a.org", "title": "A", "content": "c", "engine": "google"}]})
    seen = {}
    monkeypatch.setattr(websearch, "_http", _route_http({"searx.local": lambda u, d, h: (seen.setdefault("u", u), body)[1]}))
    with _cfg(searxng_url="http://searx.local/"):
        r = se2.search_searxng("tp53 gene")
    assert r["results"] == [{"title": "A", "snippet": "c", "url": "https://a.org", "source": "searxng:google"}]
    assert seen["u"].startswith("http://searx.local/search?") and "format=json" in seen["u"]


def test_brave_and_tavily_need_keys_and_send_them(monkeypatch):
    from ali import search_engines as se2, websearch

    with _secrets():
        assert se2.search_brave("q")["errors"] == ["brave key not configured"]
        assert se2.search_tavily("q")["errors"] == ["tavily key not configured"]
    captured = {}

    def brave(url, data, headers):
        captured["brave"] = headers
        return json.dumps({"web": {"results": [{"title": "B", "url": "https://b.org", "description": "d", "age": "2 days ago"}]}})

    def tavily(url, data, headers):
        captured["tavily"] = (json.loads(data), headers)
        return json.dumps({"results": [{"title": "T", "url": "https://t.org", "content": "tc", "published_date": "2025-01-02T00:00:00"}]})

    monkeypatch.setattr(websearch, "_http", _route_http({"api.search.brave.com": brave, "api.tavily.com": tavily}))
    with _secrets(brave="BK", tavily="TK"):
        b = se2.search_brave("q")
        t = se2.search_tavily("q")
    assert captured["brave"]["X-Subscription-Token"] == "BK"
    assert b["results"][0]["snippet"] == "2 days ago d"
    body, headers = captured["tavily"]
    assert body["query"] == "q" and headers["Authorization"] == "Bearer TK"
    assert t["results"][0]["snippet"] == "2025-01-02 tc"


# ── cascade ────────────────────────────────────────────────────────────


def _names(engines):
    return [getattr(f, "__name__", "?") for f in engines]


def test_auto_cascade_order_keys_and_switches():
    from ali import websearch

    with _cfg(), _secrets(), mock.patch.object(websearch, "_google_cse_ready", return_value=False):
        names = _names(websearch._engine_cascade("auto", []))
    assert names == ["search_bing_rss", "search_so360", "search_baidu", "search_sogou", "search_ddg", "search_wikipedia"]
    with _cfg(searxng_url="http://s", engines={"baidu": False, "bing": False}), _secrets(brave="k", serpapi="s"), \
            mock.patch.object(websearch, "_google_cse_ready", return_value=False):
        names = _names(websearch._engine_cascade("auto", []))
    assert names == ["search_serpapi_google", "search_brave", "search_so360", "search_sogou", "search_ddg",
                     "search_searxng", "search_wikipedia"]


def test_explicit_provider_puts_engine_first():
    from ali import websearch

    with _cfg(), _secrets():
        assert _names(websearch._engine_cascade("baidu", []))[:2] == ["search_baidu", "search_bing_rss"]
        assert _names(websearch._engine_cascade("ddg", []))[0] == "search_ddg"
        assert _names(websearch._engine_cascade("sogou", [])) == ["search_sogou", "search_bing_rss", "search_so360"]
        assert _names(websearch._engine_cascade("fast", [])) == ["search_bing_rss", "search_so360"]


def test_search_status_lists_all_engines():
    from ali import websearch

    with _cfg(engines={"sogou": False}), _secrets(tavily="x"):
        st = websearch.search_status()
    by_id = {e["id"]: e for e in st["engines"]}
    assert {"bing", "so360", "sogou", "wikipedia", "google_cse", "serpapi", "tavily", "brave", "baidu", "duckduckgo", "searxng"} <= set(by_id)
    assert by_id["sogou"]["enabled"] is False
    assert by_id["tavily"]["configured"] is True and by_id["brave"]["configured"] is False
    assert st["tavily_configured"] is True and st["fetch_pages"] is True


# ── fetch layer ────────────────────────────────────────────────────────


def test_opener_applies_tls_policy():
    from urllib.request import HTTPSHandler

    from ali import websearch

    def https_handlers(op):
        return [h for h in op.handlers if isinstance(h, HTTPSHandler)]

    with _cfg(verify_tls=False):
        ctx = [h._context for h in https_handlers(websearch._opener())]
    assert ctx and ctx[0].verify_mode == ssl.CERT_NONE
    with _cfg(verify_tls=True):
        strict = [h._context for h in https_handlers(websearch._opener())]
        relaxed = [h._context for h in https_handlers(websearch._opener(relaxed=True))]
    assert all(c is None or c.verify_mode != ssl.CERT_NONE for c in strict)
    assert relaxed and relaxed[-1].verify_mode == ssl.CERT_NONE


def test_search_extensions_fetch_uses_shared_http(monkeypatch):
    from ali import search_extensions as se, websearch

    seen = {}
    monkeypatch.setattr(websearch, "_http", lambda url, **k: (seen.update(url=url, **k), "ok")[1])
    assert se._fetch("https://x.org", headers={"Accept": "application/json"}) == "ok"
    assert seen["url"] == "https://x.org" and seen["headers"]["Accept"] == "application/json"


def test_parity_engine_does_not_recurse(monkeypatch):
    from ali import search_extensions as se, websearch

    calls = {"n": 0}

    def fake_structured(q, *, limit=8, deep=True):
        calls["n"] += 1
        # the nested cascade runs inside the parity worker: intent engines must be skipped
        assert websearch._intent_engines(q) == []
        assert se.search_minimax_parity(q)["errors"] == ["re-entry skipped"]
        return {"ok": True, "sources": [{"title": "t", "url": "https://u", "snippet": "s", "source": "bing"}]}

    monkeypatch.setattr(websearch, "search_structured", fake_structured)
    r = se.search_minimax_parity("tp53 review")
    assert calls["n"] == 1 and r["ok"]
    assert not se.in_parity_call()


# ── page fetch ─────────────────────────────────────────────────────────

ARTICLE = """<html><head><title>TP53 overview</title><script>var x=1;</script></head><body>
<nav>Home | About</nav>
<article><h1>TP53</h1><p>TP53 is mutated in about 50% of human cancers.</p>
<p>The gene encodes the p53 protein.</p><p>Unrelated sentence about the weather today.</p>
<p>Studies of TP53 mutations in 1,204 patients reported HR 0.71.</p></article>
<footer>© 2024</footer></body></html>"""


def test_html_to_text_and_passages():
    from ali.page_fetch import best_passages, html_to_text, page_title

    text = html_to_text(ARTICLE)
    assert "var x" not in text and "Home | About" not in text and "©" not in text
    assert "TP53 is mutated in about 50% of human cancers." in text.splitlines()
    assert page_title(ARTICLE) == "TP53 overview"
    ps = best_passages(text, "TP53 mutation cancers")
    assert ps[0].startswith("TP53 is mutated") and not any("weather" in p for p in ps)


def test_fetch_pages_parallel_skips_failures_and_non_html():
    from ali.page_fetch import fetch_pages

    sources = [
        {"url": "https://ok.org/a"}, {"url": "https://bad.org/b"},
        {"url": "https://x.org/paper.pdf"}, {"url": "https://ok.org/c"},
    ]

    def fetch(url):
        if "bad" in url:
            raise OSError("boom")
        return ARTICLE

    rows = fetch_pages(sources, "TP53 cancers", max_pages=3, fetch=fetch)
    assert [(r["n"], r["ok"]) for r in rows] == [(1, True), (2, False), (4, True)]  # pdf skipped, max 3
    assert "boom" in rows[1]["error"]
    assert rows[0]["passages"] and rows[0]["title"] == "TP53 overview"
    assert fetch_pages([], "q") == []
    assert fetch_pages(sources, "q", max_pages=0, fetch=fetch) == []


def test_fetch_page_rejects_pdf_body_and_unmatched():
    from ali.page_fetch import fetch_page

    assert fetch_page("https://a.org", "q", fetch=lambda u: "%PDF-1.7 ...")["error"] == "empty or non-HTML"
    r = fetch_page("https://a.org", "zzzz qqqq", fetch=lambda u: ARTICLE)
    assert r["ok"] is False and r["error"] == "no passage matched the query"
    assert fetch_page("ftp://a.org", "q")["error"].startswith("skipped")


@pytest.mark.parametrize("provider", ["auto", "baidu", "tavily"])
def test_cascade_never_raises_without_keys(provider):
    from ali import websearch

    with _cfg(), _secrets():
        assert isinstance(websearch._engine_cascade(provider, []), list)


def test_page_fetch_refuses_private_and_local_addresses():
    from ali.page_fetch import fetch_page, is_public_url

    for url in ("http://127.0.0.1:8765/api/settings", "http://localhost/x", "http://169.254.169.254/latest/meta-data",
                "http://10.0.0.5/", "http://192.168.1.1/", "http://[::1]/", "http://printer.local/", "file:///etc/passwd",
                "http://0.0.0.0/"):
        assert not is_public_url(url), url
    assert is_public_url("https://8.8.8.8/")
    assert is_public_url("https://example.org/page", resolve=False)
    with mock.patch("socket.getaddrinfo", return_value=[(0, 0, 0, "", ("10.1.2.3", 0))]):
        assert not is_public_url("https://evil.example/")  # public name resolving to a private IP
    # the default fetcher is never called for such URLs
    with mock.patch("ali.page_fetch._default_fetch", side_effect=AssertionError("must not fetch")):
        assert fetch_page("http://127.0.0.1:8765/api/settings", "q")["error"] == "skipped (not a public address)"


def test_redirect_to_private_address_is_refused():
    from urllib.request import Request

    from ali import websearch
    from ali.page_fetch import is_public_url

    h = websearch._CheckedRedirect(is_public_url)
    req = Request("https://example.org/")
    with pytest.raises(OSError, match="non-public"):
        h.redirect_request(req, None, 302, "Found", {}, "http://127.0.0.1:8765/api/settings")
    ok = h.redirect_request(req, None, 302, "Found", {}, "https://8.8.8.8/next")
    assert ok.full_url == "https://8.8.8.8/next"
    with _cfg():
        assert any(isinstance(x, websearch._CheckedRedirect) for x in websearch._opener(redirect_check=is_public_url).handlers)
