"""Tests for the reply reviewer (citations, URLs, identifiers, untraceable numbers)."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SOURCES = [
    {"n": 1, "title": "TP53 mutations in 42% of tumours", "url": "https://pubmed.ncbi.nlm.nih.gov/123/",
     "snippet": "n = 1,204 patients; HR 0.71 (p < 0.001)"},
    {"n": 2, "title": "Guide", "url": "https://www.nature.com/articles/x", "snippet": "IC50 of 12.5 nM"},
]


def _kinds(review):
    return [(i["kind"], i["severity"]) for i in review["issues"]]


def test_clean_reply_passes():
    from ali.reviewer import review_reply

    text = "TP53 突变见于 42% 的肿瘤 [1]，1,204 名患者中 HR 为 0.71（p < 0.001）[1]；IC50 = 12.5 nM [2]。"
    rv = review_reply(text, sources=SOURCES)
    assert rv["ok"] is True and rv["warn"] == 0, rv["issues"]
    assert rv["stats"]["citations"] == 2
    assert rv["stats"]["numbers"] == rv["stats"]["traced_numbers"] >= 4


def test_citation_out_of_range_and_without_sources():
    from ali.reviewer import review_reply

    rv = review_reply("结论 [1][3]，另见 [2-4]。", sources=SOURCES)
    out = sorted(i["text"] for i in rv["issues"] if i["kind"] == "citation_out_of_range")
    assert out == ["[3]", "[4]"]
    rv2 = review_reply("结论见 [1]。", sources=[])
    assert _kinds(rv2) == [("citation_without_sources", "warn")]
    # markdown links are not citations
    assert review_reply("见 [1](https://pubmed.ncbi.nlm.nih.gov/123/)", sources=SOURCES)["stats"]["citations"] == 0


def test_urls_checked_against_sources():
    from ali.reviewer import review_reply

    rv = review_reply(
        "来源 https://pubmed.ncbi.nlm.nih.gov/123 与 https://nature.com/articles/x/ ，"
        "以及 https://pubmed.ncbi.nlm.nih.gov/999/ 和 https://fake.example.org/paper。",
        sources=SOURCES,
    )
    urls = {i["text"]: i["severity"] for i in rv["issues"] if i["kind"] == "unlisted_url"}
    assert urls == {"https://pubmed.ncbi.nlm.nih.gov/999/": "info", "https://fake.example.org/paper": "warn"}
    # Without retrieved sources an unknown URL is only a note
    rv2 = review_reply("参考 https://fake.example.org/paper", sources=[])
    assert _kinds(rv2) == [("unlisted_url", "info")]
    # URLs provided by the user are evidence
    rv3 = review_reply("参考 https://lab.example.org/data", sources=SOURCES, evidence_texts=["我的数据在 https://lab.example.org/data"])
    assert not rv3["issues"]


def test_identifiers_malformed_and_unverified():
    from ali.reviewer import review_reply

    rv = review_reply("doi: 10.bad/xx，PMID: 12a34。另见 doi:10.1038/nature12373 与 PMID: 123。", sources=SOURCES)
    kinds = _kinds(rv)
    assert ("malformed_doi", "warn") in kinds and ("malformed_pmid", "warn") in kinds
    unverified = [i["text"] for i in rv["issues"] if i["kind"] == "unverified_identifier"]
    assert unverified == ["doi:10.1038/nature12373"]  # PMID 123 is in source 1's URL
    assert rv["identifiers"] == {"doi": ["10.1038/nature12373"], "pmid": ["123"]}


def test_markdown_emphasis_is_not_part_of_identifiers():
    from ali.reviewer import review_reply

    rv = review_reply("_见 doi:10.1038/nature12373_ 与 **https://example.org/a_b**", sources=SOURCES)
    assert rv["identifiers"]["doi"] == ["10.1038/nature12373"]
    assert [i["text"] for i in rv["issues"] if i["kind"] == "unlisted_url"] == ["https://example.org/a_b"]


def test_untraceable_numbers_flagged_code_and_years_ignored():
    from ali.reviewer import review_reply

    text = (
        "2020 年的研究显示 63% 的病例响应，p = 0.03，n = 88。\n"
        "```python\nratio = 0.37  # 99% in code is ignored\n```\n"
        "`inline 77%` 也忽略。版本 3.10。"
    )
    rv = review_reply(text, sources=SOURCES)
    flagged = sorted(i["text"] for i in rv["issues"] if i["kind"] == "untraceable_number")
    assert flagged == ["63%", "n = 88", "p = 0.03"]
    assert all(i["severity"] == "warn" for i in rv["issues"] if i["kind"] == "untraceable_number")


def test_numbers_traced_via_user_material_and_normalisation():
    from ali.reviewer import review_reply, normalize_number

    assert normalize_number("1,234.50") == "1234.5"
    assert normalize_number("0.050") == "0.05"
    rv = review_reply("共 1204 名患者，应答率 45%。", sources=[], evidence_texts=["表格：n=1,204；response 0.45"])
    assert rv["ok"] and rv["stats"]["traced_numbers"] == 2


def test_quantities_are_info_and_one_claim_per_number():
    from ali.reviewer import review_reply

    rv = review_reply("孵育 30 min，浓度 5 mg/mL，IC50 = 7.5 nM。", sources=SOURCES)
    by_text = {i["text"]: i["severity"] for i in rv["issues"]}
    assert by_text["IC50 = 7.5"] == "warn"
    assert by_text["5 mg/mL"] == "info"
    assert not any(t.startswith("7.5") for t in by_text)  # not reported twice


def test_simple_chat_and_empty_are_skipped():
    from ali.reviewer import review_reply

    assert review_reply("你好！很高兴见到你 99%", simple_chat=True)["skipped"] is True
    assert review_reply("   ")["skipped"] is True


def test_online_verification_merges_results():
    from ali.reviewer import apply_online_results, review_reply, verify_identifiers_online

    def fetch(url):
        if "crossref" in url and "nature12373" in url:
            return json.dumps({"message": {"DOI": "10.1038/nature12373", "title": ["Nanometre-scale thermometry"]}})
        if "crossref" in url:
            raise OSError("HTTP Error 404: Not Found")
        if "esummary" in url:
            return json.dumps({"result": {"uids": ["123", "99999999"], "123": {"title": "Real paper"},
                                          "99999999": {"error": "cannot get document summary"}}})
        raise AssertionError(url)

    rv = review_reply("doi:10.1038/nature12373 doi:10.1000/fake PMID: 123 PMID: 99999999", sources=SOURCES)
    res = verify_identifiers_online(rv["identifiers"], fetch=fetch)
    got = {(r["kind"], r["id"]): r["resolved"] for r in res}
    assert got == {("doi", "10.1038/nature12373"): True, ("doi", "10.1000/fake"): False,
                   ("pmid", "123"): True, ("pmid", "99999999"): False}
    merged = apply_online_results(rv, res)
    unresolved = sorted(i["text"] for i in merged["issues"] if i["kind"] == "unresolved_identifier")
    assert unresolved == ["PMID 99999999", "doi:10.1000/fake"]
    assert merged["ok"] is False and merged["online"]["results"] == res


def test_unreachable_service_is_unknown_not_wrong():
    from ali.reviewer import apply_online_results, verify_identifiers_online

    res = verify_identifiers_online({"doi": ["10.1038/x"], "pmid": ["1"]}, fetch=lambda u: (_ for _ in ()).throw(OSError("blocked")))
    assert all(r["resolved"] is None for r in res)
    assert apply_online_results({"issues": []}, res)["ok"] is True


def test_review_message_persists_on_session():
    from ali import provenance, reviewer
    from ali import sessions as store

    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        (tmp_p / "sessions").mkdir()
        with mock.patch.object(store, "SESSIONS_DIR", tmp_p / "sessions"), \
                mock.patch.object(store, "ensure_state_dirs", lambda: None), \
                mock.patch.object(provenance, "PROV_DIR", tmp_p / "prov"), \
                mock.patch("ali.audit.log_event", lambda *a, **k: None):
            s = store.create_session(title="rv")
            store.append_messages(s.id, {"role": "user", "content": "q"},
                                  {"id": "a1", "role": "assistant", "content": "结论 [5]，p = 0.2"})
            rv = reviewer.review_message(s.id, "a1")
            saved = [m for m in store.get_session(s.id).messages if m.get("id") == "a1"][0]
    assert saved["review"] == rv
    assert ("citation_without_sources", "warn") in _kinds(rv)


def test_design_parameters_are_not_untraceable_facts():
    from ali.reviewer import review_reply

    src = [{"title": "Irisin by MS", "url": "https://pubmed.ncbi.nlm.nih.gov/26278051/", "snippet": "irisin 3.6 ng/ml"}]
    text = ("样本量：统计功效 80%，考虑 20% 脱落率 → 每组需 64 人；干预强度 60–75% 最大心率；报告 95%置信区间。"
            "另据研究，运动可使鸢尾素升高约 15–30%。")
    rv = review_reply(text, sources=src)
    kinds = {(i["kind"], i["text"]) for i in rv["issues"]}
    assert ("design_parameter", "80%") in kinds and ("design_parameter", "20%") in kinds
    assert ("design_parameter", "95%") in kinds
    # a factual effect size with no source is still a warning
    assert any(i["kind"] == "untraceable_number" and i["severity"] == "warn" and "15" in i["text"] for i in rv["issues"])


def test_named_references_must_be_among_the_sources():
    from ali.reviewer import review_reply

    src = [{"title": "Detection and Quantitation of Circulating Human Irisin", "url": "https://pubmed.ncbi.nlm.nih.gov/26278051/",
            "snippet": "[2015] · Cell Metab · Jedrychowski MP, Wrann CD, Paulo JA"}]
    rv = review_reply("Jedrychowski et al. 用质谱测到 irisin [1]；Jensen 等（2015）则认为 ELISA 不可靠。", sources=src)
    refs = [i["text"] for i in rv["issues"] if i["kind"] == "unverified_reference"]
    assert refs == ["Jensen et al."] and rv["ok"] is False
    # without retrieved sources there is nothing to check against
    assert not any(i["kind"] == "unverified_reference" for i in review_reply("Jensen et al. 2015", sources=[])["issues"])


def test_design_parameter_in_a_table_row_and_pubmed_relevance_sort(monkeypatch):
    from ali import search_extensions as se
    from ali.reviewer import review_reply

    rv = review_reply("| 参数 | 数值 |\n|---|---|\n| 失访率 | 20% | 考虑运动干预依从性 |\n| 效应 | 升高 35% |",
                      sources=[{"title": "t", "url": "https://pubmed.ncbi.nlm.nih.gov/1/", "snippet": "irisin"}])
    kinds = {(i["kind"], i["text"]) for i in rv["issues"]}
    assert ("design_parameter", "20%") in kinds and ("untraceable_number", "35%") in kinds

    urls = []
    monkeypatch.setattr(se, "_fetch", lambda url, **k: urls.append(url) or '{"esearchresult": {"idlist": []}}')
    se.search_pubmed("irisin exercise")
    assert "sort=relevance" in urls[0]
