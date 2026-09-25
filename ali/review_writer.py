"""Evidence-grounded literature review writer (search → screen → write → peer review → revise → .docx).

Everything goes through Agent Hub: the configured model (``backend`` / ``models``
settings, e.g. MiniMax-M3) via ``llm_client``, the network via
``websearch._http``, reference checks via ``reviewer``, and the three
reviewers are registered Agent Hub subagents.

Grounding rules
- References come from PubMed records (E-utilities), never from the model:
  the reference list is built from the records' own metadata.
- The model cites evidence cards by id (``[R12]``); ids are renumbered to
  ``[1] … [N]`` in order of first appearance, and a card that is never cited is
  not listed.
- Each section is checked with the Hub reviewer against its evidence cards and
  rewritten once when it cites unknown ids or states untraceable numbers.
"""

from __future__ import annotations

import json
import re
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
CITE_RE = re.compile(r"\[\s*R\d+(?:\s*[,;，]\s*R?\d+)*\s*\]")
CITE_ID_RE = re.compile(r"R?(\d+)")

REVIEWERS = [
    {
        "id": "reviewer-muscle-biology",
        "label": "Reviewer 1 — muscle & myokine biology",
        "role": "research",
        "desc": ("Peer reviewer, skeletal-muscle and myokine biologist. Judge mechanistic accuracy, over-claiming "
                 "(e.g. calling a protein a myokine without secretion / circulation / endocrine-action evidence), "
                 "cell-of-origin, missing key concepts."),
    },
    {
        "id": "reviewer-ageing-metabolism",
        "label": "Reviewer 2 — ageing, metabolism & translation",
        "role": "research",
        "desc": ("Peer reviewer, ageing and metabolic-disease physician-scientist. Judge the human evidence, "
                 "biomarker claims, causality vs association, species differences, study design and clinical relevance."),
    },
    {
        "id": "reviewer-citation-integrity",
        "label": "Reviewer 3 — editor, methods & citation integrity",
        "role": "research",
        "desc": ("Handling editor. Check that every citation supports its sentence (against the evidence cards), "
                 "that critical viewpoints are sharp and defensible, structure, clarity and English."),
    },
]


# ── model access (Agent Hub settings) ─────────────────────────────────


class HubLLM:
    """The configured Agent Hub model; retries and think-tag stripping included."""

    def __init__(self, model: str = "", *, timeout: float = 300.0) -> None:
        from .providers import get_provider, pick_base_url
        from .secrets import resolve_api_key
        from .settings import load_campus_config, resolve_backend_verify_tls

        cfg = load_campus_config()
        backend = cfg.get("backend") or {}
        self.provider = str(backend.get("type") or "").strip()
        prov = get_provider(self.provider) if self.provider and self.provider != "hybrid" else None
        configured = str(backend.get("base_url") or "")
        self.base_url = pick_base_url(prov, configured) if prov else configured
        models = cfg.get("models") or {}
        self.model = (model or str(models.get("main") or backend.get("model") or "")).strip()
        self.api_key = resolve_api_key(cfg, provider=self.provider).get("key") or ""
        self.verify_tls = resolve_backend_verify_tls(cfg, {})
        self.timeout = timeout
        self.calls = 0
        self.trace: Path | None = None  # one JSON line per call (sizes, truncation, reply head) for diagnosis
        self._lock = threading.Lock()
        if not (self.base_url and self.model):
            raise RuntimeError("Agent Hub has no model configured (backend / models)")

    def __call__(self, system: str, user: str, *, max_tokens: int = 6000, temperature: float = 0.3) -> str:
        from . import llm_client
        from .streaming import strip_model_think_tags

        last: Exception | None = None
        budget = max_tokens
        for attempt in range(3):  # a stream cut mid-reply is retried (llm_client only retries before streaming)
            with self._lock:
                self.calls += 1
            meta: dict[str, Any] = {}
            try:
                text = llm_client.stream_chat(
                    self.base_url, self.api_key, model=self.model, timeout=self.timeout, verify_tls=self.verify_tls,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                    temperature=temperature, max_tokens=budget, meta=meta,
                )
            except Exception as exc:  # noqa: BLE001
                last = exc
                time.sleep(5 * (attempt + 1))
                continue
            raw = text or ""
            text = strip_model_think_tags(raw).strip()
            capped = meta.get("finish_reason") == "length"  # reasoning + answer hit the token cap
            self._log({"system": system[:60], "prompt_chars": len(user), "max_tokens": budget, "raw_chars": len(raw),
                       "chars": len(text), "truncated": bool(meta.get("truncated")), "finish": meta.get("finish_reason"),
                       "head": text[:240], "tail": text[-120:], "raw_head": raw[:240] if not text else ""})
            if text and not ((meta.get("truncated") or capped) and attempt < 2):
                return text
            if capped or not text:
                budget = min(budget * 2, 32000)
            last = RuntimeError("empty or truncated model reply")
        raise RuntimeError(f"model call failed: {last}")


    def _log(self, row: dict[str, Any]) -> None:
        if self.trace is None:
            return
        with self._lock, open(self.trace, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"t": round(time.time(), 1), **row}, ensure_ascii=False) + "\n")


def extract_json(text: str) -> Any:
    """First JSON object / array in a model reply (tolerates ```json fences and prose)."""
    s = re.sub(r"```(?:json)?", "", text or "")
    for start in [i for i, ch in enumerate(s) if ch in "{["]:  # earliest opener wins: an array of objects stays an array
        try:
            value, _ = json.JSONDecoder().raw_decode(s, start)
        except json.JSONDecodeError:
            continue
        if isinstance(value, (dict, list)):
            return value
    raise ValueError("no JSON found in model reply")


def ask_json(llm: Callable[..., str], system: str, user: str, *, expect: type = list, max_tokens: int = 8000,
             temperature: float = 0.2) -> Any:
    """A reply parsed as JSON of type ``expect``; one retry with a larger budget and a stricter instruction."""
    reply = ""
    for attempt in range(2):
        ask = user if attempt == 0 else (user + "\n\nIMPORTANT: your previous reply was not valid JSON. Reply "
                                         "with the JSON only — no prose, no Markdown, no explanation.")
        try:
            reply = llm(system, ask, max_tokens=max_tokens * (1 + attempt), temperature=temperature)
            value = extract_json(reply)
        except ValueError:
            continue
        if isinstance(value, dict) and expect is list:  # {"queries": [...]} style wrappers
            inner = [v for v in value.values() if isinstance(v, list)]
            value = inner[0] if len(inner) == 1 else value
        if isinstance(value, expect):
            return value
    raise ValueError(f"model reply is not JSON {expect.__name__}: {reply[:200]!r}")


# ── PubMed (through the Hub network layer) ────────────────────────────


def _http(url: str, timeout: float = 20.0) -> str:
    from . import websearch

    return websearch._http(url, timeout=timeout, max_timeout=timeout)


def pubmed_search(query: str, *, retmax: int = 25, http: Callable[[str], str] | None = None) -> list[str]:
    url = f"{EUTILS}/esearch.fcgi?" + urlencode({"db": "pubmed", "term": query, "retmax": retmax,
                                                  "retmode": "json", "sort": "relevance"})
    data = json.loads((http or _http)(url) or "{}")
    return list((data.get("esearchresult") or {}).get("idlist") or [])


def parse_pubmed_xml(xml_text: str) -> list[dict[str, Any]]:
    """PubMed efetch XML → records with the fields a reference and an evidence card need."""
    out: list[dict[str, Any]] = []
    root = ET.fromstring(xml_text)
    for art in root.findall(".//PubmedArticle"):
        med = art.find("MedlineCitation")
        a = med.find("Article") if med is not None else None
        if med is None or a is None:
            continue
        pmid = (med.findtext("PMID") or "").strip()
        title = "".join(a.find("ArticleTitle").itertext()).strip() if a.find("ArticleTitle") is not None else ""
        parts = []
        for ab in a.findall("Abstract/AbstractText"):
            label = ab.get("Label")
            txt = "".join(ab.itertext()).strip()
            parts.append(f"{label}: {txt}" if label else txt)
        journal = (a.findtext("Journal/ISOAbbreviation") or a.findtext("Journal/Title") or "").strip()
        year = (a.findtext("Journal/JournalIssue/PubDate/Year") or "").strip()
        if not year:
            md = a.findtext("Journal/JournalIssue/PubDate/MedlineDate") or ""
            m = re.search(r"(19|20)\d{2}", md)
            year = m.group(0) if m else ""
        volume = (a.findtext("Journal/JournalIssue/Volume") or "").strip()
        issue = (a.findtext("Journal/JournalIssue/Issue") or "").strip()
        pages = (a.findtext("Pagination/MedlinePgn") or "").strip()
        doi = ""
        for eid in a.findall("ELocationID"):
            if eid.get("EIdType") == "doi":
                doi = (eid.text or "").strip()
        if not doi:
            for aid in art.findall("PubmedData/ArticleIdList/ArticleId"):
                if aid.get("IdType") == "doi":
                    doi = (aid.text or "").strip()
        if not pages:
            for eid in a.findall("ELocationID"):
                if eid.get("EIdType") == "pii" and eid.text:
                    pages = eid.text.strip()
        authors = []
        for au in a.findall("AuthorList/Author"):
            last = au.findtext("LastName")
            if last:
                authors.append(f"{last} {au.findtext('Initials') or ''}".strip())
            elif au.findtext("CollectiveName"):
                authors.append(au.findtext("CollectiveName"))
        types = [t.text or "" for t in a.findall("PublicationTypeList/PublicationType")]
        out.append({"pmid": pmid, "title": title, "abstract": " ".join(parts), "journal": journal, "year": year,
                    "volume": volume, "issue": issue, "pages": pages, "doi": doi, "authors": authors,
                    "types": types, "review": any("Review" in t for t in types)})
    return out


def pubmed_fetch(pmids: list[str], *, http: Callable[[str], str] | None = None, batch: int = 100) -> list[dict[str, Any]]:
    recs: list[dict[str, Any]] = []
    for i in range(0, len(pmids), batch):
        chunk = pmids[i:i + batch]
        url = f"{EUTILS}/efetch.fcgi?" + urlencode({"db": "pubmed", "id": ",".join(chunk), "retmode": "xml"})
        recs.extend(parse_pubmed_xml(http(url) if http else _http(url, timeout=40.0)))
        if http is None:
            time.sleep(0.4)  # stay under the 3 requests/s E-utilities limit
    return recs


def format_reference(rec: dict[str, Any]) -> str:
    """Vancouver style from the PubMed record itself."""
    au = rec.get("authors") or []
    authors = ", ".join(au[:6]) + (", et al" if len(au) > 6 else "")
    title = (rec.get("title") or "").rstrip(".")
    loc = rec.get("year") or ""
    if rec.get("volume"):
        loc += f";{rec['volume']}"
        if rec.get("issue"):
            loc += f"({rec['issue']})"
    if rec.get("pages"):
        loc += f":{rec['pages']}"
    doi = f" doi:{rec['doi']}" if rec.get("doi") else ""
    return f"{authors}. {title}. {rec.get('journal') or ''}. {loc}.{doi} PMID: {rec.get('pmid')}".replace(" .", ".")


# ── citations ─────────────────────────────────────────────────────────


def normalize_cites(text: str) -> str:
    """[R3–R5] → [R3, R4, R5]; (R3, R7) → [R3, R7]."""
    def expand(m: re.Match) -> str:
        a, b = int(m.group(1)), int(m.group(2))
        return ", ".join(f"R{i}" for i in range(a, b + 1)) if 0 < b - a <= 15 else f"R{a}, R{b}"

    text = re.sub(r"\((\s*R\d+(?:\s*[,;，\-–—]\s*R?\d+)*\s*)\)", r"[\1]", text or "")
    return re.sub(r"\[[^\[\]]*\]", lambda m: re.sub(r"R(\d+)\s*[-–—]\s*R?(\d+)", expand, m.group(0)), text)


def cited_ids(text: str) -> list[int]:
    ids: list[int] = []
    for m in CITE_RE.finditer(normalize_cites(text)):
        ids.extend(int(x) for x in CITE_ID_RE.findall(m.group(0)))
    return ids


def renumber(texts: list[str], valid: set[int]) -> tuple[list[str], list[int]]:
    """[R12][R3, R7] → [1][2, 3] in order of first appearance; unknown ids are dropped."""
    order: list[int] = []

    def num(rid: int) -> int:
        if rid not in order:
            order.append(rid)
        return order.index(rid) + 1

    texts = [normalize_cites(t) for t in texts]
    for t in texts:
        for rid in cited_ids(t):
            if rid in valid:
                num(rid)

    def sub(m: re.Match) -> str:
        nums = sorted({num(int(x)) for x in CITE_ID_RE.findall(m.group(0)) if int(x) in valid})
        return "[" + ", ".join(str(n) for n in nums) + "]" if nums else ""

    return [re.sub(r"\s+(?=[.,;:])", "", CITE_RE.sub(sub, t)) for t in texts], order


def clean_section(text: str, heading: str = "") -> str:
    """Model prose → plain paragraphs: no Markdown headings / emphasis / bullets, no echoed heading or reference list."""
    lines = []
    for line in (text or "").splitlines():
        st = line.strip()
        if re.match(r"^#{1,6}\s", st):
            if heading and st.lstrip("#").strip().lower().lstrip("0123456789. ") == heading.lower():
                continue
            st = st.lstrip("#").strip()
            if len(st.split()) <= 12:  # a sub-heading → its own short paragraph
                lines += ["", st, ""]
                continue
        if re.match(r"^(references|bibliography)\s*:?$", st, re.I):
            break
        st = re.sub(r"^[-*•]\s+", "", st)
        lines.append(st)
    out = "\n".join(lines)
    out = re.sub(r"\*\*(.+?)\*\*", r"\1", out)
    out = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", out)
    return normalize_cites(re.sub(r"\n{3,}", "\n\n", out).strip())


def validate_citations(texts: list[str], n_refs: int) -> dict[str, Any]:
    nums: list[int] = []
    for t in texts:
        for m in re.finditer(r"\[(\d+(?:\s*,\s*\d+)*)\]", t):
            nums.extend(int(x) for x in re.findall(r"\d+", m.group(1)))
    used = set(nums)
    return {"cited": len(used), "references": n_refs, "out_of_range": sorted(n for n in used if n < 1 or n > n_refs),
            "uncited": sorted(set(range(1, n_refs + 1)) - used), "citations": len(nums)}


# ── pipeline stages ───────────────────────────────────────────────────

WRITER_SYSTEM = (
    "You are a senior scientist writing an authoritative, critical English review for a high-impact journal. "
    "Write in precise academic English. Ground every factual statement in the evidence cards you are given and "
    "cite them inline with their ids exactly as [R12] or [R3, R7]; never invent references, authors, years or "
    "numbers that are not in the cards. Where the evidence is weak, correlative, species-specific or conflicting, "
    "say so explicitly and give your own reasoned critical view. The text is the manuscript itself: never mention "
    "evidence cards, card ids in prose (write 'a secretion-defective model [R9]', not 'the R9 model'), reviewers, "
    "revisions or these instructions."
)

# manuscript prose must not talk about its own production
_META_RE = re.compile(
    r"evidence cards?|\bthe cards?\b|\bcard \[|\breviewers?\b|\bthis revision\b|\brevised (?:text|section|version)\b|"
    r"\bas requested\b|\bwe (?:have )?(?:revised|added|removed|clarified)\b|\bcitation is\b|\bis (?:fully |now )?supported by\b"
    r"|\bprevious draft\b|\bthe manuscript\b", re.I)


def prose_problems(text: str) -> list[str]:
    """Deterministic checks: card ids used as words, and text about the writing / review process."""
    problems = []
    plain = CITE_RE.sub("", normalize_cites(text))
    bare = sorted(set(re.findall(r"\bR\d+\b", plain)))
    if bare:
        problems.append(f"card ids used as words in the prose ({', '.join(bare[:6])}): name the study or model instead "
                        "and cite it in brackets")
    seen: set[str] = set()
    for m in _META_RE.finditer(plain):
        if m.group(0).lower() in seen or len(seen) >= 4:
            continue
        seen.add(m.group(0).lower())
        start = max(0, m.start() - 60)
        problems.append(f"meta text about sources / review process: \"…{plain[start:m.end() + 40].strip()}…\" — "
                        "rewrite as plain scientific prose")
    return problems


def scrub_prose(text: str) -> str:
    """Last-resort cleanup after renumbering: a remaining bare card id reads as a plain reference."""
    parts = re.split(r"(\[[^\[\]]*\])", normalize_cites(text))  # only text outside citation brackets
    return "".join(p if p.startswith("[") else re.sub(r"\b(?:the |this )?R(\d+)\b", r"ref. [R\1]", p) for p in parts)


def plan_queries(llm: HubLLM, topic: str, seeds: list[str]) -> list[str]:
    try:
        got = ask_json(llm, "You design PubMed search strategies.", (
        f"Review topic: {topic}\n\nReturn a JSON array of 10-14 distinct PubMed queries (English, PubMed syntax "
        "allowed, no wildcards) that together retrieve the primary literature and key reviews on this topic: core "
        "biology, skeletal muscle, secretion / circulation, ageing, metabolism (adipose, liver, insulin, heart), "
        "exercise, fibrosis / ECM, human cohorts / proteomics. Output only the JSON array."), expect=list, max_tokens=4000)
    except ValueError:
        got = []  # the seed queries alone still cover the topic
    queries = [str(q).strip() for q in got if isinstance(q, str) and str(q).strip()]
    return list(dict.fromkeys(seeds + queries))


def screen(llm: HubLLM, topic: str, recs: list[dict[str, Any]], *, batch: int = 12) -> dict[str, dict[str, Any]]:
    """Relevance 0-3 and a one-sentence key finding per record (from its abstract only)."""
    results: dict[str, dict[str, Any]] = {}
    failures: list[str] = []

    def run(chunk: list[dict[str, Any]]) -> None:
        cards = "\n\n".join(f"PMID {r['pmid']} | {r['title']} | {r['journal']} {r['year']}\n{(r['abstract'] or '(no abstract)')[:1600]}"
                            for r in chunk)
        try:
            rows = ask_json(llm, "You screen papers for a systematic literature review. Use only the given abstracts.", (
                f"Review topic: {topic}\n\nFor each paper return an object "
                '{"pmid": "...", "relevance": 0-3, "finding": "one factual sentence about what the paper shows '
                'regarding the topic (only from the abstract)", "model": "species / system", "section": "one of: '
                'biology, muscle, secretion, ageing, metabolism, heart, fibrosis_ecm, exercise, human, other"}. '
                "relevance 3 = directly about the topic's protein in muscle/ageing/metabolism, 2 = directly about the "
                "protein in another tissue or mechanism, 1 = context only, 0 = irrelevant. Output one JSON array.\n\n"
                + cards), expect=list, max_tokens=8000, temperature=0.1)
            for row in rows:
                if isinstance(row, dict) and str(row.get("pmid") or "") in {r["pmid"] for r in chunk}:
                    results[str(row["pmid"])] = row
        except Exception as exc:  # noqa: BLE001 — unscreened papers are simply not used
            failures.append(str(exc)[:200])

    chunks = [recs[i:i + batch] for i in range(0, len(recs), batch)]
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(run, chunks))
    if failures and not results:
        raise RuntimeError(f"screening failed for every batch: {failures[0]}")
    return results


def _rel(row: dict[str, Any] | None) -> int:
    try:
        return int(float((row or {}).get("relevance") or 0))
    except (TypeError, ValueError):
        return 0


def _card_id(x: Any) -> int:
    """Card id from 12, "12" or "R12" (0 when it is none of these)."""
    m = re.fullmatch(r"\s*\[?R?(\d+)\]?\s*", str(x))
    return int(m.group(1)) if m else 0


def evidence_cards(recs: list[dict[str, Any]], screened: dict[str, dict[str, Any]], *, limit: int = 60,
                   min_relevance: int = 2, focus: str = "", seeds: list[str] | tuple[str, ...] = (),
                   context_slots: int = 8, context_focus: str = "") -> list[dict[str, Any]]:
    """Evidence cards, best first.

    Primary cards (relevance ≥ ``min_relevance``) must mention the ``focus`` regex (the topic protein) in the title
    or abstract; seed papers and title mentions rank first.  Up to ``context_slots`` relevance-1 cards (preferably
    reviews: field definitions, the protein family) are kept for framing.
    """
    focus_re = re.compile(focus, re.I) if focus else None
    seeds = set(seeds)

    def mentions(r: dict[str, Any]) -> tuple[bool, int]:
        if not focus_re:
            return True, 0
        return bool(focus_re.search(r.get("title") or "")), len(focus_re.findall(r.get("abstract") or ""))

    def key(r: dict[str, Any]) -> tuple:
        in_title, n = mentions(r)
        return (-_rel(screened[r["pmid"]]), r["pmid"] not in seeds, not in_title, -min(n, 6), -(int(r["year"] or 0)))

    primary = [r for r in recs if _rel(screened.get(r["pmid"])) >= min_relevance
               and (r["pmid"] in seeds or not focus_re or any(mentions(r)))]
    context = [r for r in recs if _rel(screened.get(r["pmid"])) == 1 and r not in primary]
    ctx_re = re.compile(context_focus, re.I) if context_focus else None
    context.sort(key=lambda r: (not (ctx_re and ctx_re.search(r.get("title") or "")), not r.get("review"),
                                not any(mentions(r)), -(int(r["year"] or 0))))
    chosen = sorted(primary, key=key)[:max(0, limit - min(context_slots, len(context)))]
    chosen += context[:limit - len(chosen)]
    cards = []
    for i, r in enumerate(chosen, start=1):
        s = screened[r["pmid"]]
        cards.append({"id": i, "pmid": r["pmid"], "doi": r.get("doi"), "title": r["title"], "journal": r["journal"],
                      "year": r["year"], "first_author": (r.get("authors") or ["?"])[0], "review": r.get("review"),
                      "relevance": s.get("relevance"), "section": s.get("section"), "model": s.get("model"),
                      "finding": s.get("finding"), "abstract": r.get("abstract") or "", "reference": format_reference(r)})
    return cards


def card_block(cards: list[dict[str, Any]], *, abstract_chars: int = 900) -> str:
    return "\n\n".join(
        f"[R{c['id']}] {c['first_author']} et al., {c['journal']} {c['year']}{' (review)' if c.get('review') else ''} — "
        f"{c['title']}\nKey finding: {c.get('finding') or ''}\nModel: {c.get('model') or ''}\n"
        f"Abstract excerpt: {c['abstract'][:abstract_chars]}"
        for c in cards)


def make_outline(llm: HubLLM, topic: str, cards: list[dict[str, Any]]) -> dict[str, Any]:
    outline = ask_json(llm, WRITER_SYSTEM, (
        f"Topic: {topic}\n\nEvidence cards:\n{card_block(cards, abstract_chars=300)}\n\n"
        "Design the review. Return JSON: {\"title\": \"...\", \"sections\": [{\"heading\": \"...\", \"goal\": \"what the "
        "section must establish, incl. the critical angle\", \"cards\": [ids], \"words\": 600-1000}]}. 8-10 sections: "
        "Introduction; biology of the protein; expression and secretion by skeletal muscle (is it a genuine myokine?); "
        "molecular mechanisms; ageing/sarcopenia; systemic metabolism; a dedicated 'Critical perspectives and "
        "controversies' section; open questions and an experimental roadmap; conclusions. Every card should be used by "
        "at least one section. Output only JSON."), expect=dict, max_tokens=8000, temperature=0.2)
    if not isinstance(outline, dict) or not outline.get("sections"):
        raise ValueError("outline has no sections")
    return outline


def write_section(llm: HubLLM, topic: str, outline: dict[str, Any], sec: dict[str, Any], cards: list[dict[str, Any]],
                  *, check: Callable[[str, list[dict[str, Any]]], list[str]] | None = None) -> str:
    use = [c for c in cards if c["id"] in {_card_id(x) for x in sec.get("cards") or []}] or cards[:12]
    others = [c for c in cards if c not in use]
    headings = "; ".join(s.get("heading", "") for s in outline["sections"])
    prompt = (
        f"Review title: {outline.get('title') or topic}\nAll sections: {headings}\n\n"
        f"Write ONLY the section \"{sec['heading']}\" (about {sec.get('words') or 800} words, several paragraphs, no "
        f"heading line). Goal: {sec.get('goal') or ''}\n"
        "Cite the primary evidence cards below as [R<id>]. Include at least one explicitly critical assessment "
        "(limitations, alternative interpretations, what the data do NOT show). Plain paragraphs, no bullet lists, no "
        "Markdown headings, no reference list.\n\n"
        f"Primary evidence cards:\n{card_block(use)}\n\n"
        f"Other cards you may cite if relevant:\n{card_block(others, abstract_chars=0)}")
    text = clean_section(llm(WRITER_SYSTEM, prompt, max_tokens=12000), sec["heading"])
    problems = check(text, cards) if check else []
    if problems:
        text = clean_section(llm(WRITER_SYSTEM, prompt + "\n\nYour previous draft had these problems — fix them and "
                                 "return the whole section again:\n- " + "\n- ".join(problems) + "\n\nPrevious draft:\n"
                                 + text, max_tokens=12000), sec["heading"])
    return text


def section_problems(text: str, cards: list[dict[str, Any]]) -> list[str]:
    """Hub reviewer checks against the evidence cards (unknown ids, untraceable numbers, missing citations)."""
    from .reviewer import review_reply

    ids = {c["id"] for c in cards}
    problems = [f"[R{i}] is not an evidence card id" for i in sorted(set(cited_ids(text)) - ids)]
    problems += prose_problems(text)
    if len(cited_ids(text)) < 3:
        problems.append("too few citations: ground the claims in the evidence cards")
    plain = CITE_RE.sub("", text)
    sources = [{"title": c["title"], "url": f"https://pubmed.ncbi.nlm.nih.gov/{c['pmid']}/",
                "snippet": f"{c.get('finding') or ''} {c['abstract']}"} for c in cards]
    rv = review_reply(plain, sources=sources)
    for i in rv.get("issues") or []:
        if i.get("severity") == "warn" and i.get("kind") in ("untraceable_number", "unverified_reference", "malformed_doi"):
            problems.append(f"{i['kind']}: {i['text']} — not supported by any evidence card; remove it or cite the card that states it")
    return problems[:10]


def key_studies_table(llm: HubLLM, cards: list[dict[str, Any]], *, rows: int = 12) -> list[dict[str, str]]:
    primary = [c for c in cards if not c.get("review")][:rows + 6]
    try:
        got = ask_json(llm, WRITER_SYSTEM, (
        f"From these evidence cards pick the {rows} most important primary studies and return a JSON array of "
        '{"card": id, "model": "species / system", "finding": "main finding (<=25 words)", "limitation": "main '
        'limitation or caveat (<=20 words)"}. Use only the cards.\n\n' + card_block(primary, abstract_chars=500)),
        expect=list, max_tokens=6000, temperature=0.1)
    except ValueError:
        return []
    ids = {c["id"] for c in cards}
    return [r for r in got if isinstance(r, dict) and _card_id(r.get("card")) in ids][:rows]


def run_reviewers(llm: HubLLM, draft: str, cards: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Three Agent Hub subagents review the draft in parallel."""
    from . import agents

    subs = []
    for spec in REVIEWERS:
        try:
            agents.upsert_subagent(spec)
        except Exception:  # noqa: BLE001 — catalog persistence is optional here
            pass
        subs.append(agents._normalize_subagent(spec))

    def one(sub: dict[str, Any]) -> dict[str, str]:
        system = agents.subagent_system_prompt(sub)
        report = llm(system, (
            "Review this manuscript as its peer reviewer. Evidence cards (the only sources the author used) follow the "
            "manuscript; citations appear as [R<id>].\n\nReturn Markdown with: 'Summary assessment' (3-4 sentences, "
            "recommendation), 'Major comments' (numbered, each with the exact passage or section, the problem, and a "
            "concrete fix), 'Minor comments' (numbered). Be demanding and specific; check claims against the cards.\n\n"
            f"MANUSCRIPT\n{draft}\n\nEVIDENCE CARDS\n{card_block(cards, abstract_chars=500)}"), max_tokens=12000, temperature=0.4)
        return {"id": sub["id"], "label": sub["label"], "report": report}

    with ThreadPoolExecutor(max_workers=3) as pool:
        return list(pool.map(one, subs))


def revise_section(llm: HubLLM, sec_heading: str, text: str, reviews: list[dict[str, str]], cards: list[dict[str, Any]]) -> str:
    comments = "\n\n".join(f"### {r['label']}\n{r['report']}" for r in reviews)
    return llm(WRITER_SYSTEM, (
        f"Revise the section \"{sec_heading}\" to address every reviewer comment that concerns it (and the general ones). "
        "Keep the [R<id>] citation style; only cite evidence cards; keep or sharpen the critical viewpoint. Keep the "
        "length within about 20% of the current section — tighten elsewhere when adding material. Return only the "
        "revised section text: no heading, no notes, and no mention of reviewers, comments, cards or the revision."
        f"\n\nREVIEWER COMMENTS\n{comments}\n\nCURRENT SECTION\n{text}\n\n"
        f"EVIDENCE CARDS\n{card_block(cards, abstract_chars=400)}"), max_tokens=12000)


def audit_section(llm: HubLLM, heading: str, text: str, cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Citation audit: sentences whose cited cards do not support them (checked against the cards' abstracts)."""
    by_id = {c["id"]: c for c in cards}
    used = [by_id[i] for i in dict.fromkeys(cited_ids(text)) if i in by_id]
    if not used:
        return []
    got = ask_json(llm, "You are a meticulous fact-checker for a scientific journal. Use only the given abstracts.", (
        f"Section \"{heading}\" of a review cites evidence cards as [R<id>]. For every sentence with a citation, check "
        "whether the cited card(s) actually support the specific claim (finding, species, direction of effect, "
        "tissue, numbers). Return a JSON array of the problems only: {\"sentence\": \"exact sentence\", \"cards\": [ids], "
        "\"issue\": \"what is not supported or is misattributed\", \"fix\": \"corrected wording or the card that does "
        "support it\"}. Ignore sentences that are the author's own interpretation and are phrased as such. Return [] if "
        f"all citations are supported.\n\nSECTION\n{text}\n\nCITED CARDS\n{card_block(used, abstract_chars=1400)}"),
        expect=list, max_tokens=12000, temperature=0.1)
    return [g for g in got if isinstance(g, dict) and g.get("sentence")]


def apply_audit(llm: HubLLM, heading: str, text: str, issues: list[dict[str, Any]], cards: list[dict[str, Any]]) -> str:
    listing = "\n".join(f"- \"{i.get('sentence')}\" — {i.get('issue')} Fix: {i.get('fix')}" for i in issues)
    return clean_section(llm(WRITER_SYSTEM, (
        f"A fact-check of the section \"{heading}\" found citations that do not support their sentences. Correct each "
        "one (reword the claim to what the card shows, cite the right card, or drop the claim); change nothing else. "
        f"Return the full section.\n\nPROBLEMS\n{listing}\n\nSECTION\n{text}\n\nEVIDENCE CARDS\n"
        f"{card_block(cards, abstract_chars=400)}"), max_tokens=12000), heading)


def response_letter(llm: HubLLM, reviews: list[dict[str, str]], changes: str) -> str:
    comments = "\n\n".join(f"### {r['label']}\n{r['report']}" for r in reviews)
    return llm(WRITER_SYSTEM, (
        "Write a point-by-point 'Response to reviewers' in Markdown: for each reviewer and each major comment, quote the "
        "comment briefly and state what was changed (or why not). Be factual about what the revision did.\n\n"
        f"REVIEWS\n{comments}\n\nSUMMARY OF CHANGES\n{changes}"), max_tokens=8000, temperature=0.2)


def write_abstract(llm: HubLLM, title: str, body: str) -> dict[str, Any]:
    return ask_json(llm, WRITER_SYSTEM, (
        f"Write the abstract (200-250 words, one paragraph, no citations) and 5-6 keywords for this review titled "
        f"\"{title}\". Return JSON {{\"abstract\": \"...\", \"keywords\": [...]}}.\n\n{body[:30000]}"), expect=dict, max_tokens=6000)


# ── Word output ───────────────────────────────────────────────────────


def build_docx(path: Path, *, title: str, abstract: str, keywords: list[str], sections: list[tuple[str, str]],
               table: list[dict[str, str]], references: list[str], note: str = "") -> None:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(11)
    h = doc.add_heading(title, level=0)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if note:
        p = doc.add_paragraph(note)
        p.runs[0].italic = True
    doc.add_heading("Abstract", level=1)
    doc.add_paragraph(abstract)
    if keywords:
        kp = doc.add_paragraph()
        kp.add_run("Keywords: ").bold = True
        kp.add_run("; ".join(keywords))
    for i, (heading, body) in enumerate(sections, start=1):
        doc.add_heading(f"{i}. {heading}", level=1)
        for para in [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]:
            doc.add_paragraph(re.sub(r"\s*\n\s*", " ", para))
    if table:
        doc.add_heading("Table 1. Key primary studies", level=1)
        t = doc.add_table(rows=1, cols=4)
        t.style = "Light Grid Accent 1"
        for cell, head in zip(t.rows[0].cells, ("Ref.", "Model / system", "Main finding", "Limitation")):
            cell.text = head
        for row in table:
            cells = t.add_row().cells
            cells[0].text, cells[1].text = row.get("ref", ""), row.get("model", "")
            cells[2].text, cells[3].text = row.get("finding", ""), row.get("limitation", "")
    doc.add_heading("References", level=1)
    for i, ref in enumerate(references, start=1):
        doc.add_paragraph(f"[{i}] {ref}")
    doc.save(str(path))


# ── orchestration ─────────────────────────────────────────────────────


class Checkpoints:
    """Stage results under ``out_dir/checkpoints`` so a re-run resumes at the stage that failed.

    A change of run parameters (topic, limits, model) discards them.  Per-section stages save after every
    section, so one failing section does not lose the others.
    """

    def __init__(self, out_dir: Path, params: dict[str, Any], *, log: Callable[[str], None] = print) -> None:
        self.dir = out_dir / "checkpoints"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.log = log
        self._lock = threading.Lock()
        pfile = self.dir / "params.json"
        stamp = json.dumps(params, sort_keys=True, ensure_ascii=False)
        if pfile.exists() and pfile.read_text(encoding="utf-8") != stamp:
            for f in self.dir.glob("*.json"):
                f.unlink()
            log("checkpoints: parameters changed — starting fresh")
        pfile.write_text(stamp, encoding="utf-8")

    def get(self, name: str) -> Any:
        f = self.dir / f"{name}.json"
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None

    def put(self, name: str, value: Any) -> Any:
        with self._lock:
            tmp = self.dir / f".{name}.tmp"
            tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.dir / f"{name}.json")
        return value

    def stage(self, name: str, fn: Callable[[], Any]) -> Any:
        got = self.get(name)
        if got is not None:
            self.log(f"{name}: resumed from checkpoint")
            return got
        return self.put(name, fn())

    def per_item(self, name: str, n: int, fn: Callable[[int], str], *, workers: int = 3) -> list[str]:
        """``fn(i)`` for every item without a saved result; raises after the stage if any item failed."""
        done = self.get(name) or []
        items: list[str] = (list(done) + [""] * n)[:n]
        todo = [i for i in range(n) if not items[i]]
        if len(todo) < n:
            self.log(f"{name}: {n - len(todo)}/{n} resumed from checkpoint")
        errors: list[str] = []

        def one(i: int) -> None:
            try:
                items[i] = fn(i)
            except Exception as exc:  # noqa: BLE001 — recorded, the stage fails after the others finish
                errors.append(f"item {i + 1}: {type(exc).__name__}: {exc}")
                return
            self.put(name, items)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(one, todo))
        if errors:
            raise RuntimeError(f"{name}: {len(errors)} of {n} failed — " + "; ".join(errors)[:1500])
        return items


def run(topic: str, out_dir: Path, *, seed_queries: list[str], seed_pmids: list[str] | None = None, focus: str = "",
        context_focus: str = "", min_refs: int = 40, max_cards: int = 60, retmax: int = 25, max_queries: int = 0, max_sections: int = 0,
        log: Callable[[str], None] = print, llm: HubLLM | None = None) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    llm = llm or HubLLM()
    if isinstance(llm, HubLLM):
        llm.trace = out_dir / "llm_trace.jsonl"
    log(f"model: {llm.provider}/{llm.model} via {llm.base_url}")
    ck = Checkpoints(out_dir, {"topic": topic, "seed_queries": seed_queries, "seed_pmids": seed_pmids or [],
                               "focus": focus, "context_focus": context_focus, "min_refs": min_refs, "max_cards": max_cards, "retmax": retmax,
                               "max_queries": max_queries, "max_sections": max_sections,
                               "model": f"{llm.provider}/{llm.model}"}, log=log)

    queries = ck.stage("queries", lambda: plan_queries(llm, topic, seed_queries))
    if max_queries:
        queries = queries[:max_queries]
    log(f"queries: {len(queries)}")

    def search() -> list[dict[str, Any]]:
        pmids: list[str] = list(dict.fromkeys(seed_pmids or []))  # known key papers are always screened
        for q in queries:
            try:
                got = pubmed_search(q, retmax=retmax)
            except Exception as exc:  # noqa: BLE001
                log(f"  search failed ({q[:60]}): {exc}")
                continue
            pmids.extend(p for p in got if p not in pmids)
            log(f"  {len(got):3d} ← {q[:90]}")
            time.sleep(0.4)
        return [r for r in pubmed_fetch(pmids) if r.get("abstract")]

    recs = ck.stage("records", search)
    log(f"records with abstracts: {len(recs)}")

    def do_screen() -> dict[str, Any]:
        screened = screen(llm, topic, recs)
        for pid in seed_pmids or []:  # a key paper the screen found at least context-relevant stays in
            row = screened.get(pid)
            if row and _rel(row) >= 1:
                row["relevance"] = max(2, _rel(row))
        return screened

    screened = ck.stage("screened", do_screen)
    log(f"screened: {len(screened)} ({sum(1 for r in screened.values() if _rel(r) >= 2)} relevant)")
    cards = evidence_cards(recs, screened, limit=max_cards, focus=focus, seeds=seed_pmids or (),
                           context_focus=context_focus)
    if len(cards) < min_refs:
        cards = evidence_cards(recs, screened, limit=max_cards, min_relevance=1, focus=focus, seeds=seed_pmids or (),
                               context_focus=context_focus)
    log(f"evidence cards: {len(cards)}")
    (out_dir / "evidence_cards.json").write_text(json.dumps(cards, ensure_ascii=False, indent=1), encoding="utf-8")

    outline = ck.stage("outline", lambda: make_outline(llm, topic, cards))
    title = str(outline.get("title") or topic)
    sections = [s for s in outline["sections"] if isinstance(s, dict) and s.get("heading")]
    if max_sections:
        sections = sections[:max_sections]
    log(f"outline: {title} — {len(sections)} sections")

    def draft(i: int) -> str:
        text = write_section(llm, topic, outline, sections[i], cards, check=section_problems)
        log(f"  drafted {i + 1}/{len(sections)} {sections[i]['heading'][:60]} ({len(text.split())} words, "
            f"{len(set(cited_ids(text)))} cards)")
        return text

    drafts = ck.per_item("drafts", len(sections), draft)
    draft_md = "\n\n".join(f"## {s['heading']}\n\n{t}" for s, t in zip(sections, drafts))
    (out_dir / "draft_v1.md").write_text(f"# {title}\n\n{draft_md}", encoding="utf-8")

    reviews = ck.stage("reviews", lambda: run_reviewers(llm, draft_md, cards))
    (out_dir / "reviewer_reports.md").write_text(
        "\n\n".join(f"# {r['label']}\n\n{r['report']}" for r in reviews), encoding="utf-8")
    log("reviews: " + ", ".join(f"{r['id']} ({len(r['report'].split())} words)" for r in reviews))

    def revise(i: int) -> str:
        text = clean_section(revise_section(llm, sections[i]["heading"], drafts[i], reviews, cards), sections[i]["heading"])
        problems = section_problems(text, cards)
        if problems:
            text = clean_section(llm(WRITER_SYSTEM, "Fix these problems in the section and return it in full:\n- "
                                     + "\n- ".join(problems) + f"\n\nSECTION\n{text}\n\nEVIDENCE CARDS\n"
                                     + card_block(cards, abstract_chars=400), max_tokens=12000), sections[i]["heading"])
        log(f"  revised {i + 1}/{len(sections)} ({len(text.split())} words, {len(set(cited_ids(text)))} cards)")
        return text

    revised = ck.per_item("revised", len(sections), revise)

    def integrate() -> list[str]:  # enough distinct references? ask sections to use unused cards where they fit
        out = list(revised)
        valid = {c["id"] for c in cards}
        used = {i for t in out for i in cited_ids(t) if i in valid}
        if len(used) >= min_refs:
            return out
        unused = [c for c in cards if c["id"] not in used]
        log(f"only {len(used)} distinct references cited — integrating {len(unused)} more cards")
        for i, sec in enumerate(sections):
            fit = [c for c in unused if c.get("section") and c["section"].lower() in sec["heading"].lower()] or unused[:6]
            if not fit:
                continue
            out[i] = clean_section(llm(WRITER_SYSTEM, (
                "Integrate the additional evidence cards below where they genuinely strengthen or qualify the argument "
                "(cite as [R<id>]); do not pad. Return the full section.\n\nSECTION\n" + out[i]
                + "\n\nADDITIONAL CARDS\n" + card_block(fit[:8], abstract_chars=500)), max_tokens=12000), sec["heading"])
            used = {x for t in out for x in cited_ids(t) if x in valid}
            unused = [c for c in cards if c["id"] not in used]
            if len(used) >= min_refs or not unused:
                break
        return out

    revised = ck.stage("integrated", integrate)
    audit_log: list[dict[str, Any]] = []

    def audit(i: int) -> str:
        heading = sections[i]["heading"]
        issues = audit_section(llm, heading, revised[i], cards)
        text = apply_audit(llm, heading, revised[i], issues, cards) if issues else revised[i]
        if prose_problems(text):
            text = clean_section(llm(WRITER_SYSTEM, "Fix these problems in the section and return it in full:\n- "
                                     + "\n- ".join(prose_problems(text)) + f"\n\nSECTION\n{text}", max_tokens=12000),
                                 heading)
        audit_log.append({"section": heading, "issues": issues})
        log(f"  audited {i + 1}/{len(sections)}: {len(issues)} unsupported citation(s) corrected")
        return text

    revised = ck.per_item("audited", len(sections), audit)
    if audit_log:
        (out_dir / "citation_audit.json").write_text(json.dumps(audit_log, ensure_ascii=False, indent=1), encoding="utf-8")
    valid = {c["id"] for c in cards}
    table_rows = ck.stage("table", lambda: key_studies_table(llm, cards))
    table_texts = [r.get("finding", "") for r in table_rows]
    body_texts = [scrub_prose(t) for t in revised] + [f"[R{_card_id(r['card'])}]" for r in table_rows]
    numbered, order = renumber(body_texts, valid)
    sections_final = [(s["heading"], t) for s, t in zip(sections, numbered[:len(sections)])]
    by_id = {c["id"]: c for c in cards}
    references = [by_id[i]["reference"] for i in order]
    table_final = [{"ref": numbered[len(sections) + k], "model": r.get("model", ""), "finding": table_texts[k],
                    "limitation": r.get("limitation", "")} for k, r in enumerate(table_rows)]
    check = validate_citations([t for _, t in sections_final] + [r["ref"] for r in table_final], len(references))
    log(f"citations: {check}")

    body_plain = "\n\n".join(f"{h}\n{t}" for h, t in sections_final)
    meta = ck.stage("abstract", lambda: write_abstract(llm, title, body_plain))
    changes = "\n".join(f"- {s['heading']}: revised against the reviews" for s in sections)
    letter = ck.stage("response", lambda: response_letter(llm, reviews, changes))
    (out_dir / "response_to_reviewers.md").write_text(letter, encoding="utf-8")
    final_md = f"# {title}\n\n## Abstract\n\n{meta.get('abstract', '')}\n\n" + "\n\n".join(
        f"## {i}. {h}\n\n{t}" for i, (h, t) in enumerate(sections_final, start=1)) + "\n\n## References\n\n" + "\n".join(
        f"[{i}] {r}" for i, r in enumerate(references, start=1))
    (out_dir / "review_final.md").write_text(final_md, encoding="utf-8")
    build_docx(out_dir / "review.docx", title=title, abstract=str(meta.get("abstract") or ""),
               keywords=[str(k) for k in meta.get("keywords") or []], sections=sections_final, table=table_final,
               references=references,
               note=f"Drafted with Agent Hub ({llm.provider}/{llm.model}); references retrieved from PubMed; "
                    "peer-reviewed by three Agent Hub reviewer subagents and revised.")
    summary = {"title": title, "model": f"{llm.provider}/{llm.model}", "llm_calls": llm.calls, "queries": len(queries),
               "records": len(recs), "cards": len(cards), "sections": len(sections), "references": len(references),
               "citation_check": check, "words": sum(len(t.split()) for _, t in sections_final)}
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary
