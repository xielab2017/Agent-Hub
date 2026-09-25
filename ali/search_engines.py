"""Additional external search engines.

Key-free:  DuckDuckGo (HTML endpoint), Baidu (best-effort HTML), SearXNG (your
           own instance, JSON API).
Keyed:     Brave Search API, Tavily.

All engines share the websearch contract::

    fn(query, *, limit=8, timeout=…) -> {"ok", "query", "results": [{title, snippet, url, source}],
                                         "errors", "engine"}

and the network path ``websearch._http`` (search proxy + TLS policy).  Each
engine is gated by ``search.engines.<id>`` (default on) plus its key / URL;
``available_engines()`` reports which are usable.  (The Bing Web Search API
was retired by Microsoft in 2025 and is intentionally not included.)
"""

from __future__ import annotations

import json
import re
from html import unescape
from typing import Any, Callable
from urllib.parse import parse_qs, urlencode, urlparse


def _ws():
    from . import websearch

    return websearch


def _cfg() -> dict[str, Any]:
    return _ws()._search_cfg()


def _secret(slot: str) -> str:
    return _ws()._secret(slot)


def _strip(s: str) -> str:
    s = unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()


def _pack(engine: str, q: str, items: list[dict[str, Any]], errors: list[str], limit: int) -> dict[str, Any]:
    return {"ok": bool(items), "query": q, "results": items[:limit], "errors": errors[:2], "engine": engine}


def _item(title: str, snippet: str, url: str, source: str) -> dict[str, Any]:
    return _ws()._result(title, snippet, url, source)


# ── key-free ──────────────────────────────────────────────────────────


def _ddg_real_url(href: str) -> str:
    href = unescape(href or "")
    if href.startswith("//"):
        href = "https:" + href
    try:
        p = urlparse(href)
    except ValueError:
        return href
    if "duckduckgo.com" in p.netloc and p.path.startswith("/l/"):
        target = (parse_qs(p.query).get("uddg") or [""])[0]
        return target or href
    return href


def search_ddg(query: str, *, limit: int = 8, timeout: float = 6.0) -> dict[str, Any]:
    q = (query or "").strip()
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    if not q:
        return _pack("duckduckgo", q, items, ["empty query"], limit)
    try:
        html = _ws()._http("https://html.duckduckgo.com/html/?" + urlencode({"q": q, "kl": "wt-wt"}), timeout=timeout)
        # Lookahead split keeps each block's opening tag (ads are marked by its class).
        blocks = re.split(r'(?=<div[^>]+class="[^"]*\bresult\b)', html)[1:]
        for b in blocks:
            a = re.search(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>([\s\S]*?)</a>', b)
            if not a:
                continue
            if "result--ad" in b.split(">", 1)[0] or "ad_domain" in b:
                continue
            sn = re.search(r'class="[^"]*result__snippet[^"]*"[^>]*>([\s\S]*?)</(?:a|div|td)>', b)
            url = _ddg_real_url(a.group(1))
            if not url.startswith("http"):
                continue
            items.append(_item(_strip(a.group(2)), _strip(sn.group(1)) if sn else "", url, "duckduckgo"))
            if len(items) >= limit:
                break
        if not items and "anomaly" in html.lower():
            errors.append("duckduckgo: bot check")
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
    return _pack("duckduckgo", q, items, errors, limit)


def search_baidu(query: str, *, limit: int = 8, timeout: float = 6.0) -> dict[str, Any]:
    q = (query or "").strip()
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    if not q:
        return _pack("baidu", q, items, ["empty query"], limit)
    try:
        html = _ws()._http("https://www.baidu.com/s?" + urlencode({"wd": q, "rn": min(limit, 20), "ie": "utf-8"}), timeout=timeout)
        if "百度安全验证" in html or "wappass.baidu.com" in html:
            errors.append("baidu: captcha")
        blocks = re.split(r'(?=<div[^>]+class="[^"]*\b(?:result|c-container)\b)', html)[1:]
        for b in blocks:
            a = re.search(r"<h3[^>]*>[\s\S]*?<a[^>]+href=\"([^\"]+)\"[^>]*>([\s\S]*?)</a>", b)
            if not a:
                continue
            mu = re.search(r'\bmu="(https?://[^"]+)"', b)
            url = unescape(mu.group(1) if mu else a.group(1))
            sn = re.search(
                r'class="[^"]*(?:content-right|c-abstract|c-span-last|summary-text)[^"]*"[^>]*>([\s\S]*?)</(?:span|div)>', b
            )
            title = _strip(a.group(2))
            if not title or not url.startswith("http"):
                continue
            items.append(_item(title, _strip(sn.group(1)) if sn else "", url, "baidu"))
            if len(items) >= limit:
                break
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
    return _pack("baidu", q, items, errors, limit)


def search_searxng(query: str, *, limit: int = 8, timeout: float = 6.0) -> dict[str, Any]:
    q = (query or "").strip()
    base = str(_cfg().get("searxng_url") or "").strip().rstrip("/")
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    if not base:
        return _pack("searxng", q, items, ["searxng_url not configured"], limit)
    try:
        data = json.loads(_ws()._http(
            f"{base}/search?" + urlencode({"q": q, "format": "json", "language": "auto"}),
            headers={"Accept": "application/json"}, timeout=timeout,
        ))
        for r in data.get("results") or []:
            url = r.get("url") or ""
            if not url:
                continue
            eng = r.get("engine") or ",".join(r.get("engines") or [])
            items.append(_item(r.get("title") or url, r.get("content") or "", url, f"searxng:{eng}" if eng else "searxng"))
            if len(items) >= limit:
                break
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
    return _pack("searxng", q, items, errors, limit)


# ── keyed ─────────────────────────────────────────────────────────────


def search_brave(query: str, *, limit: int = 8, timeout: float = 6.0) -> dict[str, Any]:
    q = (query or "").strip()
    key = _secret("brave") or _secret("BRAVE_API_KEY")
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    if not key:
        return _pack("brave", q, items, ["brave key not configured"], limit)
    try:
        data = json.loads(_ws()._http(
            "https://api.search.brave.com/res/v1/web/search?" + urlencode({"q": q, "count": min(limit, 20)}),
            headers={"Accept": "application/json", "X-Subscription-Token": key}, timeout=timeout,
        ))
        for r in ((data.get("web") or {}).get("results")) or []:
            snippet = " ".join(x for x in ((r.get("age") or ""), _strip(r.get("description") or "")) if x)
            items.append(_item(_strip(r.get("title") or ""), snippet, r.get("url") or "", "brave"))
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
    return _pack("brave", q, items, errors, limit)


def search_tavily(query: str, *, limit: int = 8, timeout: float = 8.0) -> dict[str, Any]:
    q = (query or "").strip()
    key = _secret("tavily") or _secret("TAVILY_API_KEY")
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    if not key:
        return _pack("tavily", q, items, ["tavily key not configured"], limit)
    try:
        body = json.dumps({"query": q, "max_results": min(limit, 10), "search_depth": "basic",
                           "include_answer": False, "api_key": key}).encode("utf-8")
        data = json.loads(_ws()._http(
            "https://api.tavily.com/search", data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json",
                     "Authorization": f"Bearer {key}"},
            timeout=timeout, max_timeout=8.0,
        ))
        for r in data.get("results") or []:
            snippet = " ".join(x for x in ((r.get("published_date") or "")[:10], r.get("content") or "") if x)
            items.append(_item(r.get("title") or r.get("url") or "", snippet, r.get("url") or "", "tavily"))
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
    return _pack("tavily", q, items, errors, limit)


# ── registry ──────────────────────────────────────────────────────────

ENGINES: list[dict[str, Any]] = [
    {"id": "tavily", "label": "Tavily", "fn": search_tavily, "needs": "key", "slot": "tavily"},
    {"id": "brave", "label": "Brave Search", "fn": search_brave, "needs": "key", "slot": "brave"},
    {"id": "baidu", "label": "百度 Baidu", "fn": search_baidu, "needs": ""},
    {"id": "duckduckgo", "label": "DuckDuckGo", "fn": search_ddg, "needs": ""},
    {"id": "searxng", "label": "SearXNG", "fn": search_searxng, "needs": "url"},
]
_BY_ID = {e["id"]: e for e in ENGINES}
# Built-in websearch engines that can also be switched off per engine.
BUILTIN_IDS = ("bing", "so360", "sogou", "wikipedia", "google_cse", "serpapi")


def engine_switches(cfg: dict[str, Any] | None = None) -> dict[str, bool]:
    sw = (cfg if cfg is not None else _cfg()).get("engines")
    return {str(k): bool(v) for k, v in sw.items()} if isinstance(sw, dict) else {}


def is_enabled(engine_id: str, cfg: dict[str, Any] | None = None) -> bool:
    return engine_switches(cfg).get(engine_id, True)


def configured(engine_id: str, cfg: dict[str, Any] | None = None) -> bool:
    e = _BY_ID.get(engine_id)
    if not e:
        return True
    if e["needs"] == "key":
        return bool(_secret(e["slot"]) or _secret(e["slot"].upper() + "_API_KEY"))
    if e["needs"] == "url":
        return bool(str((cfg if cfg is not None else _cfg()).get("searxng_url") or "").strip())
    return True


def available_engines(cfg: dict[str, Any] | None = None) -> list[Callable[..., dict[str, Any]]]:
    """Usable extra engines in priority order (keyed first, they are the most reliable)."""
    cfg = cfg if cfg is not None else _cfg()
    return [e["fn"] for e in ENGINES if is_enabled(e["id"], cfg) and configured(e["id"], cfg)]


def engine_by_id(engine_id: str) -> Callable[..., dict[str, Any]] | None:
    e = _BY_ID.get(engine_id)
    return e["fn"] if e else None


def status(cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cfg = cfg if cfg is not None else _cfg()
    return [
        {"id": e["id"], "label": e["label"], "needs": e["needs"], "enabled": is_enabled(e["id"], cfg),
         "configured": configured(e["id"], cfg)}
        for e in ENGINES
    ]


__all__ = [
    "search_ddg", "search_baidu", "search_searxng", "search_brave", "search_tavily",
    "ENGINES", "BUILTIN_IDS", "available_engines", "engine_by_id", "status", "is_enabled", "configured",
]
