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


def test_card_ids_and_focus_ranking():
    assert [rw._card_id(x) for x in (12, "12", "R12", "[R12]", "x")] == [12, 12, 12, 12, 0]
    base = rw.parse_pubmed_xml(XML)[0]
    recs = [{**base, "pmid": "1", "title": "Omics of the heart", "abstract": "many genes incl. THBS4", "year": "2025"},
            {**base, "pmid": "2", "title": "Thrombospondin-4 in muscle", "abstract": "THBS4 THBS4", "year": "2010"},
            {**base, "pmid": "3", "title": "Unrelated", "abstract": "no mention", "year": "2024"},
            {**base, "pmid": "4", "title": "Myokines review", "abstract": "muscle secretome", "year": "2020",
             "review": True},
            {**base, "pmid": "5", "title": "Seed paper", "abstract": "Thbs1 only", "year": "2019"}]
    screened = {"1": {"relevance": 2}, "2": {"relevance": 2}, "3": {"relevance": 2}, "4": {"relevance": 1},
                "5": {"relevance": 2}}
    cards = rw.evidence_cards(recs, screened, limit=10, focus=r"THBS-?4|thrombospondin-4", seeds=["5"])
    assert [c["pmid"] for c in cards] == ["5", "2", "1", "4"]  # seed, title mention, abstract mention, context
    screened["6"] = {"relevance": 3}
    recs.append({**base, "pmid": "6", "title": "Thrombospondin-4 again", "abstract": "THBS4", "year": "2026"})
    top = rw.evidence_cards(recs, screened, limit=2, focus=r"THBS-?4|thrombospondin-4", seeds=["5"], context_slots=0)
    assert [c["pmid"] for c in top] == ["5", "6"]  # a relevance-2 seed still outranks a relevance-3 paper


def test_map_card_ids_to_final_numbers():
    out = rw.map_card_ids("R45 is misread; see [R12, R3] and (R7). R99 too.", [3, 12, 45])
    assert out == "ref. 3 is misread; see [ref. 2; ref. 1] and [an uncited source (card 7)]. an uncited source (card 99) too."


def test_prose_checks_and_scrub():
    text = "The R9 model [R9] shows (R3, R4) effects. This claim is supported by evidence card [R2]."
    problems = rw.prose_problems(text)
    assert any("card ids used as words (R9)" in p or "(R9)" in p for p in problems)
    assert any("meta text" in p for p in problems)
    assert rw.prose_problems("THBS4 stabilises the sarcolemma [R2] in mice [R3, R4].") == []
    assert rw.scrub_prose("derives from R44 rather than R35 [R1–R2].") == "derives from ref. [R44] rather than ref. [R35] [R1, R2]."


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
                {"heading": "1. Introduction", "goal": "g", "cards": [f"R{i}" for i in ids[:half]], "words": 300},
                {"heading": "Critical perspectives and controversies", "goal": "g", "cards": ids[half:], "words": 300}]})
        if "most important primary studies" in user:
            return json.dumps([{"card": i, "model": "mouse", "finding": "f", "limitation": "l"} for i in ids[:3]])
        if "peer reviewer" in user or "Review this manuscript" in user:
            return "Summary assessment\n\nMajor comments\n1. Over-claims myokine status.\n\nMinor comments\n1. Typo."
        if "fact-checker" in system:
            return '[{"sentence": "THBS4 is expressed in muscle.", "cards": [1], "issue": "overstated", "fix": "reword"}]'
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
    assert sum("fact-checker" in s for s in llm.systems) == 2  # one citation audit per section
    audit = json.loads((tmp_path / "citation_audit.json").read_text())
    assert len(audit) == 2 and audit[0]["issues"][0]["issue"] == "overstated"
    for name in ("review.docx", "draft_v1.md", "reviewer_reports.md", "response_to_reviewers.md", "evidence_cards.json"):
        assert (tmp_path / name).exists(), name
    from docx import Document

    text = "\n".join(p.text for p in Document(str(tmp_path / "review.docx")).paragraphs)
    assert "1. Introduction" in text and "1. 1." not in text and "[45] " in text and "Keywords:" in text


def _offline(monkeypatch, n=45):
    recs = []
    for k in range(1, n + 1):
        [r] = rw.parse_pubmed_xml(XML)
        recs.append({**r, "pmid": str(1000 + k), "title": f"Paper {k}"})
    monkeypatch.setattr(rw, "pubmed_search", lambda q, retmax=25: [r["pmid"] for r in recs])
    monkeypatch.setattr(rw, "pubmed_fetch", lambda pmids: [r for r in recs if r["pmid"] in pmids])
    from ali import agents

    monkeypatch.setattr(agents, "upsert_subagent", lambda spec: {})


def test_run_resumes_from_the_failed_stage(tmp_path, monkeypatch):
    pytest.importorskip("docx")
    _offline(monkeypatch)

    class FailingReviews(FakeLLM):
        def __call__(self, system, user, **kw):
            if "Review this manuscript" in user:
                raise RuntimeError("reviewer call failed")
            return super().__call__(system, user, **kw)

    first = FailingReviews()
    with pytest.raises(RuntimeError, match="reviewer call failed"):
        rw.run("THBS4", tmp_path, seed_queries=["thbs4"], min_refs=40, max_cards=45, log=lambda m: None, llm=first)
    assert (tmp_path / "checkpoints" / "drafts.json").exists() and (tmp_path / "draft_v1.md").exists()

    second, logs = FakeLLM(), []
    summary = rw.run("THBS4", tmp_path, seed_queries=["thbs4"], min_refs=40, max_cards=45, log=logs.append, llm=second)
    assert summary["citation_check"]["cited"] == 45
    assert not any("screen papers" in s for s in second.systems)  # screening, outline and drafts were reused
    assert "drafts: 2/2 resumed from checkpoint" in logs
    # changed parameters discard the checkpoints
    logs.clear()
    rw.run("THBS4", tmp_path, seed_queries=["thbs4"], min_refs=40, max_cards=44, log=logs.append, llm=FakeLLM())
    assert "checkpoints: parameters changed — starting fresh" in logs


def test_per_item_keeps_finished_items_when_one_fails(tmp_path):
    ck = rw.Checkpoints(tmp_path, {"a": 1}, log=lambda m: None)

    def fn(i):
        if i == 1:
            raise ValueError("boom")
        return f"text {i}"

    with pytest.raises(RuntimeError, match="1 of 3 failed"):
        ck.per_item("drafts", 3, fn)
    assert ck.get("drafts") == ["text 0", "", "text 2"]
    assert ck.per_item("drafts", 3, lambda i: f"again {i}") == ["text 0", "again 1", "text 2"]


class ProfileLLM(FakeLLM):
    """FakeLLM that also answers the profile-planning prompt."""

    def __call__(self, system, user, **kw):
        if "design systematic literature reviews" in system:
            self.calls += 1
            self.systems.append(system)
            return json.dumps({
                "focus_terms": ["multi-omics", "integration"], "context_terms": ["software review"],
                "query_guidance": "tools, benchmarks", "screen_rubric": "relevance 3 = a multi-omics tool, 1 = context only",
                "screen_sections": ["tools", "benchmarks", "other"],
                "outline_guidance": "Introduction; Survey of tools; Critical perspectives and controversies; Conclusions",
                "reviewers": [{"id": "Reviewer Bioinformatics", "label": "Reviewer 1 — bioinformatics", "desc": "tools"},
                              {"id": "reviewer-biology", "label": "Reviewer 2 — biology", "desc": "biology"},
                              {"id": "reviewer-editor", "label": "Reviewer 3 — editor", "desc": "citations"}],
                "table": {"title": "Table 1. Tools", "select": "tools", "primary_only": False,
                          "columns": [{"key": "tool", "label": "Tool", "hint": "name"},
                                      {"key": "strengths", "label": "Strengths", "hint": "pros"},
                                      {"key": "limitations", "label": "Limitations", "hint": "cons"}]}})
        if "most important primary studies" in user or "rows for a table" in user:
            ids = sorted({int(x) for x in re.findall(r"\[R(\d+)\]", user)})
            return json.dumps([{"card": i, "tool": f"T{i}", "strengths": "s", "limitations": "l"} for i in ids[:3]])
        return super().__call__(system, user, **kw)


def test_profile_run_plans_fields_features_work_and_states_coi(tmp_path, monkeypatch):
    pytest.importorskip("docx")
    recs = []
    for k in range(1, 46):
        [r] = rw.parse_pubmed_xml(XML)
        recs.append({**r, "pmid": str(1000 + k), "title": f"A multi-omics integration tool {k}"})
    recs.append({**recs[0], "pmid": "40932530", "title": "EasyMultiProfiler: a multi-omics workflow", "year": "2025"})
    monkeypatch.setattr(rw, "pubmed_search", lambda q, retmax=25: [r["pmid"] for r in recs][:40])
    monkeypatch.setattr(rw, "pubmed_fetch", lambda pmids: [r for r in recs if r["pmid"] in pmids])
    from ali import agents

    registered = []
    monkeypatch.setattr(agents, "upsert_subagent", lambda spec: registered.append(spec["id"]) or {})
    llm = ProfileLLM()
    profile = {"topic": "Multi-omics analysis software", "seed_queries": ["multi-omics software"],
               "featured": {"pmid": "40932530", "name": "EasyMultiProfiler", "emphasis": "the authors' workflow"},
               "coi_statement": "The authors developed EasyMultiProfiler."}
    summary = rw.run("", tmp_path, profile=profile, min_refs=40, max_cards=45, log=lambda m: None, llm=llm)
    prof = json.loads((tmp_path / "profile.json").read_text())
    assert prof["focus_terms"] == ["multi-omics", "integration"] and prof["seed_queries"] == ["multi-omics software"]
    assert registered == ["reviewer-bioinformatics", "reviewer-biology", "reviewer-editor"]
    cards = json.loads((tmp_path / "evidence_cards.json").read_text())
    assert cards[0]["pmid"] == "40932530"  # the featured work leads the evidence
    assert summary["featured"]["reference"] is not None
    assert any("features EasyMultiProfiler" in s for s in llm.systems)  # writer note
    from docx import Document

    doc = Document(str(tmp_path / "review.docx"))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "Competing interests" in text and "The authors developed EasyMultiProfiler." in text
    assert [c.text for c in doc.tables[0].rows[0].cells] == ["Ref.", "Tool", "Strengths", "Limitations"]
    assert doc.tables[0].rows[1].cells[1].text.startswith("T")


def test_load_profile_and_terms_regex(tmp_path):
    f = tmp_path / "p.yaml"
    f.write_text("topic: X\nfocus_terms: [multi-omics, MOFA]\nseed_pmids: ['1']\n")
    prof = rw.load_profile(f, seed_pmids=["2"])
    assert prof["topic"] == "X" and prof["seed_pmids"] == ["2"] and prof["reviewers"] == rw.REVIEWERS
    rx = re.compile(rw.terms_regex(prof["focus_terms"]), re.I)
    assert rx.search("a multiomics tool") and rx.search("Multi-omics") and rx.search("MOFA+") and not rx.search("omics")


def test_reviewer_gaps_add_cards_for_missing_literature(monkeypatch):
    base = rw.parse_pubmed_xml(XML)[0]
    recs = {"900": {**base, "pmid": "900", "title": "MOFA: multi-omics factor analysis"},
            "901": {**base, "pmid": "901", "title": "Unrelated"}}
    monkeypatch.setattr(rw, "pubmed_search", lambda q, retmax=3: ["900", "901", "1"] if "MOFA" in q else [])
    monkeypatch.setattr(rw, "pubmed_fetch", lambda pmids: [recs[p] for p in pmids if p in recs])

    def llm(system, user, **kw):
        if "precise PubMed searches" in system:
            return '[{"item": "MOFA", "query": "MOFA multi-omics factor analysis"}, {"item": "x", "query": "none"}]'
        return json.dumps([{"pmid": "900", "relevance": 3, "finding": "f", "model": "m", "section": "tools"},
                           {"pmid": "901", "relevance": 0, "finding": "", "model": "", "section": "other"}])

    cards = [{"id": 1, "pmid": "1", "first_author": "A", "year": "2020", "title": "t"},
             {"id": 7, "pmid": "7", "first_author": "B", "year": "2021", "title": "u"}]
    reviews = [{"label": "R1", "report": "MOFA is missing."}]
    new = rw.reviewer_gaps(llm, "topic", reviews, cards, rubric="r", log=lambda m: None)
    assert [(c["id"], c["pmid"]) for c in new] == [(8, "900")]  # ids continue; irrelevant and known papers skipped


def test_uncited_draft_gets_a_citation_pass():
    cards = [{"id": i, "first_author": "A", "journal": "J", "year": "2020", "title": f"t{i}", "abstract": "a",
              "finding": "f", "model": "m"} for i in (1, 2, 3)]
    calls = []

    def llm(system, user, **kw):
        calls.append(user)
        if "cites no evidence cards" in user:
            return "Hu and colleagues benchmarked tools [R1]. Seurat ranked high [R2, R3]."
        return "Hu and colleagues benchmarked tools. Seurat ranked high."

    sec = {"heading": "Benchmarks", "cards": [1, 2, 3]}
    text = rw.write_section(llm, "t", {"sections": [sec]}, sec, cards, check=lambda t, c: ["too few citations"])
    assert rw.cited_ids(text) == [1, 2, 3] and len(calls) == 3
