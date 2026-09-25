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

from .reviewer import _CLAIM_PATTERNS, CONC_UNIT, normalize_number, normalize_value
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
_CONFLICT_KINDS = ("percent", "statistic", "concentration")
_REL_TOL = 0.05
# Concentrations vary between cohorts and conditions; only a ≥5× gap is a disagreement.
_CONC_RATIO = 5.0
MAX_FACTS = 24

_CONC_RE = re.compile(r"^(" + CONC_UNIT + r")")
_MASS = {"pg": 1e-3, "ng": 1.0, "µg": 1e3, "μg": 1e3, "ug": 1e3, "mg": 1e6, "g": 1e9}
_VOL = {"l": 1e-3, "dl": 1e-1, "ml": 1.0, "µl": 1e3, "μl": 1e3}
_MOLAR = {"fM": 1e-6, "pM": 1e-3, "nM": 1.0, "μM": 1e3, "µM": 1e3, "uM": 1e3, "mM": 1e6}
# Sample matrices: a plasma level and a CSF level are different quantities.
# Plasma / serum / "circulating" levels are compared as one blood matrix (the ≥5× rule absorbs their gap).
_MATRIX = (
    ("csf", ("cerebrospinal", "csf", "脑脊液")),
    ("blood", ("plasma", "血浆", "serum", "血清", "blood", "血液", "circulat", "循环")),
    ("urine", ("urine", "尿")), ("saliva", ("saliva", "唾液")), ("tissue", ("tissue", "组织")),
)
# Assay / method names describe how a number was measured, never what was measured.
_METHOD_WORDS = frozenset(
    "elisa assay assays kit kits mass spectrometry ms lc-ms ms/ms western blot blotting pcr qpcr rt-qpcr "
    "immunoassay antibody antibodies sequencing rna-seq microarray flow cytometry facs hplc".split()
)


def _conc(display: str, value: str) -> tuple[str, float] | None:
    """(family, amount in ng/mL or nM) for a concentration; None for other units."""
    unit = re.sub(r"^[\d.,\s\-–—~～至到∼约]+", "", display).strip()
    try:
        nums = [float(x) for x in value.split("-")]
    except ValueError:
        return None
    amount = (nums[0] * nums[-1]) ** 0.5 if len(nums) == 2 and min(nums) > 0 else nums[-1]
    if unit in _MOLAR:
        return "molar", amount * _MOLAR[unit]
    m = _CONC_RE.match(unit)
    if not m:
        return None
    mass, _, vol = re.sub(r"\s+", "", m.group(1)).lower().partition("/")
    f_vol = _VOL.get(vol)
    if f_vol is None:
        return None
    if mass in ("iu", "u"):
        return "activity", amount / f_vol
    f_mass = _MASS.get(mass)
    if f_mass is None:
        return None
    return "mass", amount * f_mass / f_vol


def _context_key(context: str, subjects: list[str]) -> str:
    """'<analyte>@<matrix>' from the sentence (and the one before it)."""
    low = context.lower()
    analyte = next((t for t in subjects if t.lower() in low), "")
    if analyte and not analyte.isascii():
        # "鸢尾素（irisin）": a Chinese name stands for the question's English analyte.
        analyte = next((t for t in subjects if t.isascii()), analyte)
    matrix = next((name for name, words in _MATRIX if any(w in low for w in words)), "")
    return f"{analyte.lower()}@{matrix}" if analyte else ""


def subject_terms(query: str) -> list[str]:
    """Topic words of the question used to tie a number to what it measures."""
    stop = _KEY_STOP_EN | {"what", "which", "why", "how", "does", "level", "levels", "concentration", "human",
                           "plasma", "serum", "method", "methods", "measure", "measured", "different", "results"}
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", query or "")
             if w.lower() not in stop and w.lower() not in _METHOD_WORDS]
    zh_split = "|".join(sorted({w for _, ws in _MATRIX for w in ws if not w.isascii()} | set(_ZH_FUNCTION), key=len, reverse=True))
    for run in re.findall(r"[一-鿿]+", query or ""):
        words += [w for w in re.split(zh_split, run) if len(w) >= 2]
    return list(dict.fromkeys(words))[:8]


_ZH_FUNCTION = ("为什么", "是多少", "多少", "浓度", "水平", "含量", "不同", "方法", "结果", "一致", "测量", "检测",
                "质谱", "试剂盒", "抗体", "差很多", "差别", "差异", "比较", "对比",
                "什么", "如何", "怎么", "哪些", "的", "中", "是", "在", "和", "与", "及", "人", "了", "吗", "呢")


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
        if "-" in a or "-" in b:  # ranges: close when they overlap
            try:
                (a1, a2), (b1, b2) = [([float(p) for p in v.split("-")] * 2)[:2] if "-" not in v
                                      else [float(p) for p in v.split("-")] for v in (a, b)]
                return a1 <= b2 and b1 <= a2
            except ValueError:
                return a == b
        return a == b
    if x == y:
        return True
    return abs(x - y) / max(abs(x), abs(y), 1e-9) <= _REL_TOL


def extract_facts(text: str, subjects: list[str] | None = None) -> list[dict[str, Any]]:
    """Numeric facts ``{kind, key, value, display}`` stated in ``text`` (one per span).

    Concentrations become ``kind="concentration"`` with ``amount`` in a common
    unit (ng/mL, nM) and ``key`` = ``analyte@matrix`` from ``subjects``.
    """
    out: list[dict[str, Any]] = []
    prev = ""
    for sent in _SENT_SPLIT.split(text or ""):
        context, prev = (prev + " " + (sent or "")), (sent or "")
        if not sent or not re.search(r"\d", sent):
            continue
        spans: list[tuple[int, int]] = []
        for kind, pat, _sev in _CLAIM_PATTERNS:
            for m in pat.finditer(sent):
                a, b = m.start(1), m.end(1)
                if any(x < b and a < y for x, y in spans):
                    continue
                raw = m.group(1)
                value = normalize_number(re.split(r"\s*[×x*eE]", raw)[0]) if kind == "p_value" else normalize_value(raw)
                if kind == "quantity" and re.fullmatch(r"(?:19|20)\d{2}", value):
                    continue
                spans.append((a, b))
                conc = _conc(m.group(0).strip(), value) if kind == "quantity" else None
                if conc:
                    out.append({"kind": "concentration", "key": _context_key(context, subjects or []),
                                "value": value, "display": m.group(0).strip()[:40],
                                "family": conc[0], "amount": conc[1]})
                    continue
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
    extra: dict[tuple[str, str, str], dict[str, Any]] = {}
    subjects = subject_terms(query)
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
        for f in extract_facts(blob, subjects):
            k = (f["kind"], f["key"], f["value"])
            occ.setdefault(k, {})[n] = domain
            display.setdefault(k, f["display"])
            if f["kind"] == "concentration":
                extra.setdefault(k, {"family": f["family"], "amount": f["amount"]})

    facts: list[dict[str, Any]] = []
    for (kind, key, value), by_n in occ.items():
        domains = sorted({d for d in by_n.values() if d})
        facts.append({
            "kind": kind, "key": key, "value": value, "display": display[(kind, key, value)],
            "sources": sorted(by_n), "domains": len(domains) or len(by_n),
            **extra.get((kind, key, value), {}),
        })
    facts.sort(key=lambda f: (-f["domains"], -len(f["sources"]), f["key"], f["value"]))

    # conflicts: same kind+key, values that are not close, stated by different sources
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for f in facts:
        if f["key"] and f["kind"] in _CONFLICT_KINDS:
            gkey = f["key"] + ("|" + f["family"] if f["kind"] == "concentration" else "")
            groups.setdefault((f["kind"], gkey), []).append(f)
    conflicts: list[dict[str, Any]] = []
    for (kind, gkey), fs in groups.items():
        key = gkey.split("|", 1)[0]
        distinct: list[dict[str, Any]] = []
        for f in fs:
            if kind == "concentration":
                close = any(max(f["amount"], d["amount"]) / max(min(f["amount"], d["amount"]), 1e-12) < _CONC_RATIO
                            for d in distinct)
            else:
                close = any(_values_close(f["value"], d["value"]) for d in distinct)
            if not close:
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
