"""External + deep information search for Agent Hub.

Campus networks often block Google/DDG/Wikipedia HTTPS. Working paths here:
  - Bing RSS (Google-like SERP, reachable on many campus nets)
  - 360 so.com / Sogou HTML (Chinese deep coverage)
  - Google Programmable Search (CSE) when API key + CX configured
  - SerpAPI Google when key configured
  - Optional HTTP(S)_PROXY for Google endpoints

Deep search expands queries and merges multi-engine results.
"""

from __future__ import annotations

import json
import os
import re
import socket
import ssl
import time
import xml.etree.ElementTree as ET
from html import unescape
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener, urlopen

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def _search_cfg() -> dict[str, Any]:
    try:
        from .settings import load_campus_config

        cfg = load_campus_config() or {}
        return dict(cfg.get("search") or {})
    except Exception:  # noqa: BLE001
        return {}


def _secret(slot: str) -> str:
    try:
        from .secrets import get_api_key

        return (get_api_key(slot) or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _proxy_handlers() -> list[Any]:
    """Return opener handlers.

    When campus/env proxy is unset, force ProxyHandler({}) so urllib does not
    silently pick a broken macOS system proxy (common Clash :7890 TLS hangs).
    """
    sc = _search_cfg()
    # Do not inherit a broken desktop proxy implicitly.  Search proxying is an
    # explicit Control Center setting; unset means direct outbound requests.
    proxy = str(sc.get("proxy") or "").strip()
    if proxy:
        return [ProxyHandler({"http": proxy, "https": proxy})]
    return [ProxyHandler({})]


def _ssl_context(*, relaxed: bool = False) -> ssl.SSLContext | None:
    sc = _search_cfg()
    verify = sc.get("verify_tls", True)
    if verify and not relaxed:
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _fetch(url: str, *, timeout: float = 8.0, relaxed_tls: bool = False) -> str:
    # A stalled public endpoint must not freeze auto-plan or chat.  The caller
    # can still fan out across engines, so a short per-request cap is safer.
    timeout = min(max(float(timeout), 1.0), 4.0)
    req = Request(
        url,
        headers={
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "identity",
            "Connection": "close",
        },
    )
    handlers = _proxy_handlers()
    ctx = _ssl_context(relaxed=relaxed_tls)
    opener = build_opener(*handlers) if handlers else None

    def _open():
        if opener is not None:
            return opener.open(req, timeout=timeout)
        if ctx is not None:
            return urlopen(req, timeout=timeout, context=ctx)
        return urlopen(req, timeout=timeout)

    try:
        with _open() as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as first:  # noqa: BLE001
        msg = str(first).lower()
        sslish = any(
            k in msg for k in ("ssl", "handshake", "certificate", "timed out", "timeout", "eof")
        ) or isinstance(first, (ssl.SSLError, TimeoutError, socket.timeout, URLError))
        if relaxed_tls or not sslish:
            raise
        with (
            build_opener(*handlers).open(req, timeout=min(timeout, 3.5))
            if handlers
            else urlopen(req, timeout=min(timeout, 3.5), context=_ssl_context(relaxed=True))
        ) as resp:
            return resp.read().decode("utf-8", errors="replace")


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


# ── engines ──────────────────────────────────────────────────────────────


def search_bing_rss(query: str, *, limit: int = 8, timeout: float = 8.0) -> dict[str, Any]:
    """Bing RSS — Google-like ranking; usually works on campus when Google SSL fails."""
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "empty query", "results": [], "engine": "bing_rss"}
    errors: list[str] = []
    results: list[dict[str, Any]] = []
    try:
        xml_text = _fetch(
            "https://www.bing.com/search?" + urlencode({"q": q, "format": "rss", "count": min(limit, 20)}),
            timeout=timeout,
        )
        root = ET.fromstring(xml_text)
        for item in root.findall(".//item")[:limit]:
            results.append(
                _result(
                    item.findtext("title") or q,
                    item.findtext("description") or "",
                    item.findtext("link") or "",
                    "bing",
                )
            )
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
    return {
        "ok": bool(results),
        "query": q,
        "results": results,
        "errors": errors[:2],
        "engine": "bing_rss",
    }


def search_so360(query: str, *, limit: int = 8, timeout: float = 8.0) -> dict[str, Any]:
    """360 so.com HTML — strong Chinese coverage on campus."""
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "empty query", "results": [], "engine": "so360"}
    errors: list[str] = []
    results: list[dict[str, Any]] = []
    try:
        html = _fetch("https://www.so.com/s?" + urlencode({"q": q}), timeout=timeout)
        for block in re.findall(r'<li class="res-list"[\s\S]*?</li>', html)[: limit + 2]:
            a = re.search(r'<h3[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>([\s\S]*?)</a>', block)
            if not a:
                continue
            href = a.group(1)
            if "image.so.com" in href or href.startswith("javascript:"):
                continue
            sn = re.search(r'class="res-desc"[^>]*>([\s\S]*?)</p>', block)
            if not sn:
                sn = re.search(r'class="res-rich"[\s\S]*?<p[^>]*>([\s\S]*?)</p>', block)
            results.append(_result(a.group(2), sn.group(1) if sn else "", href, "so360"))
            if len(results) >= limit:
                break
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
    return {"ok": bool(results), "query": q, "results": results, "errors": errors[:2], "engine": "so360"}


def search_sogou(query: str, *, limit: int = 8, timeout: float = 8.0) -> dict[str, Any]:
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "empty query", "results": [], "engine": "sogou"}
    errors: list[str] = []
    results: list[dict[str, Any]] = []
    try:
        html = _fetch("https://www.sogou.com/web?" + urlencode({"query": q}), timeout=timeout)
        for block in re.findall(r'<div class="vrwrap"[\s\S]*?</div>\s*(?=<div class="vrwrap"|<div id="pagebar")', html)[
            : limit + 3
        ]:
            a = re.search(r"<h3[\s\S]*?<a[^>]*href=\"([^\"]+)\"[^>]*>([\s\S]*?)</a>", block)
            if not a:
                continue
            href = a.group(1)
            if href.startswith("javascript:"):
                continue
            if href.startswith("/"):
                href = "https://www.sogou.com" + href
            sn = re.search(r'class="star-wiki"|class="str-text"|class="space-txt"[\s\S]*?>([\s\S]*?)</(?:p|div|span)>', block)
            results.append(_result(a.group(2), sn.group(1) if sn else "", href, "sogou"))
            if len(results) >= limit:
                break
        if not results:
            for a in re.finditer(r"<h3[\s\S]*?<a[^>]*href=\"([^\"]+)\"[^>]*>([\s\S]*?)</a>", html):
                href = a.group(1)
                if href.startswith("javascript:") or "sogou.com" in href and "/web?" in href:
                    continue
                if href.startswith("/"):
                    href = "https://www.sogou.com" + href
                results.append(_result(a.group(2), "", href, "sogou"))
                if len(results) >= limit:
                    break
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
    return {"ok": bool(results), "query": q, "results": results, "errors": errors[:2], "engine": "sogou"}


def search_google_cse(query: str, *, limit: int = 8, timeout: float = 10.0) -> dict[str, Any]:
    """Google Programmable Search (Custom Search JSON API)."""
    q = (query or "").strip()
    sc = _search_cfg()
    key = _secret("google_cse") or _secret("GOOGLE_CSE_API_KEY") or os.environ.get("GOOGLE_CSE_API_KEY", "").strip()
    cx = (sc.get("google_cse_cx") or os.environ.get("GOOGLE_CSE_CX") or "").strip()
    if not q:
        return {"ok": False, "error": "empty query", "results": [], "engine": "google_cse"}
    if not key or not cx:
        return {"ok": False, "error": "missing google_cse key or cx", "results": [], "engine": "google_cse"}
    errors: list[str] = []
    results: list[dict[str, Any]] = []
    try:
        raw = _fetch(
            "https://www.googleapis.com/customsearch/v1?"
            + urlencode({"key": key, "cx": cx, "q": q, "num": min(max(limit, 1), 10)}),
            timeout=timeout,
            relaxed_tls=not bool(sc.get("verify_tls", True)),
        )
        data = json.loads(raw)
        for item in (data.get("items") or [])[:limit]:
            results.append(
                _result(item.get("title") or q, item.get("snippet") or "", item.get("link") or "", "google_cse")
            )
        if data.get("error"):
            errors.append(str(data.get("error")))
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
    return {"ok": bool(results), "query": q, "results": results, "errors": errors[:2], "engine": "google_cse"}


def search_serpapi_google(query: str, *, limit: int = 8, timeout: float = 12.0) -> dict[str, Any]:
    """SerpAPI Google organic results (paid; good for deep Google parity)."""
    q = (query or "").strip()
    key = _secret("serpapi") or _secret("SERPAPI_API_KEY") or os.environ.get("SERPAPI_API_KEY", "").strip()
    if not q:
        return {"ok": False, "error": "empty query", "results": [], "engine": "serpapi"}
    if not key:
        return {"ok": False, "error": "missing serpapi key", "results": [], "engine": "serpapi"}
    errors: list[str] = []
    results: list[dict[str, Any]] = []
    try:
        raw = _fetch(
            "https://serpapi.com/search.json?"
            + urlencode({"engine": "google", "q": q, "api_key": key, "num": min(limit, 10), "hl": "zh-CN"}),
            timeout=timeout,
        )
        data = json.loads(raw)
        for item in (data.get("organic_results") or [])[:limit]:
            results.append(
                _result(item.get("title") or q, item.get("snippet") or "", item.get("link") or "", "serpapi_google")
            )
        if data.get("error"):
            errors.append(str(data.get("error")))
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
    return {"ok": bool(results), "query": q, "results": results, "errors": errors[:2], "engine": "serpapi"}


def search_wikipedia(query: str, *, limit: int = 4, timeout: float = 3.0) -> dict[str, Any]:
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "empty query", "results": []}
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        for lang in ("zh", "en"):
            wiki = json.loads(
                _fetch(
                    f"https://{lang}.wikipedia.org/w/api.php?"
                    + urlencode(
                        {
                            "action": "opensearch",
                            "search": q,
                            "limit": min(limit, 5),
                            "namespace": 0,
                            "format": "json",
                        }
                    ),
                    timeout=timeout,
                )
            )
            if not (isinstance(wiki, list) and len(wiki) >= 4):
                continue
            titles, descs, urls = wiki[1], wiki[2], wiki[3]
            for i, title in enumerate(titles):
                results.append(
                    _result(title, (descs[i] if i < len(descs) else "") or title, urls[i] if i < len(urls) else "", f"wikipedia_{lang}")
                )
                if len(results) >= limit:
                    break
            if results:
                break
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
    return {
        "ok": bool(results),
        "query": q,
        "results": results[:limit],
        "summary": _summarize_results(q, results[:limit]),
        "errors": errors[:2],
        "engine": "wikipedia",
    }


# ── merge / deep ─────────────────────────────────────────────────────────


def _dedupe(results: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for r in results:
        key = (r.get("url") or "").split("?")[0].rstrip("/").lower() or (r.get("title") or "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(r)
        if len(out) >= limit:
            break
    return out


_SPORT_KEYS = (
    "世界杯", "欧洲杯", "欧冠", "FIFA", "World Cup", "积分榜", "战局",
    "比分", "赛程", "NBA", "CBA", "英超", "西甲", "懂球帝", "虎扑",
)

# Prefer these hosts for event/sports queries (boost + soft filter).
_SPORT_HOST_HINTS = (
    "fifa.com", "espn.com", "qq.com", "sina.com.cn", "sohu.com", "163.com",
    "dongqiudi.com", "hupu.com", "cctv.com", "thepaper.cn", "wikipedia.org",
    "baike.baidu.com", "goal.com", "skysports.com", "bbc.com", "reuters.com",
)

_WORLD_CUP_PRIMARY_SOURCES = (
    {
        "title": "FIFA 2026 世界杯官方赛程、赛果与球队",
        "snippet": "FIFA 官方赛程页面，用于核验比赛日期、阶段和已公布赛果。",
        "url": "https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/articles/match-schedule-fixtures-results-teams-stadiums?os=tmb",
        "source": "fifa_official",
    },
    {
        "title": "AP 2026 世界杯赛事报道",
        "snippet": "权威通讯社赛事报道，用于交叉核验淘汰赛阶段新闻；不以此页面推断未列出的比分。",
        "url": "https://apnews.com/article/afa13ed9fa933f8b75bd56eb16546031",
        "source": "ap_news",
    },
)


def _query_tokens(query: str) -> list[str]:
    """Tokenize for relevance scoring — Chinese keywords + English words."""
    q = (query or "").strip()
    if not q:
        return []
    tokens: list[str] = []
    # Known multi-char entities first (order matters: longer first)
    known = sorted(
        {
            "世界杯", "欧洲杯", "美洲杯", "欧冠", "亚冠", "英超", "西甲", "德甲", "意甲",
            "法甲", "中超", "积分榜", "战局", "战况", "比分", "赛程", "淘汰赛", "小组赛",
            "半决赛", "决赛", "最新", "World Cup", "Champions League", "FIFA", "NBA", "CBA",
        },
        key=len,
        reverse=True,
    )
    ql = q.lower()
    rest = q
    for k in known:
        if k.lower() in ql or k in rest:
            tokens.append(k)
            rest = rest.replace(k, " ")
            ql = rest.lower()
    for t in re.findall(r"[A-Za-z][A-Za-z0-9\-]{1,}", rest):
        if len(t) >= 2:
            tokens.append(t)
    for t in re.findall(r"[\u4e00-\u9fff]{2,8}", rest):
        tokens.append(t)
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out[:12]


def expand_queries(query: str, *, deep: bool = True) -> list[str]:
    q = re.sub(r"\s+", " ", (query or "").strip())
    if not q:
        return []
    if not deep:
        return [q]
    extras = [
        q,
        f"{q} 综述",
        f"{q} 官方",
        f"{q} overview OR review",
    ]
    ql = q.lower()
    sportish = any(k in q or k.lower() in ql for k in _SPORT_KEYS)
    if sportish:
        extras = [
            q,
            f"{q} 积分榜 赛果 对阵",
            "FIFA World Cup latest scores standings results 2026",
            "世界杯 最新赛况 积分榜 site:sports.sina.com.cn OR site:fifa.com",
        ]
        # Relative-date sports questions need temporal disambiguation.  In
        # particular, do not let a generic latest-scores query fabricate a
        # group-stage result after that stage has ended.
        if any(token in ql for token in ("昨晚", "昨天", "前一晚", "last night", "yesterday")) and any(
            token in ql for token in ("世界杯", "world cup", "fifa")
        ):
            from datetime import date, timedelta

            target = date.today() - timedelta(days=1)
            day = target.isoformat()
            extras = [
                q,
                f"FIFA World Cup 2026 {day} official match results schedule",
                f"2026 世界杯 {day} 小组赛 是否结束 FIFA 赛程",
                f"2026 世界杯 {day} 半决赛 决赛阶段 赛果 官方",
            ]
    # keep short / avoid huge fan-out
    seen = set()
    out = []
    for e in extras:
        e = e.strip()
        if e and e not in seen:
            seen.add(e)
            out.append(e)
    return out[:4]


def search_web(query: str, *, limit: int = 8, deep: bool | None = None) -> dict[str, Any]:
    """Auto provider cascade for a single query (or deep multi-query)."""
    sc = _search_cfg()
    if sc.get("enabled") is False:
        return {"ok": False, "error": "search disabled", "results": [], "offline": True}
    if deep is None:
        deep = bool(sc.get("deep", True))
    provider = str(sc.get("provider") or "auto").strip().lower()
    # Shallow search is the UI fast path: do not fan out into every
    # specialized scraper. Deep search is the deliberate research path.
    return deep_search(query, limit=limit) if deep else _search_once(
        query, limit=limit, provider=(provider if provider != "auto" else "fast")
    )


def _intent_engines(query: str) -> list[Any]:
    """Return specialized engines for the query's intent (event / academic / news / code / general)."""
    try:
        from . import search_extensions as _se
        intent = _se.classify_intent(query)
        return _se.engines_for_intent(intent)
    except Exception:  # noqa: BLE001
        return []


def _apply_grounding(query: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    """Run relevance gate; on failure, return structured fallback (no fabrication)."""
    try:
        from . import search_extensions as _se
        intent = _se.classify_intent(query)
        return _se.apply_grounding_gate(query, intent, results)
    except Exception:  # noqa: BLE001
        return {"ok": bool(results), "results": results}


def _search_once(query: str, *, limit: int, provider: str = "auto") -> dict[str, Any]:
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "empty query", "results": []}
    # Intent-first routing: specialized engines go to the front of the cascade.
    intent_first = _intent_engines(q)
    engines: list[Any] = []
    if provider == "fast":
        engines = [search_bing_rss, search_so360]
    elif provider == "google_cse":
        engines = list(intent_first) + [search_google_cse, search_bing_rss, search_so360]
    elif provider == "serpapi":
        engines = list(intent_first) + [search_serpapi_google, search_bing_rss, search_so360]
    elif provider == "bing":
        engines = list(intent_first) + [search_bing_rss, search_so360, search_sogou]
    elif provider in ("so360", "360"):
        engines = list(intent_first) + [search_so360, search_bing_rss, search_sogou]
    else:  # auto: prefer configured Google, then campus-reachable engines
        engines = list(intent_first)
        if _secret("serpapi") or _secret("SERPAPI_API_KEY") or os.environ.get("SERPAPI_API_KEY"):
            engines.append(search_serpapi_google)
        if (_secret("google_cse") or os.environ.get("GOOGLE_CSE_API_KEY")) and (
            _search_cfg().get("google_cse_cx") or os.environ.get("GOOGLE_CSE_CX")
        ):
            engines.append(search_google_cse)
        engines.extend([search_bing_rss, search_so360, search_sogou, search_wikipedia])

    results: list[dict[str, Any]] = []
    errors: list[str] = []
    used: list[str] = []
    for fn in engines:
        try:
            data = fn(q, limit=limit)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{getattr(fn, '__name__', 'engine')}: {exc}")
            continue
        if data.get("errors"):
            errors.extend([f"{data.get('engine')}: {e}" for e in data["errors"]])
        got = data.get("results") or []
        if got:
            used.append(str(data.get("engine") or getattr(fn, "__name__", "?")))
            results.extend(got)
        # auto: gather ≥2 campus engines for diversity; keyed Google alone is enough
        if provider == "auto":
            if any(u.startswith("google") or u.startswith("serpapi") for u in used) and len(results) >= max(3, limit // 2):
                break
            if len(used) >= 2 and len(results) >= limit:
                break
            if len(used) >= 3:
                break
        elif len(results) >= limit:
            break
    uniq = _dedupe(results, limit=limit)
    # Grounding gate: if results are too few / too irrelevant, swap in a structured fallback
    # so downstream doesn't hallucinate scores from the original query.
    if not uniq or len(used) == 0:
        gated = _apply_grounding(q, [])
        return {
            "ok": False,
            "offline": True,
            "query": q,
            "results": [],
            "intent": gated.get("intent"),
            "note": gated.get("note"),
            "errors": errors[:4],
            "engines": used,
            "provider": provider,
        }
    return {
        "ok": bool(uniq),
        "query": q,
        "results": uniq,
        "summary": _summarize_results(q, uniq),
        "errors": errors[:4] if not uniq else errors[:2],
        "engines": used,
        "offline": not bool(uniq),
        "provider": provider,
    }


def deep_search(query: str, *, limit: int = 10) -> dict[str, Any]:
    """Multi-query × multi-engine information search (Google-first when keyed)."""
    # Search is an optional enrichment step and must never hold the planner or
    # chat request indefinitely when one outbound engine stalls.
    deadline = time.monotonic() + 24.0
    sc = _search_cfg()
    provider = str(sc.get("provider") or "auto").strip().lower()
    queries = expand_queries(query, deep=True)
    merged: list[dict[str, Any]] = []
    errors: list[str] = []
    engines_used: list[str] = []
    per_query: list[dict[str, Any]] = []
    per_limit = max(4, min(8, limit))
    for i, qq in enumerate(queries):
        if time.monotonic() >= deadline:
            errors.append("search deadline exceeded")
            break
        # First query gets full cascade; expansions prefer Chinese engines + bing
        if i == 0:
            hit = _search_once(qq, limit=per_limit, provider=provider)
        else:
            hit = _search_once(qq, limit=max(3, per_limit // 2), provider="bing")
            if not hit.get("results"):
                hit = _search_once(qq, limit=max(3, per_limit // 2), provider="so360")
        per_query.append({"query": qq, "ok": hit.get("ok"), "n": len(hit.get("results") or [])})
        merged.extend(hit.get("results") or [])
        errors.extend(hit.get("errors") or [])
        engines_used.extend(hit.get("engines") or [])
    uniq = _dedupe(merged, limit=max(limit * 2, 12))
    q_tokens = _query_tokens(query)
    sportish = any(k.lower() in (query or "").lower() or k in (query or "") for k in _SPORT_KEYS)

    def _host(url: str) -> str:
        try:
            from urllib.parse import urlparse

            return (urlparse(url or "").netloc or "").lower()
        except Exception:  # noqa: BLE001
            return ""

    def _hit_count(r: dict[str, Any]) -> int:
        blob = f"{r.get('title') or ''} {r.get('snippet') or ''}".lower()
        return sum(1 for t in q_tokens if t.lower() in blob)

    def _score(r: dict[str, Any]) -> tuple:
        src = r.get("source") or ""
        hit = _hit_count(r)
        host = _host(str(r.get("url") or ""))
        sport_boost = 0
        if sportish and any(h in host for h in _SPORT_HOST_HINTS):
            sport_boost = -3
        # Penalize obvious off-topic geography / map pages when asking sports
        title = (r.get("title") or "").lower()
        if sportish and any(bad in title for bad in ("世界地图", "电子地图", "world map", "全球地图")):
            sport_boost += 8
        tier = 0 if "google" in src or "serpapi" in src else (1 if src in ("bing", "so360", "sogou") else 2)
        return (sport_boost, -hit, tier, -len(r.get("snippet") or ""))

    uniq.sort(key=_score)
    # Drop zero-relevance noise when the query has concrete tokens
    if q_tokens and uniq:
        relevant = [r for r in uniq if _hit_count(r) > 0]
        if sportish:
            # Prefer sports hosts when available; keep non-host hits that still match tokens
            host_hits = [
                r for r in relevant
                if any(h in _host(str(r.get("url") or "")) for h in _SPORT_HOST_HINTS)
            ]
            if host_hits:
                relevant = host_hits + [r for r in relevant if r not in host_hits]
        if relevant:
            uniq = relevant
    uniq = uniq[:limit]
    # Final grounding check on the ranked top-N: if relevance is still low, swap in a fallback.
    if not uniq:
        gated = _apply_grounding(query, [])
        return {
            "ok": False,
            "offline": True,
            "query": query,
            "queries": queries,
            "results": [],
            "intent": gated.get("intent"),
            "note": gated.get("note"),
            "errors": errors[:5],
            "engines": list(dict.fromkeys(engines_used)),
            "per_query": per_query,
            "mode": "deep",
            "provider": provider,
        }
    gated = _apply_grounding(query, uniq)
    if gated.get("ok") is False and gated.get("note"):
        return {
            "ok": False,
            "offline": True,
            "query": query,
            "queries": queries,
            "results": list(gated.get("results") or [])[:3],
            "intent": gated.get("intent"),
            "note": gated.get("note"),
            "summary": gated.get("note"),
            "errors": errors[:5],
            "engines": list(dict.fromkeys(engines_used)),
            "per_query": per_query,
            "mode": "deep",
            "provider": provider,
        }
    uniq = list(gated.get("results") or uniq)[:limit]
    authoritative_count = sum(
        1 for r in uniq
        if any(host in str(r.get("url") or "").lower() for host in (
            "fifa.com", "reuters.com", "apnews.com", "bbc.com", "who.int",
            "nature.com", "science.org", "gov.cn", "cctv.com",
        ))
    )
    return {
        "ok": bool(uniq),
        "query": query,
        "queries": queries,
        "results": uniq,
        "summary": _summarize_results(query, uniq),
        "errors": errors[:5] if not uniq else errors[:2],
        "engines": list(dict.fromkeys(engines_used)),
        "per_query": per_query,
        "offline": not bool(uniq),
        "mode": "deep",
        "provider": provider,
        "intent": gated.get("intent"),
        "relevance": gated.get("relevance"),
        "quality": {
            "source_count": len(uniq),
            "authoritative_count": authoritative_count,
            "verified": bool(uniq and authoritative_count > 0),
        },
        "warnings": (["未发现明确权威域名，关键结论需人工核验"] if uniq and not authoritative_count else []),
    }


def search_status() -> dict[str, Any]:
    sc = _search_cfg()
    has_cse = bool(
        (_secret("google_cse") or os.environ.get("GOOGLE_CSE_API_KEY", "").strip())
        and (sc.get("google_cse_cx") or os.environ.get("GOOGLE_CSE_CX", "").strip())
    )
    has_serp = bool(_secret("serpapi") or os.environ.get("SERPAPI_API_KEY", "").strip())
    proxy = bool(sc.get("proxy"))
    return {
        "enabled": sc.get("enabled", True) is not False,
        "provider": sc.get("provider") or "auto",
        "deep": bool(sc.get("deep", True)),
        "google_cse_configured": has_cse,
        "serpapi_configured": has_serp,
        "google_cse_cx": bool(sc.get("google_cse_cx") or os.environ.get("GOOGLE_CSE_CX")),
        "proxy_configured": proxy,
        "campus_note_zh": "校园网下 Google 直连常 SSL 超时；已启用 Bing RSS + 360/搜狗深搜。配置 Google CSE / SerpAPI（可加代理）可强化 Google 结果。",
        "campus_note_en": "Campus nets often block Google SSL; Bing RSS + 360/Sogou deep search are active. Add Google CSE / SerpAPI (+ proxy) for Google-strength results.",
        "extensions": _extensions_status(),
    }


def _extensions_status() -> dict[str, Any]:
    """Reveal which specialized engines are wired in (intent-aware routing)."""
    try:
        from . import search_extensions as _se
        return {
            "loaded": True,
            "intents": list(_se.INTENTS.keys()),
            "engines": {
                "event": [getattr(f, "__name__", "?") for f in _se.engines_for_intent("event")],
                "news": [getattr(f, "__name__", "?") for f in _se.engines_for_intent("news")],
                "academic": [getattr(f, "__name__", "?") for f in _se.engines_for_intent("academic")],
            },
            "grounding_gate": "relevance>=0.20 and n>=2 else fallback",
        }
    except Exception as exc:  # noqa: BLE001
        return {"loaded": False, "error": str(exc)}


def _summarize_results(query: str, results: list[dict[str, Any]]) -> str:
    if not results:
        return f"未找到与「{query}」相关的公开结果。"
    # Structured brief: lead with headline synthesis, then numbered sources.
    tops = []
    for r in results[:5]:
        title = (r.get("title") or "").strip()
        snip = (r.get("snippet") or "").strip()
        bit = title
        if snip and snip not in title:
            bit = f"{title} — {snip[:120]}" if title else snip[:160]
        if bit:
            tops.append(bit)
    lead = "；".join(tops[:3]) if tops else ""
    lines = [
        f"关于「{query}」的结构化检索摘要（{len(results)} 条，多引擎）：",
    ]
    if lead:
        lines.append(f"要点：{lead}")
    lines.append("来源：")
    for i, r in enumerate(results[:8], 1):
        lines.append(f"{i}. [{r.get('source')}] {r.get('title') or '（无标题）'} — {(r.get('snippet') or '')[:180]}")
        if r.get("url"):
            lines.append(f"   {r['url']}")
    return "\n".join(lines)


def fill_form_from_search(
    query: str,
    fields: list[str] | list[dict[str, Any]],
    *,
    limit: int = 6,
) -> dict[str, Any]:
    search = search_web(query, limit=limit, deep=True)
    blob = " ".join(f"{r.get('title') or ''} {r.get('snippet') or ''}" for r in (search.get("results") or []))
    filled: list[dict[str, Any]] = []
    for f in fields or []:
        if isinstance(f, dict):
            name = str(f.get("name") or f.get("id") or f.get("label") or "").strip()
            label = str(f.get("label") or name)
            hint = str(f.get("hint") or f.get("keywords") or name)
        else:
            name = str(f).strip()
            label = name
            hint = name
        if not name:
            continue
        value = _extract_field_value(hint or name, blob, search.get("results") or [])
        filled.append(
            {
                "name": name,
                "label": label,
                "value": value,
                "confidence": "medium" if value else "low",
                "source": "web_search",
            }
        )
    return {
        "ok": bool(search.get("ok")),
        "query": query,
        "search": search,
        "fields": filled,
        "note_zh": "字段值来自多引擎公开摘要，请人工核对后再写入。",
        "note_en": "Values from multi-engine snippets — verify before writing.",
    }


def _extract_field_value(hint: str, blob: str, results: list[dict[str, Any]]) -> str:
    hint_l = (hint or "").lower()
    if any(k in hint_l for k in ("email", "邮箱", "mail")):
        m = re.search(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", blob)
        if m:
            return m.group(0)
    if any(k in hint_l for k in ("phone", "电话", "手机", "tel")):
        m = re.search(r"(?:\+?\d[\d\- ()]{7,}\d)", blob)
        if m:
            return m.group(0).strip()
    if any(k in hint_l for k in ("year", "年份", "年度")):
        m = re.search(r"\b(19|20)\d{2}\b", blob)
        if m:
            return m.group(0)
    keys = [k for k in re.split(r"[\s_/|，,]+", hint) if len(k) >= 2][:4]
    for r in results:
        text = f"{r.get('title') or ''}。{r.get('snippet') or ''}"
        if any(k.lower() in text.lower() for k in keys):
            parts = re.split(r"[。；;\n]", text)
            for p in parts:
                if any(k.lower() in p.lower() for k in keys):
                    return p.strip()[:200]
            return text.strip()[:200]
    if results:
        return ((results[0].get("snippet") or results[0].get("title") or "")[:200]).strip()
    return ""


def _apply_advanced_operators(
    results: list[dict[str, Any]],
    operators: dict[str, Any],
) -> list[dict[str, Any]]:
    """Post-filter results by MiniMax-code style advanced operators.

    `site:` matches when the URL's host equals or is a subdomain of the
    target domain.  `inurl:` matches when the URL contains the fragment.
    `intitle:`/`intext:`/`inanchor:` match against the result's title or
    snippet.  `-term` drops any result whose title+snippet contains the
    term.  `"exact"` is informational only — the snippet already reflects
    what the engine matched.
    """
    if not operators or not results:
        return results
    site = str(operators.get("site") or "").strip().lower()
    inurl = str(operators.get("inurl") or "").strip().lower()
    intitle = str(operators.get("intitle") or "").strip().lower()
    intext = str(operators.get("intext") or "").strip().lower()
    inanchor = str(operators.get("inanchor") or "").strip().lower()
    exclude = [str(x).strip().lower() for x in (operators.get("exclude") or []) if str(x).strip()]
    out: list[dict[str, Any]] = []
    for r in results:
        if not isinstance(r, dict):
            continue
        url = str(r.get("url") or "").lower()
        title = str(r.get("title") or "")
        snippet = str(r.get("snippet") or "")
        body = f"{title} {snippet}".lower()
        if site and site not in url:
            continue
        if inurl and inurl not in url:
            continue
        if intitle and intitle not in title.lower():
            continue
        if intext and intext not in body:
            continue
        if inanchor and inanchor not in body:
            continue
        if exclude and any(term in body for term in exclude):
            continue
        out.append(r)
    return out


def _domain(url: str) -> str:
    from urllib.parse import urlparse

    try:
        host = (urlparse(url).hostname or "").lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:  # noqa: BLE001
        return ""


def _structure_sources(results: list[dict[str, Any]], *, limit: int = 12) -> list[dict[str, Any]]:
    """Dedupe / domain-cap results into portable source objects."""
    out: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    per_domain: dict[str, int] = {}
    for r in results or []:
        if not isinstance(r, dict):
            continue
        url = str(r.get("url") or "").strip()
        title = str(r.get("title") or "").strip()
        if not url or url in seen_urls:
            continue
        dom = _domain(url)
        if dom and per_domain.get(dom, 0) >= 2:
            continue
        seen_urls.add(url)
        if dom:
            per_domain[dom] = per_domain.get(dom, 0) + 1
        out.append(
            {
                "title": title or url,
                "url": url,
                "snippet": str(r.get("snippet") or "").strip()[:400],
                "source": str(r.get("source") or r.get("engine") or "").strip(),
            }
        )
        if len(out) >= limit:
            break
    return out


def search_structured(query: str, *, limit: int = 8, deep: bool = True) -> dict[str, Any]:
    """Structured search payload for planners / lane grounding."""
    # MiniMax-code style operator pre-processing.  If the query contains
    # site:/inurl:/intitle:/intext:/inanchor/-exclude/~synonym/"exact" the
    # planner likely wants results filtered by those constraints; we parse
    # them out, run a normal search on the cleaned body, then post-filter
    # the results so the user still gets the contracted payload shape.
    operators: dict[str, Any] = {}
    cleaned_query = query
    try:
        from .minimax_search_parity import parse_query as _parse_operators
        _parsed = _parse_operators(query or "")
        if _parsed.has_operators():
            cleaned_query = _parsed.cleaned or (" ".join(_parsed.exact) if _parsed.exact else query)
            operators = {
                "site": _parsed.site,
                "inurl": _parsed.inurl,
                "intitle": _parsed.intitle,
                "intext": _parsed.intext,
                "inanchor": _parsed.inanchor,
                "exclude": list(_parsed.exclude),
                "synonym": list(_parsed.synonym),
                "exact": list(_parsed.exact),
            }
    except Exception:  # noqa: BLE001
        operators = {}

    data = deep_search(cleaned_query, limit=limit) if deep else search_web(cleaned_query, limit=limit, deep=False)
    raw_results = list(data.get("results") or [])
    if operators:
        raw_results = _apply_advanced_operators(raw_results, operators)
        data["results"] = raw_results
    if operators:
        data["operators"] = operators
        data["cleaned_query"] = cleaned_query
    sources = _structure_sources(data.get("results") or [], limit=max(limit, 8))
    # Search engines frequently rank dictionary pages for the relative word
    # "昨晚".  For World Cup questions, preserve authoritative anchors even
    # when the live SERP is noisy; downstream must still verify each claim.
    ql = (query or "").lower()
    if ("世界杯" in query or "world cup" in ql or "fifa" in ql) and not operators:
        sports_sources = [
            s for s in sources
            if any(host in str(s.get("url") or "").lower() for host in (
                "fifa.com", "espn.com", "apnews.com", "reuters.com", "bbc.com",
                "nbcsports.com", "cbssports.com", "sina.com.cn", "thepaper.cn",
            ))
        ]
        if len(sports_sources) < 2:
            # When the SERP is dominated by dictionary/noise pages, discard
            # those pages rather than presenting them as sports evidence.
            # Respect the user's site:/inurl:/exclude operator set —
            # we never want to inject authoritative anchors that the
            # user explicitly excluded by scoping the query.
            merged = list(_WORLD_CUP_PRIMARY_SOURCES) + sports_sources
            sources = _structure_sources(merged, limit=max(limit, 8))
    # Expose a quality signal to the planner and main agent. This prevents a
    # plausible-looking summary from hiding a dictionary page, duplicate, or
    # weakly related result.
    tokens = _query_tokens(query)
    def _coverage(item: dict[str, Any]) -> float:
        blob = f"{item.get('title') or ''} {item.get('snippet') or ''}".lower()
        if not tokens:
            return 1.0
        return sum(1 for token in tokens if token.lower() in blob) / len(tokens)

    quality_scores = [_coverage(s) for s in sources]
    authoritative = sum(
        1 for s in sources
        if any(host in str(s.get("url") or "").lower() for host in (
            "fifa.com", "reuters.com", "apnews.com", "bbc.com", "who.int",
            "nature.com", "science.org", "gov.cn", "cctv.com",
        ))
    )
    quality = {
        "relevance": round(sum(quality_scores) / max(len(quality_scores), 1), 3),
        "source_count": len(sources),
        "authoritative_count": authoritative,
        "verified": bool(sources and max(quality_scores or [0]) >= 0.25),
    }
    warnings: list[str] = []
    if not sources:
        warnings.append("没有召回可引用来源")
    elif quality["relevance"] < 0.25:
        warnings.append("来源相关性偏低，禁止输出精确数字或比分")
    if authoritative == 0 and sources:
        warnings.append("未发现明确权威域名，结论需要标注不确定性")
    if not sources:
        err = "; ".join(data.get("errors") or []) or data.get("error") or "unknown"
        md = (
            "## Web search offline\n"
            f"Outbound search failed ({err}).\n"
            "Continue offline; footnote once at the end if needed.\n"
        )
        return {
            "ok": False,
            "query": query,
            "sources": [],
            "summary": "",
            "context_markdown": md,
            "errors": data.get("errors") or [err],
            "engines": data.get("engines") or [],
            "quality": quality,
            "warnings": warnings,
        }
    engines = ", ".join(data.get("engines") or []) or "multi"
    lines = [
        "## Deep information search results (cite URLs; do not invent)",
        f"Query: {query}",
        f"Engines: {engines} · mode={data.get('mode') or 'standard'}",
        data.get("summary") or "",
        f"Source quality: relevance={quality['relevance']} · authoritative={authoritative} · verified={quality['verified']}",
        "Use these sources. Prefer primary sources. Mark uncertain claims.",
    ]
    if warnings:
        lines.append("Warnings: " + "；".join(warnings))
    for r in sources:
        lines.append(f"- [{r.get('title')}]({r.get('url')}) ({r.get('source')}) — {r.get('snippet')}")
    lines.append(
        "If filling a form/table: Markdown field → value → source URL. "
        "Results above are authoritative for this turn."
    )
    return {
        "ok": True,
        "query": query,
        "sources": sources,
        "summary": data.get("summary") or "",
        "context_markdown": "\n".join(lines),
        "errors": data.get("errors") or [],
        "engines": data.get("engines") or [],
        "quality": quality,
        "warnings": warnings,
        "operators": operators or None,
        "cleaned_query": cleaned_query if operators else None,
    }


def search_context_for_prompt(query: str, *, limit: int = 8, deep: bool = True) -> str:
    return str(search_structured(query, limit=limit, deep=deep).get("context_markdown") or "")
