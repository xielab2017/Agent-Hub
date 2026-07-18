"""Search extensions for Agent Hub.

Adds intent-aware routing + specialized engines on top of `websearch.py`:

  * Intent router   — classifies query → event / academic / news / code / general
  * News engines    — Sina Sports RSS, Sina News, Dongqiudi (Chinese news feeds)
  * Academic engines — OpenAlex, arXiv, PubMed (free, no key required)
  * Grounding gate  — relevance score + fallback template (no hallucinated scores)

All engines return the same dict shape as `websearch.search_*`:
    {"ok": bool, "query": str, "results": [{title,snippet,url,source}, ...],
     "errors": [...], "engine": str}
"""

from __future__ import annotations

import json
import os
import re
import socket
import ssl
from html import unescape
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode, quote_plus
from urllib.request import ProxyHandler, Request, build_opener, urlopen

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# 1. Intent router
# ---------------------------------------------------------------------------

# Each entry: (intent_name, frozenset of trigger keywords)
_INTENT_RULES: list[tuple[str, frozenset[str]]] = [
    ("event", frozenset({
        # 赛事实体
        "世界杯", "欧洲杯", "美洲杯", "欧冠", "亚冠", "英超", "西甲", "德甲",
        "意甲", "法甲", "中超", "J联赛", "K联赛", "NBA", "CBA", "WNBA",
        "FIFA", "Euro", "World Cup", "Champions League",
        # 时效词
        "比分", "赛程", "今晚比赛", "今晚赛事", "赛事直播", "对阵", "积分榜",
        "战况", "战局", "战报", "进球", "红牌", "黄牌", "点球", "淘汰赛", "小组赛",
        "决赛", "半决赛", "1/8决赛", "1/4决赛",
    })),
    ("academic", frozenset({
        "论文", "文献", "literature", "doi", "arxiv", "pubmed", "openalex",
        "research", "研究综述", "meta-analysis", "meta分析", "荟萃分析",
        "preprint", "预印本", "期刊", "影响因子", "h-index", "h指数",
        "期刊分区", "JCR", "中科院分区",
    })),
    ("news", frozenset({
        "新闻", "最新", "今日", "昨天", "本周", "刚刚", "突发", "报道",
        "官宣", "发布会", "新闻发布会", "快讯", "头条",
    })),
    ("code", frozenset({
        "github", "stackoverflow", "stack overflow", "pypi", "npm",
        "源代码", "源码", "API 调用", "api call", "怎么用", "how to use",
    })),
]
INTENTS = {name: kws for name, kws in _INTENT_RULES}


def classify_intent(query: str) -> str:
    """Return one of: event / academic / news / code / general.

    Priority: event > academic > news > code. English research-phrase fallback:
    if query is mostly lowercase ASCII noun-phrase (no event/code/news markers),
    lean academic — researchers often search with English technical terms.
    """
    q = (query or "").strip().lower()
    if not q:
        return "general"
    for name, kws in _INTENT_RULES:
        if any(k.lower() in q for k in kws):
            return name
    # Heuristic: English research-style queries (≥2 lowercase words, ≥2 English tokens).
    en_tokens = re.findall(r"[a-z][a-z\-]{2,}", q)
    if len(en_tokens) >= 2 and not re.search(r"[\u4e00-\u9fff]", q):
        # No Chinese, no event/code/news marker → likely a research query.
        return "academic"
    return "general"


# ---------------------------------------------------------------------------
# 2. Low-level fetch (mirrors websearch._fetch but inlined for independence)
# ---------------------------------------------------------------------------

def _secret(slot: str) -> str:
    try:
        from .secrets import get_api_key
        return (get_api_key(slot) or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _proxy_handlers() -> list[Any]:
    proxy = ""
    try:
        from .settings import load_campus_config
        cfg = load_campus_config() or {}
        proxy = str(cfg.get("search", {}).get("proxy") or "").strip()
    except Exception:  # noqa: BLE001
        proxy = ""
    # Only use a proxy when explicitly configured for Search.
    if proxy.strip():
        return [ProxyHandler({"http": proxy, "https": proxy})]
    # Bypass broken macOS system proxies (e.g. Clash :7890 TLS hangs)
    return [ProxyHandler({})]


def _ssl_context() -> ssl.SSLContext | None:
    verify = True
    try:
        from .settings import load_campus_config
        cfg = load_campus_config() or {}
        verify = cfg.get("search", {}).get("verify_tls", True) is not False
    except Exception:  # noqa: BLE001
        verify = True
    if verify:
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _fetch(url: str, *, timeout: float = 6.0, headers: dict[str, str] | None = None) -> str:
    # Specialized feeds are optional; cap each outbound request so they cannot
    # block the planner when a campus network silently drops a connection.
    timeout = min(max(float(timeout), 1.0), 4.0)
    h = {"User-Agent": _UA, "Accept": "*/*", "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
    if headers:
        h.update(headers)
    req = Request(url, headers=h)
    handlers = _proxy_handlers()
    ctx = _ssl_context()
    opener = build_opener(*handlers) if handlers else None

    def _open():
        if opener is not None:
            return opener.open(req, timeout=timeout)
        if ctx is not None:
            return urlopen(req, timeout=timeout, context=ctx)
        return urlopen(req, timeout=timeout)

    try:
        with _open() as resp:
            data = resp.read()
            return data.decode("utf-8", errors="replace")
    except Exception as first:  # noqa: BLE001
        msg = str(first).lower()
        if any(k in msg for k in ("ssl", "handshake", "certificate", "timed out", "timeout", "eof")) \
                or isinstance(first, (ssl.SSLError, TimeoutError, socket.timeout, URLError)):
            # relaxed retry
            relaxed = ssl.create_default_context()
            relaxed.check_hostname = False
            relaxed.verify_mode = ssl.CERT_NONE
            with urlopen(req, timeout=min(timeout, 3.5), context=relaxed) as resp:
                return resp.read().decode("utf-8", errors="replace")
        raise


def _strip_html(s: str) -> str:
    s = unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()


def _result(title: str, snippet: str, url: str, source: str) -> dict[str, Any]:
    return {
        "title": _strip_html(title)[:200],
        "snippet": _strip_html(snippet)[:500],
        "url": (url or "").strip(),
        "source": source,
    }


# ---------------------------------------------------------------------------
# 3. Chinese news engines (RSS-based, no key)
# ---------------------------------------------------------------------------
# Live sport/news homepages (RSS endpoints on Sina have been mostly deprecated).
# We scrape the HTML homepages instead — they are public, no key required, and
# the article headlines + URLs are reliable.
_SINA_NEWS_HOME = (
    "https://www.sina.com.cn/",
    "https://news.sina.com.cn/",
)
_SINA_SPORTS_HOME = (
    "https://sports.sina.com.cn/",
    "https://sports.sina.com.cn/global/",
    "https://sports.sina.com.cn/china/",
    "https://sports.sina.com.cn/basketball/",
)
# Article URL pattern Sina uses (covers all sport/news subdomains).
_SINA_NAV_DENY = re.compile(
    r"(联系我们|网站律师|版权所有|招聘信息|网站地图|客户端|意见反馈|新浪新闻"
    r"|新浪体育意见反馈|导航|登录|注册|订阅|客户端下载|App|下载|客户端"
    r"|手机新浪网|移动版|简体|繁体|English|网站首页|加入收藏|设为主页"
    r"|通行证|新浪通行证|新浪首页|新浪网|首页|导航栏|我要反馈|我要投稿"
    r"|广告服务|公益|About Sina|广告刊例|我要推广|诚聘英才|新浪微博"
    r"|新浪娱乐|新浪财经|新浪体育|新浪科技|新浪博客|新浪游戏)",
    re.IGNORECASE,
)
# Article URL pattern Sina uses: dated paths like /l/2026-07-16/doc-inXXXXX.shtml
_SINA_ARTICLE_URL = re.compile(
    r'href="(https?://(?:sports|news|www|finance|tech|edu|ent|auto|eladies|games?|video|blog|book|\\w+)\.sina\.com\.cn/'
    r'[a-z0-9_/\-]*(?:20\d{2}-\d{2}-\d{2}/doc-[a-z0-9]+|[a-z0-9_/\-]+\.(?:shtml|html))\.[a-z]{3,5})"'
    r'[^>]*>([^<]{6,140})</a>',
    re.IGNORECASE,
)


def _parse_rss_items(xml_text: str, source: str, limit: int) -> list[dict[str, Any]]:
    """Tolerant RSS parser — works for Sina-style RSS that isn't perfectly namespace-clean."""
    items: list[dict[str, Any]] = []
    for m in re.finditer(r"<item\b[^>]*>([\s\S]*?)</item>", xml_text or ""):
        if len(items) >= limit:
            break
        body = m.group(1)
        title = re.search(r"<title>(?:<!\[CDATA\[)?([\s\S]*?)(?:\]\]>)?</title>", body)
        link = re.search(r"<link>(?:<!\[CDATA\[)?([\s\S]*?)(?:\]\]>)?</link>", body)
        desc = re.search(r"<description>(?:<!\[CDATA\[)?([\s\S]*?)(?:\]\]>)?</description>", body)
        pub = re.search(r"<pubDate>([\s\S]*?)</pubDate>", body)
        if not title or not link:
            continue
        items.append(
            _result(
                title.group(1).strip(),
                (desc.group(1).strip() if desc else "") + (
                    f" ({pub.group(1).strip()})" if pub else ""
                ),
                link.group(1).strip(),
                source,
            )
        )
    return items


def _parse_sina_html(html_text: str, source: str, limit: int) -> list[dict[str, Any]]:
    """Extract (url, title) pairs from Sina HTML homepages — skip nav/footer noise."""
    if not html_text:
        return []
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    for url, title in _SINA_ARTICLE_URL.findall(html_text):
        title = title.strip()
        if not title or _SINA_NAV_DENY.search(title):
            continue
        # Skip URLs that are clearly section pages (no article slug)
        if url.endswith(("index.html", "index.shtml", ".cn/")):
            continue
        if url in seen:
            continue
        seen.add(url)
        items.append(_result(title, "", url, source))
        if len(items) >= limit:
            break
    return items


def search_sina_news(query: str, *, limit: int = 8, timeout: float = 6.0) -> dict[str, Any]:
    """Sina News homepage scrape — Chinese breaking news headlines."""
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "empty query", "results": [], "engine": "sina_news"}
    errors: list[str] = []
    items: list[dict[str, Any]] = []
    q_tokens = [t for t in re.split(r"[\s/|，,、]+", q) if len(t) >= 2]
    try:
        for url in _SINA_NEWS_HOME:
            try:
                html = _fetch(url, timeout=timeout)
                items.extend(_parse_sina_html(html, "sina_news", limit=limit * 3))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{url}: {exc}")
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))

    def _hit(it: dict[str, Any]) -> int:
        blob = f"{it.get('title') or ''} {it.get('snippet') or ''}"
        return sum(1 for t in q_tokens if t.lower() in blob.lower())

    matched = [it for it in items if _hit(it) > 0]
    matched.sort(key=_hit, reverse=True)
    out = matched or items  # soften: if nothing matches the query, return latest headlines anyway
    return {
        "ok": bool(out),
        "query": q,
        "results": out[:limit],
        "errors": errors[:2],
        "engine": "sina_news",
    }


def search_sina_sports(query: str, *, limit: int = 8, timeout: float = 6.0) -> dict[str, Any]:
    """Sina Sports HTML scrape — Chinese football/basketball/other-sport headlines."""
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "empty query", "results": [], "engine": "sina_sports"}
    errors: list[str] = []
    items: list[dict[str, Any]] = []
    q_tokens = [t for t in re.split(r"[\s/|，,、]+", q) if len(t) >= 2]
    try:
        for url in _SINA_SPORTS_HOME:
            try:
                html = _fetch(url, timeout=timeout)
                items.extend(_parse_sina_html(html, "sina_sports", limit=limit * 3))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{url}: {exc}")
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))

    def _hit(it: dict[str, Any]) -> int:
        blob = f"{it.get('title') or ''} {it.get('snippet') or ''}"
        return sum(1 for t in q_tokens if t.lower() in blob.lower())

    matched = [it for it in items if _hit(it) > 0]
    matched.sort(key=_hit, reverse=True)
    # Never dump unrelated homepage headlines when the query is specific
    # (e.g. 世界杯/FIFA) — empty is better than lottery/围棋 noise.
    out = matched
    return {
        "ok": bool(out),
        "query": q,
        "results": out[:limit],
        "errors": errors[:2],
        "engine": "sina_sports",
    }


def search_wikipedia_event(query: str, *, limit: int = 6, timeout: float = 4.0) -> dict[str, Any]:
    """Bilingual Wikipedia look-up tailored for event / sports queries.

    Wikipedia is the cheapest reliable source for *structured* event data
    (tournament brackets, team rosters, host cities, historical results).
    The standard opensearch endpoint returns titles + 1-line snippets; we
    also pull the first ~400 chars of each article so downstream agents
    can quote real facts instead of guessing scores.
    """
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "empty query", "results": [], "engine": "wikipedia_event"}
    errors: list[str] = []
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for lang in ("zh", "en"):
        if len(items) >= limit:
            break
        try:
            payload = json.loads(_fetch(
                f"https://{lang}.wikipedia.org/w/api.php?" + urlencode({
                    "action": "query", "list": "search", "srsearch": q,
                    "srlimit": min(limit, 8), "format": "json", "utf8": "1",
                }),
                timeout=timeout,
            ))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"search/{lang}: {exc}")
            continue
        hits = ((payload or {}).get("query") or {}).get("search") or []
        for h in hits:
            title = str(h.get("title") or "").strip()
            if not title or title in seen:
                continue
            seen.add(title)
            snippet = _strip_html(str(h.get("snippet") or ""))
            # Pull the first paragraph for a real source quote.
            try:
                extract_payload = json.loads(_fetch(
                    f"https://{lang}.wikipedia.org/w/api.php?" + urlencode({
                        "action": "query", "prop": "extracts", "exintro": "1",
                        "explaintext": "1", "exsentences": "3",
                        "titles": title, "format": "json", "utf8": "1",
                    }),
                    timeout=timeout,
                ))
                pages = ((extract_payload or {}).get("query") or {}).get("pages") or {}
                for page in pages.values():
                    extract = str(page.get("extract") or "").strip()
                    if extract and len(extract) > len(snippet):
                        snippet = extract[:600]
            except Exception:  # noqa: BLE001
                pass
            url = f"https://{lang}.wikipedia.org/wiki/{quote_plus(title.replace(' ', '_'))}"
            items.append({
                "title": title,
                "snippet": snippet or title,
                "url": url,
                "source": f"wikipedia_{lang}",
            })
            if len(items) >= limit:
                break
    return {
        "ok": bool(items),
        "query": q,
        "results": items[:limit],
        "errors": errors[:2],
        "engine": "wikipedia_event",
    }


# ---------------------------------------------------------------------------
# 4. Academic engines (free, no key)
# ---------------------------------------------------------------------------

def search_openalex(query: str, *, limit: int = 8, timeout: float = 15.0) -> dict[str, Any]:
    """OpenAlex works API — `display_name`, abstract_inverted_index reconstructed to text."""
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "empty query", "results": [], "engine": "openalex"}
    errors: list[str] = []
    items: list[dict[str, Any]] = []
    try:
        url = "https://api.openalex.org/works?" + urlencode({
            "search": q,
            "per_page": min(limit, 25),
        })
        text = _fetch(url, timeout=timeout, headers={"Accept": "application/json"})
        data = json.loads(text)
        for w in data.get("results") or []:
            title = w.get("title") or w.get("display_name") or ""
            abstract = _reconstruct_inverted(w.get("abstract_inverted_index") or {})
            year = (w.get("publication_year") or "")
            authors = ", ".join(
                (a.get("author") or {}).get("display_name", "")
                for a in (w.get("authorships") or [])[:3]
            )
            venue = (w.get("primary_location") or {}).get("source", {}) or {}
            venue_name = venue.get("display_name") or ""
            doi = w.get("doi") or ""
            url_o = doi or w.get("id") or ""
            snippet = " · ".join(filter(None, [
                f"[{year}]" if year else "",
                venue_name,
                authors,
                abstract[:240],
            ]))
            items.append(_result(title, snippet, url_o, "openalex"))
            if len(items) >= limit:
                break
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
    return {
        "ok": bool(items),
        "query": q,
        "results": items[:limit],
        "errors": errors[:2],
        "engine": "openalex",
    }


def _reconstruct_inverted(idx: dict[str, list[int]]) -> str:
    """OpenAlex stores abstracts as inverted index; reconstruct a short preview."""
    if not idx:
        return ""
    pos_word: list[tuple[int, str]] = []
    for word, positions in idx.items():
        for p in positions:
            pos_word.append((p, word))
    pos_word.sort()
    return " ".join(w for _, w in pos_word)


def search_arxiv(query: str, *, limit: int = 8, timeout: float = 8.0) -> dict[str, Any]:
    """arXiv API — Atom feed, free, no key."""
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "empty query", "results": [], "engine": "arxiv"}
    errors: list[str] = []
    items: list[dict[str, Any]] = []
    try:
        url = "http://export.arxiv.org/api/query?" + urlencode({
            "search_query": f"all:{q}",
            "start": 0,
            "max_results": min(limit, 20),
        })
        text = _fetch(url, timeout=timeout, headers={"Accept": "application/atom+xml,*/*"})
        # Atom entries
        for m in re.finditer(r"<entry>([\s\S]*?)</entry>", text or ""):
            if len(items) >= limit:
                break
            body = m.group(1)
            title = re.search(r"<title>([\s\S]*?)</title>", body)
            link = re.search(r'<link[^>]*href="([^"]+)"', body)
            summary = re.search(r"<summary>([\s\S]*?)</summary>", body)
            published = re.search(r"<published>([\s\S]*?)</published>", body)
            authors = ", ".join(re.findall(r"<author>\s*<name>([\s\S]*?)</name>", body))[:200]
            year_m = re.search(r"\b(19|20)\d{2}\b", published.group(1) if published else "")
            snippet = " · ".join(filter(None, [
                f"[{year_m.group(0)}]" if year_m else "",
                authors,
                _strip_html(summary.group(1))[:240] if summary else "",
            ]))
            items.append(_result(
                title.group(1).strip() if title else "",
                snippet,
                link.group(1).strip() if link else "",
                "arxiv",
            ))
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
    return {
        "ok": bool(items),
        "query": q,
        "results": items[:limit],
        "errors": errors[:2],
        "engine": "arxiv",
    }


def search_pubmed(query: str, *, limit: int = 8, timeout: float = 8.0) -> dict[str, Any]:
    """NCBI PubMed eSearch + eSummary — free, no key (rate-limited to 3 rps without key)."""
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "empty query", "results": [], "engine": "pubmed"}
    errors: list[str] = []
    items: list[dict[str, Any]] = []
    try:
        # 1) eSearch to get IDs
        es_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + urlencode({
            "db": "pubmed",
            "term": q,
            "retmax": min(limit, 20),
            "retmode": "json",
        })
        es = json.loads(_fetch(es_url, timeout=timeout, headers={"Accept": "application/json"}))
        ids = (es.get("esearchresult") or {}).get("idlist") or []
        if ids:
            # 2) eSummary to fetch metadata
            su_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?" + urlencode({
                "db": "pubmed",
                "id": ",".join(ids),
                "retmode": "json",
            })
            su = json.loads(_fetch(su_url, timeout=timeout, headers={"Accept": "application/json"}))
            result = su.get("result") or {}
            uids = result.get("uids") or ids
            for pid in uids:
                rec = result.get(str(pid)) or {}
                title = rec.get("title") or ""
                pubdate = rec.get("pubdate") or ""
                source = rec.get("source") or ""
                authors = ", ".join(
                    (a.get("name") or "") for a in (rec.get("authors") or [])[:3]
                )
                snippet = " · ".join(filter(None, [
                    f"[{pubdate[:4]}]" if pubdate else "",
                    source,
                    authors,
                ]))
                items.append(_result(
                    title,
                    snippet,
                    f"https://pubmed.ncbi.nlm.nih.gov/{pid}/",
                    "pubmed",
                ))
                if len(items) >= limit:
                    break
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
    return {
        "ok": bool(items),
        "query": q,
        "results": items[:limit],
        "errors": errors[:2],
        "engine": "pubmed",
    }


def search_minimax_parity(
    query: str,
    *,
    limit: int = 8,
    timeout: float = 8.0,
) -> dict[str, Any]:
    """MiniMax code parity engine.

    Honours advanced operators (`site:`, `inurl:`, `intitle:`, `intext:`,
    `inanchor:`, `-exclude`, `~synonym`, `"exact"`) by running a single
    `websearch.search_structured` call and post-filtering results.  For
    quoted queries it also runs the cleaned (un-quoted) variant in
    parallel so the user gets both the strict and the broader result set,
    which is what MiniMax code does to avoid empty responses on strict
    queries.  Falls back to the primary engine gracefully if the parity
    module is unavailable.
    """
    from .minimax_search_parity import (
        format_brief,
        parallel_search,
        parse_query,
    )

    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "empty query", "results": [], "engine": "minimax_parity"}

    parsed = parse_query(q)
    cleaned = parsed.cleaned or (parsed.exact[0] if parsed.exact else q)
    queries_to_run: list[str] = [cleaned]
    if parsed.exact and cleaned != parsed.exact[0]:
        queries_to_run.append(parsed.exact[0])

    def _call(qu: str) -> dict[str, Any]:
        # Lazy import to avoid cycles; `websearch` does the real work.
        from . import websearch as _ws

        return _ws.search_structured(qu, limit=min(limit, 6), deep=False)

    par = parallel_search(queries_to_run, search_fn=_call, max_workers=len(queries_to_run))

    # Merge results in original query order, de-dup by URL.
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    for block in par.blocks:
        for r in block.get("results") or []:
            url = str(r.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            r2 = dict(r)
            r2["engine"] = r2.get("engine") or "minimax_parity"
            items.append(r2)
            if len(items) >= limit:
                break
        if len(items) >= limit:
            break

    errors: list[str] = []
    if par.errors:
        errors.extend(par.errors[:2])
    if not items and parsed.exact:
        # Last-ditch: try the raw query without operator cleanup.
        try:
            raw = _call(q)
            for r in raw.get("results") or []:
                url = str(r.get("url") or "").strip()
                if not url or url in seen:
                    continue
                seen.add(url)
                items.append(r)
                if len(items) >= limit:
                    break
            if raw.get("error"):
                errors.append(str(raw["error"]))
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    return {
        "ok": bool(items),
        "query": q,
        "results": items[:limit],
        "errors": errors[:2],
        "engine": "minimax_parity",
        "cleaned_query": cleaned,
        "operators": {
            "site": parsed.site,
            "inurl": parsed.inurl,
            "intitle": parsed.intitle,
            "intext": parsed.intext,
            "inanchor": parsed.inanchor,
            "exclude": list(parsed.exclude),
            "synonym": list(parsed.synonym),
            "exact": list(parsed.exact),
        },
        "combined_markdown": par.combined_markdown or format_brief(items),
    }


# ---------------------------------------------------------------------------
# 5. Engine registry by intent
# ---------------------------------------------------------------------------

INTENT_ENGINES: dict[str, list] = {
    # Event: sport scores / standings / bracket queries.
    # ‑ sina_sports carries Chinese football/basketball headlines and is
    #   campus-reachable.
    # ‑ wikipedia (zh + en) provides structured bracket / team / venue
    #   pages that no news engine exposes cleanly.
    # ‑ minimax_parity fans out the cleaned + raw queries in parallel and
    #   honours advanced operators (site:/inurl:/...).
    # The general cascade in websearch._search_once still adds Bing /
    # So360 / Sogou for breadth, so the event intent is *additive* —
    # not exclusive.
    "event": [search_sina_sports, search_wikipedia_event, search_minimax_parity],
    "news": [search_sina_news, search_sina_sports, search_minimax_parity],
    "academic": [search_openalex, search_arxiv, search_pubmed, search_minimax_parity],
    "code": [search_minimax_parity],   # operators like `site:github.com` shine here
    "general": [search_wikipedia_event, search_minimax_parity],
}


def engines_for_intent(intent: str) -> list:
    """Return the ordered engine list for an intent (empty list if none)."""
    return list(INTENT_ENGINES.get(intent, []))


# ---------------------------------------------------------------------------
# 6. Grounding gate (relevance score + fallback template)
# ---------------------------------------------------------------------------

def relevance_score(query: str, results: list[dict[str, Any]]) -> float:
    """Return 0..1. Computes average token coverage across results.

    Tokens: Chinese entity keywords + English words (not whole-phrase-only).
    Coverage: hits_in_top_n / n (capped at 5).
    """
    if not query or not results:
        return 0.0
    try:
        from .websearch import _query_tokens

        tokens = _query_tokens(query)
    except Exception:  # noqa: BLE001
        tokens = [t for t in re.split(r"[\s/|，,、]+", query) if len(t) >= 2]
    if not tokens:
        return 0.0
    n = min(len(results), 5)
    cov = 0.0
    for r in results[:n]:
        blob = f"{r.get('title') or ''} {r.get('snippet') or ''}".lower()
        if not blob.strip():
            continue
        hits = sum(1 for t in tokens if t.lower() in blob)
        cov += hits / max(len(tokens), 1)
    return cov / max(n, 1)


def fallback_message(query: str, intent: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the no-grounding response: short structured fallback, no fabrication."""
    zh_map = {
        "event": (
            "本会话暂无体育赛事实时数据通道，请直接查看：\n"
            "  • FIFA 官网 fifa.com → Live Scores\n"
            "  • 央视体育 / 咪咕视频（中文解说）\n"
            "  • 虎扑、懂球帝、ESPN 中文版"
        ),
        "academic": (
            "本轮公开学术搜索未召回命中，备选通道：\n"
            "  • Google Scholar → scholar.google.com\n"
            "  • PubMed → pubmed.ncbi.nlm.nih.gov\n"
            "  • arXiv → arxiv.org（如已返回结果但相关度低，请补充更具体的关键词）"
        ),
        "news": (
            "本轮新闻通道未召回命中，备选：\n"
            "  • 新浪新闻 → news.sina.com.cn\n"
            "  • 央视新闻 → news.cctv.com\n"
            "  • The Paper / 澎湃新闻"
        ),
        "code": (
            "本轮代码搜索未召回命中，备选：\n"
            "  • GitHub → github.com\n"
            "  • Stack Overflow → stackoverflow.com\n"
            "  • PyPI / npm 官方文档"
        ),
        "general": "本轮检索未召回足够相关结果，建议换个具体关键词，或直接告知我你期望的来源（例如「只看新闻」「只看论文」）。",
    }
    msg = zh_map.get(intent, zh_map["general"])
    return {
        "ok": False,
        "offline": True,
        "intent": intent,
        "query": query,
        "results": results[:3],   # still keep a few weak hits if any
        "note": msg,
    }


def apply_grounding_gate(query: str, intent: str, results: list[dict[str, Any]], *,
                         min_score: float = 0.2) -> dict[str, Any]:
    """If relevance is too low OR result count is too small, swap in a fallback note."""
    if len(results) < 2:
        return fallback_message(query, intent, results)
    score = relevance_score(query, results)
    if score < min_score:
        return fallback_message(query, intent, results)
    return {"ok": True, "intent": intent, "relevance": round(score, 3), "results": results}


__all__ = [
    "classify_intent",
    "engines_for_intent",
    "INTENTS",
    "INTENT_ENGINES",
    "search_sina_news",
    "search_sina_sports",
    "search_openalex",
    "search_arxiv",
    "search_pubmed",
    "relevance_score",
    "fallback_message",
    "apply_grounding_gate",
]
