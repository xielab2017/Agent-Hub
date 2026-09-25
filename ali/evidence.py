"""Evidence digest: grade sources, read passages, cross-check numbers.

``build_evidence(query, sources, pages)`` turns one turn's search results
(plus any opened pages from ``page_fetch``) into:

* ``sources``  — numbered, graded (tier / date), with the best passages
* ``facts``    — numeric facts found in the evidence, each with the sources
                 that state it and how many *independent domains* agree
* ``conflicts``— the same metric reported with different values by
                 different sources
* ``coverage`` — counts that describe how solid the evidence base is

``render_block`` formats that for the prompt, including the required answer
structure (conclusions / key data table / disagreements / next steps).
Everything is deterministic and offline.
"""

from __future__ import annotations

import re
from typing import Any

from .reviewer import _CLAIM_PATTERNS, normalize_number
from .source_quality import annotate, host_of

_SENT_SPLIT = re.compile(r"(?<=[。！？!?；;])|(?<=\.)\s+|\n+")
_KEY_STOP_ZH = ("大约", "约为", "超过", "达到", "高达", "仅为", "左右", "其中", "分别", "约", "为", "是", "达",
                "占", "的", "有", "在", "中", "了", "和", "与", "及", "共", "每", "已", "将", "比", "率为")
_KEY_STOP_EN = frozenset(
    "about approximately around roughly nearly over under than of in on at to the a an is was were are be been "
    "with by for from and or as that this which reported found showed increased decreased rose fell reached".split()
)
_CJK = re.compile(r"[一-鿿]+")
_EN_WORD = re.compile(r"[A-Za-z][A-Za-z0-9\-]{1,24}")
_STAT_NAME = re.compile(r"\b(IC50|EC50|Kd|Ki|HR|OR|RR|AUC|R2|R²|FDR|log2FC|CI)\b", re.I)
# Only these kinds describe comparable quantities across studies; p-values and n= never "conflict".
_CONFLICT_KINDS = ("percent", "statistic")
_REL_TOL = 0.05
MAX_FACTS = 24


def _metric_key(sentence: str, start: int) -> str:
    """Name of the quantity a number measures, from the words just before it."""
    before = sentence[max(0, start - 40): start]
    cjk = _CJK.findall(before)
    if cjk:
        seg = cjk[-1]
        changed = True
        while changed and seg:
            changed = False
            for stop in _KEY_STOP_ZH:
                if seg.endswith(stop) and len(seg) > len(stop):
                    seg = seg[: -len(stop)]
                    changed = True
        seg = seg[-6:]
        if len(seg) >= 2:
            return seg
    words = [w.lower() for w in _EN_WORD.findall(before) if w.lower() not in _KEY_STOP_EN]
    return " ".join(words[-2:])


def _values_close(a: str, b: str) -> bool:
    try:
        x, y = float(a), float(b)
    except ValueError:
        return a == b
    if x == y:
        return True
    return abs(x - y) / max(abs(x), abs(y), 1e-9) <= _REL_TOL


def extract_facts(text: str) -> list[dict[str, str]]:
    """Numeric facts ``{kind, key, value, display}`` stated in ``text`` (one per span)."""
    out: list[dict[str, str]] = []
    for sent in _SENT_SPLIT.split(text or ""):
        if not sent or not re.search(r"\d", sent):
            continue
        spans: list[tuple[int, int]] = []
        for kind, pat, _sev in _CLAIM_PATTERNS:
            for m in pat.finditer(sent):
                a, b = m.start(1), m.end(1)
                if any(x < b and a < y for x, y in spans):
                    continue
                raw = m.group(1)
                value = normalize_number(re.split(r"\s*[×x*eE]", raw)[0]) if kind == "p_value" else normalize_number(raw)
                if kind == "quantity" and re.fullmatch(r"(?:19|20)\d{2}", value):
                    continue
                spans.append((a, b))
                if kind == "statistic":
                    name = _STAT_NAME.search(m.group(0))
                    ctx = _metric_key(sent, m.start())
                    key = " ".join(x for x in ((name.group(1).lower() if name else ""), ctx) if x)
                else:
                    key = _metric_key(sent, m.start())
                out.append({"kind": kind, "key": key, "value": value, "display": m.group(0).strip()[:40]})
    return out


def build_evidence(query: str, sources: list[dict[str, Any]], pages: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    page_by_n = {int(p.get("n") or 0): p for p in (pages or []) if p.get("n")}
    graded: list[dict[str, Any]] = []
    # fact occurrences: (kind, key, value) -> {n: domain}
    occ: dict[tuple[str, str, str], dict[int, str]] = {}
    display: dict[tuple[str, str, str], str] = {}
    for i, raw in enumerate(sources or [], start=1):
        if not isinstance(raw, dict):
            continue
        s = annotate(raw)
        n = int(raw.get("n") or i)
        page = page_by_n.get(n) or {}
        passages = list(page.get("passages") or [])
        domain = host_of(str(s.get("url") or ""))
        graded.append({
            "n": n,
            "title": str(s.get("title") or "")[:200],
            "url": str(s.get("url") or ""),
            "domain": domain,
            "engine": str(s.get("source") or s.get("engine") or ""),
            "tier": s["tier"],
            "tier_label": s["tier_label"],
            "tier_label_zh": s["tier_label_zh"],
            "credibility": s["credibility"],
            "preprint": s["preprint"],
            "date": s["date"] or (page and _page_date(page)) or "",
            "page_read": bool(page.get("ok")),
            "passages": passages[:4],
        })
        blob = "\n".join([str(s.get("title") or ""), str(s.get("snippet") or "")] + passages)
        for f in extract_facts(blob):
            k = (f["kind"], f["key"], f["value"])
            occ.setdefault(k, {})[n] = domain
            display.setdefault(k, f["display"])

    facts: list[dict[str, Any]] = []
    for (kind, key, value), by_n in occ.items():
        domains = sorted({d for d in by_n.values() if d})
        facts.append({
            "kind": kind, "key": key, "value": value, "display": display[(kind, key, value)],
            "sources": sorted(by_n), "domains": len(domains) or len(by_n),
        })
    facts.sort(key=lambda f: (-f["domains"], -len(f["sources"]), f["key"], f["value"]))

    # conflicts: same kind+key, values that are not close, stated by different sources
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for f in facts:
        if f["key"] and f["kind"] in _CONFLICT_KINDS:
            groups.setdefault((f["kind"], f["key"]), []).append(f)
    conflicts: list[dict[str, Any]] = []
    for (kind, key), fs in groups.items():
        distinct: list[dict[str, Any]] = []
        for f in fs:
            if not any(_values_close(f["value"], d["value"]) for d in distinct):
                distinct.append(f)
        srcs = {n for f in distinct for n in f["sources"]}
        if len(distinct) >= 2 and len(srcs) >= 2:
            conflicts.append({"kind": kind, "key": key,
                              "values": [{"value": f["value"], "display": f["display"], "sources": f["sources"]}
                                         for f in distinct]})
    conflict_values = {(c["kind"], c["key"], v["value"]) for c in conflicts for v in c["values"]}
    for f in facts:
        f["conflict"] = (f["kind"], f["key"], f["value"]) in conflict_values

    tiers = [g["tier"] for g in graded]
    dates = sorted(g["date"] for g in graded if g["date"])
    return {
        "query": query,
        "sources": graded,
        "facts": facts[:MAX_FACTS],
        "conflicts": conflicts[:8],
        "coverage": {
            "sources": len(graded),
            "pages_read": sum(1 for g in graded if g["page_read"]),
            "authoritative": sum(1 for t in tiers if t in ("official", "database", "academic")),
            "ugc": sum(1 for t in tiers if t == "ugc"),
            "ugc_only": bool(tiers) and all(t == "ugc" for t in tiers),
            "corroborated_facts": sum(1 for f in facts if f["domains"] >= 2),
            "latest_date": dates[-1] if dates else "",
        },
    }


def _page_date(page: dict[str, Any]) -> str:
    from .source_quality import extract_date

    return extract_date(str(page.get("title") or ""), " ".join(page.get("passages") or []))


def render_block(ev: dict[str, Any]) -> str:
    """Prompt block: graded sources, passages, cross-checked facts, conflicts, answer structure."""
    if not ev or not ev.get("sources"):
        return ""
    cov = ev.get("coverage") or {}
    lines = [
        "## Evidence digest (cross-checked by Agent Hub)",
        f"Sources {cov.get('sources', 0)} · authoritative {cov.get('authoritative', 0)} · "
        f"pages read {cov.get('pages_read', 0)} · corroborated facts {cov.get('corroborated_facts', 0)}"
        + (f" · latest {cov['latest_date']}" if cov.get("latest_date") else ""),
    ]
    if cov.get("ugc_only"):
        lines.append("⚠ All sources are forums / self-media — treat every claim as unverified.")
    for s in ev["sources"]:
        lines.append(f"- [{s['n']}] {s['tier_label']}{' · ' + s['date'] if s['date'] else ''} · {s['domain']} — {s['title'][:90]}")
        for p in s.get("passages") or []:
            lines.append(f"    > {p[:240]}")
    facts = ev.get("facts") or []
    if facts:
        lines.append("### Numbers found in the sources")
        for f in facts[:12]:
            refs = "".join(f"[{n}]" for n in f["sources"])
            agree = f"{f['domains']} independent domains" if f["domains"] >= 2 else "single source"
            flag = " · CONFLICT" if f.get("conflict") else ""
            lines.append(f"- {f['key'] or f['kind']}: {f['display']} {refs} — {agree}{flag}")
    for c in ev.get("conflicts") or []:
        alts = " vs ".join(f"{v['display']} {''.join(f'[{n}]' for n in v['sources'])}" for v in c["values"])
        lines.append(f"- ⚠ Sources disagree on “{c['key']}”: {alts} — report both values and say which is more reliable and why.")
    lines += [
        "### Answer structure for research / search tasks",
        "1. **结论摘要 / Summary** — 3–5 bullet conclusions, each with [n].",
        "2. **关键数据 / Key data** — Markdown table: 指标 | 数值 | 来源 [n] | 一致性 (多源一致 / 单一来源 / 有分歧).",
        "3. **分歧与不确定 / Disagreements & uncertainty** — conflicts above, single-source or dated numbers, gaps.",
        "4. **下一步 / Next steps** — 2–4 concrete follow-up actions.",
        "Only use numbers that appear above or in the user's material; prefer higher-tier and more recent sources.",
    ]
    return "\n".join(lines)


def compact(ev: dict[str, Any]) -> dict[str, Any]:
    """Provenance-sized copy (passages trimmed)."""
    if not ev:
        return {}
    out = dict(ev)
    out["sources"] = [
        {**{k: v for k, v in s.items() if k != "passages"}, "passages": [p[:200] for p in (s.get("passages") or [])[:2]]}
        for s in ev.get("sources") or []
    ]
    return out
