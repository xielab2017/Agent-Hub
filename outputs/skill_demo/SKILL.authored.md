---
name: literature-review
description: Evidence-grounded biomedical literature review — PubMed search, screening, drafting, three reviewer subagents, revision, citation audit and a Word manuscript with numbered references.
triggers: literature review, review article, systematic review, narrative review, write a review, critical review, 综述, 文献综述, 撰写综述, 系统综述
entry: run.py
origin: agent-hub-authored
authored_by: minimax-cn/MiniMax-M3
authored_at: 2026-09-25T20:38:08Z
---

# Literature review (evidence-grounded, peer-reviewed)

## When to use
A biomedical review article — narrative, systematic-style or critical appraisal — that must cite real literature inline as `[1]`, `[2]` … and take a critical position. The reference list is built from PubMed records (E-utilities), never from the model; the model cites evidence cards by id and ids are renumbered to `[n]` in order of first appearance. A card that is never cited is not listed. Each section is checked by the Hub reviewer against its evidence cards and rewritten once when it cites unknown ids or states untraceable numbers.

## Inputs
CLI arguments (the only ones supported):
- `--topic "<English topic>"` — the Hub model plans the profile (queries, focus terms, screen rubric, outline, reviewers, table columns).
- `--profile <name|path>` — a profile from `profiles/` (bundled: `multiomics-emp`, `thbs4`), or a path to a YAML file.
- `--max-cards N` — cap on the number of evidence cards.
- `--min-refs N` — minimum number of distinct references required to pass the quality gate.
- `--out <dir>` — output directory.
- `--fresh` — ignore `checkpoints/` and start over from stage 1.
- `--smoke` — exercise every stage at small scale to verify the pipeline end-to-end.
- `--help` — show usage.

Profile fields (YAML keys inside a profile file; not command-line options). Fields the profile leaves at defaults are planned by the model for the topic:
- `topic:` — review topic.
- `seed_queries:` — initial PubMed queries.
- `seed_pmids:` — initial PMIDs (e.g. a landmark paper).
- `focus_terms:` — terms used to rank evidence cards.
- `context_terms:` — broader terms that frame the review.
- `query_guidance:` — guidance for the model when designing additional queries.
- `screen_rubric:` — relevance rubric used during screening.
- `screen_sections:` — section list used to bias screening.
- `outline_guidance:` — guidance for outline design.
- `reviewers:` — list of Hub subagent names used as the three reviewers.
- `table:` — comparative / summary table column specification.
- `featured:` — a featured work (e.g. `featured.pmid`) surfaced during ranking.
- `coi_statement:` — competing-interest statement.

Examples:
```
python run.py --topic "Thrombospondin-4 in skeletal muscle ageing" --min-refs 40
python run.py --profile thbs4 --min-refs 50
python run.py --profile multiomics-emp --max-cards 80 --fresh
python run.py --smoke
```

## Steps
Stages are checkpointed in this order; a re-run resumes from the first incomplete stage.

1. **profile** — load or plan the profile (topic, seeds, focus terms, rubric, outline guidance, reviewers, table, featured work, COI). Produces the effective profile used downstream.
2. **queries** — combine seed queries with model-designed PubMed queries. Produces the final query list (e.g. 30 queries).
3. **records** — PubMed E-utilities search and abstract fetch. Produces the raw record set (e.g. 336 records with abstracts).
4. **screened** — model screens each record (relevance 0–3 plus a one-sentence finding). Produces the screened set (e.g. 324 screened, 85 relevant).
5. **outline** — section outline planned by the model from the profile. Produces the section list (e.g. 10 sections).
6. **drafts** — sections drafted in parallel, citing evidence cards only. Produces per-section drafts.
7. **reviews** — three reviewer subagents (registered in Agent Hub) write reports. Produces `reviewer_reports.md` (e.g. reviewer-muscle-biology, reviewer-ageing-metabolism, reviewer-citation-integrity).
8. **gaps** — literature named by the reviewers as missing is searched in PubMed, screened and added as new evidence cards.
9. **revised** — each section is rewritten once when the reviewer flags unknown card ids or untraceable numbers.
10. **integrated** — sections are stitched into a single manuscript and renumbered to `[n]` by order of first appearance; uncited cards are dropped.
11. **audited** — per-section citation audit against the cited abstracts. Produces `citation_audit.json`; unsupported citations are corrected (e.g. 32 corrected in the bundled run).
12. **table** — comparative / summary table built per the profile.
13. **abstract** — abstract drafted against the integrated manuscript.
14. **response** — point-by-point response letter to the three reviewers. Produces `response_to_reviewers.md`.

## Outputs
- `review.docx` — final Word manuscript with numbered references.
- `review_final.md` — final Markdown manuscript.
- `draft_v1.md` — first integrated draft before revision.
- `reviewer_reports.md` — reports from the three reviewer subagents.
- `response_to_reviewers.md` — point-by-point response letter.
- `citation_audit.json` — per-section citation audit results.
- `evidence_cards.json` — the evidence cards used.
- `summary.json` — run summary (`title`, `model`, `llm_calls`, `queries`, `records`, `cards`, `sections`, `references`, `citation_check`, `words`).
- `llm_trace.jsonl` — LLM call trace.
- `checkpoints/` — per-stage checkpoints for resume.

## Quality gates
- Every `[n]` in the prose maps to a reference in the reference list, and every reference is cited at least once (`cited == references`, `out_of_range == []`, `uncited == []`).
- ≥ `--min-refs` distinct references in the final manuscript.
- No raw evidence-card ids (e.g. `[R12]`) and no meta text appear in the prose.
- The reference list is built from PubMed record metadata, never generated by the model.
- A card that is never cited is not listed as a reference.
- Each section passes the Hub reviewer's check against its evidence cards (no unknown ids, no untraceable numbers); otherwise it is rewritten once.
- The bundled thbs4 run ships at `summary.json`: `cited: 59, references: 59, out_of_range: [], uncited: [], citations: 257` across 9,204 words → `RESULT: PASS`.

## Recovery
- Re-running `run.py` with the same arguments reuses finished stages from `checkpoints/` and resumes from the first incomplete stage in this order: profile → queries → records → screened → outline → drafts → reviews → gaps → revised → integrated → audited → table → abstract → response.
- `--fresh` deletes or ignores `checkpoints/` and starts the pipeline over from stage 1.
- `--smoke` exercises every stage at small scale to verify the pipeline without producing a full manuscript.

## Transfer
- The skill is bundled in `skills/literature-review/` on the source Agent Hub (entry `run.py`, plus `profiles/`).
- On the target Hub, install via the skill installer / `POST /api/skills/install` with the bundle, then ensure:
  - the configured model (`backend` / `models`, e.g. `minimax-cn/MiniMax-M3`) is reachable through `llm_client`;
  - outbound HTTP via `websearch._http` reaches the PubMed E-utilities endpoints;
  - the reference checker `reviewer` is available;
  - the three reviewer subagents are registered in the target Hub under the names listed in the profile's `reviewers:` field;
  - bundled profiles (`profiles/multiomics-emp`, `profiles/thbs4`) and any additional profiles are copied alongside `run.py` so `--profile <name>` resolves.
