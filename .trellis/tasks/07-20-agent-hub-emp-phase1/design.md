# Cross-Repository Design

## Architecture

```text
Agent Hub UI
  -> thin /api/emp/* routes
  -> EmpService (policy, persistence, idempotency, orchestration)
     -> EmpDiscovery (read-only local inspection)
     -> EmpClient (versioned HTTP adapter)
        -> EMP Plumber API
           -> existing build_mae/add_experiment_to_mae/workflow helpers
     -> Agent Hub EMP state/artifact store
  -> bounded result interpretation
```

## Ownership Boundaries

- `emp_models.py`: validated value objects and deterministic serialization only.
- `emp_discovery.py`: local read-only filesystem/data preview; no HTTP and no LLM.
- `emp_client.py`: HTTP transport, compatibility, error translation and secure downloads; no UI policy.
- `emp_service.py`: endpoint selection, manifest/plan lifecycle, approvals, mappings, idempotency, job recovery and artifact registry.
- `emp_tools.py`: fixed tool registry and JSON Schemas; delegates to service only.
- `routes.py`: thin request/response adapter.
- EMP `helpers/path_import.R`: allowed-root validation, preview and import delegation.
- EMP existing `helpers/import.R`: remains the single MAE construction implementation.

## State Model

```text
STATE_DIR/emp/
  manifests/<manifest-id>.json
  plans/<plan-id>.json
  mappings/<hub-session-id>.json
  jobs/<run-id>.json
  artifacts/<hub-session-id>/<run-id>/<files>
  reports/<hub-session-id>/<run-id>/<report>.md
```

Writes use temporary files plus atomic replace. IDs are generated locally and validated before path construction. Stored source paths prefer workspace-relative paths; resolved absolute paths are runtime-only except endpoint-scoped local import records.

## API Surface

EMP additions:

- `GET /api/capabilities`
- `POST /api/import/path/preview`
- `POST /api/import/path`

Agent Hub additions:

- `GET /api/emp/status`
- `POST /api/emp/datasets/scan`
- `POST /api/emp/datasets/preview`
- `POST /api/emp/plans`
- `POST /api/emp/plans/<id>/confirm`
- `POST /api/emp/plans/<id>/run`
- `GET /api/emp/runs/<id>`
- `POST /api/emp/runs/<id>/cancel`
- `GET /api/emp/runs/<id>/artifacts`

Only routes required by the MVP are implemented. Cancel may return unsupported when EMP capabilities omit cancellation.

## Plan State Machine

```text
draft -> validated -> confirmed -> queued -> running
running -> completed | failed | cancelled
failed -> queued (explicit retry only)
```

Transition checks are centralized in `EmpService`. A plan fingerprint covers manifest checksum, endpoint ID, workflow, experiment and canonical parameters. An active/completed fingerprint blocks duplicate submission unless explicit rerun is requested.

## Security

- Allowed roots are configuration-derived, never chat-derived.
- Path containment uses resolved `Path.relative_to` semantics in Python and normalized path-component comparison in R, including case normalization on Windows.
- Discovery does not follow symlink directories.
- Remote endpoint configuration is not accepted by MVP routes.
- The client accepts only HTTP loopback hosts in local mode.
- Artifact download URLs must resolve to the configured EMP origin; names are reduced to safe basenames.
- Result context sent to LLM is capped and contains summaries/selected rows only.

## Compatibility

- Agent Hub config receives an additive `emp` object with safe defaults and `enabled=false` unless explicitly enabled through the UI/config migration policy.
- Old session JSON remains readable; EMP mappings are stored separately.
- EMP multipart import and existing UI routes are unchanged.
- `EMP_SESSION_DIR` and `EMP_JOB_DIR` preserve current file format.

## Rollback

- Set `emp.enabled=false` to remove Agent Hub integration from routing/UI.
- Revert EMP additive routes/environment defaults without touching user session directories.
- Keep downloaded artifacts and manifests; rollback never deletes input or result files.
