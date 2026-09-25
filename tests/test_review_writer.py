"""Review writer: PubMed parsing, citation renumbering, and one offline end-to-end run."""

from __future__ import annotations

import json
import re

import pytest

from ali import review_writer as rw

XML = """<?xml version="1.0"?>
<PubmedArticleSet>
 <PubmedArticle>
  <MedlineCitation><PMID>27669143</PMID>
   <Article>
    <Journal><JournalIssue><Volume>5</Volume><PubDate><Year>2016</Year></PubDate></JournalIssue>
     <ISOAbbreviation>Elife</ISOAbbreviation></Journal>
    <ArticleTitle>Thrombospondin expression in myofibers stabilizes muscle membranes.</ArticleTitle>
    <ELocationID EIdType="pii">e17589</ELocationID>
    <ELocationID EIdType="doi">10.7554/eLife.17589</ELocationID>
    <Abstract><AbstractText Label="BACKGROUND">Skeletal muscle is sensitive.</AbstractText>
     <AbstractText>Thbs4 overexpression protected dystrophic mice.</AbstractText></Abstract>
    <AuthorList><Author><LastName>Vanhoutte</LastName><Initials>D</Initials></Author>
     <Author><LastName>Molkentin</LastName><Initials>JD</Initials></Author></AuthorList>
    <PublicationTypeList><PublicationType>Journal Article</PublicationType></PublicationTypeList>
   </Article>
  </MedlineCitation>
 </PubmedArticle>
</PubmedArticleSet>"""


def test_parse_and_format_reference():
    [rec] = rw.parse_pubmed_xml(XML)
    assert rec["pmid"] == "27669143" and rec["doi"] == "10.7554/eLife.17589" and rec["pages"] == "e17589"
    assert rec["abstract"].startswith("BACKGROUND: Skeletal") and not rec["review"]
    ref = rw.format_reference(rec)
    assert ref == ("Vanhoutte D, Molkentin JD. Thrombospondin expression in myofibers stabilizes muscle membranes. "
                   "Elife. 2016;5:e17589. doi:10.7554/eLife.17589 PMID: 27669143")


def test_renumber_ranges_parentheses_and_unknown_ids():
    texts, order = rw.renumber(["A [R3–R5] and (R9, R2). B [R2][R99] end [R99]."], {2, 3, 4, 5, 9})
    assert texts == ["A [1, 2, 3] and [4, 5]. B [5] end."] and order == [3, 4, 5, 9, 2]
    chk = rw.validate_citations(texts, 5)
    assert chk["cited"] == 5 and not chk["out_of_range"] and not chk["uncited"]
    assert rw.validate_citations(["x [7]"], 5)["out_of_range"] == [7]


def test_extract_json_and_clean_section():
    assert rw.extract_json('Sure:\n```json\n[{"a": 1}]\n```') == [{"a": 1}]
    assert rw.extract_json('prose {"x": [1, {"y": 2}]} tail') == {"x": [1, {"y": 2}]}
    with pytest.raises(ValueError):
        rw.extract_json("no json here")
    out = rw.clean_section("## Intro\n\n**Bold** claim [R1].\n- item *x*\n\nReferences\n[1] junk", "Intro")
    assert out == "Bold claim [R1].\nitem x"


class FakeLLM:
    """Answers each pipeline prompt by its shape; cites every card it is shown."""

    provider, model, base_url = "stub", "stub-model", "http://stub"

    def __init__(self):
        self.calls = 0
        self.systems = []

    def __call__(self, system, user, *, max_tokens=6000, temperature=0.3):
        self.calls += 1
        self.systems.append(system)
        ids = sorted({int(x) for x in re.findall(r"\[R(\d+)\]", user)})
        if "PubMed queries" in user:
            return '["thbs4 muscle", "thbs4 ageing"]'
        if "screen papers" in system:
            pmids = re.findall(r"PMID (\d+)", user)
            return json.dumps([{"pmid": p, "relevance": 3, "finding": f"finding {p}", "model": "mouse",
                                "section": "muscle"} for p in pmids])
        if "Design the review" in user:
            half = max(1, len(ids) // 2)
            return json.dumps({"title": "THBS4 review", "sections": [
                {"heading": "Introduction", "goal": "g", "cards": ids[:half], "words": 300},
                {"heading": "Critical perspectives and controversies", "goal": "g", "cards": ids[half:], "words": 300}]})
        if "most important primary studies" in user:
            return json.dumps([{"card": i, "model": "mouse", "finding": "f", "limitation": "l"} for i in ids[:3]])
        if "peer reviewer" in user or "Review this manuscript" in user:
            return "Summary assessment\n\nMajor comments\n1. Over-claims myokine status.\n\nMinor comments\n1. Typo."
        if "abstract (200-250 words" in user:
            return '{"abstract": "An abstract.", "keywords": ["THBS4", "myokine"]}'
        if "Response to reviewers" in user:
            return "## Response\n\nAddressed."
        return "## Heading\n\nTHBS4 is expressed in muscle " + " ".join(f"[R{i}]" for i in ids) + ". However, causality is unproven."


def test_run_end_to_end_offline(tmp_path, monkeypatch):
    pytest.importorskip("docx")
    recs = []
    for n in range(1, 46):
        [r] = rw.parse_pubmed_xml(XML)
        recs.append({**r, "pmid": str(1000 + n), "title": f"Paper {n}"})
    monkeypatch.setattr(rw, "pubmed_search", lambda q, retmax=25: [r["pmid"] for r in recs])
    monkeypatch.setattr(rw, "pubmed_fetch", lambda pmids: [r for r in recs if r["pmid"] in pmids])
    from ali import agents

    monkeypatch.setattr(agents, "upsert_subagent", lambda spec: {})
    llm = FakeLLM()
    summary = rw.run("THBS4 in muscle", tmp_path, seed_queries=["thbs4"], seed_pmids=["1001"], min_refs=40,
                     max_cards=45, log=lambda m: None, llm=llm)
    assert summary["cards"] == 45 and summary["references"] == 45
    chk = summary["citation_check"]
    assert chk["cited"] == 45 and not chk["out_of_range"] and not chk["uncited"]
    final = (tmp_path / "review_final.md").read_text()
    assert "[R" not in final and "[1" in final and "[45] " in final
    # the three reviewers are the Hub subagents
    assert sum('Agent Hub subagent "Reviewer' in s for s in llm.systems) == 3
    for name in ("review.docx", "draft_v1.md", "reviewer_reports.md", "response_to_reviewers.md", "evidence_cards.json"):
        assert (tmp_path / name).exists(), name
    from docx import Document

    text = "\n".join(p.text for p in Document(str(tmp_path / "review.docx")).paragraphs)
    assert "1. Introduction" in text and "[45] " in text and "Keywords:" in text
