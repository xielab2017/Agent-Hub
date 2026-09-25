"""Reply reviewer (modelled on Claude Science's background reviewer).

Deterministic, offline and fast, so it can run on every reply:

* ``citation_out_of_range`` / ``citation_without_sources`` — ``[n]`` markers that
  point at no retrieved source.
* ``unlisted_url`` — URLs that appear in neither the retrieved sources nor the
  evidence (user message, workspace excerpts, tool output).
* ``malformed_doi`` / ``malformed_pmid`` and ``unverified_identifier``.
* ``untraceable_number`` — quantitative claims (percentages, p-values, stats,
  n=, quantities with units, fold changes) that occur in none of the evidence.

``verify_identifiers_online`` optionally resolves DOIs (Crossref) and PMIDs
(NCBI eSummary).  The reviewer only flags; it never rewrites the reply.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Callable
from urllib.parse import quote, urlparse

_CODE_FENCE_RE = re.compile(r"```[\s\S]*?(?:```|$)")
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_URL_RE = re.compile(r"https?://[^\s<>\"'`，。；、）)\]]+")
_CITE_RE = re.compile(r"\[(\d{1,3}(?:\s*[,，、–\-]\s*\d{1,3})*)\](?!\()")
_DOI_RE = re.compile(r"\b10\.\d{4,9}/[^\s\"<>，。；、）)\]]+")
_STOP = r"\s,，。；;、）)\]】>\"'"
_DOI_CANDIDATE_RE = re.compile(r"(?:\bdoi\s*[:：]\s*|doi\.org/)([^" + _STOP + r"]+)", re.I)
_DOI_VALID_RE = re.compile(r"^10\.\d{4,9}/[-._;()/:A-Za-z0-9<>]+$")
_PMID_RE = re.compile(r"\bPMID\s*[:：]?\s*([^" + _STOP + r"]+)", re.I)

# Mass / activity per volume in any case (ng/ml, pg/mL, mg/dL, IU/L); tried before bare "ng".
CONC_UNIT = r"(?i:(?:[pnmµμu]?g|IU|U)\s*/\s*[dmµμ]?l)(?![a-z])"
_UNITS = (
    CONC_UNIT + r"|nM|μM|µM|uM|mM|pM|fM|mg/kg|mg|μg|µg|ng|kg|kDa|Da|Å|bp|kb|Mb|Gb|aa|"
    r"mmHg|°C|倍|fold|例|名患者|名受试者|名|位患者|人|只小鼠|只|个样本|个细胞|samples?|patients?|"
    r"participants?|subjects?|cells?|mice|reads|genes?|个基因"
)
_NUM = r"\d+(?:[.,]\d+)*(?:\.\d+)?"
_RANGE_SEP = r"\s*(?:-|–|—|~|～|至|到)\s*"
_NUM_RANGE = _NUM + r"(?:" + _RANGE_SEP + _NUM + r")?"
_CLAIM_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    ("percent", re.compile(r"(?<![\w.])(" + _NUM_RANGE + r")\s*[%％]"), "warn"),
    ("p_value", re.compile(r"\b[pP]\s*(?:值)?\s*[<=≤>≥]\s*(" + r"\d*\.?\d+(?:\s*[×x*]\s*10\^?-?\d+|[eE]-?\d+)?" + r")"), "warn"),
    ("statistic", re.compile(r"\b(?:IC50|EC50|Kd|Ki|HR|OR|RR|AUC|R2|R²|FDR|log2FC|CI)\s*(?:值)?\s*[=:：为≈~]?\s*(" + _NUM + r")", re.I), "warn"),
    ("sample_size", re.compile(r"\b[nN]\s*=\s*(\d[\d,]*)"), "warn"),
    ("quantity", re.compile(r"(?<![\w.])(" + _NUM_RANGE + r")\s*(?:" + _UNITS + r")(?![A-Za-z])"), "info"),
]
_YEAR_RE = re.compile(r"^(?:19|20)\d{2}$")
_EVIDENCE_NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")

_MAX_ISSUES_PER_KIND = 12
# Words that mark a number as a parameter the author sets, e.g. in an experiment design.
_DESIGN_CUES = re.compile(
    r"脱落|失访|统计功效|功效|把握度|检验效能|显著性水平|置信区间|置信水平|最大心率|HRmax|VO2max|最大摄氧|剂量|给药|"
    r"样本量|每组|/组|总样本|假设为|设定为|设为|预计|预期|阈值|截断值|变异系数|\bCV\b|LOA|一致性界限|检出限|定量限|LOD|LOQ|"
    r"dropout|attrition|power|alpha|α|β|confidence|\bCI\b|sample size|per group|dose|assum|threshold",
    re.I,
)
# "Jensen et al." / "Jensen 等（2015）" — a named reference that must be among the retrieved sources.
_NAMED_REF_RE = re.compile(r"\b([A-Z][a-z]{2,}(?:-[A-Z][a-z]+)?)\s*(?:et\s+al\.?|等人?\s*[（(]\s*(?:19|20)\d{2})")
# Trailing punctuation and Markdown emphasis (`_doi:10.1/x_`, `**…**`) are never part of an id.
_TRAIL = ".,;:!?)）]】_*~'\""


def _iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _prose(text: str) -> str:
    return _INLINE_CODE_RE.sub(" ", _CODE_FENCE_RE.sub(" ", text or ""))


def _norm_url(url: str) -> str:
    u = (url or "").strip().rstrip(_TRAIL + "}>")
    try:
        p = urlparse(u)
    except ValueError:
        return u.lower()
    host = (p.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return f"{host}{p.path.rstrip('/')}" + (f"?{p.query}" if p.query else "")


def _domain(url: str) -> str:
    try:
        host = (urlparse(url).netloc or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def normalize_number(raw: str) -> str:
    """Canonical form for matching: drop thousands separators and trailing zeros."""
    s = (raw or "").strip().replace(" ", "")
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", s):
        s = s.replace(",", "")
    if "." in s:
        head, _, tail = s.partition(".")
        tail = tail.rstrip("0")
        s = f"{head}.{tail}" if tail else head
    if s.startswith("."):
        s = "0" + s
    s = s.lstrip("0") or "0"
    if s.startswith("."):
        s = "0" + s
    return s


def normalize_value(raw: str) -> str:
    """normalize_number, keeping ranges ("0.26–1.86" → "0.26-1.86")."""
    parts = [p for p in re.split(_RANGE_SEP, (raw or "").strip()) if p]
    if len(parts) == 2:
        return f"{normalize_number(parts[0])}-{normalize_number(parts[1])}"
    return normalize_number(raw)


def _evidence_numbers(evidence: str) -> set[str]:
    out: set[str] = set()
    for m in _EVIDENCE_NUM_RE.findall(evidence or ""):
        out.add(normalize_number(m))
        # "1,234" may also be two numbers in a list
        for part in re.split(r"[,]", m):
            if part:
                out.add(normalize_number(part))
    return out


def _sentence_window(text: str, start: int, end: int, *, before: int = 30, after: int = 16) -> str:
    """Up to ``before``/``after`` characters around a match, never crossing a sentence end."""
    left = text[max(0, start - before): start]
    cut = max(left.rfind(c) for c in "。；;！？!?\n|")
    if cut >= 0:
        left = left[cut + 1:]
    right = text[end: end + after]
    stops = [i for i in (right.find(c) for c in "。；;！？!?\n|") if i >= 0]
    if stops:
        right = right[: min(stops)]
    return left + text[start:end] + right


def _states_value(value: str, nums: set[str]) -> bool:
    return all(p in nums for p in normalize_value(value).split("-") if p)


def _traceable(value: str, kind: str, evidence_nums: set[str]) -> bool:
    rng = normalize_value(value)
    if "-" in rng:
        return all(p in evidence_nums for p in rng.split("-"))
    n = normalize_number(value)
    if n in evidence_nums:
        return True
    if kind == "percent":
        # 45% ↔ 0.45
        try:
            frac = normalize_number(repr(round(float(n) / 100.0, 6)))
            if frac in evidence_nums:
                return True
        except ValueError:
            pass
    return False


def _expand_citations(group: str) -> list[int]:
    nums: list[int] = []
    for part in re.split(r"\s*[,，、]\s*", group):
        rng = re.split(r"\s*[–\-]\s*", part)
        try:
            if len(rng) == 2:
                a, b = int(rng[0]), int(rng[1])
                if 0 < a <= b and b - a <= 50:
                    nums.extend(range(a, b + 1))
            elif rng and rng[0]:
                nums.append(int(rng[0]))
        except ValueError:
            continue
    return nums


def _issue(kind: str, severity: str, text: str, detail: str = "", detail_zh: str = "") -> dict[str, str]:
    return {"kind": kind, "severity": severity, "text": text[:200], "detail": detail[:300],
            "detail_zh": (detail_zh or detail)[:300]}


def review_reply(
    text: str,
    *,
    sources: list[dict[str, Any]] | None = None,
    evidence_texts: list[str] | None = None,
    simple_chat: bool = False,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Review one reply against its retrieved sources and evidence.

    ``evidence`` (from ``evidence.build_evidence``) adds corroboration checks:
    numbers stated by a single source, numbers the sources disagree on, and
    evidence bases made only of forums / self-media.
    """
    body = text or ""
    if simple_chat or not body.strip():
        return {"ok": True, "skipped": True, "checked_at": _iso(), "issues": [], "counts": {}, "stats": {}}

    srcs = [s for s in (sources or []) if isinstance(s, dict)]
    n_sources = len(srcs)
    source_blob = "\n".join(f"{s.get('title') or ''} {s.get('snippet') or ''} {s.get('url') or ''}" for s in srcs)
    evidence_blob = "\n".join([source_blob] + [str(e or "") for e in (evidence_texts or [])])
    evidence_lower = evidence_blob.lower()
    known_urls = {_norm_url(s.get("url") or "") for s in srcs if s.get("url")}
    known_urls |= {_norm_url(u) for u in _URL_RE.findall(evidence_blob)}
    known_domains = {_domain(s.get("url") or "") for s in srcs if s.get("url")}
    prose = _prose(body)
    issues: list[dict[str, str]] = []

    # 1) numbered citations
    cited: list[int] = []
    for m in _CITE_RE.finditer(prose):
        cited.extend(_expand_citations(m.group(1)))
    cited_set = sorted(set(cited))
    if cited_set and n_sources == 0:
        issues.append(_issue(
            "citation_without_sources", "warn",
            " ".join(f"[{n}]" for n in cited_set[:10]),
            "Reply cites numbered sources but no sources were retrieved for this turn.",
            "回复使用了编号引用，但本轮没有检索到任何来源。",
        ))
    else:
        # Sources may carry task-wide numbers ("n"); otherwise they are 1..N in order.
        valid = {int(s.get("n") or i) for i, s in enumerate(srcs, start=1)}
        for n in cited_set:
            if n not in valid:
                issues.append(_issue("citation_out_of_range", "warn", f"[{n}]", f"Only {n_sources} sources were retrieved.",
                                     f"本轮只检索到 {n_sources} 条来源。"))

    # 2) URLs
    urls = list(dict.fromkeys(u.rstrip(_TRAIL) for u in _URL_RE.findall(prose)))
    for u in urls:
        if _norm_url(u) in known_urls:
            continue
        if n_sources and _domain(u) in known_domains:
            issues.append(_issue("unlisted_url", "info", u, "Same domain as a retrieved source, but this exact page was not retrieved.",
                                 "与已检索来源同域名，但并未检索到这个具体页面。"))
        else:
            issues.append(_issue(
                "unlisted_url", "warn" if n_sources else "info", u,
                "Not among the retrieved sources or evidence — verify before relying on it.",
                "不在检索来源或提供的材料中——使用前请核实。",
            ))

    # 3) identifiers
    dois: list[str] = []
    for cand in _DOI_CANDIDATE_RE.findall(prose):
        c = cand.rstrip(_TRAIL)
        if not _DOI_VALID_RE.match(c):
            issues.append(_issue("malformed_doi", "warn", c, "Not a syntactically valid DOI (10.<registrant>/<suffix>).",
                                 "DOI 格式不合法（应为 10.<注册号>/<后缀>）。"))
        else:
            dois.append(c)
    dois.extend(d.rstrip(_TRAIL) for d in _DOI_RE.findall(prose))
    dois = list(dict.fromkeys(dois))
    pmids: list[str] = []
    for cand in _PMID_RE.findall(prose):
        c = cand.rstrip(_TRAIL)
        if not re.fullmatch(r"\d{1,9}", c):
            issues.append(_issue("malformed_pmid", "warn", c, "PMIDs are 1–9 digit integers.", "PMID 应为 1–9 位整数。"))
        else:
            pmids.append(c)
    pmids = list(dict.fromkeys(pmids))
    for d in dois:
        if d.lower() not in evidence_lower:
            issues.append(_issue("unverified_identifier", "info", f"doi:{d}", "DOI not found in retrieved sources — use online verification.",
                                 "检索来源中没有这个 DOI——可点“联网核验引用”。"))
    for p in pmids:
        if not re.search(r"(?<!\d)" + re.escape(p) + r"(?!\d)", evidence_blob):
            issues.append(_issue("unverified_identifier", "info", f"PMID {p}", "PMID not found in retrieved sources — use online verification.",
                                 "检索来源中没有这个 PMID——可点“联网核验引用”。"))

    # 4) untraceable numbers
    evidence_nums = _evidence_numbers(evidence_blob)
    facts_ev = list((evidence or {}).get("facts") or [])
    conflicts_ev = list((evidence or {}).get("conflicts") or [])
    if ((evidence or {}).get("coverage") or {}).get("ugc_only"):
        issues.append(_issue(
            "ugc_only_sources", "info", "UGC",
            "Every retrieved source is a forum / Q&A / self-media page — treat conclusions as unverified.",
            "检索到的来源全部是论坛 / 问答 / 自媒体——结论需视为未经核实。",
        ))
    claims = 0
    traced = 0
    seen: set[str] = set()
    spans: list[tuple[int, int]] = []
    number_prose = _DOI_RE.sub(" ", _URL_RE.sub(" ", prose))
    reply_nums = _evidence_numbers(number_prose)
    for kind, pat, severity in _CLAIM_PATTERNS:
        for m in pat.finditer(number_prose):
            raw = m.group(1)
            norm = normalize_number(re.split(r"\s*[×x*eE]", raw)[0]) if kind == "p_value" else normalize_value(raw)
            if _YEAR_RE.match(norm) and kind == "quantity":
                continue
            # One claim per number: skip repeats and overlaps with an earlier pattern
            # ("IC50 = 12.5 nM" is a statistic, not also a separate quantity).
            if norm in seen or any(a < m.end(1) and m.start(1) < b for a, b in spans):
                continue
            seen.add(norm)
            spans.append((m.start(1), m.end(1)))
            claims += 1
            if _traceable(raw if kind != "p_value" else norm, kind, evidence_nums):
                traced += 1
                support = [f for f in facts_ev if f.get("value") == norm]
                if support:
                    shown = m.group(0).strip()
                    if any(f.get("conflict") for f in support):
                        alt = next((c for c in conflicts_ev if any(v["value"] == norm for v in c["values"])), None)
                        other_vals = [v for v in (alt or {}).get("values", []) if v["value"] != norm]
                        others = ", ".join(v["display"] for v in other_vals)
                        if other_vals and all(_states_value(v["value"], reply_nums) for v in other_vals):
                            # The reply already reports the competing values — the digest's instruction was followed.
                            issues.append(_issue(
                                "conflict_reported", "info", shown,
                                f"Sources disagree ({others}); the reply states both values.",
                                f"来源数值不一致（{others}）；回复已同时列出。",
                            ))
                        else:
                            issues.append(_issue(
                                "conflicting_number", "warn", shown,
                                f"Sources disagree on this metric (other values: {others or 'n/a'}) — state both and justify the choice.",
                                f"来源对该指标的数值不一致（其他值：{others or '无'}）——应同时列出并说明取舍理由。",
                            ))
                    elif max(int(f.get("domains") or 0) for f in support) < 2:
                        issues.append(_issue(
                            "single_source_number", "info", shown,
                            "Backed by only one source domain — corroborate before relying on it.",
                            "只有一个来源域名支持——建议再找独立来源核对。",
                        ))
                continue
            snippet = number_prose[max(0, m.start() - 24): m.end() + 12].replace("\n", " ").strip()
            if _DESIGN_CUES.search(_sentence_window(number_prose, m.start(), m.end())):
                # a value the reply chooses (power, α, dropout, CI level, dose, sample size) — not a sourced fact
                issues.append(_issue(
                    "design_parameter", "info", m.group(0).strip(),
                    f"…{snippet}… — a design / planning parameter chosen in the reply, not a sourced fact.",
                    f"…{snippet}…——回复自行设定的设计参数（非引用事实），请按实际研究条件确认。",
                ))
                continue
            issues.append(_issue(
                "untraceable_number", severity, m.group(0).strip(),
                f"…{snippet}… — not found in any retrieved source or provided material.",
                f"…{snippet}…——在检索来源和提供的材料中都找不到出处。",
            ))

    # 5) named references ("Jensen et al. 2015") that no retrieved source or provided material mentions
    if n_sources:
        for name in dict.fromkeys(m.group(1) for m in _NAMED_REF_RE.finditer(_DOI_RE.sub(" ", _URL_RE.sub(" ", prose)))):
            if name.lower() not in evidence_lower:
                issues.append(_issue(
                    "unverified_reference", "warn", f"{name} et al.",
                    "Named reference not among the retrieved sources or provided material — it may be misattributed.",
                    "点名引用的文献不在检索来源或提供的材料中——可能张冠李戴或并不存在，请核实。",
                ))

    # cap per kind, keep counts exact
    counts: dict[str, int] = {}
    capped: list[dict[str, str]] = []
    for it in issues:
        counts[it["kind"]] = counts.get(it["kind"], 0) + 1
        if counts[it["kind"]] <= _MAX_ISSUES_PER_KIND:
            capped.append(it)
    warn = sum(1 for it in issues if it["severity"] == "warn")
    info = len(issues) - warn
    return {
        "ok": warn == 0,
        "skipped": False,
        "checked_at": _iso(),
        "counts": counts,
        "warn": warn,
        "info": info,
        "issues": capped,
        "stats": {
            "sources": n_sources,
            "citations": len(cited_set),
            "urls": len(urls),
            "identifiers": len(dois) + len(pmids),
            "numbers": claims,
            "traced_numbers": traced,
        },
        "identifiers": {"doi": dois[:20], "pmid": pmids[:20]},
    }


def _default_fetch(url: str) -> str:
    from . import search_extensions as se

    return se._fetch(url, timeout=4.0, headers={"Accept": "application/json"})


def verify_identifiers_online(
    identifiers: dict[str, list[str]],
    *,
    fetch: Callable[[str], str] | None = None,
) -> list[dict[str, Any]]:
    """Resolve DOIs via Crossref and PMIDs via NCBI eSummary.

    Returns ``[{kind, id, resolved: True|False|None, title, error}]`` —
    ``None`` means the service could not be reached (unknown, not wrong).
    """
    fetch = fetch or _default_fetch
    out: list[dict[str, Any]] = []
    for doi in (identifiers.get("doi") or [])[:10]:
        row: dict[str, Any] = {"kind": "doi", "id": doi, "resolved": None, "title": "", "error": ""}
        try:
            data = json.loads(fetch(f"https://api.crossref.org/works/{quote(doi, safe='/')}"))
            msg = data.get("message") or {}
            row["resolved"] = bool(msg.get("DOI"))
            row["title"] = ((msg.get("title") or [""])[0] or "")[:200]
        except json.JSONDecodeError:
            row["resolved"] = False
            row["error"] = "not found"
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if "404" in msg:
                row["resolved"] = False
                row["error"] = "not found"
            else:
                row["error"] = msg[:160]
        out.append(row)
    pmids = (identifiers.get("pmid") or [])[:20]
    if pmids:
        try:
            data = json.loads(fetch(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&retmode=json&id=" + ",".join(pmids)
            ))
            result = data.get("result") or {}
            for p in pmids:
                rec = result.get(p) or {}
                ok = bool(rec) and not rec.get("error") and bool(rec.get("title"))
                out.append({"kind": "pmid", "id": p, "resolved": ok, "title": str(rec.get("title") or "")[:200],
                            "error": "" if ok else str(rec.get("error") or "not found")})
        except Exception as exc:  # noqa: BLE001
            out.extend({"kind": "pmid", "id": p, "resolved": None, "title": "", "error": str(exc)[:160]} for p in pmids)
    return out


def apply_online_results(review: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge online verification into a review (unresolved ids become warnings)."""
    rv = dict(review or {})
    issues = [it for it in (rv.get("issues") or []) if it.get("kind") != "unresolved_identifier"]
    for r in results:
        if r.get("resolved") is False:
            label = f"doi:{r['id']}" if r.get("kind") == "doi" else f"PMID {r['id']}"
            issues.append(_issue("unresolved_identifier", "warn", label, "Does not resolve — likely incorrect or fabricated.",
                                 "无法解析——很可能有误或是编造的。"))
    rv["issues"] = issues
    counts: dict[str, int] = {}
    for it in issues:
        counts[it["kind"]] = counts.get(it["kind"], 0) + 1
    rv["counts"] = counts
    rv["warn"] = sum(1 for it in issues if it.get("severity") == "warn")
    rv["info"] = len(issues) - rv["warn"]
    rv["ok"] = rv["warn"] == 0
    rv["online"] = {"checked_at": _iso(), "results": results}
    return rv


# ── session integration ───────────────────────────────────────────────


def review_message(session_id: str, message_id: str, *, online: bool = False,
                   fetch: Callable[[str], str] | None = None) -> dict[str, Any]:
    """Re-review a stored assistant message and persist the result on it."""
    from . import provenance
    from . import sessions as store

    with store._lock:
        session = store.get_session(session_id)
        if session is None:
            raise FileNotFoundError("session not found")
        idx = next((i for i, m in enumerate(session.messages) if m.get("id") == message_id), -1)
        if idx < 0 or session.messages[idx].get("role") != "assistant":
            raise FileNotFoundError("assistant message not found")
        msg = session.messages[idx]
        user_text = next(
            (str(m.get("content") or "") for m in reversed(session.messages[:idx]) if m.get("role") == "user"), ""
        )
        record = provenance.load_record(session_id, message_id) or {}
        sources = ((record.get("search") or {}).get("sources")) or []
        prompt = (((record.get("context") or {}).get("system_prompt") or {}).get("text")) or ""
        tools = " ".join(str(t.get("preview") or "") for t in (record.get("tools") or msg.get("tools") or []))
        review = review_reply(
            str(msg.get("content") or ""),
            sources=sources,
            evidence_texts=[user_text, prompt, tools],
            simple_chat=bool((msg.get("route") or {}).get("simple_chat")),
        )
        if online and not review.get("skipped"):
            review = apply_online_results(review, verify_identifiers_online(review.get("identifiers") or {}, fetch=fetch))
        msg = dict(msg)
        msg["review"] = review
        session.messages[idx] = msg
        store.save_session(session)
    try:
        from . import audit

        audit.log_event("review", {"session_id": session_id, "message_id": message_id, "online": online,
                                   "warn": review.get("warn"), "info": review.get("info")})
    except Exception:  # noqa: BLE001
        pass
    return review
