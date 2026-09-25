"""Tests for source grading, the evidence digest and cross-source accuracy checks."""

from __future__ import annotations

from unittest import mock

SOURCES = [
    {"n": 1, "title": "TP53 突变约占 50% 的人类肿瘤", "url": "https://www.nature.com/articles/a", "snippet": "2023 综述", "source": "bing"},
    {"n": 2, "title": "Review", "url": "https://pubmed.ncbi.nlm.nih.gov/1/", "snippet": "TP53 突变约占 50% 的肿瘤 (2021-06-01)", "source": "pubmed"},
    {"n": 3, "title": "知乎回答", "url": "https://www.zhihu.com/question/1", "snippet": "TP53 突变约占 30% 的肿瘤", "source": "baidu"},
]


# ── source grading ─────────────────────────────────────────────────────


def test_classify_source_tiers():
    from ali.source_quality import classify_source, is_authoritative

    cases = {
        "https://www.nhc.gov.cn/x": "official", "https://www.who.int/news": "official",
        "https://www.tsinghua.edu.cn/a": "official", "https://www.cas.cn/": "official",
        "https://www.uniprot.org/uniprotkb/P04637": "database", "https://www.ncbi.nlm.nih.gov/geo/": "database",
        "https://pubmed.ncbi.nlm.nih.gov/123/": "academic", "https://doi.org/10.1/x": "academic",
        "https://www.biorxiv.org/content/1": "academic",
        "https://www.reuters.com/world/": "news", "https://www.thepaper.cn/news": "news",
        "https://www.zhihu.com/q/1": "ugc", "https://blog.csdn.net/x": "ugc", "https://baike.baidu.com/item/x": "ugc",
        "https://example.com/": "other",
    }
    for url, tier in cases.items():
        assert classify_source(url)["tier"] == tier, url
    pre = classify_source("https://www.biorxiv.org/content/1")
    assert pre["preprint"] and pre["label_zh"] == "预印本" and pre["score"] < classify_source("https://doi.org/x")["score"]
    assert classify_source("", engine="uniprot")["tier"] == "database"
    assert is_authoritative("https://www.reuters.com/a") and is_authoritative("https://www.fifa.com/")
    assert not is_authoritative("https://www.zhihu.com/q") and not is_authoritative("https://example.com")


def test_extract_date_prefers_most_specific_latest():
    from ali.source_quality import extract_date

    assert extract_date("发布于 2024年3月5日，更新 2023-01-02") == "2024-03-05"
    assert extract_date("https://x.org/2021/07/post") == "2021-07"
    assert extract_date("Published 2019, revised 2022") == "2022"
    assert extract_date("version 3.14, no year") == ""
    assert extract_date("", "snippet 2020") == "2020"


# ── facts & evidence ───────────────────────────────────────────────────


def test_extract_facts_kinds_keys_and_years_skipped():
    from ali.evidence import extract_facts

    facts = extract_facts("TP53 突变约占 50% 的肿瘤。Response rate was 63% (p = 0.01), n = 120, HR 0.71. 成立于 2020 年，共 30 mg。")
    by_display = {f["display"]: f for f in facts}
    assert by_display["50%"]["key"] == "突变" and by_display["50%"]["kind"] == "percent"
    assert by_display["63%"]["key"] == "response rate"
    assert by_display["HR 0.71"]["kind"] == "statistic" and by_display["HR 0.71"]["key"].startswith("hr")
    assert "30 mg" in by_display and not any(f["value"] == "2020" for f in facts)


def test_build_evidence_corroboration_conflicts_coverage():
    from ali.evidence import build_evidence

    ev = build_evidence("TP53 突变频率", SOURCES, [{"n": 1, "ok": True, "passages": ["TP53 is mutated in 50% of cancers."]}])
    fifty = next(f for f in ev["facts"] if f["key"] == "突变" and f["value"] == "50")
    assert fifty["sources"] == [1, 2] and fifty["domains"] == 2 and fifty["conflict"]
    assert ev["conflicts"][0]["key"] == "突变"
    assert {v["value"] for v in ev["conflicts"][0]["values"]} == {"50", "30"}
    cov = ev["coverage"]
    assert cov == {**cov, "sources": 3, "pages_read": 1, "authoritative": 2, "ugc": 1, "ugc_only": False,
                   "corroborated_facts": 1, "latest_date": "2023"}
    s2 = ev["sources"][1]
    assert s2["tier"] == "academic" and s2["date"] == "2021-06-01" and s2["n"] == 2
    assert ev["sources"][0]["passages"] == ["TP53 is mutated in 50% of cancers."] and ev["sources"][0]["page_read"]


def test_close_values_and_p_values_do_not_conflict():
    from ali.evidence import build_evidence

    srcs = [
        {"title": "rate 42.0%", "url": "https://a.org/1", "snippet": "response rate 42.0% (p = 0.01)"},
        {"title": "x", "url": "https://b.org/2", "snippet": "response rate 42.5% (p = 0.30)"},
    ]
    ev = build_evidence("q", srcs)
    assert ev["conflicts"] == []


def test_render_block_structure_and_ugc_warning():
    from ali.evidence import build_evidence, render_block

    block = render_block(build_evidence("TP53", SOURCES))
    assert block.startswith("## Evidence digest")
    assert "[1] Academic · 2023 · nature.com" in block
    assert "2 independent domains · CONFLICT" in block and "Sources disagree on “突变”" in block
    for part in ("结论摘要", "关键数据", "分歧与不确定", "下一步"):
        assert part in block
    ugc = render_block(build_evidence("q", [SOURCES[2]]))
    assert "All sources are forums" in ugc
    assert render_block(build_evidence("q", [])) == ""


def test_compact_trims_passages():
    from ali.evidence import build_evidence, compact

    ev = build_evidence("q", SOURCES, [{"n": 1, "ok": True, "passages": ["x" * 500, "b", "c"]}])
    c = compact(ev)
    assert len(c["sources"][0]["passages"]) == 2 and len(c["sources"][0]["passages"][0]) == 200


# ── reviewer corroboration ─────────────────────────────────────────────


def test_reviewer_flags_conflict_single_source_and_ugc():
    from ali.evidence import build_evidence
    from ali.reviewer import review_reply

    ev = build_evidence("TP53", SOURCES)
    rv = review_reply("TP53 突变约占 50% 的肿瘤 [1][2]；也有说法为 30% [3]。", sources=SOURCES, evidence=ev)
    kinds = {(i["kind"], i["text"]) for i in rv["issues"]}
    assert ("conflicting_number", "50%") in kinds and ("conflicting_number", "30%") in kinds
    assert rv["ok"] is False
    conflict = next(i for i in rv["issues"] if i["kind"] == "conflicting_number" and i["text"] == "50%")
    assert "30%" in conflict["detail"] and "30%" in conflict["detail_zh"]

    single = [{"title": "Only one", "url": "https://a.org/x", "snippet": "adoption reached 37% in 2024"}]
    rv2 = review_reply("adoption reached 37% [1]", sources=single, evidence=build_evidence("q", single))
    assert [(i["kind"], i["severity"]) for i in rv2["issues"]] == [("single_source_number", "info")]
    assert rv2["ok"] is True

    rv3 = review_reply("结论见 [1]", sources=[SOURCES[2]], evidence=build_evidence("q", [SOURCES[2]]))
    assert any(i["kind"] == "ugc_only_sources" for i in rv3["issues"])


def test_reviewer_without_evidence_is_unchanged():
    from ali.reviewer import review_reply

    rv = review_reply("TP53 突变约占 50% 的肿瘤 [1]", sources=SOURCES)
    assert not any(i["kind"] in ("conflicting_number", "single_source_number") for i in rv["issues"])


# ── form fill agreement ────────────────────────────────────────────────


def test_form_fill_prefers_value_agreed_by_domains():
    from ali import websearch

    results = [
        {"title": "Lab", "snippet": "contact: wrong@old.org", "url": "https://old.org/a"},
        {"title": "Lab page", "snippet": "email lab@suat.edu.cn", "url": "https://www.suat-sz.edu.cn/lab"},
        {"title": "Directory", "snippet": "Lab@SUAT.edu.cn office", "url": "https://dir.example.com/x"},
    ]
    picked = websearch._extract_field("邮箱 email", results)
    assert picked["value"].lower() == "lab@suat.edu.cn" and picked["confidence"] == "high" and picked["domains"] == 2
    assert picked["alternatives"] == ["wrong@old.org"]
    one = websearch._extract_field("email", results[:1])
    assert one["confidence"] == "medium"
    text = websearch._extract_field("研究方向", [{"title": "x", "snippet": "研究方向：肌肉因子。其他", "url": "https://a"}])
    assert text["value"] == "研究方向：肌肉因子" and text["confidence"] == "medium"
    assert websearch._extract_field("研究方向", [])["confidence"] == "low"

    with mock.patch.object(websearch, "search_web", return_value={"ok": True, "results": results}):
        out = websearch.fill_form_from_search("lab", ["邮箱"])
    assert out["fields"][0]["confidence"] == "high" and out["fields"][0]["agreeing_domains"] == 2
