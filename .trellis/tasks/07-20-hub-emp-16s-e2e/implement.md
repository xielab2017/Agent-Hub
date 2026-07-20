# Implementation Plan

## 1. Runtime Readiness

- [x] Add focused tests for Hub status when EMP is reachable but path import is disabled or arbitrary R is enabled.
- [x] Make the local EMP launcher persist `EMP_ALLOWED_ROOTS` and `EMP_ENABLE_USER_R=false` while retaining `127.0.0.1` binding.
- [x] Restart EMP and verify capabilities report `path_import=true` and `arbitrary_r=false`.
- [x] Present actionable Hub readiness states without exposing shell commands as the normal workflow.

## 2. Scientific Metadata Controls

- [x] Add a bounded metadata summary contract to `DatasetManifest` with backward-compatible deserialization.
- [x] Compute safe categorical levels and counts during scan and after pairing changes.
- [x] Update plan validation to use the summary rather than persisted raw metadata rows.
- [x] Replace reference/test free-text fallbacks with real dropdown levels in the Hub panel.
- [x] Add unit and route tests for valid levels, missing levels, high-cardinality fields and the controlled 16S pair.

## 3. Hub-Window Vertical Slice

- [x] Render a persistent six-stage Data, Pairing, Parameters, Plan, Run and Results workflow before a dataset is selected.
- [x] Give each disabled stage a concise prerequisite and highlight the next available action.
- [x] Use the Hub picker to select the EMP test directory or either file within it.
- [x] Scan and verify `16S_level-7.csv` + `16S_mapping.csv` and overlap `132/130/130`.
- [x] Generate a local `microbiome_16s` plan using `Group`, actual reference/test levels, `Genus` and `shannon`.
- [x] Confirm and run import, validation, taxonomy preparation, Alpha diversity and plot generation through typed EMP calls.
- [x] Verify duplicate-click protection, stable progress layout and normalized failure display.

## 4. Recovery And Results

- [ ] Refresh Hub while a job is active and verify state recovery.
- [x] Register and open a machine-readable result, plot/PDF and provenance Markdown artifact.
- [ ] Verify “Add to chat” uses bounded summaries and source links.
- [x] Confirm original fixture checksums remain unchanged.

## 5. Quality Gates

- [x] Run focused Agent Hub EMP tests and the complete Python suite.
- [x] Run EMP agent API tests and the real local 16S HTTP smoke test.
- [ ] Validate JavaScript syntax, `git diff --check`, desktop layout and narrow viewport layout.
- [x] Record exact Hub-window operating steps, results, remaining risks and rollback instructions.

## Hub Window Acceptance Runbook

1. Open `http://127.0.0.1:8765` and choose **Control Center -> Joint Analysis**.
2. Confirm the local EMP status is ready, then use the browse button beside the local data path.
3. Select `EasyMultiProfiler-Web-V2/tests`, `16S_level-7.csv`, or `16S_mapping.csv`, and click **Scan omics data**.
4. Verify the assay, metadata and `132 / 130 / 130` sample-overlap result; apply the pairing if changed.
5. Select `Group`, choose two actual group levels, keep local EMP, then select the desired taxonomy and Alpha options.
6. Click **Generate analysis plan**, review inputs and parameters, then click **Confirm and run**.
7. Follow the progress list without leaving the panel. After completion, use **Open** or **Add to chat** on the resulting artifacts.

## Validation Record

- Agent Hub final full suite: `246 passed in 20.47s`.
- Focused EMP integration suite after the final adapter fix: `35 passed`.
- Real run: manifest `manifest-6e55bd570900401bbb8086402e2d6baf`, plan `plan-e3f607c8cc5b4479b35b539c5a166cdb`, job `empjob-79b216edd3d5452085cc5e66c16e4694`.
- Real result: five typed steps completed; JSON tables, PNG, PDF and provenance Markdown were persisted.
- Scientific inputs: assay `132`, metadata `130`, matched `130`; `IBS_before n=36` vs `IBS_after n=36`, Genus, Shannon, Wilcoxon/BH.
- EMP capability gate: `path_import=true`, `arbitrary_r=false`, loopback endpoint.
- Fixture files remain clean in the EMP Git worktree.
- Remaining manual checks: browser security policy blocked the final refresh/narrow-viewport pass and active-job refresh/Add-to-chat interaction; those checklist items remain open above.

## Rollback

- Agent Hub: revert the EMP-specific files listed in this task; existing chat and non-EMP workflows are independent.
- EMP: revert the six modified backend/launcher files. Setting `emp.enabled=false` disables Hub integration without deleting manifests or artifacts.
