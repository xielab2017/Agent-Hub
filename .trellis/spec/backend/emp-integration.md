# EMP Integration Contract

## Status Semantics

`EmpService.status()` must distinguish service discovery from authorization:

- `enabled` means the Hub configuration authorizes EMP operations.
- `reachable` means the configured loopback endpoint answered `/api/capabilities`.
- `compatible` means the API version and required workflow are supported.
- `ready` means `enabled && compatible` and controls Hub-side analysis actions.
- `path_import_available` mirrors the optional EMP capability. Its absence must be shown as a configuration warning, not as whole-service incompatibility.
- `arbitrary_r_enabled` mirrors EMP's arbitrary R capability and must remain visible as a security warning.
- `analysis_ready` means `ready && path_import_available && !arbitrary_r_enabled`. Use it for the positive "ready to analyze" badge without changing the backward-compatible meaning of `ready`.

Status probing may instantiate a validated client while disabled. Every mutating or analysis operation must continue through `_require_enabled()`.

## Typed Tool Parameter Boundary

Every planning parameter must remain under its schema name until the registered tool adapter translates it for one known endpoint. Endpoint aliases are tool-specific: for example, `reference_level` and `test_level` become `ref_group` and `test_group` only for `emp.analyze.differential`; `emp.visualize.alpha` keeps the schema names so the plot can filter to the confirmed comparison.

An Alpha plot with a grouping variable must exclude samples with missing group metadata. When the plan confirms reference/test levels, those levels are passed explicitly to EMP so plot contents do not depend on whether another analysis step mutated the current EMP object first.

## Filesystem Picker Boundary

The shared filesystem API may return directories and regular files. Consumers must branch on `is_dir`: directories are navigable/selectable, while files are informational when the target field expects a directory. Hidden entries remain excluded by default and directories sort before files.

When one overlay can launch another, the launched overlay must have an explicit higher stacking layer. Do not rely on DOM order when sibling overlays share a z-index.

## Required Regression Checks

- Disabled but reachable EMP reports online and not ready.
- Enabled and compatible EMP reports ready.
- Optional `path_import=false` remains compatible and is exposed separately.
- `analysis_ready` is false when path import is unavailable or arbitrary R is enabled.
- Typed-tool tests verify that endpoint aliases do not leak across tools.
- Filesystem listing includes regular files, preserves directory selection, and excludes hidden entries.
- Cross-layer changes run the full Python suite and `node --check static/app.js`.
