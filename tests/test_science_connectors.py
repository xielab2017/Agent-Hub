"""Tests for scientific database connectors.

Network is never touched: ``search_extensions._fetch`` is replaced by a stub
that serves fixtures shaped like each public API's documented JSON.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FIXTURES = {
    "rest.uniprot.org": {"results": [{
        "primaryAccession": "P04637", "uniProtkbId": "P53_HUMAN",
        "organism": {"scientificName": "Homo sapiens"},
        "proteinDescription": {"recommendedName": {"fullName": {"value": "Cellular tumor antigen p53"}}},
        "genes": [{"geneName": {"value": "TP53"}}],
        "comments": [{"commentType": "FUNCTION", "texts": [{"value": "Acts as a tumor suppressor."}]}],
        "sequence": {"length": 393},
    }]},
    "search.rcsb.org": {"result_set": [{"identifier": "4HHB", "score": 1.0}]},
    "data.rcsb.org": {
        "struct": {"title": "THE CRYSTAL STRUCTURE OF HUMAN DEOXYHAEMOGLOBIN"},
        "rcsb_entry_info": {"resolution_combined": [1.74], "experimental_method": "X-ray"},
        "rcsb_accession_info": {"initial_release_date": "1984-07-17T00:00:00+0000"},
    },
    "rest.ensembl.org": {
        "id": "ENSG00000141510", "display_name": "TP53", "biotype": "protein_coding",
        "description": "tumor protein p53 [Source:HGNC Symbol;Acc:HGNC:11998]",
        "seq_region_name": "17", "start": 7661779, "end": 7687538, "strand": -1, "assembly_name": "GRCh38",
    },
    "chembl/api/data/molecule/search": {"molecules": [{
        "molecule_chembl_id": "CHEMBL941", "pref_name": "IMATINIB", "max_phase": "4.0",
        "molecule_type": "Small molecule",
        "molecule_properties": {"full_mwt": "493.62", "full_molformula": "C29H31N7O"},
    }]},
    "chembl/api/data/molecule/CHEMBL941": {
        "molecule_chembl_id": "CHEMBL941", "pref_name": "IMATINIB", "max_phase": "4.0",
        "molecule_type": "Small molecule", "molecule_properties": {"full_mwt": "493.62"},
    },
    "clinicaltrials.gov": {"studies": [{"protocolSection": {
        "identificationModule": {"nctId": "NCT04280705", "briefTitle": "Adaptive COVID-19 Treatment Trial"},
        "statusModule": {"overallStatus": "COMPLETED"},
        "designModule": {"phases": ["PHASE3"]},
        "conditionsModule": {"conditions": ["COVID-19"]},
    }}]},
    "esearch.fcgi?db=gds": {"esearchresult": {"idlist": ["200012345"]}},
    "esummary.fcgi?db=gds": {"result": {"uids": ["200012345"], "200012345": {
        "accession": "GSE12345", "title": "TP53 knockdown expression profiling",
        "gdstype": "Expression profiling by array", "taxon": "Homo sapiens", "n_samples": 12, "summary": "…",
    }}},
    "esearch.fcgi?db=clinvar": {"esearchresult": {"idlist": ["12356"]}},
    "esummary.fcgi?db=clinvar": {"result": {"uids": ["12356"], "12356": {
        "title": "NM_000546.6(TP53):c.743G>A (p.Arg248Gln)", "accession": "VCV000012356",
        "germline_classification": {"description": "Pathogenic"}, "genes": [{"symbol": "TP53"}],
    }}},
    "reactome.org": {"results": [{"typeName": "Pathway", "entries": [{
        "stId": "R-HSA-109581", "name": "<span class=\"highlighting\">Apoptosis</span>",
        "species": ["Homo sapiens"], "summation": "Apoptosis is a distinct form of cell death.",
    }]}]},
    "europepmc": {"resultList": {"result": [{
        "id": "12345678", "source": "MED", "pmid": "12345678", "doi": "10.1000/xyz123",
        "title": "TP53 in cancer", "authorString": "Doe J, Roe R.", "journalTitle": "Nature", "pubYear": "2020",
    }]}},
    "api.crossref.org/works/": {"message": {
        "DOI": "10.1038/nature12373", "title": ["Nanometre-scale thermometry in a living cell"],
        "container-title": ["Nature"], "issued": {"date-parts": [[2013, 7, 31]]},
        "author": [{"given": "G.", "family": "Kucsko"}],
    }},
    "api.crossref.org/works?": {"message": {"items": [{
        "DOI": "10.1000/abc", "title": ["A paper"], "container-title": ["J"], "issued": {"date-parts": [[2021]]},
    }]}},
}


@pytest.fixture(autouse=True)
def _no_audit():
    with mock.patch("ali.audit.log_event", lambda *a, **k: None):
        yield


def fake_fetch(url, *, timeout=4.0, headers=None):
    for key in sorted(FIXTURES, key=len, reverse=True):
        if key in url:
            return json.dumps(FIXTURES[key])
    raise AssertionError(f"unexpected URL {url}")


def _patched():
    from ali import search_extensions as se

    return mock.patch.object(se, "_fetch", side_effect=fake_fetch)


# ── detection & routing ────────────────────────────────────────────────


def test_detect_entities_ids_and_genes():
    from ali.science_connectors import detect_entities

    e = detect_entities("TP53 R248Q rs121913529 NCT04280705 CHEMBL941 GSE12345 ENSG00000141510 doi:10.1038/nature12373 P04637")
    assert e["ids"]["rsid"] == ["rs121913529"]
    assert e["ids"]["nct"] == ["NCT04280705"]
    assert e["ids"]["chembl"] == ["CHEMBL941"]
    assert e["ids"]["geo"] == ["GSE12345"]
    assert e["ids"]["ensembl"] == ["ENSG00000141510"]
    assert e["ids"]["doi"] == ["10.1038/nature12373"]
    assert e["ids"]["uniprot"] == ["P04637"]
    assert e["genes"] == ["TP53"]  # R248Q is a protein change, not a gene


def test_pdb_ids_need_structure_cue_and_years_never_match():
    from ali.science_connectors import detect_entities

    assert detect_entities("PDB 4HHB 结构")["ids"]["pdb"] == ["4HHB"]
    assert "pdb" not in detect_entities("2024 年 1ABC 计划")["ids"]
    assert "pdb" not in detect_entities("crystal structure solved in 2019")["ids"]


def test_all_letter_symbols_need_bio_context_and_acronyms_are_ignored():
    from ali.science_connectors import detect_entities

    assert detect_entities("KRAS EGFR 在肿瘤中的突变")["genes"] == ["KRAS", "EGFR"]
    assert detect_entities("请用 PCA 和 UMAP 分析单细胞数据")["genes"] == []
    assert detect_entities("整理 CSV 和 PDF 报告 API")["genes"] == []


def test_tech_tokens_are_not_genes_outside_bio_context():
    from ali.science_connectors import detect_entities, route
    from ali.search_extensions import classify_intent

    for q in ("GPT4 是什么", "RTX4090 显卡价格", "USB3 和 HDMI2 接口", "IPv6 配置", "M3 芯片"):
        assert detect_entities(q)["genes"] == [], q
        assert route(q, {}) == [], q
    assert classify_intent("RTX4090 显卡价格") == "general"
    # genuine symbols still work, including ones that look tech-like inside a bio question
    assert detect_entities("TP53 BRCA1 CD19")["genes"] == ["TP53", "BRCA1", "CD19"]


def test_keywords_use_word_boundaries():
    from ali.science_connectors import detect_entities, route

    assert detect_entities("general generate genetic")["topics"] == []
    assert route("帮我优化这篇文章的结构", {}) == []
    assert route("整理一个机器学习数据集", {}) == []


def test_route_by_entities_and_topics():
    from ali.science_connectors import route

    assert route("TP53 蛋白功能", {}) == ["uniprot", "ensembl"]
    assert route("NCT04280705 临床试验", {}) == ["clinicaltrials"]
    assert route("PDB 4HHB 结构", {}) == ["pdb"]
    assert route("apoptosis 信号通路", {}) == ["reactome"]
    assert route("rs121913529 致病性", {}) == ["clinvar"]
    assert route("10.1038/nature12373", {}) == ["crossref"]


def test_disabled_connectors_and_restricted_policy():
    from ali.science_connectors import enabled_map, route, search_science

    cfg = {"science": {"connectors": {"uniprot": False}}}
    assert route("TP53 蛋白功能", cfg) == ["ensembl"]
    restricted = {"data_policy": "restricted"}
    assert not any(enabled_map(restricted).values())
    assert route("TP53 蛋白功能", restricted) == []
    with mock.patch("ali.search_extensions._fetch", side_effect=AssertionError("no network")):
        r = search_science("TP53 蛋白功能", cfg=restricted)
    assert r["ok"] is False and r["results"] == []


# ── parsers ────────────────────────────────────────────────────────────


def test_each_connector_parses_documented_shape():
    from ali import science_connectors as sc

    with _patched():
        u = sc.search_uniprot("TP53 protein")
        p = sc.search_pdb("PDB 4HHB 结构")
        p2 = sc.search_pdb("haemoglobin crystal structure")
        e = sc.search_ensembl("TP53 gene")
        c = sc.search_chembl("imatinib compound")
        c2 = sc.search_chembl("CHEMBL941")
        t = sc.search_clinicaltrials("NCT04280705")
        g = sc.search_geo("GSE12345")
        v = sc.search_clinvar("rs121913529")
        r = sc.search_reactome("apoptosis pathway")
        m = sc.search_europepmc("TP53 cancer")
        x = sc.search_crossref("10.1038/nature12373")
        x2 = sc.search_crossref("thermometry living cell")
    assert u["results"][0]["url"] == "https://www.uniprot.org/uniprotkb/P04637/entry"
    assert "Cellular tumor antigen p53" in u["results"][0]["title"] and "393 aa" in u["results"][0]["snippet"]
    assert p["results"][0]["url"] == "https://www.rcsb.org/structure/4HHB" and "1.74 Å" in p["results"][0]["snippet"]
    assert p2["results"][0]["title"].endswith("(4HHB)")
    assert "chr17:7661779-7687538" in e["results"][0]["snippet"] and "[Source" not in e["results"][0]["snippet"]
    assert c["results"][0]["title"] == "IMATINIB (CHEMBL941)" and "max phase 4.0" in c["results"][0]["snippet"]
    assert c2["results"][0]["url"].endswith("/CHEMBL941/")
    assert t["results"][0]["url"] == "https://clinicaltrials.gov/study/NCT04280705" and "PHASE3" in t["results"][0]["snippet"]
    assert g["results"][0]["url"].endswith("acc=GSE12345") and "12 samples" in g["results"][0]["snippet"]
    assert "Pathogenic" in v["results"][0]["snippet"]
    assert r["results"][0]["title"] == "Apoptosis" and r["results"][0]["url"].endswith("R-HSA-109581")
    assert m["results"][0]["url"] == "https://europepmc.org/article/MED/12345678"
    assert x["results"][0]["url"] == "https://doi.org/10.1038/nature12373" and "[2013]" in x["results"][0]["snippet"]
    assert x2["results"][0]["url"] == "https://doi.org/10.1000/abc"
    for res in (u, p, e, c, t, g, v, r, m, x):
        assert res["ok"] and all(set(i) == {"title", "snippet", "url", "source"} for i in res["results"])


def test_connector_errors_are_reported_not_raised():
    from ali import science_connectors as sc
    from ali import search_extensions as se

    with mock.patch.object(se, "_fetch", side_effect=OSError("blocked")):
        r = sc.search_uniprot("TP53 protein")
    assert r["ok"] is False and r["results"] == [] and "blocked" in r["errors"][0]


def test_pdb_never_returns_unretrieved_placeholders():
    from ali import science_connectors as sc
    from ali import search_extensions as se

    with mock.patch.object(se, "_fetch", side_effect=OSError("blocked")):
        r = sc.search_pdb("PDB 4HHB 结构")
    assert r["ok"] is False and r["results"] == [] and "4HHB" in r["errors"][0]


def test_search_science_parallel_merge_survives_one_failure():
    from ali import science_connectors as sc

    def flaky(url, *, timeout=4.0, headers=None):
        if "ensembl" in url:
            raise OSError("ensembl down")
        return fake_fetch(url)

    with mock.patch("ali.search_extensions._fetch", side_effect=flaky):
        r = sc.search_science("TP53 蛋白功能", cfg={})
    assert r["connectors"] == ["uniprot", "ensembl"]
    assert r["ok"] and r["results"][0]["source"] == "uniprot"
    assert r["per_connector"] == {"uniprot": 1, "ensembl": 0}
    assert any("ensembl down" in e for e in r["errors"])
    assert r["engine"] == "science:uniprot"


def test_no_entity_means_no_network():
    from ali import science_connectors as sc

    with mock.patch("ali.search_extensions._fetch", side_effect=AssertionError("no network")):
        r = sc.search_science("帮我写一封会议邀请邮件", cfg={})
    assert r["ok"] is False and r["connectors"] == []


# ── registration in the search cascade ─────────────────────────────────


def test_academic_intent_registers_science_first_and_keeps_parity():
    from ali import search_extensions as se

    names = [fn.__name__ for fn in se.engines_for_intent("academic")]
    assert names[0] == "search_science_databases"
    assert "search_europepmc" in names and "search_crossref" in names
    assert se.search_minimax_parity in se.engines_for_intent("academic")


def test_classify_intent_science_queries():
    from ali.search_extensions import classify_intent

    assert classify_intent("PDB 4HHB 结构") == "academic"
    assert classify_intent("TP53 蛋白功能") == "academic"
    assert classify_intent("NCT04280705") == "academic"
    assert classify_intent("昨晚世界杯小组赛战况") == "event"
    assert classify_intent("你好") == "general"


def test_list_connectors_hides_functions():
    from ali.science_connectors import list_connectors

    data = list_connectors({})
    assert {c["id"] for c in data["items"]} >= {"uniprot", "pdb", "ensembl", "chembl", "clinicaltrials", "geo", "clinvar", "reactome"}
    assert all("fn" not in c and c["enabled"] for c in data["items"])
    json.dumps(data)
