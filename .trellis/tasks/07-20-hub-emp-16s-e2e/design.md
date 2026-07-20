# Hub-Driven 16S E2E Design

## User Experience

The supported path begins and ends in Agent Hub:

```text
Control Center -> Joint Analysis -> choose file/folder -> scan
  -> verify assay + metadata + overlap
  -> choose Group and real comparison levels
  -> generate plan -> confirm and run
  -> monitor stable progress -> open/add artifacts to chat
```

EMP remains a local computation service. Users do not need to open its Web UI or type API commands. The Hub panel shows connection readiness, path-import readiness, security readiness, pairing diagnostics, plan confirmation, run progress and artifacts as separate states.

The workflow surface is always rendered, including before a scan:

```text
1 Data -> 2 Pairing -> 3 Parameters -> 4 Plan -> 5 Run -> 6 Results
```

The current stage is emphasized, completed stages show completion, and later stages remain visible but disabled with their prerequisite. Dynamic content fills these stable sections instead of inserting large blocks that cause controls to appear unexpectedly or shift the modal.

## Runtime Preflight

Hub reads `GET /api/capabilities` and treats the local service as analysis-ready only when:

- the endpoint is reachable and API-compatible;
- `path_import=true` for local path mode;
- the selected path is accepted by EMP's own allowed roots;
- Agent-facing arbitrary R execution is disabled (`arbitrary_r=false`).

The local EMP launch configuration uses loopback binding, the selected test root in `EMP_ALLOWED_ROOTS`, and `EMP_ENABLE_USER_R=false`. Hub never broadens EMP roots from chat text and does not silently claim readiness when a process restart is required. A failed preflight returns a specific corrective status instead of a generic “not enabled” badge.

## Metadata Summary Contract

Raw metadata rows are not persisted merely to populate controls. Discovery emits a bounded, privacy-minimized summary on the manifest:

```json
{
  "metadata_summary": {
    "columns": ["SampleID", "Group", "Group_sub"],
    "categorical": {
      "Group": {"levels": [{"value": "...", "count": 10}], "truncated": false}
    }
  }
}
```

The summary is recomputed whenever assay/metadata pairing changes. Limits cap rows, columns, unique levels and text length. Identifier-like or high-cardinality columns remain available as column names but do not expose value lists. The plan compiler validates selected levels against the same summary, removing the current dependency on persisted raw preview rows.

## Pairing And Plan

For the controlled pair, Hub must report assay `132`, metadata `130`, matched `130`, with `K_XYL_F_0009_03` and `K_XYL_F_0035_03` marked assay-only. The user selects `Group` and two actual levels from dropdowns. The plan remains explicitly confirmable and records the selected levels, taxonomy level, Alpha metric, endpoint, manifest fingerprint and input checksums.

## Execution And Recovery

The existing `EmpService` owns import, typed workflow calls, polling, idempotency, state persistence and artifact registration. Routes remain thin. A stable progress region prevents layout jumps. Refresh reloads the persisted Hub job and queries EMP again. Repeated confirmation of the same active fingerprint returns the existing job rather than submitting duplicate work.

## Artifacts

Successful completion registers at least:

- a machine-readable result/manifest;
- an Alpha diversity plot in PNG or PDF;
- a Markdown provenance report linking input checksums, selected parameters, EMP/R versions and source artifacts.

“Open” displays the local artifact and “Add to chat” injects only bounded result context, not the raw abundance matrix.

## Error Handling

Connection, capability, allowed-root, import, validation, job and artifact failures map to the existing normalized EMP error model. Any scientific endpoint mismatch is captured with a redacted request shape and an automated regression test. Input files are read-only throughout.

## Compatibility And Rollback

The manifest extension is additive and older manifests remain readable with an empty summary. Disabling `emp.enabled` removes the integration without deleting state. Runtime configuration can be reverted independently; rollback never removes source data or downloaded artifacts.
