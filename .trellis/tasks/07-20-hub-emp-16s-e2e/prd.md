# Agent Hub x EMP 16S end-to-end analysis

## Goal

Prove that Agent Hub and EasyMultiProfiler can complete one reproducible local 16S workflow from data discovery through EMP computation and Hub artifact/report recovery.

## Background

- Agent Hub v5.0.6 is listening on `127.0.0.1:8765` and EMP v7.0.0 is listening on `127.0.0.1:8000`.
- Hub EMP integration is enabled and supports the `microbiome_16s` workflow.
- The configured Hub allowed root is `EasyMultiProfiler-Web-V2/tests`.
- EMP currently reports `path_import=false` because its process was started without `EMP_ALLOWED_ROOTS`; this blocks local path import despite both services being healthy.
- A controlled test pair is available: `tests/16S_level-7.csv` (assay) and `tests/16S_mapping.csv` (metadata with `Group` and `Group_sub`).

## Requirements

- Configure EMP path import for the selected test root without exposing broader filesystem access.
- Preserve loopback-only EMP binding and existing Hub authentication/security behavior.
- Scan the test directory in Hub and identify the assay/metadata pair with sample-overlap diagnostics.
- Create a confirmed `microbiome_16s` analysis plan using `Group` as the initial grouping variable.
- Execute validation, taxonomy preparation, Alpha diversity, and visualization through EMP.
- Track the asynchronous job in Hub and recover after page refresh.
- Register JSON, plot/PDF, and Markdown report outputs as Hub artifacts with checksums and provenance.
- Record any EMP API mismatch as a reproducible defect with the failing request and normalized error.
- Keep the normal user workflow entirely inside the Hub window; users must not need terminal commands or the EMP Web UI to run an analysis.
- Populate grouping variables and reference/test levels from bounded metadata summaries so invalid placeholder levels cannot be submitted.
- Keep the complete analysis workflow visible before scanning as a six-stage progress surface; unavailable stages are disabled with a concrete prerequisite instead of being absent from the page.

## Acceptance Criteria

- [x] EMP capabilities report `path_import=true` for the test root and `arbitrary_r=false` for Agent-facing use.
- [x] Hub scan reports the expected assay and metadata with nonzero matched samples and no unreviewed pairing ambiguity.
- [x] The plan is visible and explicitly confirmed before execution.
- [x] The EMP job reaches `done`, or a genuine EMP defect is isolated with an automated regression test and actionable error.
- [x] Hub registers at least one machine-readable result, one plot/PDF, and one provenance report.
- [ ] Refreshing Hub does not lose the job or artifacts.
- [ ] A user can complete the documented Hub-window runbook from dataset selection through opening or attaching an artifact.
- [x] Before any dataset is selected, the panel visibly communicates the complete Data, Pairing, Parameters, Plan, Run and Results sequence and identifies the next available action.
- [x] Existing Agent Hub and EMP regression tests remain green.

## Out Of Scope

- Remote EMP upload.
- User research conclusions or publication-ready interpretation.
- Workflows other than the initial 16S vertical slice.
- Broad filesystem authorization outside the selected test root.

## Confirmed First Dataset

The first run uses the controlled EMP test pair:

- assay: `tests/16S_level-7.csv`
- metadata: `tests/16S_mapping.csv`
- grouping variable: `Group`

Real research data remains unchanged and is not used until this controlled vertical slice passes.
