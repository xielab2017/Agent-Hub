"""Open the top search results and pull the passages that answer the query.

Snippets are often truncated or stale; deep search reads the actual pages.
``fetch_pages`` downloads the first N result URLs in parallel (bounded time,
failures skipped), extracts readable text (``<article>`` / ``<main>`` first),
and keeps the sentences that best match the query — preferring sentences that
carry numbers, since those are what later cross-source checks need.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from concurrent.futures import ThreadPoolExecutor, wait
from urllib.parse import urlparse
from html import unescape
from typing import Any, Callable

_DROP_BLOCKS = re.compile(
    r"<(script|style|noscript|iframe|svg|canvas|form|button|nav|footer|header|aside|select|template)\b[^>]*>[\s\S]*?</\1\s*>",
    re.I,
)
_BREAK_TAGS = re.compile(r"<\s*(?:br|/p|/div|/li|/h[1-6]|/tr|/section|/article|/blockquote|/pre|/td|/th)\b[^>]*>", re.I)
_TAG = re.compile(r"<[^>]+>")
_SENT_SPLIT = re.compile(r"(?<=[。！？!?；;])|(?<=[.])\s+(?=[A-Z0-9一-鿿])|\n+")
_SKIP_EXT = re.compile(r"\.(?:pdf|zip|gz|rar|7z|docx?|xlsx?|pptx?|png|jpe?g|gif|mp4|mp3)(?:$|\?)", re.I)

MAX_PAGE_CHARS = 6000
MAX_PASSAGES = 4
PASSAGE_CHARS = 320


def html_to_text(html: str) -> str:
    """Readable text with line breaks kept at block boundaries."""
    if not html:
        return ""
    body = html
    for tag in ("article", "main"):
        m = re.search(rf"<{tag}\b[^>]*>([\s\S]*?)</{tag}\s*>", html, re.I)
        if m and len(_TAG.sub("", m.group(1))) > 200:
            body = m.group(1)
            break
    else:
        m = re.search(r"<body\b[^>]*>([\s\S]*)</body\s*>", html, re.I)
        if m:
            body = m.group(1)
    body = _DROP_BLOCKS.sub(" ", body)
    body = _BREAK_TAGS.sub("\n", body)
    text = unescape(_TAG.sub(" ", body))
    text = re.sub(r"[ \t 　]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def page_title(html: str) -> str:
    m = re.search(r"<title\b[^>]*>([\s\S]*?)</title\s*>", html or "", re.I)
    return re.sub(r"\s+", " ", unescape(m.group(1))).strip()[:200] if m else ""


def _tokens(query: str) -> list[str]:
    try:
        from .websearch import _query_tokens

        toks = _query_tokens(query)
    except Exception:  # noqa: BLE001
        toks = []
    if not toks:
        toks = [t for t in re.split(r"[\s,，、/|]+", query or "") if len(t) >= 2]
    return [t.lower() for t in toks]


def best_passages(text: str, query: str, *, k: int = MAX_PASSAGES) -> list[str]:
    """Top-k query-relevant sentences, kept in document order."""
    toks = _tokens(query)
    sents = [s.strip() for s in _SENT_SPLIT.split(text or "") if s and len(s.strip()) >= 12]
    scored: list[tuple[float, int, str]] = []
    for i, s in enumerate(sents):
        low = s.lower()
        hits = sum(1 for t in toks if t in low)
        if not hits:
            continue
        score = hits / max(len(toks), 1) + (0.25 if re.search(r"\d", s) else 0.0) - (0.1 if len(s) > 400 else 0.0)
        scored.append((score, i, s[:PASSAGE_CHARS]))
    top = sorted(scored, key=lambda x: (-x[0], x[1]))[:k]
    return [s for _, _, s in sorted(top, key=lambda x: x[1])]


def is_public_url(url: str, *, resolve: bool = True) -> bool:
    """Only fetch public http(s) pages.

    Search results are untrusted: a result pointing at localhost, a LAN
    address or a cloud metadata endpoint must never be fetched (SSRF), or local
    data could end up in the model prompt.
    """
    try:
        p = urlparse(str(url or ""))
    except ValueError:
        return False
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    host = p.hostname.strip("[]").lower()
    if host in ("localhost", "localhost.localdomain") or host.endswith((".local", ".internal", ".localhost")):
        return False
    try:
        addrs = [ipaddress.ip_address(host)]
    except ValueError:
        if not resolve:
            return True
        try:
            addrs = [ipaddress.ip_address(info[4][0].split("%")[0]) for info in socket.getaddrinfo(host, None)]
        except (OSError, ValueError):
            return False
    return bool(addrs) and all(
        not (a.is_private or a.is_loopback or a.is_link_local or a.is_reserved or a.is_multicast or a.is_unspecified)
        for a in addrs
    )


def _default_fetch(url: str) -> str:
    from . import websearch

    return websearch._http(url, timeout=5.0, max_timeout=5.0, redirect_check=is_public_url)


def fetch_page(url: str, query: str, *, fetch: Callable[[str], str] | None = None) -> dict[str, Any]:
    row: dict[str, Any] = {"url": url, "ok": False, "title": "", "chars": 0, "passages": [], "error": ""}
    if not str(url or "").startswith(("http://", "https://")) or _SKIP_EXT.search(url):
        row["error"] = "skipped (not an HTML page)"
        return row
    if fetch is None and not is_public_url(url):
        row["error"] = "skipped (not a public address)"
        return row
    try:
        html = (fetch or _default_fetch)(url)
    except Exception as exc:  # noqa: BLE001
        row["error"] = str(exc)[:160]
        return row
    if not html or html.lstrip().startswith("%PDF"):
        row["error"] = "empty or non-HTML"
        return row
    text = html_to_text(html)[:MAX_PAGE_CHARS * 3]
    row["title"] = page_title(html)
    row["chars"] = len(text)
    row["passages"] = best_passages(text[:MAX_PAGE_CHARS * 3], query)
    row["text"] = text[:MAX_PAGE_CHARS]
    row["ok"] = bool(row["passages"])
    if not row["ok"]:
        row["error"] = "no passage matched the query"
    return row


def fetch_pages(
    sources: list[dict[str, Any]],
    query: str,
    *,
    max_pages: int = 3,
    fetch: Callable[[str], str] | None = None,
    deadline: float = 10.0,
) -> list[dict[str, Any]]:
    """Fetch up to ``max_pages`` source URLs in parallel; returns one row per attempted page.

    Each row carries ``n`` (the source number) so passages stay citable.
    """
    picks = [(int(s.get("n") or i), s) for i, s in enumerate(sources or [], start=1) if isinstance(s, dict) and s.get("url")]
    picks = [(i, s) for i, s in picks if not _SKIP_EXT.search(str(s.get("url")))][: max(0, int(max_pages))]
    if not picks:
        return []
    pool = ThreadPoolExecutor(max_workers=min(4, len(picks)))
    rows: list[dict[str, Any]] = []
    try:
        futs = {pool.submit(fetch_page, str(s["url"]), query, fetch=fetch): (i, s) for i, s in picks}
        done, _ = wait(futs, timeout=deadline)
        for fut, (i, s) in futs.items():
            if fut in done:
                try:
                    row = fut.result()
                except Exception as exc:  # noqa: BLE001
                    row = {"url": s.get("url"), "ok": False, "passages": [], "error": str(exc)[:160]}
            else:
                row = {"url": s.get("url"), "ok": False, "passages": [], "error": "timeout"}
            row["n"] = i
            rows.append(row)
    finally:
        pool.shutdown(wait=False)
    rows.sort(key=lambda r: r["n"])
    return rows
