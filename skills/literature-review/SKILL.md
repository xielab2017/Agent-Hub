---
name: literature-review
description: Evidence-grounded critical review on any biomedical topic — PubMed search, screening, drafting, three reviewer subagents, revision, citation audit and a Word manuscript with numbered references.
triggers: literature review, review article, 综述, systematic review, write a review
entry: run.py
origin: agent-hub
---

# Literature review (evidence-grounded, peer-reviewed)

Baseline description shipped with the repository; `POST /api/skills/author` lets the Hub's own model rewrite this
file from the pipeline and a finished run (see `skills/literature-review/` in Agent Hub).

## When to use
A review article, narrative or systematic-style, that must cite real literature inline as [1], [2] … and take a
critical position.

## Inputs
- `--topic "<English topic>"` — the Hub model plans the profile (queries, focus terms, rubric, outline, reviewers,
  table columns); or
- `--profile <name|path>` — a profile from `profiles/` (e.g. `thbs4`, `multiomics-emp`), optionally with a featured
  work (`featured.pmid`) and a competing-interest statement.

## Steps
1. Profile → PubMed queries (seed + model-designed).
2. PubMed E-utilities search and abstracts; model screening (relevance 0-3, one-sentence finding).
3. Evidence cards (focus-term ranking, seed / featured papers first, a few framing reviews).
4. Outline → sections drafted in parallel, citing cards only; Hub reviewer checks each section.
5. Three reviewer subagents (registered in the Hub) → reports; literature they name as missing is searched in
   PubMed, screened and added as new evidence cards.
6. Revision → citation integration (≥ min refs) → per-section citation audit against the cited abstracts.
7. Renumber to [n] by first appearance → abstract, response letter, Word document.

## Outputs
`review.docx`, `review_final.md`, `draft_v1.md`, `reviewer_reports.md`, `response_to_reviewers.md`,
`citation_audit.json`, `evidence_cards.json`, `summary.json`, `llm_trace.jsonl`, `checkpoints/`.

## Quality gates
Every [n] maps to a reference and every reference is cited; ≥ `--min-refs` distinct references; no card ids or
meta text in the prose; references are built from PubMed records, never from the model.

## Recovery
Re-run with the same arguments: finished stages are reused from `checkpoints/`; `--fresh` starts over;
`--smoke` checks every stage at small scale.
