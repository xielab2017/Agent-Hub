"""Scientific database connectors (modelled on Claude Science's curated connectors).

Public, read-only, key-free REST APIs, each wrapped as a search engine with the
same contract as ``search_extensions`` engines::

    fn(query, *, limit=5, timeout=4.0) -> {"ok", "results": [{title, snippet, url, source}],
                                           "engine", "errors"}

``detect_entities`` spots identifiers (UniProt / PDB / Ensembl / ChEMBL / NCT /
rsID / GEO / DOI / PMID / gene symbols) and domain keywords; ``route`` turns
that into the connectors worth asking, honouring the per-connector switches in
``cfg["science"]["connectors"]`` and ``data_policy=restricted`` (no external
calls at all).  ``search_science`` fans the chosen connectors out in parallel.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, wait
from typing import Any, Callable
from urllib.parse import quote, urlencode

from . import search_extensions as se

_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# ── entity & keyword detection ────────────────────────────────────────

_ID_PATTERNS: dict[str, re.Pattern] = {
    "uniprot": re.compile(r"\b(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})\b"),
    "ensembl": re.compile(r"\bENS[A-Z]*[GTP]\d{11}\b"),
    "chembl": re.compile(r"\bCHEMBL\d+\b", re.I),
    "nct": re.compile(r"\bNCT\d{8}\b", re.I),
    "rsid": re.compile(r"\brs\d{3,}\b"),
    "geo": re.compile(r"\bG(?:SE|DS|SM|PL)\d{2,}\b"),
    "doi": re.compile(r"\b10\.\d{4,9}/[^\s\"<>，。；、)\]]+"),
    "pmid": re.compile(r"\bPMID[:：\s]*(\d{4,9})\b", re.I),
    "pdb": re.compile(r"\b[1-9][A-Za-z0-9]{3}\b"),
}

_KEYWORDS: dict[str, tuple[str, ...]] = {
    "protein": ("蛋白", "protein", "uniprot", "酶活", "enzyme", "受体", "receptor", "抗体", "antibody"),
    "gene": ("基因", "gene", "转录本", "transcript", "ensembl", "外显子", "exon", "启动子", "promoter"),
    "structure": ("蛋白结构", "晶体结构", "三维结构", "结构生物", "冷冻电镜", "pdb", "protein structure",
                  "crystal structure", "cryo-em", "alphafold"),
    "compound": ("化合物", "compound", "药物", "drug", "小分子", "small molecule", "抑制剂", "inhibitor", "chembl", "ic50"),
    "trial": ("临床试验", "clinical trial", "临床研究", "随机对照", "clinicaltrials"),
    "dataset": ("表达谱", "expression profile", "geo", "测序数据", "rna-seq", "单细胞", "single-cell", "scrna-seq"),
    "variant": ("变异", "variant", "突变", "mutation", "snp", "clinvar", "致病", "pathogenic", "hgvs"),
    "pathway": ("通路", "pathway", "reactome", "信号转导", "代谢途径"),
}

# Upper-case tokens that look like gene symbols but are not.
_NOT_GENES = frozenset(
    "DNA RNA MRNA CDNA PCR QPCR API AI LLM GPT USA UK EU PDF CSV JSON HTML HTTP URL ID IDS OK FAQ "
    "WHO FDA NIH NCBI EBI PDB GEO GSE RCT SNP HGVS IC50 EC50 KD PH UV IR NMR MS LC GC CRISPR CAS9 "
    "ATP ADP GTP NADH SD SEM CI OR HR RR NA NS FDR BMI HIV COVID COVID19 SARS COV2 PHD MD CEO IT PC "
    "PCA UMAP TSNE GWAS EQTL QC NGS WGS WES ATAC CHIP ELISA FACS WB KO WT OE CPU GPU HPC SSH SQL XML "
    "YAML CSS SVG PNG JPG TSV XLSX DOCX PPT GTF GFF BAM SAM VCF FASTA FASTQ BED MAF TPM FPKM RPKM "
    "LOG2FC AUC ROC ANOVA SVM MCP UI UX PR CI CD19X AND NOT THE FOR WITH FROM".split()
)
# Product / tech tokens with digits that are not genes (GPT4, RTX4090, USB3, IPv6, M3 …).
_TECH_RE = re.compile(
    r"(?:GPT|RTX|GTX|RX|USB|HDMI|MP|H26|IOS|WIN|PS|XBOX|IPV|HTTP|TLS|UTF|ISO|PYTHON|PY|ES|CSS|HTML|IE|"
    r"X86|ARM|AMD|DDR|PCIE|NVME|CUDA|QWEN|GLM|LLAMA|YOLO|K8S|EC|S|M|A|V|R|C|G|T|SM|LTE|WIFI|SSD|CPU|GPU|"
    r"TB|GB|MB|KB|MHZ|GHZ|ISBN|IP|OS)\d{1,4}(?:[A-Z]{0,2})"
)
_GENE_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,9}(?:-[A-Z0-9]{1,4})?\b")
_BIO_CONTEXT = sum(_KEYWORDS.values(), ()) + ("表达", "expression", "信号", "肿瘤", "tumor", "cancer", "癌", "knockout", "敲除")


def _kw_hit(low: str, kw: str) -> bool:
    # English keywords need word boundaries ("gene" must not match "general").
    if kw.isascii():
        return re.search(r"(?<![a-z0-9])" + re.escape(kw) + r"(?:s|es)?(?![a-z0-9])", low) is not None
    return kw in low


def _has_kw(low: str, kind: str) -> bool:
    return any(_kw_hit(low, k) for k in _KEYWORDS[kind])


def detect_entities(text: str) -> dict[str, Any]:
    """Return ``{"ids": {kind: [..]}, "genes": [..], "topics": [..]}``."""
    raw = text or ""
    low = raw.lower()
    ids: dict[str, list[str]] = {}
    for kind, pat in _ID_PATTERNS.items():
        if kind == "pdb":
            continue
        found = pat.findall(raw)
        if found:
            ids[kind] = list(dict.fromkeys(found))[:5]
    # PDB IDs are 4 chars and collide with years / words: require a PDB/structure cue
    # and at least one letter in the ID.
    if _has_kw(low, "structure"):
        pdb = [m for m in _ID_PATTERNS["pdb"].findall(raw) if re.search(r"[A-Za-z]", m) and not m.isalpha()]
        if pdb:
            ids["pdb"] = list(dict.fromkeys(x.upper() for x in pdb))[:5]
    taken = {v.upper() for vals in ids.values() for v in vals}
    genes: list[str] = []
    bio = any(_kw_hit(low, k) for k in _BIO_CONTEXT)
    for tok in _GENE_RE.findall(raw):
        up = tok.upper()
        if up in _NOT_GENES or up in taken:
            continue
        if re.fullmatch(r"[A-Z]\d+[A-Z*]", tok):  # protein change (R248Q), not a symbol
            continue
        if _TECH_RE.fullmatch(up) and not bio:  # GPT4 / RTX4090 / USB3 outside a bio question
            continue
        has_digit = bool(re.search(r"\d", tok))
        # TP53 / BRCA1 / IL6 qualify alone; all-letter symbols (KRAS, EGFR) need bio context.
        if (has_digit and not tok[1:].isdigit()) or (bio and len(tok) >= 3):
            genes.append(tok)
    topics = [k for k in _KEYWORDS if _has_kw(low, k)]
    return {"ids": ids, "genes": list(dict.fromkeys(genes))[:5], "topics": topics}


def _english_terms(text: str) -> str:
    """Strip CJK and punctuation so English-only APIs get a usable query."""
    toks = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-+.:/]*", text or "")
    stop = {"the", "and", "for", "with", "of", "in", "on", "to", "a", "an", "is", "are", "what", "how"}
    return " ".join(t for t in toks if t.lower() not in stop)[:200]


# ── connectors ────────────────────────────────────────────────────────


def _get_json(url: str, timeout: float) -> Any:
    return json.loads(se._fetch(url, timeout=timeout, headers={"Accept": "application/json"}))


def _pack(engine: str, query: str, items: list[dict[str, Any]], errors: list[str], limit: int) -> dict[str, Any]:
    return {"ok": bool(items), "query": query, "results": items[:limit], "errors": errors[:2], "engine": engine}


def search_uniprot(query: str, *, limit: int = 5, timeout: float = 4.0) -> dict[str, Any]:
    ent = detect_entities(query)
    if ent["ids"].get("uniprot"):
        q = " OR ".join(f"accession:{a}" for a in ent["ids"]["uniprot"])
    elif ent["genes"]:
        q = "(" + " OR ".join(f"gene_exact:{g}" for g in ent["genes"]) + ") AND reviewed:true"
    else:
        q = _english_terms(query) or query
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        data = _get_json(
            "https://rest.uniprot.org/uniprotkb/search?"
            + urlencode({"query": q, "size": min(limit, 10), "format": "json",
                         "fields": "accession,id,protein_name,gene_names,organism_name,cc_function,length"}),
            timeout,
        )
        for r in data.get("results") or []:
            acc = r.get("primaryAccession") or ""
            pd = r.get("proteinDescription") or {}
            name = (((pd.get("recommendedName") or {}).get("fullName") or {}).get("value")
                    or (((pd.get("submissionNames") or [{}])[0].get("fullName") or {}).get("value"))
                    or r.get("uniProtkbId") or acc)
            genes = ", ".join(((g.get("geneName") or {}).get("value") or "") for g in (r.get("genes") or [])[:3])
            org = (r.get("organism") or {}).get("scientificName") or ""
            func = ""
            for c in r.get("comments") or []:
                if c.get("commentType") == "FUNCTION":
                    func = " ".join(t.get("value", "") for t in c.get("texts") or [])
                    break
            length = (r.get("sequence") or {}).get("length")
            snippet = " · ".join(x for x in (acc, genes, org, f"{length} aa" if length else "", func[:260]) if x)
            items.append(se._result(f"{name} ({acc})", snippet, f"https://www.uniprot.org/uniprotkb/{acc}/entry", "uniprot"))
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
    return _pack("uniprot", q, items, errors, limit)


def search_pdb(query: str, *, limit: int = 5, timeout: float = 4.0) -> dict[str, Any]:
    ent = detect_entities(query)
    ids = list(ent["ids"].get("pdb") or [])
    errors: list[str] = []
    q = ", ".join(ids) or _english_terms(query) or query
    try:
        if not ids:
            body = {
                "query": {"type": "terminal", "service": "full_text", "parameters": {"value": q}},
                "return_type": "entry",
                "request_options": {"paginate": {"start": 0, "rows": min(limit, 10)}},
            }
            data = _get_json("https://search.rcsb.org/rcsbsearch/v2/query?json=" + quote(json.dumps(body)), timeout)
            ids = [str(r.get("identifier") or "") for r in data.get("result_set") or [] if r.get("identifier")]
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
    items: list[dict[str, Any]] = []
    for pid in ids[:limit]:
        # Only entries we actually retrieved count as sources (no placeholder hits).
        try:
            e = _get_json(f"https://data.rcsb.org/rest/v1/core/entry/{quote(pid)}", timeout)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{pid}: {exc}")
            continue
        title = ((e.get("struct") or {}).get("title") or pid)
        info = e.get("rcsb_entry_info") or {}
        res = info.get("resolution_combined") or []
        method = info.get("experimental_method") or ""
        released = ((e.get("rcsb_accession_info") or {}).get("initial_release_date") or "")[:10]
        snippet = " · ".join(x for x in (pid, method, f"{res[0]} Å" if res else "", released) if x)
        items.append(se._result(f"{title} ({pid})", snippet or pid, f"https://www.rcsb.org/structure/{pid}", "pdb"))
    return _pack("pdb", q, items, errors, limit)


def search_ensembl(query: str, *, limit: int = 5, timeout: float = 4.0) -> dict[str, Any]:
    ent = detect_entities(query)
    targets = [("id", x) for x in ent["ids"].get("ensembl") or []] + [("symbol", g) for g in ent["genes"]]
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    for kind, val in targets[:limit]:
        path = f"lookup/id/{quote(val)}" if kind == "id" else f"lookup/symbol/homo_sapiens/{quote(val)}"
        try:
            g = _get_json(f"https://rest.ensembl.org/{path}?content-type=application/json", timeout)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{val}: {exc}")
            continue
        gid = g.get("id") or val
        loc = ""
        if g.get("seq_region_name") and g.get("start"):
            strand = "+" if g.get("strand") == 1 else "-"
            loc = f"chr{g['seq_region_name']}:{g['start']}-{g.get('end')} ({strand}) {g.get('assembly_name') or ''}".strip()
        desc = re.sub(r"\s*\[Source:.*?\]", "", str(g.get("description") or ""))
        snippet = " · ".join(x for x in (gid, g.get("biotype") or "", loc, desc) if x)
        items.append(se._result(
            f"{g.get('display_name') or val} ({gid})", snippet,
            f"https://www.ensembl.org/Homo_sapiens/Gene/Summary?g={gid}", "ensembl",
        ))
    return _pack("ensembl", ", ".join(v for _, v in targets), items, errors, limit)


def _chembl_item(m: dict[str, Any]) -> dict[str, Any]:
    cid = m.get("molecule_chembl_id") or ""
    props = m.get("molecule_properties") or {}
    phase = m.get("max_phase")
    snippet = " · ".join(str(x) for x in (
        cid, m.get("molecule_type") or "",
        f"max phase {phase}" if phase not in (None, "") else "",
        props.get("full_molformula") or "", f"MW {props['full_mwt']}" if props.get("full_mwt") else "",
    ) if x)
    return se._result(f"{m.get('pref_name') or cid} ({cid})", snippet,
                      f"https://www.ebi.ac.uk/chembl/compound_report_card/{cid}/", "chembl")


def search_chembl(query: str, *, limit: int = 5, timeout: float = 4.0) -> dict[str, Any]:
    ent = detect_entities(query)
    ids = [x.upper() for x in ent["ids"].get("chembl") or []]
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    q = ", ".join(ids) or _english_terms(query) or query
    try:
        if ids:
            for cid in ids[:limit]:
                items.append(_chembl_item(_get_json(f"https://www.ebi.ac.uk/chembl/api/data/molecule/{cid}.json", timeout)))
        else:
            data = _get_json(
                "https://www.ebi.ac.uk/chembl/api/data/molecule/search.json?" + urlencode({"q": q, "limit": min(limit, 10)}),
                timeout,
            )
            items = [_chembl_item(m) for m in data.get("molecules") or []]
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
    return _pack("chembl", q, items, errors, limit)


def search_clinicaltrials(query: str, *, limit: int = 5, timeout: float = 4.0) -> dict[str, Any]:
    ent = detect_entities(query)
    ids = [x.upper() for x in ent["ids"].get("nct") or []]
    q = " OR ".join(ids) or _english_terms(query) or query
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        data = _get_json(
            "https://clinicaltrials.gov/api/v2/studies?" + urlencode({"query.term": q, "pageSize": min(limit, 10), "format": "json"}),
            timeout,
        )
        for st in data.get("studies") or []:
            ps = st.get("protocolSection") or {}
            ident = ps.get("identificationModule") or {}
            nct = ident.get("nctId") or ""
            status = (ps.get("statusModule") or {}).get("overallStatus") or ""
            phases = "/".join((ps.get("designModule") or {}).get("phases") or [])
            conds = ", ".join(((ps.get("conditionsModule") or {}).get("conditions") or [])[:3])
            snippet = " · ".join(x for x in (nct, status, phases, conds) if x)
            items.append(se._result(ident.get("briefTitle") or nct, snippet, f"https://clinicaltrials.gov/study/{nct}", "clinicaltrials"))
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
    return _pack("clinicaltrials", q, items, errors, limit)


def _eutils_summaries(db: str, term: str, limit: int, timeout: float) -> list[tuple[str, dict[str, Any]]]:
    es = _get_json(f"{_EUTILS}/esearch.fcgi?" + urlencode({"db": db, "term": term, "retmax": min(limit, 10), "retmode": "json"}), timeout)
    ids = (es.get("esearchresult") or {}).get("idlist") or []
    if not ids:
        return []
    su = _get_json(f"{_EUTILS}/esummary.fcgi?" + urlencode({"db": db, "id": ",".join(ids), "retmode": "json"}), timeout)
    result = su.get("result") or {}
    return [(str(uid), result.get(str(uid)) or {}) for uid in (result.get("uids") or ids)]


def search_geo(query: str, *, limit: int = 5, timeout: float = 4.0) -> dict[str, Any]:
    ent = detect_entities(query)
    ids = ent["ids"].get("geo") or []
    q = " OR ".join(f"{x}[ACCN]" for x in ids) or " ".join(ent["genes"]) or _english_terms(query) or query
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        for _uid, rec in _eutils_summaries("gds", q, limit, timeout):
            acc = rec.get("accession") or ""
            snippet = " · ".join(str(x) for x in (
                acc, rec.get("gdstype") or "", rec.get("taxon") or "",
                f"{rec['n_samples']} samples" if rec.get("n_samples") else "", (rec.get("summary") or "")[:220],
            ) if x)
            items.append(se._result(rec.get("title") or acc, snippet,
                                    f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={acc}", "geo"))
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
    return _pack("geo", q, items, errors, limit)


def search_clinvar(query: str, *, limit: int = 5, timeout: float = 4.0) -> dict[str, Any]:
    ent = detect_entities(query)
    rs = ent["ids"].get("rsid") or []
    q = " OR ".join(rs) or " OR ".join(f"{g}[gene]" for g in ent["genes"]) or _english_terms(query) or query
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        for uid, rec in _eutils_summaries("clinvar", q, limit, timeout):
            sig = ((rec.get("germline_classification") or {}).get("description")
                   or (rec.get("clinical_significance") or {}).get("description") or "")
            genes = ", ".join(g.get("symbol", "") for g in (rec.get("genes") or [])[:3])
            snippet = " · ".join(x for x in (rec.get("accession") or "", genes, sig) if x)
            items.append(se._result(rec.get("title") or uid, snippet,
                                    f"https://www.ncbi.nlm.nih.gov/clinvar/variation/{uid}/", "clinvar"))
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
    return _pack("clinvar", q, items, errors, limit)


def search_reactome(query: str, *, limit: int = 5, timeout: float = 4.0) -> dict[str, Any]:
    ent = detect_entities(query)
    q = " ".join(ent["genes"]) or _english_terms(query) or query
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        data = _get_json(
            "https://reactome.org/ContentService/search/query?"
            + urlencode({"query": q, "species": "Homo sapiens", "types": "Pathway", "cluster": "true", "rows": min(limit, 10)}),
            timeout,
        )
        for group in data.get("results") or []:
            for e in group.get("entries") or []:
                st = e.get("stId") or e.get("id") or ""
                snippet = " · ".join(x for x in (st, ", ".join(e.get("species") or []), se._strip_html(e.get("summation") or "")[:240]) if x)
                items.append(se._result(e.get("name") or st, snippet, f"https://reactome.org/content/detail/{st}", "reactome"))
                if len(items) >= limit:
                    break
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
    return _pack("reactome", q, items, errors, limit)


def search_europepmc(query: str, *, limit: int = 5, timeout: float = 4.0) -> dict[str, Any]:
    q = _english_terms(query) or (query or "").strip()
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    if not q:
        return _pack("europepmc", q, items, ["empty query"], limit)
    try:
        data = _get_json(
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search?"
            + urlencode({"query": q, "format": "json", "pageSize": min(limit, 10), "resultType": "lite"}),
            timeout,
        )
        for r in ((data.get("resultList") or {}).get("result")) or []:
            pmid, doi = r.get("pmid") or "", r.get("doi") or ""
            url = (f"https://europepmc.org/article/MED/{pmid}" if pmid
                   else f"https://doi.org/{doi}" if doi
                   else f"https://europepmc.org/article/{r.get('source') or 'MED'}/{r.get('id') or ''}")
            snippet = " · ".join(x for x in (
                f"[{r['pubYear']}]" if r.get("pubYear") else "", r.get("journalTitle") or "",
                (r.get("authorString") or "")[:120], f"PMID {pmid}" if pmid else "", f"doi:{doi}" if doi else "",
            ) if x)
            items.append(se._result(r.get("title") or url, snippet, url, "europepmc"))
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
    return _pack("europepmc", q, items, errors, limit)


def _crossref_item(w: dict[str, Any]) -> dict[str, Any]:
    doi = w.get("DOI") or ""
    parts = ((w.get("issued") or {}).get("date-parts") or [[None]])[0]
    year = parts[0] if parts else None
    authors = ", ".join(" ".join(x for x in (a.get("given"), a.get("family")) if x) for a in (w.get("author") or [])[:3])
    snippet = " · ".join(str(x) for x in (
        f"[{year}]" if year else "", (w.get("container-title") or [""])[0], authors, f"doi:{doi}" if doi else "",
    ) if x)
    return se._result((w.get("title") or [doi])[0] or doi, snippet, f"https://doi.org/{doi}", "crossref")


def search_crossref(query: str, *, limit: int = 5, timeout: float = 4.0) -> dict[str, Any]:
    ent = detect_entities(query)
    dois = ent["ids"].get("doi") or []
    q = ", ".join(dois) or _english_terms(query) or (query or "").strip()
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        if dois:
            for d in dois[:limit]:
                items.append(_crossref_item((_get_json(f"https://api.crossref.org/works/{quote(d, safe='/')}", timeout)).get("message") or {}))
        elif q:
            data = _get_json("https://api.crossref.org/works?" + urlencode({"query": q, "rows": min(limit, 10)}), timeout)
            items = [_crossref_item(w) for w in ((data.get("message") or {}).get("items")) or []]
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
    return _pack("crossref", q, items, errors, limit)


# ── registry, routing, fan-out ────────────────────────────────────────

CONNECTORS: list[dict[str, Any]] = [
    {"id": "uniprot", "label": "UniProt", "label_zh": "UniProt 蛋白", "host": "rest.uniprot.org", "fn": search_uniprot,
     "desc": "Protein sequences & function", "desc_zh": "蛋白序列、功能注释"},
    {"id": "pdb", "label": "RCSB PDB", "label_zh": "PDB 结构", "host": "search.rcsb.org", "fn": search_pdb,
     "desc": "3D macromolecular structures", "desc_zh": "蛋白 / 核酸三维结构"},
    {"id": "ensembl", "label": "Ensembl", "label_zh": "Ensembl 基因", "host": "rest.ensembl.org", "fn": search_ensembl,
     "desc": "Gene models & genomic coordinates", "desc_zh": "基因模型、基因组坐标"},
    {"id": "chembl", "label": "ChEMBL", "label_zh": "ChEMBL 化合物", "host": "www.ebi.ac.uk", "fn": search_chembl,
     "desc": "Bioactive molecules & drugs", "desc_zh": "生物活性分子、药物"},
    {"id": "clinicaltrials", "label": "ClinicalTrials.gov", "label_zh": "临床试验", "host": "clinicaltrials.gov",
     "fn": search_clinicaltrials, "desc": "Registered clinical studies", "desc_zh": "注册临床研究"},
    {"id": "geo", "label": "NCBI GEO", "label_zh": "GEO 数据集", "host": "eutils.ncbi.nlm.nih.gov", "fn": search_geo,
     "desc": "Functional genomics datasets", "desc_zh": "表达谱 / 测序数据集"},
    {"id": "clinvar", "label": "ClinVar", "label_zh": "ClinVar 变异", "host": "eutils.ncbi.nlm.nih.gov", "fn": search_clinvar,
     "desc": "Variant clinical significance", "desc_zh": "变异临床意义"},
    {"id": "reactome", "label": "Reactome", "label_zh": "Reactome 通路", "host": "reactome.org", "fn": search_reactome,
     "desc": "Curated biological pathways", "desc_zh": "生物通路"},
    {"id": "europepmc", "label": "Europe PMC", "label_zh": "Europe PMC 文献", "host": "www.ebi.ac.uk", "fn": search_europepmc,
     "desc": "Life-science literature", "desc_zh": "生命科学文献"},
    {"id": "crossref", "label": "Crossref", "label_zh": "Crossref 元数据", "host": "api.crossref.org", "fn": search_crossref,
     "desc": "DOI metadata", "desc_zh": "DOI 元数据"},
]
_BY_ID: dict[str, dict[str, Any]] = {c["id"]: c for c in CONNECTORS}

# Which connectors each signal wakes up (literature engines are registered
# separately in the academic intent, so they are only routed here for DOIs).
_ROUTES: dict[str, tuple[str, ...]] = {
    "uniprot": ("uniprot",), "pdb": ("pdb",), "ensembl": ("ensembl",), "chembl": ("chembl",),
    "nct": ("clinicaltrials",), "rsid": ("clinvar",), "geo": ("geo",), "doi": ("crossref",),
    "genes": ("uniprot", "ensembl"),
    "protein": ("uniprot",), "gene": ("ensembl", "uniprot"), "structure": ("pdb",), "compound": ("chembl",),
    "trial": ("clinicaltrials",), "dataset": ("geo",), "variant": ("clinvar",), "pathway": ("reactome",),
}


def _load_cfg(cfg: dict[str, Any] | None) -> dict[str, Any]:
    if cfg is not None:
        return cfg
    try:
        from .settings import load_campus_config

        return load_campus_config()
    except Exception:  # noqa: BLE001
        return {}


def enabled_map(cfg: dict[str, Any] | None = None) -> dict[str, bool]:
    cfg = _load_cfg(cfg)
    sw = ((cfg.get("science") or {}).get("connectors") or {}) if isinstance(cfg.get("science"), dict) else {}
    restricted = str(cfg.get("data_policy") or "internal").lower() == "restricted"
    return {c["id"]: (not restricted) and bool(sw.get(c["id"], True)) for c in CONNECTORS}


def route(query: str, cfg: dict[str, Any] | None = None) -> list[str]:
    """Connector ids worth asking for this query (enabled ones only, stable order)."""
    ent = detect_entities(query)
    wanted: list[str] = []
    for kind in ent["ids"]:
        wanted.extend(_ROUTES.get(kind, ()))
    if ent["genes"]:
        wanted.extend(_ROUTES["genes"])
    for topic in ent["topics"]:
        wanted.extend(_ROUTES.get(topic, ()))
    enabled = enabled_map(cfg)
    order = [c["id"] for c in CONNECTORS]
    chosen = {w for w in wanted if enabled.get(w)}
    return [cid for cid in order if cid in chosen]


def search_science(
    query: str,
    *,
    limit: int = 8,
    connectors: list[str] | None = None,
    cfg: dict[str, Any] | None = None,
    per_connector: int = 3,
    deadline: float = 12.0,
) -> dict[str, Any]:
    """Run the routed (or given) connectors in parallel and merge in registry order."""
    q = (query or "").strip()
    enabled = enabled_map(cfg)
    ids = [c for c in (connectors if connectors is not None else route(q, cfg)) if c in _BY_ID and enabled.get(c)]
    if not q or not ids:
        return {"ok": False, "query": q, "results": [], "errors": [], "engine": "science", "connectors": ids, "per_connector": {}}
    try:
        from . import audit

        audit.log_event("science_query", {"query": q[:200], "connectors": ids})
    except Exception:  # noqa: BLE001
        pass
    blocks: dict[str, dict[str, Any]] = {}
    fns: dict[str, Callable[..., dict[str, Any]]] = {cid: _BY_ID[cid]["fn"] for cid in ids}
    pool = ThreadPoolExecutor(max_workers=min(6, len(ids)))
    try:
        futs = {pool.submit(fns[cid], q, limit=per_connector): cid for cid in ids}
        done, _pending = wait(futs, timeout=deadline)
        for fut in futs:
            cid = futs[fut]
            if fut not in done:
                blocks[cid] = {"ok": False, "results": [], "errors": ["timeout"]}
                continue
            try:
                blocks[cid] = fut.result()
            except Exception as exc:  # noqa: BLE001
                blocks[cid] = {"ok": False, "results": [], "errors": [str(exc)]}
    finally:
        pool.shutdown(wait=False)
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    for cid in ids:
        b = blocks.get(cid) or {}
        results.extend(b.get("results") or [])
        errors.extend(f"{cid}: {e}" for e in (b.get("errors") or []))
    used = [cid for cid in ids if (blocks.get(cid) or {}).get("results")]
    return {
        "ok": bool(results),
        "query": q,
        "results": results[:limit],
        "errors": errors[:6],
        "engine": "science:" + ",".join(used or ids),
        "connectors": ids,
        "per_connector": {cid: len((blocks.get(cid) or {}).get("results") or []) for cid in ids},
    }


def search_science_databases(query: str, *, limit: int = 8, timeout: float = 4.0) -> dict[str, Any]:
    """Academic-intent engine: no-op (no network) unless a science entity/topic is detected."""
    return search_science(query, limit=limit)


def list_connectors(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = _load_cfg(cfg)
    enabled = enabled_map(cfg)
    restricted = str(cfg.get("data_policy") or "internal").lower() == "restricted"
    return {
        "ok": True,
        "restricted": restricted,
        "items": [
            {k: v for k, v in c.items() if k != "fn"} | {"enabled": enabled[c["id"]]}
            for c in CONNECTORS
        ],
    }


def set_enabled(switches: dict[str, Any]) -> dict[str, Any]:
    from .settings import load_campus_config, save_campus_config

    cfg = load_campus_config()
    sci = cfg.get("science") if isinstance(cfg.get("science"), dict) else {}
    cur = sci.get("connectors") if isinstance(sci.get("connectors"), dict) else {}
    for cid, val in (switches or {}).items():
        if cid in _BY_ID:
            cur[cid] = bool(val)
    sci["connectors"] = cur
    cfg["science"] = sci
    save_campus_config(cfg)
    try:
        from . import audit

        audit.log_event("science_connectors", {"connectors": cur})
    except Exception:  # noqa: BLE001
        pass
    return list_connectors(cfg)
