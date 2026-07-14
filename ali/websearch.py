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
    sc = _search_cfg()
    proxy = (sc.get("proxy") or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or "").strip()
    if not proxy:
        return []
    return [ProxyHandler({"http": proxy, "https": proxy})]


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
            build_opener(*handlers).open(req, timeout=min(timeout, 6.0))
            if handlers
            else urlopen(req, timeout=min(timeout, 6.0), context=_ssl_context(relaxed=True))
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
    return deep_search(query, limit=limit) if deep else _search_once(query, limit=limit, provider=provider)


def _search_once(query: str, *, limit: int, provider: str = "auto") -> dict[str, Any]:
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "empty query", "results": []}
    engines: list[Any] = []
    if provider == "google_cse":
        engines = [search_google_cse, search_bing_rss, search_so360]
    elif provider == "serpapi":
        engines = [search_serpapi_google, search_bing_rss, search_so360]
    elif provider == "bing":
        engines = [search_bing_rss, search_so360, search_sogou]
    elif provider in ("so360", "360"):
        engines = [search_so360, search_bing_rss, search_sogou]
    else:  # auto: prefer configured Google, then campus-reachable engines
        engines = []
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
    sc = _search_cfg()
    provider = str(sc.get("provider") or "auto").strip().lower()
    queries = expand_queries(query, deep=True)
    merged: list[dict[str, Any]] = []
    errors: list[str] = []
    engines_used: list[str] = []
    per_query: list[dict[str, Any]] = []
    per_limit = max(4, min(8, limit))
    for i, qq in enumerate(queries):
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
    q_tokens = [t for t in re.split(r"[\s/|，,、]+", query) if len(t) >= 2]

    def _score(r: dict[str, Any]) -> tuple:
        src = r.get("source") or ""
        blob = f"{r.get('title') or ''} {r.get('snippet') or ''}"
        hit = sum(1 for t in q_tokens if t.lower() in blob.lower())
        tier = 0 if "google" in src or "serpapi" in src else (1 if src in ("bing", "so360", "sogou") else 2)
        # relevance first, then engine tier, then snippet length
        return (-hit, tier, -len(r.get("snippet") or ""))

    uniq.sort(key=_score)
    uniq = uniq[:limit]
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
    }


def search_status() -> dict[str, Any]:
    sc = _search_cfg()
    has_cse = bool(
        (_secret("google_cse") or os.environ.get("GOOGLE_CSE_API_KEY", "").strip())
        and (sc.get("google_cse_cx") or os.environ.get("GOOGLE_CSE_CX", "").strip())
    )
    has_serp = bool(_secret("serpapi") or os.environ.get("SERPAPI_API_KEY", "").strip())
    proxy = bool(sc.get("proxy") or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY"))
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
    }


def _summarize_results(query: str, results: list[dict[str, Any]]) -> str:
    if not results:
        return f"未找到与「{query}」相关的公开结果。"
    lines = [f"关于「{query}」的检索摘要（{len(results)} 条，多引擎）："]
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


def search_context_for_prompt(query: str, *, limit: int = 8, deep: bool = True) -> str:
    data = deep_search(query, limit=limit) if deep else search_web(query, limit=limit, deep=False)
    if not data.get("ok") and not data.get("results"):
        err = "; ".join(data.get("errors") or []) or data.get("error") or "unknown"
        return (
            "## Web search offline\n"
            f"Outbound search failed ({err}).\n"
            "CRITICAL: Do NOT open with 「重要说明：网络搜索不可用」. Continue the task offline; "
            "footnote once at the end if needed.\n"
        )
    engines = ", ".join(data.get("engines") or []) or "multi"
    lines = [
        "## Deep information search results (cite URLs; do not invent)",
        f"Query: {query}",
        f"Engines: {engines} · mode={data.get('mode') or 'standard'}",
        data.get("summary") or "",
        "Use these sources for answers / form-fill. Prefer primary sources. Mark uncertain claims.",
    ]
    for r in data.get("results") or []:
        lines.append(f"- [{r.get('title')}]({r.get('url')}) ({r.get('source')}) — {r.get('snippet')}")
    lines.append(
        "If filling a form/table: output Markdown field → value → source URL. "
        "Do not refuse for lack of live Google — results above are authoritative for this turn."
    )
    return "\n".join(lines)
