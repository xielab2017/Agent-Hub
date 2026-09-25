---
name: literature-review
description: Evidence-grounded biomedical literature review: PubMed search, screening, drafting with [R-id] citations, three reviewer subagents, revision, citation audit, and a Word manuscript with [1]…[N] references.
triggers: literature review, review article, systematic review, narrative review, critical review, write a review, 综述, 系统综述, 循证综述, 文献综述, 写综述
entry: run.py
origin: agent-hub-authored
authored_by: minimax-cn/MiniMax-M3
authored_at: 2026-09-25T19:29:26Z
---

# Literature review (evidence-grounded, peer-reviewed)

A pipeline that searches PubMed (E-utilities), screens abstracts, builds evidence cards, drafts the review in parallel sections, routes the draft through three Agent Hub reviewer subagents, revises and integrates citations, audits every `[n]` against the cited abstracts, and renders a `.docx`. Everything routes through Agent Hub: the configured model via `llm_client`, the network via `websearch._http`, reference checks via `reviewer`, and the three reviewers are registered Agent Hub subagents.

## When to use

A review article (narrative, systematic-style or critical appraisal) that must cite real literature inline as `[1]`, `[2]` …, take a critical position, and survive a structured peer-review pass before the Word manuscript is produced. Not for unstructured essays, opinion pieces, or outputs that should not be grounded in PubMed records.

## Inputs

CLI arguments (consumed by `run.py`):

- `--topic "<English topic>"` — when no profile is given, the model plans the profile itself (queries, focus terms, screen rubric, outline, reviewer list, table columns).
- `--profile <name|path>` — a profile from `profiles/` (bundled: `multiomics-emp`, `thbs4`) or a path to a profile JSON/YAML. Optional `--profile` overrides win over model planning.
- `--fresh` — discard `checkpoints/` and start over.
- `--smoke` — run every stage at small scale (used to validate a profile or environment).
- `--min-refs N` — minimum distinct references required to pass (default is the profile's value).
- `--model <backend/model>` — overrides the Hub default from `backend` / `models` (e.g. `minimax-cn/MiniMax-M3`).

Profile fields (see `DEFAULT_PROFILE` / `load_profile`; fields left at defaults are planned by the model for the topic):

- `topic` — short English topic string.
- `seed_queries` — initial PubMed queries, e.g. `["thbs4 skeletal muscle", "thrombospondin-4 secreted factor"]`.
- `seed_pmids` — PMIDs that must appear in evidence cards, e.g. `["30778219", "33259807"]`.
- `focus_terms` — terms used to rank evidence cards, e.g. `["THBS4", "muscle secreted factor", "ageing", "metabolism"]`.
- `context_terms` — broader terms allowed for framing, e.g. `["exercise", "insulin sensitivity"]`.
- `query_guidance` — extra instructions to the query planner.
- `screen_rubric` — inclusion / exclusion criteria used during abstract screening (relevance 0–3 + one-sentence finding).
- `screen_sections` — section hints used to assign screened records.
- `outline_guidance` — constraints on the model-planned outline (section count, headings, scope).
- `reviewers` — list of three Agent Hub reviewer subagents. The `thbs4` run shipped `reviewer-muscle-biology`, `reviewer-ageing-metabolism`, `reviewer-citation-integrity`.
- `table` — specification of any comparative / summary table columns.
- `featured.pmid` — a PMID that must be cited (a featured work).
- `coi_statement` — competing-interest statement appended to the manuscript.

## Steps

Stages are checkpointed in this exact order: `profile`, `queries`, `records`, `screened`, `outline`, `drafts`, `reviews`, `revised`, `integrated`, `audited`, `table`, `abstract`, `response`.

1. **Profile** — load the named profile or plan one from `--topic`. Produces the effective profile used for the rest of the run.
2. **Queries** — combine `seed_queries` with model-planned queries. Produces the final query list (e.g. 30 queries).
3. **Records** — fetch PubMed records via E-utilities through `websearch._http`. Produces raw records with abstracts (e.g. 336 records).
4. **Screened** — model screens each abstract against `screen_rubric` (relevance 0–3 + one-sentence finding). Produces the screened set (e.g. 324 screened, 85 relevant).
5. **Outline** — model designs the section outline under `outline_guidance`. Produces the section list (e.g. 10 sections) and per-section card budgets.
6. **Drafts** — sections are drafted in parallel; the model cites evidence cards by id (`[R12]`). Each section is checked once by the Hub reviewer against its evidence cards and rewritten once if it cites unknown ids or states untraceable numbers. Produces per-section drafts (10/10).
7. **Reviews** — three registered Agent Hub reviewer subagents produce independent reports (e.g. `reviewer-muscle-biology` 1548 words, `reviewer-ageing-metabolism` 2019 words, `reviewer-citation-integrity` 1268 words). Produces `reviewer_reports.md`.
8. **Revised** — each section is revised in light of the reviewer reports. Produces revised per-section drafts (10/10).
9. **Integrated** — citation integration across sections, ensuring the manuscript reaches at least `min_refs` distinct references. Produces the integrated manuscript body.
10. **Audited** — per-section citation audit: every `[n]` must resolve to an evidence card, every cited card must appear in the reference list, no card ids (`[R12]`) or meta text may leak into the prose. Produces `citation_audit.json` (e.g. 32 unsupported citations corrected).
11. **Table** — generate the comparative / summary table per `table` columns. Produces the table artefact.
12. **Abstract** — generate the structured abstract from the audited manuscript. Produces the abstract section.
13. **Response** — produce a point-by-point response to the three reviewer reports. Produces `response_to_reviewers.md`.

Citation handling across stages: the reference list is built from PubMed records' own metadata, never from the model. Card ids (`[R12]`) are renumbered to `[1] … [N]` in order of first appearance; a card that is never cited is not listed.

## Outputs

- `review.docx` — final Word manuscript with numbered references `[1] … [N]`.
- `review_final.md` — final manuscript in Markdown.
- `draft_v1.md` — first-pass assembled draft before the audit / response pass.
- `reviewer_reports.md` — concatenated reports from the three reviewer subagents.
- `response_to_reviewers.md` — point-by-point responses.
- `citation_audit.json` — per-section citation audit (`cited`, `references`, `out_of_range`, `uncited`, `citations`).
- `evidence_cards.json` — the cards used to ground the manuscript.
- `summary.json` — top-line run summary (title, model, queries, records, cards, sections, references, citation_check, words).
- `llm_trace.jsonl` — full LLM call trace.
- `checkpoints/` — per-stage checkpoints (`profile`, `queries`, `records`, `screened`, `outline`, `drafts`, `reviews`, `revised`, `integrated`, `audited`, `table`, `abstract`, `response`) for resume.

## Quality gates

- Every inline `[n]` maps to a reference in the reference list, and every reference in the reference list is cited at least once (`uncited == []`, `out_of_range == []`).
- The manuscript carries at least `--min-refs` distinct references.
- No evidence-card ids (`[R12]`, etc.) or pipeline meta text appear in the prose.
- The reference list is built from PubMed records' own metadata; the model is not allowed to invent references.
- The per-section Hub reviewer check passes (or the section has been rewritten once and now passes).
- Citation audit reports zero unsupported citations after correction.
- Run-level result line: `RESULT: PASS — N distinct references cited` (e.g. `RESULT: PASS — 59 distinct references cited`).

## Recovery

- Re-running `run.py` with the same arguments resumes from `checkpoints/`: any stage whose checkpoint exists is reused. The log line `resumed from checkpoint` confirms the stage was skipped.
- `--fresh` deletes `checkpoints/` and re-runs every stage from scratch.
- `--smoke` exercises every stage at a small scale (fewer queries, fewer records, fewer cards, fewer sections) and is the recommended pre-flight for a new profile or a new environment.
- Per-stage `resumed from checkpoint` markers in `run-log.txt` indicate which stages did and did not re-execute; `summary.json` is the canonical record of the final state.

## Transfer

Exporting from the source Agent Hub:

- The skill lives at `skills/literature-review/` in Agent Hub; copy that directory (containing `run.py`, `SKILL.md`, `profiles/`, and the writer module under `ali/`) to the target Agent Hub.
- Bundled profiles (`multiomics-emp`, `thbs4`) ship inside `profiles/` and can be used as-is or as templates for new topics.
- A finished run's `summary.json`, `citation_audit.json` and `llm_trace.jsonl` are the canonical artefacts to attach when redistributing the skill as a reference run.

Installing on another Agent Hub:

- Place the skill under `skills/literature-review/` and ensure it is discoverable by `POST /api/skills` (or by the Hub's skill indexer). The skill is then invokable like any other Hub skill with `entry: run.py`.
- The target Hub must provide:
  - A configured chat model under `backend` / `models` (the run-log example uses `minimax-cn` at `https://api.minimaxi.com/v1` with model `MiniMax-M3`); reachable via the Hub's `llm_client`.
  - Outbound HTTP for PubMed E-utilities via `websearch._http`.
  - The reference-check helper `reviewer`.
  - Three reviewer subagents registered in the Hub, named in the profile's `reviewers` field (the `thbs4` profile registers `reviewer-muscle-biology`, `reviewer-ageing-metabolism`, `reviewer-citation-integrity`).
  - Python dependencies required to render `.docx` (the same stack used by `ali/review_writer.py`).
- After install, run `python run.py --profile thbs4 --smoke` to verify every stage executes end-to-end on the target Hub before a full run.
