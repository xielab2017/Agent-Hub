# EMP Integration Contract

## Status Semantics

`EmpService.status()` must distinguish service discovery from authorization:

- `enabled` means the Hub configuration authorizes EMP operations.
- `reachable` means the configured loopback endpoint answered `/api/capabilities`.
- `compatible` means the API version and required workflow are supported.
- `ready` means `enabled && compatible` and controls Hub-side analysis actions.
- `path_import_available` mirrors the optional EMP capability. Its absence must be shown as a configuration warning, not as whole-service incompatibility.

Status probing may instantiate a validated client while disabled. Every mutating or analysis operation must continue through `_require_enabled()`.

## Filesystem Picker Boundary

The shared filesystem API may return directories and regular files. Consumers must branch on `is_dir`: directories are navigable/selectable, while files are informational when the target field expects a directory. Hidden entries remain excluded by default and directories sort before files.

When one overlay can launch another, the launched overlay must have an explicit higher stacking layer. Do not rely on DOM order when sibling overlays share a z-index.

## Required Regression Checks

- Disabled but reachable EMP reports online and not ready.
- Enabled and compatible EMP reports ready.
- Optional `path_import=false` remains compatible and is exposed separately.
- Filesystem listing includes regular files, preserves directory selection, and excludes hidden entries.
- Cross-layer changes run the full Python suite and `node --check static/app.js`.
