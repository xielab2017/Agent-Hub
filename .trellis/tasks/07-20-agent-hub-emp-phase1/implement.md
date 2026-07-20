# Implementation Plan

## Phase 0 - Freeze Baseline

- [x] Record Agent Hub branch/status and test command.
- [x] Record EMP branch/status, route inventory and runtime command.
- [x] Run Agent Hub baseline: `python3 -m pytest -q` -> `153 passed`.
- [x] Confirm EMP API is not currently running; R 4.4.2 is installed.
- [x] Repair or replace the missing EMP smoke test referenced by `smoke_local.sh`.
- [x] Add capabilities/import contract fixtures and a minimal 16S manifest fixture.

## Phase 1A - EMP API

- [x] Make session/job roots environment-configurable and persistent by default.
- [x] Add capabilities response.
- [x] Add allowed-root parser and secure path resolver.
- [x] Add path preview with bounded file reads and sample overlap summary.
- [x] Add path import that reuses existing import helpers.
- [x] Add R tests for allowed roots, traversal, symlink escape, preview and import parity.
- [x] Start EMP on an isolated port and run API smoke tests.

## Phase 1B - Agent Hub Backend

- [x] Add additive EMP settings and safe public settings view.
- [x] Implement typed models, discovery, client, service and tool registry.
- [x] Add atomic manifest/plan/mapping/job/artifact persistence.
- [x] Add plan validation, confirmation gate and idempotency fingerprint.
- [x] Add thin `/api/emp/*` routes and audit events.
- [x] Add recovery polling integration without blocking HTTP requests.
- [x] Add backend tests for scanning, paths, HTTP errors, persistence and duplicate runs.

## Phase 1C - Agent Hub UI

- [x] Add EMP status/config controls in the existing control center.
- [x] Add “扫描组学数据” to the existing control center workspace workflow.
- [x] Add dataset pairing preview/correction and editable scientific parameters.
- [x] Add plan confirmation and stable-size step progress.
- [x] Add artifact grouping/open/download and report summary.
- [x] Add complete zh/en strings and auto-language behavior.

## Phase 1D - Integration and Release

- [x] Run fixed 16S local path import and analysis chain.
- [x] Verify refresh/restart recovery and duplicate-submit protection.
- [x] Verify one table and one PDF/PNG artifact with checksum.
- [x] Verify source-linked Markdown summary and LLM minimization.
- [x] Run all Agent Hub tests and EMP smoke/contract tests.
- [x] Review both repos for secret/path/log leakage.
- [x] Document setup, troubleshooting, rollback and known limitations.
- [ ] Commit EMP changes separately, then commit/push Agent Hub `v5.0.6`.

## Validation Commands

```bash
# Agent Hub
python3 -m pytest -q

# EMP unit/contract tests (exact command finalized with added harness)
Rscript webapp/tests/test_emp_agent_api.R

# Local integration
EMP_SESSION_DIR=<temp> EMP_JOB_DIR=<temp> EMP_ALLOWED_ROOTS=<fixture-root> \
  API_PORT=8010 Rscript webapp/backend/run_api.R
python3 tests/emp_e2e_smoke.py --api http://127.0.0.1:8010
```

## Risk and Rollback Points

- Do not migrate or delete current `/tmp/emp_sessions`; environment root is additive.
- Do not change existing multipart import response fields.
- Do not register EMP arbitrary R endpoints.
- Do not stage unrelated untracked Agent Hub omics files.
- Stop and diagnose any scientific result difference before continuing.
