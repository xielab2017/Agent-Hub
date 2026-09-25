---
name: literature-review
description: Evidence-grounded biomedical literature review: PubMed search, screening, drafting, three reviewer subagents, citation audit, Word manuscript.
triggers: literature review, review article, systematic review, critical review, narrative review, write a review, 综述, 文献综述, 系统综述, 撰写综述
entry: run.py
origin: agent-hub-authored
authored_by: minimax-cn/MiniMax-M3
authored_at: 2026-09-25T20:18:11Z
---

# Literature review (evidence-grounded, peer-reviewed)

## When to use
A biomedical review article (narrative or systematic-style) that must cite real literature inline as `[1]`,
`[2]` …, take a critical position, and be produced as a numbered Word manuscript. Everything goes through the
Hub: the configured model via `llm_client`, the network via `websearch._http`, reference checks via
`reviewer`, and the three reviewer subagents.

## Inputs
### CLI arguments
- `--topic "<English topic>"` — when no profile is given, the Hub model plans the run topic-specifically
  (queries, focus terms, screen rubric, outline, reviewers, table columns).
- `--profile <name|path>` — a profile from `profiles/` (bundled: `multiomics-emp`, `thbs4`) or a path to a
  profile YAML file. Profile fields the user leaves at their defaults are planned by the model for the topic.
- `--out <dir>` — output directory.
- `--min-refs <N>` — minimum distinct references required (citation-integration gate).
- `--max-cards <N>` — cap on evidence cards.
- `--smoke` — runs every stage at small scale for verification.
- `--fresh` — ignore `checkpoints/` and start over.
- `--help` — show help.

These are the **only** command-line options.

### Profile fields (YAML)
Inside a profile file (bundled or user-supplied); `featured:` is a profile field, not a CLI option.

```yaml
topic: "Thrombospondin-4 as a skeletal muscle-derived secreted factor in ageing and metabolism"
seed_queries:
  - "THBS4 skeletal muscle"
  - "thrombospondin-4 secreted factor myokine"
seed_pmids:
  - "PMID:12345"
  - "PMID:67890"
focus_terms: ["THBS4", "myokine", "skeletal muscle"]
context_terms: ["ageing", "metabolism", "exercise"]
query_guidance: "Prefer 2018-2024 human and mouse studies; cover secreted-factor literature."
screen_rubric: "Relevance 0-3; one-sentence finding; keep ≥ 2."
screen_sections: ["background", "evidence", "controversies"]
outline_guidance: "10 sections, critical-appraisal framing."
reviewers:
  - reviewer-muscle-biology
  - reviewer-ageing-metabolism
  - reviewer-citation-integrity
table:
  columns: ["Study", "Model", "Finding", "Relevance"]
featured:
  pmid: "PMID:12345"
  reason: "First report of THBS4 as a myokine."
coi_statement: "The authors declare no competing interests."
```

## Steps
The stages below are checkpointed in this order:
`profile → queries → records → screened → outline → drafts → reviews → gaps → revised → integrated → audited → table → abstract → response`
(the `evidence cards` stage is built between `screened` and `outline`).

1. **Profile** — load the profile (or plan one from `--topic`); emit the topic-specific plan.
2. **Queries** — produce PubMed queries: the profile's `seed_queries` plus model-designed queries guided by
   `query_guidance`, `focus_terms` and `context_terms`.
3. **Records** — run the queries against PubMed E-utilities; fetch abstracts. Inject `seed_pmids` (and
   `featured.pmid`) so they appear even if not returned by the queries.
4. **Screened** — the model screens every record for relevance (0–3) and writes a one-sentence finding;
   `screen_rubric` and `screen_sections` guide the judgement.
5. **Evidence cards** — produce evidence cards from screened records, ranked by focus-term overlap, with
   `seed_pmids` and `featured.pmid` first and a few framing reviews included. Cap at `--max-cards`.
6. **Outline** — the model drafts the section outline guided by `outline_guidance`.
7. **Drafts** — sections are drafted in parallel; the prose cites evidence cards **only** by id (`[R12]`).
8. **Reviews** — the Hub reviewer checks every section against its evidence cards (catches unknown ids and
   untraceable numbers → one rewrite per section). Then the three reviewer subagents from `reviewers:` write
   independent reports.
9. **Gaps** — literature the reviewers name as missing is searched in PubMed, screened, and added as new
   evidence cards.
10. **Revised** — sections are revised using reviewer feedback and the gap cards.
11. **Integrated** — the manuscript is integrated with at least `--min-refs` distinct references; card ids
    are renumbered to `[1] … [N]` in order of first appearance; uncited cards are dropped from the list.
12. **Audited** — per-section citation audit: every `[n]` must map to a reference whose abstract supports the
    statement; every reference must be cited. Unsupported citations are corrected.
13. **Table** — the summary table described by `table.columns` is rendered.
14. **Abstract** — a structured abstract is written from the integrated draft.
15. **Response** — `response_to_reviewers.md` answers each reviewer point.

## Outputs
- `review.docx` — final Word manuscript with numbered references.
- `review_final.md` — final markdown manuscript.
- `draft_v1.md` — first integrated draft (pre-audit).
- `reviewer_reports.md` — the three reviewer reports.
- `response_to_reviewers.md` — point-by-point response.
- `citation_audit.json` — per-section audit results and the final `citation_check`.
- `evidence_cards.json` — all evidence cards (cited and dropped).
- `summary.json` — run summary (title, model, counts, `citation_check`, word count).
- `llm_trace.jsonl` — every Hub LLM call.
- `checkpoints/` — per-stage artefacts for resume.

## Quality gates
- Every `[n]` in the prose maps to a reference; every reference is cited in the prose
  (`cited == references`, no `out_of_range`, no `uncited`).
- `len(references) >= --min-refs` distinct references.
- No raw card ids (`[R12]`) and no meta text leak into the prose — only renumbered `[n]` citations.
- References are built from PubMed records' own metadata, **never** from the model.
- Per-section Hub reviewer check: a section that cites unknown ids or states untraceable numbers is rewritten
  once and re-checked.
- Final `citation_check` includes `cited`, `references`, `out_of_range`, `uncited`, `citations`.

Example pass (from a finished run): 59 distinct references, 257 citations, 0 uncited, 0 out-of-range,
32 unsupported citations corrected by the audit.

## Recovery
- Re-run with the same arguments: each stage in `checkpoints/`
  (`profile`, `queries`, `records`, `screened`, `outline`, `drafts`, `reviews`, `gaps`, `revised`,
  `integrated`, `audited`, `table`, `abstract`, `response`) is reused.
- `--fresh` deletes the checkpoint state for that run and starts over.
- `--smoke` runs every stage at small scale (few queries, fewer cards, short drafts) to confirm the
  pipeline end-to-end before a full run.
- Stage-level resume is per-stage: a finished stage is not re-executed unless its checkpoint is removed or
  `--fresh` is passed.

## Transfer
The skill is the `skills/literature-review/` folder plus the `profiles/` directory and the `run.py` entry.

To install on another Agent Hub:
1. Copy the skill folder and `profiles/` to the target Hub.
2. The target Hub must provide:
   - A configured model via `backend` / `models` (e.g. `minimax-cn/MiniMax-M3`) accessible through
     `llm_client`.
   - Outbound network for `websearch._http` to reach PubMed E-utilities.
   - The `reviewer` reference-check primitive.
   - Three reviewer subagents registered (the names listed in `reviewers:`, e.g.
     `reviewer-muscle-biology`, `reviewer-ageing-metabolism`, `reviewer-citation-integrity`).
3. Bundle or copy the profile files the run needs (the skill ships with `multiomics-emp` and `thbs4` by
   default).
4. Re-run with `python run.py --profile <name> --out <dir>` (or `--topic` for a model-planned run); the Hub
   resolves the model, network and subagents from its own configuration.
