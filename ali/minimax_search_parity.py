"""MiniMax code search parity module.

Ported from https://github.com/MiniMax-AI/minimax_search (MIT, MiniMax AI) and
adapted to Agent-Hub-3.0.  We do not import the original `minimax_search_browse`
because it depends on a private MiniMax-M2 tokenizer and the Google Serper /
Jina APIs; instead we keep the algorithmic core and inject the Agent-Hub
search / LLM clients at the boundary.

What we keep from MiniMax code:
  1. Advanced search-operator parser — `site:`, `inurl:`, `intitle:`,
     `intext:`, `inanchor:`, `-exclude`, `~synonym`, `"exact phrase"`.
  2. Parallel multi-query fan-out — `ThreadPoolExecutor(max_workers=len(queries))`
     with deterministic result ordering.
  3. Brief-text formatter — `<title>...</title><url>...</url><snippet>...</snippet>`
     blocks, preferring `extra_snippets` over `snippet` over `description`.
  4. Batch URL browsing — fetch N URLs in parallel, send each (or each chunk)
     to an LLM with a strict "refuse if not relevant" prompt.
  5. Token-aware chunking — long pages are split before the LLM call so a
     single huge Wikipedia article does not exceed the context window.
  6. Empty-result fallback — if a quoted query returns nothing, retry without
     quotes; if still empty, return a structured "no result" message instead
     of a fabricated answer.

What we replace:
  * Token counting: char-based heuristic (avg 2 chars / token) instead of
    requiring the `transformers` library.
  * Google Serper / Jina: Agent-Hub already has `websearch.search_*` and a
    configurable HTTP fetcher, so we accept those as injected callables.
  * MiniMax LLM: Agent-Hub has its own `llm_client._chat_once`; we accept an
    `llm_fn(prompt) -> str` callable.

Public API:
  parse_query(query)        -> ParsedQuery (dataclass with operator tags + cleaned)
  format_brief(results)     -> str
  parallel_search(queries, *, search_fn, max_workers=None) -> ParallelSearchResult
  browse_urls(urls, query, *, fetch_fn, llm_fn, max_chars=12000,
              chunk_chars=4000) -> str
  search_structured(query, *, cfg=None) -> dict
"""

from __future__ import annotations

import math
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from html import unescape
from typing import Any, Callable, Iterable

# ---------------------------------------------------------------------------
# 1. Advanced search-operator parser
# ---------------------------------------------------------------------------

_OPERATOR_KEYWORDS = ("site", "inurl", "intitle", "intext", "inanchor")
_PATTERN_KEYWORDS = {
    "exclude": r"-([^\s]+)",
    "synonym": r"~([^\s]+)",
    "exact": r'"([^"]+)"',
}


@dataclass
class ParsedQuery:
    """Result of `parse_query` — preserves the operator intent while
    returning a cleaned query suitable for an actual search engine."""

    cleaned: str
    site: str = ""
    inurl: str = ""
    intitle: str = ""
    intext: str = ""
    inanchor: str = ""
    exclude: list[str] = field(default_factory=list)
    synonym: list[str] = field(default_factory=list)
    exact: list[str] = field(default_factory=list)
    raw: str = ""

    def has_operators(self) -> bool:
        return any(
            getattr(self, k)
            for k in ("site", "inurl", "intitle", "intext", "inanchor")
        ) or bool(self.exclude or self.synonym or self.exact)


def parse_query(query: str) -> ParsedQuery:
    """Extract advanced-search operators from a free-form query.

    Operators (in MiniMax code's order):
      site:DOMAIN    — restrict results to a domain
      inurl:FRAG     — URL must contain FRAG
      intitle:FRAG   — page title must contain FRAG
      intext:FRAG    — page body must contain FRAG
      inanchor:FRAG  — anchor text must contain FRAG
      -TERM          — exclude TERM
      ~TERM          — synonym expansion (we keep the hint; engines apply)
      "phrase"       — exact match (kept verbatim in `exact`; the words
                       remain in the cleaned body so a broader fallback
                       query still has the same intent)
    """
    raw = (query or "").strip()
    result = ParsedQuery(cleaned="", raw=raw)
    work = raw

    for keyword in _OPERATOR_KEYWORDS:
        pattern = rf"{keyword}:([^\s]+)"
        m = re.search(pattern, work)
        if m:
            setattr(result, keyword, m.group(1).strip())
            work = re.sub(pattern, "", work, count=1).strip()

    for tag, pattern in _PATTERN_KEYWORDS.items():
        matches = re.findall(pattern, work)
        for m in matches:
            (result.exclude if tag == "exclude" else result.synonym if tag == "synonym" else result.exact).append(m)
        # For "exact" we keep the words in the cleaned body (just remove
        # the quote marks).  For exclude/synonym the term is removed
        # entirely — the operator carries the intent.
        if tag == "exact":
            work = re.sub(pattern, lambda mm: mm.group(1), work).strip()
        else:
            work = re.sub(pattern, "", work).strip()

    # Drop leftover punctuation; preserve CJK and alphanumerics.
    cleaned = re.sub(r"[^\w\s\u4e00-\u9fff\u3400-\u4dbf\-]", " ", work)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    result.cleaned = cleaned
    return result


# ---------------------------------------------------------------------------
# 2. Brief-text formatter
# ---------------------------------------------------------------------------

def format_brief(results: Iterable[dict[str, Any]]) -> str:
    """Format search-engine result dicts into the MiniMax-style block format.

    Each result becomes:
        <title>...</title>
        <url>...</url>
        <snippet>...</snippet>
    Prefers `extra_snippets` (list) joined by newline; falls back to `snippet`,
    then `description`.  Empty / non-dict inputs are skipped.
    """
    chunks: list[str] = []
    for r in results or []:
        if not isinstance(r, dict):
            continue
        title = str(r.get("title") or "").strip()
        url = str(r.get("url") or r.get("link") or "").strip()
        extra = r.get("extra_snippets")
        if isinstance(extra, list) and extra:
            snippet = "\n".join(str(x) for x in extra if x)
        else:
            snippet = str(r.get("snippet") or r.get("description") or "").strip()
        if not (title or url or snippet):
            continue
        chunks.append(
            f"<title>{title}</title>\n<url>{url}</url>\n<snippet>\n{snippet}\n</snippet>"
        )
    return "\n\n".join(chunks).strip()


# ---------------------------------------------------------------------------
# 3. Parallel multi-query fan-out
# ---------------------------------------------------------------------------

@dataclass
class ParallelSearchResult:
    """Result of `parallel_search`."""

    ok: bool
    blocks: list[dict[str, Any]] = field(default_factory=list)
    # Each block: {"query": str, "ok": bool, "results": [...], "error": str|None, "took": float}
    combined_markdown: str = ""
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "blocks": self.blocks,
            "combined_markdown": self.combined_markdown,
            "errors": self.errors,
        }


def parallel_search(
    queries: list[str],
    *,
    search_fn: Callable[[str], dict[str, Any]],
    max_workers: int | None = None,
    per_query_timeout: float = 8.0,
) -> ParallelSearchResult:
    """Run a list of queries through `search_fn` in parallel.

    `search_fn` should accept a query string and return a dict with at least
    `ok`, `results`, optionally `error`.  We preserve the original query
    order in the output.  Empty query strings are short-circuited to an
    "empty" block so the worker pool is not wasted.
    """
    if not queries:
        return ParallelSearchResult(ok=True)

    workers = max_workers or min(len(queries), 6)
    blocks: list[dict[str, Any] | None] = [None] * len(queries)
    started = [0.0] * len(queries)

    def _run(idx: int, q: str) -> tuple[int, dict[str, Any]]:
        t0 = time.monotonic()
        if not (q or "").strip():
            return idx, {
                "query": q,
                "ok": False,
                "results": [],
                "error": "empty_query",
                "took": 0.0,
            }
        try:
            payload = search_fn(q) or {}
            # search_fn may return either `results` (websearch.search_web) or
            # `sources` (websearch.search_structured) — accept both.
            results = payload.get("results")
            if results is None:
                results = payload.get("sources") or []
            return idx, {
                "query": q,
                "ok": bool(payload.get("ok")),
                "results": list(results),
                "error": payload.get("error"),
                "took": time.monotonic() - t0,
                "engine": payload.get("engine") or "",
            }
        except Exception as e:  # noqa: BLE001
            return idx, {
                "query": q,
                "ok": False,
                "results": [],
                "error": f"{type(e).__name__}: {e}",
                "took": time.monotonic() - t0,
            }

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = []
        for i, q in enumerate(queries):
            started[i] = time.monotonic()
            futures.append(pool.submit(_run, i, q))
        for fut in as_completed(futures, timeout=per_query_timeout * max(1, workers)):
            try:
                idx, block = fut.result(timeout=per_query_timeout)
            except Exception as e:  # noqa: BLE001
                # Find which index failed; result timed out without resolving.
                blocks = [b if b is not None else {
                    "query": queries[len([x for x in blocks if x is not None])],
                    "ok": False, "results": [], "error": f"timeout: {e}", "took": per_query_timeout,
                } for b in blocks]
                continue
            blocks[idx] = block

    blocks = [b if b is not None else {
        "query": queries[i], "ok": False, "results": [], "error": "no_result", "took": 0.0,
    } for i, b in enumerate(blocks)]

    md_chunks: list[str] = []
    errs: list[str] = []
    any_ok = False
    for b in blocks:
        if b.get("ok"):
            any_ok = True
        if b.get("error"):
            errs.append(f"{b['query']}: {b['error']}")
        md_chunks.append(
            f"--- search result for [{b['query']}] ---\n"
            f"{format_brief(b.get('results') or [])}\n"
            f"--- end of search result ---"
        )
    return ParallelSearchResult(
        ok=any_ok,
        blocks=blocks,
        combined_markdown="\n\n".join(md_chunks).strip(),
        errors=errs,
    )


# ---------------------------------------------------------------------------
# 4. URL fetching + LLM-synthesized browsing
# ---------------------------------------------------------------------------

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_BLOCKLIST_TAGS = re.compile(
    r"<(script|style|noscript|iframe|svg|canvas|form|button|input|nav|footer|header)[^>]*>.*?</\1>",
    re.S | re.I,
)


def extract_text(url: str, *, fetch_fn: Callable[[str], str] | None = None) -> str:
    """Fetch a URL and return a clean text/markdown body.

    If `fetch_fn` is provided it must return the raw HTML.  Otherwise we use
    `websearch._fetch` (urllib + UA) which respects the Agent-Hub proxy /
    TLS settings.  We strip scripts/styles, drop tags, and collapse
    whitespace, but preserve paragraph breaks.
    """
    fetcher = fetch_fn
    if fetcher is None:
        from . import websearch  # local import to avoid cycles

        fetcher = lambda u: websearch._fetch(u, timeout=4.0)  # noqa: E731
    try:
        html = fetcher(url)
    except Exception as e:  # noqa: BLE001
        return f"[fetch error: {type(e).__name__}: {e}]"
    if not html:
        return ""

    text = _BLOCKLIST_TAGS.sub(" ", html)
    text = _TAG_RE.sub(" ", text)
    text = unescape(text)
    # Normalize line breaks: keep blank lines for paragraphs.
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = _WS_RE.sub(" ", text)
    return text.strip()


def chunk_text(text: str, *, chunk_chars: int = 4000, overlap: int = 200) -> list[str]:
    """Split text into character-bounded chunks with optional overlap.

    We use a char-based heuristic (~2 chars per token) to stay
    tokenizer-free.  The overlap preserves cross-chunk context so the
    LLM can stitch answers together.
    """
    if not text:
        return []
    if len(text) <= chunk_chars:
        return [text]
    step = max(1, chunk_chars - overlap)
    chunks: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        end = min(i + chunk_chars, n)
        chunks.append(text[i:end])
        if end >= n:
            break
        i += step
    return chunks


def _browse_chunk_prompt(chunk: str, query: str) -> str:
    return (
        "Please read the source content and answer the following question.\n"
        "If there is no relevant information, please clearly refuse to answer.\n"
        "When answering, identify and quote the original content as evidence.\n\n"
        f"--- begin of source content ---\n{chunk}\n--- end of source content ---\n\n"
        f"Question: {query}"
    )


def _browse_full_prompt(source: str, query: str) -> str:
    return (
        "Please read the source content and answer the following question.\n"
        "If there is no relevant information, please clearly refuse to answer.\n"
        "When answering, identify and quote the original content as evidence.\n\n"
        f"---begin of source content---\n{source}\n---end of source content---\n\n"
        f"Question: {query}"
    )


def _synthesize_chunks(
    chunks: list[str],
    query: str,
    *,
    llm_fn: Callable[[str], str | None],
) -> str:
    """Run each chunk through the LLM in parallel and stitch results."""
    if not chunks:
        return ""
    if len(chunks) == 1:
        out = llm_fn(_browse_full_prompt(chunks[0], query))
        return (out or "").strip()

    pieces: list[str | None] = [None] * len(chunks)
    with ThreadPoolExecutor(max_workers=min(len(chunks), 4)) as pool:
        futures = {
            pool.submit(llm_fn, _browse_chunk_prompt(c, query)): i
            for i, c in enumerate(chunks)
        }
        for fut in as_completed(futures):
            i = futures[fut]
            try:
                pieces[i] = fut.result() or ""
            except Exception:  # noqa: BLE001
                pieces[i] = ""
    out_parts = [
        f"--- begin of result part {i + 1} ---\n{pieces[i].strip()}\n--- end of result part {i + 1} ---"
        for i in range(len(chunks))
    ]
    preamble = (
        "The content is split into multiple parts; combine the parts to "
        "recover the complete answer.\n\n"
    )
    return preamble + "\n\n".join(out_parts)


def browse_url(
    url: str,
    query: str,
    *,
    llm_fn: Callable[[str], str | None],
    fetch_fn: Callable[[str], str] | None = None,
    max_chars: int = 12000,
    chunk_chars: int = 4000,
) -> str:
    """Fetch a single URL and return an LLM-synthesized answer."""
    source = extract_text(url, fetch_fn=fetch_fn)
    if not source or source.startswith("[fetch error"):
        return f"Browse error: {source or 'empty response'}"
    if query.strip() == "":
        query = "Detailed summary of the page."
    # Truncate to max_chars before chunking; keep head + tail for context.
    if len(source) > max_chars:
        head = source[: max_chars // 2]
        tail = source[-max_chars // 2 :]
        source = head + "\n\n[...content truncated...]\n\n" + tail
    chunks = chunk_text(source, chunk_chars=chunk_chars)
    answer = _synthesize_chunks(chunks, query, llm_fn=llm_fn)
    return (answer or "").strip() or "Browse error: empty answer."


def browse_urls(
    urls: list[str],
    query: str,
    *,
    llm_fn: Callable[[str], str | None],
    fetch_fn: Callable[[str], str] | None = None,
    max_chars: int = 12000,
    chunk_chars: int = 4000,
    max_workers: int | None = None,
) -> str:
    """Fetch and LLM-summarize a list of URLs in parallel.

    Returns a single markdown string with one block per URL:
        --- answer based on [URL] ---
        <answer>
        --- end of answer ---
    """
    if not urls:
        return "No URLs to browse."
    workers = max_workers or min(len(urls), 4)

    def _one(i: int, u: str) -> tuple[int, str]:
        return i, browse_url(
            u, query, llm_fn=llm_fn, fetch_fn=fetch_fn,
            max_chars=max_chars, chunk_chars=chunk_chars,
        )

    pieces: list[str | None] = [None] * len(urls)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(_one, i, u) for i, u in enumerate(urls)]
        for fut in as_completed(futures):
            i, ans = fut.result()
            pieces[i] = ans
    chunks: list[str] = []
    for i, ans in enumerate(pieces):
        chunks.append(
            f"--- answer based on [{urls[i]}] ---\n{ans}\n--- end of answer ---"
        )
    return "\n\n".join(chunks).strip()


# ---------------------------------------------------------------------------
# 5. search_structured — drop-in parity shim for websearch.search_structured
# ---------------------------------------------------------------------------

def search_structured(
    query: str,
    *,
    search_fn: Callable[[str], dict[str, Any]] | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """High-level parity entry point.

    Parses advanced operators, fans the (cleaned) query out to `search_fn`,
    and assembles a result dict that matches the Agent-Hub convention:
        {"ok": bool, "query": str, "results": [...], "errors": [...],
         "engine": str, "cleaned_query": str, "operators": {...}}
    If no `search_fn` is provided, falls back to `websearch.search_structured`
    on the cleaned query.
    """
    parsed = parse_query(query)
    if not parsed.cleaned and not parsed.has_operators():
        return {
            "ok": False,
            "query": query,
            "results": [],
            "errors": ["empty_query"],
            "engine": "minimax-parity",
            "cleaned_query": "",
            "operators": _parsed_to_dict(parsed),
        }

    target_query = parsed.cleaned or (parsed.exact[0] if parsed.exact else "")

    def _default_search(q: str) -> dict[str, Any]:
        from . import websearch  # local import to avoid cycles

        return websearch.search_structured(q, deep=False)

    fn = search_fn or _default_search
    primary = fn(target_query) if target_query else {"ok": False, "results": [], "error": "empty"}

    results = list(primary.get("results") or [])
    engine = primary.get("engine") or "minimax-parity"
    errors: list[str] = []
    if primary.get("error"):
        errors.append(str(primary["error"]))

    # Empty-result fallback: try the original query verbatim (in case the
    # operator cleanup dropped a token the engine needed).
    if not results and parsed.has_operators():
        retry = fn(query)
        if retry.get("results"):
            results = list(retry.get("results") or [])
            errors.append(
                f"Search result for [{target_query}] is empty. "
                f"Return search result for original query instead."
            )

    return {
        "ok": bool(results),
        "query": query,
        "results": results,
        "errors": errors,
        "engine": f"{engine}+minimax-parity",
        "cleaned_query": target_query,
        "operators": _parsed_to_dict(parsed),
    }


def _parsed_to_dict(p: ParsedQuery) -> dict[str, Any]:
    return {
        "site": p.site,
        "inurl": p.inurl,
        "intitle": p.intitle,
        "intext": p.intext,
        "inanchor": p.inanchor,
        "exclude": list(p.exclude),
        "synonym": list(p.synonym),
        "exact": list(p.exact),
        "has_operators": p.has_operators(),
    }


__all__ = [
    "ParsedQuery",
    "ParallelSearchResult",
    "parse_query",
    "format_brief",
    "parallel_search",
    "extract_text",
    "chunk_text",
    "browse_url",
    "browse_urls",
    "search_structured",
]
