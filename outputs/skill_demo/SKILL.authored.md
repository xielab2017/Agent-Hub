---
name: literature-review
description: Evidence-grounded biomedical review — PubMed search, screening, drafting, three reviewer subagents, revision, citation audit, and a Word manuscript with numbered references.
triggers: literature review, review article, narrative review, systematic review, critical review, evidence-grounded review, write a review, PubMed review, 综述, 文献综述, 系统综述, 撰写综述, 写综述
entry: run.py
origin: agent-hub-authored
authored_by: minimax-cn/MiniMax-M3
authored_at: 2026-09-25T19:40:24Z
---

# Literature review (evidence-grounded, peer-reviewed)

## When to use
A review article (narrative or systematic-style) on a biomedical topic that must:
- cite real literature inline as numbered `[1]`, `[2]`, … drawn from PubMed records (E-utilities), never from the model's own knowledge;
- take a critical position grounded in the cited evidence;
- pass through three reviewer subagents and a per-section citation audit before delivery.

## Inputs

CLI arguments (forwarded to `run.py`):
- `--topic "<English topic>"` — when no profile is supplied, the Hub model plans the profile fields (queries, focus terms, rubric, outline, reviewers, table columns) from the topic.
- `--profile <name|path>` — a topic-specific profile. Bundled profiles in `profiles/`: `multiomics-emp`, `thbs4`.
- `--min-refs <N>` — minimum number of distinct references required in the final manuscript (quality gate).
- `--fresh` — ignore `checkpoints/` and re-run every stage from scratch.
- `--smoke` — run every stage at small scale as a pipeline sanity check.

Profile fields (from `DEFAULT_PROFILE` / `load_profile`; fields left at defaults are planned by the Hub model for the topic):
- `topic` — the review's subject.
- `seed_queries` — initial PubMed query strings.
- `seed_pmids` — PMIDs of must-include papers.
- `focus_terms` — terms used to rank evidence cards.
- `context_terms` — terms used for background / framing.
- `query_guidance` — free-text guidance for query design.
- `screen_rubric` — rubric used by the model to screen records (relevance 0–3 plus one-sentence finding).
- `screen_sections` — preliminary section buckets used during screening.
- `outline_guidance` — free-text guidance for the outline.
- `reviewers` — list of three reviewer-subagent names registered in Agent Hub (e.g. `reviewer-muscle-biology`, `reviewer-ageing-metabolism`, `reviewer-citation-integrity`).
- `table` — specification of the featured / comparison table.
- `featured` — object whose `pmid` names a featured work to surface prominently.
- `coi_statement` — competing-interest statement to include in the manuscript.

Example invocations:
```
python run.py --topic "Thrombospondin-4 in skeletal muscle ageing" --min-refs 30
python run.py --profile thbs4 --min-refs 50
```

## Steps

Stages run in order, each writing a checkpoint under `checkpoints/`:

1. **profile** — resolve the effective profile (CLI + named profile + topic-driven planning) and write `profile.json`. Produces the topic-specific configuration that drives every later stage.
2. **queries** — assemble the PubMed query list from `seed_queries` plus model-designed queries guided by `focus_terms`, `context_terms`, and `query_guidance`. Produces `queries.json`.
3. **records** — fetch records and abstracts from PubMed via E-utilities (`websearch._http`). Produces `records.json` (one entry per PMID with abstract).
4. **screened** — model screens every record against `screen_rubric`, assigning relevance 0–3 and a one-sentence finding. Produces `screened.json`.
5. **outline** — model plans the section structure (guided by `outline_guidance` and `screen_sections`). Produces `outline.json`.
6. **drafts** — sections are drafted in parallel. Each section cites evidence cards by id (`[R12]`); a Hub reviewer check is run against the section's evidence cards and triggers exactly one rewrite when the section cites unknown ids or states untraceable numbers. Produces `drafts/<section>.md`.
7. **reviews** — three reviewer subagents registered in Agent Hub (configured by `profile.reviewers`) read the full draft and produce reports. Produces `reviewer_reports.md` and per-reviewer artefacts.
8. **revised** — sections are revised in response to the reviewer reports. Produces `drafts/<section>.revised.md`.
9. **integrated** — integrate revised sections into one manuscript and renumber card ids to `[1] … [N]` in order of first appearance; cards never cited are not listed. Enforces `≥ --min-refs` distinct references. Produces `review_final.md`.
10. **audited** — per-section citation audit: each `[n]` is checked against the cited PubMed abstract; sections that fail are rewritten once. Produces `citation_audit.json`.
11. **table** — assemble the featured / comparison table specified by `profile.table`. Produces `table.md`, embedded in the manuscript.
12. **abstract** — write the abstract to match the audited, integrated manuscript. Produces `abstract.md`.
13. **response** — draft the response letter to the three reviewers and render the final Word document. Produces `response_to_reviewers.md` and `review.docx`.

## Outputs

Written to the run directory:
- `review.docx` — final Word manuscript with numbered references.
- `review_final.md` — final integrated Markdown manuscript.
- `draft_v1.md` — first-pass integrated draft (pre-revision).
- `reviewer_reports.md` — combined reports from the three reviewer subagents.
- `response_to_reviewers.md` — point-by-point response letter.
- `citation_audit.json` — per-section audit: cited ids, out-of-range ids, uncited references, total citations.
- `evidence_cards.json` — the card store the draft cites.
- `summary.json` — run summary: title, model, `llm_calls`, `queries`, `records`, `cards`, `sections`, `references`, `citation_check`, `words`.
- `llm_trace.jsonl` — per-call LLM trace (prompts, responses, timings).
- `checkpoints/` — per-stage checkpoints enabling resume.

Example `summary.json` shape (from the `thbs4` run):
```json
{
  "title": "Thrombospondin-4 as a skeletal muscle-derived secreted factor: regulatory mechanisms in ageing and metabolism — a critical appraisal",
  "model": "minimax-cn/MiniMax-M3",
  "llm_calls": 0,
  "queries": 30,
  "records": 336,
  "cards": 60,
  "sections": 10,
  "references": 59,
  "citation_check": { "cited": 59, "references": 59, "out_of_range": [], "uncited": [], "citations": 257 },
  "words": 9204
}
```

## Quality gates

The run is marked PASS only if all of the following hold:
- **Citation closure** — every `[n]` in the prose maps to a reference and every reference is cited at least once (`uncited == []`, `out_of_range == []`).
- **Reference floor** — `≥ --min-refs` distinct references survive renumbering.
- **No card leakage** — no card ids (e.g. `[R12]`) and no drafting-meta text appear in the final prose.
- **Reference provenance** — the reference list is built from PubMed records' own metadata (E-utilities), never from the model's own knowledge.
- **Per-section audit** — each section's citations have been checked against its cited abstracts; sections with unknown ids or untraceable numbers are rewritten exactly once (the `thbs4` run corrected 32 unsupported citations at this stage).

## Recovery

- All thirteen stages checkpoint into `checkpoints/`. Re-running with the **same arguments** resumes from the latest completed stage; earlier stages are reused as-is. The `thbs4` run-log shows resume from checkpoints at every stage (`queries: resumed from checkpoint`, `drafts: 10/10 resumed from checkpoint`, etc.).
- `--fresh` clears `checkpoints/` and re-runs every stage from the start.
- `--smoke` runs every stage at small scale (fewer queries / records / cards / sections) to verify the pipeline end-to-end without producing a real manuscript.

## Transfer

To export and install on another Agent Hub:

1. Copy the skill folder (containing `run.py`, the `ali/review_writer.py` pipeline, `profiles/`, and `SKILL.md`) into the target Hub's `skills/literature-review/` directory.
2. The target Hub must provide:
   - A configured chat model in its `backend` / `models` settings (e.g. `minimax-cn/MiniMax-M3`) reachable via `llm_client`.
   - Outbound network access from `websearch._http` to the PubMed E-utilities endpoints.
   - The three reviewer subagents registered in the Hub's subagent registry, named to match `profile.reviewers` (defaults: `reviewer-muscle-biology`, `reviewer-ageing-metabolism`, `reviewer-citation-integrity`).
   - The `reviewer` reference-checking utility used per-section.
3. Bundled profiles ship with the skill (`profiles/multiomics-emp`, `profiles/thbs4`); additional profiles can be added as JSON / YAML in `profiles/`.
4. After install, the Hub's `POST /api/skills/author` endpoint can rewrite this `SKILL.md` from a new finished run (see `skills/literature-review/` in Agent Hub).
