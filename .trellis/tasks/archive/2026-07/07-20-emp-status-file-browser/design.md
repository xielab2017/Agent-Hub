# Technical Design

## State Contract

`GET /api/emp/status` remains backward compatible and adds `ready`:

- `enabled`: Hub configuration authorizes EMP operations.
- `reachable`: the configured local endpoint answered the capabilities request.
- `compatible`: the API contract and required workflow are present.
- `ready`: `enabled && compatible`; this is the only field that enables analysis actions.
- `path_import_available`: EMP currently permits local path import; a false value is a configuration warning rather than whole-service incompatibility.

The service creates a probe client directly from validated configuration so status checks do not pass through `_require_enabled()`. Operational methods continue to call `_require_enabled()`.

## UI Flow

The EMP badge renders four states in priority order: connected/ready, online-awaiting-enable, incompatible, and offline. A separate warning explains unavailable path import. The scan button binds to `status.ready` rather than compatibility alone because Hub-side discovery does not require EMP path import.

The filesystem overlay receives a higher stacking layer than the Control Center. It does not close or recreate the Control Center, preserving form state. Filesystem rows use the backend `is_dir` discriminator: directories navigate and support the existing double-click selection; files are non-selectable informational rows.

## Filesystem Contract

`ali.fsutil.list_dir()` returns regular files as `{name, path, is_dir: false, size}` and directories as the existing `{name, path, is_dir: true}` shape. It skips unsupported entry types and entries that cannot be inspected. Sorting is `(not is_dir, casefolded name)`.

## Compatibility And Rollback

Existing consumers that assumed all entries were directories are updated in the shared browser renderer. The API only adds entries and fields; no existing field is removed. Reverting the service, renderer, and CSS changes restores prior behavior without data migration.
