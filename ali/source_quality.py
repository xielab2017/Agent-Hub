"""Source credibility tiers and dates.

``classify_source(url)`` → ``{tier, score, label, label_zh, preprint}`` where tier is one of:

* ``official``  government, intergovernmental, universities / academies
* ``database``  curated scientific databases (UniProt, PDB, NCBI …)
* ``academic``  journals, publishers, DOI, PubMed, preprint servers (preprints flagged)
* ``news``      established news agencies and outlets
* ``ugc``       forums, Q&A, blogs, social media, wikis anyone can edit quickly
* ``other``

Scores are a simple prior for ranking and "is this backed by something
authoritative?" checks — not a truth oracle.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

TIER_SCORE = {"official": 1.0, "database": 0.95, "academic": 0.9, "news": 0.7, "other": 0.5, "ugc": 0.3}
TIER_LABEL = {
    "official": ("Official", "官方"),
    "database": ("Database", "数据库"),
    "academic": ("Academic", "学术"),
    "news": ("News", "新闻"),
    "ugc": ("User content", "社区/自媒体"),
    "other": ("Other", "其他"),
}
AUTHORITATIVE_TIERS = ("official", "database", "academic")

_OFFICIAL_SUFFIX = (".gov", ".gov.cn", ".mil", ".edu", ".edu.cn", ".ac.cn", ".ac.uk", ".gov.uk", ".gc.ca",
                    ".gov.au", ".go.jp", ".go.kr", ".int", ".europa.eu")
_OFFICIAL_HOSTS = ("who.int", "un.org", "worldbank.org", "imf.org", "oecd.org", "nih.gov", "cdc.gov", "fda.gov",
                   "nhc.gov.cn", "stats.gov.cn", "cas.cn", "nsfc.gov.cn", "most.gov.cn", "fifa.com", "olympics.com")
_DATABASE_HOSTS = ("uniprot.org", "rcsb.org", "wwpdb.org", "ensembl.org", "ebi.ac.uk", "ncbi.nlm.nih.gov",
                   "clinicaltrials.gov", "reactome.org", "kegg.jp", "genome.jp", "string-db.org", "proteinatlas.org",
                   "gtexportal.org", "cancer.gov", "gnomad.broadinstitute.org", "alphafold.ebi.ac.uk")
_ACADEMIC_HOSTS = ("doi.org", "pubmed.ncbi.nlm.nih.gov", "pmc.ncbi.nlm.nih.gov", "europepmc.org", "nature.com",
                   "science.org", "cell.com", "thelancet.com", "nejm.org", "bmj.com", "jamanetwork.com",
                   "springer.com", "link.springer.com", "wiley.com", "onlinelibrary.wiley.com", "sciencedirect.com",
                   "elsevier.com", "plos.org", "frontiersin.org", "mdpi.com", "acs.org", "rsc.org", "ieee.org",
                   "acm.org", "oup.com", "academic.oup.com", "tandfonline.com", "sagepub.com", "pnas.org",
                   "annualreviews.org", "cnki.net", "wanfangdata.com.cn", "openalex.org", "semanticscholar.org",
                   "crossref.org", "scholar.google.com", "researchgate.net")
_PREPRINT_HOSTS = ("arxiv.org", "biorxiv.org", "medrxiv.org", "chemrxiv.org", "ssrn.com", "preprints.org",
                   "researchsquare.com")
_NEWS_HOSTS = ("reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "nytimes.com", "wsj.com", "ft.com",
               "economist.com", "theguardian.com", "bloomberg.com", "xinhuanet.com", "news.cn", "people.com.cn",
               "cctv.com", "cctv.cn", "chinadaily.com.cn", "caixin.com", "thepaper.cn", "yicai.com", "scmp.com",
               "nhk.or.jp", "espn.com", "sina.com.cn", "sohu.com", "163.com", "qq.com", "ifeng.com", "statnews.com",
               "sciencedaily.com", "newscientist.com", "sciencenet.cn")
_UGC_HOSTS = ("zhihu.com", "weibo.com", "tieba.baidu.com", "csdn.net", "jianshu.com", "douban.com", "bilibili.com",
              "reddit.com", "quora.com", "medium.com", "stackexchange.com", "stackoverflow.com", "twitter.com",
              "x.com", "facebook.com", "youtube.com", "tiktok.com", "douyin.com", "xiaohongshu.com", "baike.baidu.com",
              "zhidao.baidu.com", "blogspot.com", "wordpress.com", "substack.com", "toutiao.com", "mp.weixin.qq.com")

# Science connector engine names → database tier even without a URL match.
_DATABASE_ENGINES = ("uniprot", "pdb", "ensembl", "chembl", "clinicaltrials", "geo", "clinvar", "reactome")


def host_of(url: str) -> str:
    try:
        host = (urlparse(str(url or "")).netloc or "").lower().split("@")[-1].split(":")[0]
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _matches(host: str, hosts: tuple[str, ...]) -> bool:
    return any(host == h or host.endswith("." + h) for h in hosts)


def _path_match(url: str, hosts: tuple[str, ...]) -> bool:
    low = str(url or "").lower()
    return any(h in low for h in hosts if "/" in h)


def classify_source(url: str, engine: str = "") -> dict[str, Any]:
    host = host_of(url)
    eng = (engine or "").lower()
    preprint = _matches(host, _PREPRINT_HOSTS)
    if _matches(host, _UGC_HOSTS):
        tier = "ugc"
    elif _matches(host, _DATABASE_HOSTS) or eng in _DATABASE_ENGINES:
        # PubMed / PMC live under ncbi but are literature, not a database record
        tier = "academic" if _matches(host, ("pubmed.ncbi.nlm.nih.gov", "pmc.ncbi.nlm.nih.gov")) else "database"
    elif _matches(host, _ACADEMIC_HOSTS) or preprint or eng in ("europepmc", "crossref", "openalex", "pubmed", "arxiv"):
        tier = "academic"
    elif _matches(host, _OFFICIAL_HOSTS) or any(host.endswith(s) for s in _OFFICIAL_SUFFIX):
        tier = "official"
    elif _matches(host, _NEWS_HOSTS):
        tier = "news"
    else:
        tier = "other"
    score = TIER_SCORE[tier] - (0.2 if preprint else 0.0)
    en, zh = TIER_LABEL[tier]
    if preprint:
        en, zh = "Preprint", "预印本"
    return {"tier": tier, "score": round(score, 2), "label": en, "label_zh": zh, "preprint": preprint, "host": host}


# Wire agencies / national broadcasters count as authoritative for news and events.
_WIRE_HOSTS = ("reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "xinhuanet.com", "news.cn",
               "people.com.cn", "cctv.com", "cctv.cn", "nhk.or.jp")


def is_authoritative(url: str, engine: str = "") -> bool:
    q = classify_source(url, engine)
    return q["tier"] in AUTHORITATIVE_TIERS or _matches(q["host"], _WIRE_HOSTS)


_DATE_PATTERNS = (
    re.compile(r"(?<!\d)((?:19|20)\d{2})[-/.年](0?[1-9]|1[0-2])[-/.月](0?[1-9]|[12]\d|3[01])日?(?!\d)"),
    re.compile(r"(?<!\d)((?:19|20)\d{2})[-/.年](0?[1-9]|1[0-2])月?(?!\d)"),
    re.compile(r"(?<![\d.])((?:19|20)\d{2})(?![\d.])"),
)


def extract_date(*texts: str) -> str:
    """Most specific date found (YYYY-MM-DD / YYYY-MM / YYYY), latest first; '' if none."""
    found: list[str] = []
    for text in texts:
        t = str(text or "")
        for i, pat in enumerate(_DATE_PATTERNS):
            for m in pat.finditer(t):
                parts = [m.group(1)] + [g.zfill(2) for g in m.groups()[1:]]
                found.append("-".join(parts))
            if found:
                break
        if found:
            break
    if not found:
        return ""
    best_len = max(len(d) for d in found)
    return max(d for d in found if len(d) == best_len)


def annotate(source: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of a search source with tier / score / date added."""
    s = dict(source)
    q = classify_source(str(s.get("url") or ""), str(s.get("source") or s.get("engine") or ""))
    s["tier"] = q["tier"]
    s["tier_label"] = q["label"]
    s["tier_label_zh"] = q["label_zh"]
    s["credibility"] = q["score"]
    s["preprint"] = q["preprint"]
    s["date"] = extract_date(str(s.get("url") or ""), str(s.get("snippet") or ""), str(s.get("title") or ""))
    return s
