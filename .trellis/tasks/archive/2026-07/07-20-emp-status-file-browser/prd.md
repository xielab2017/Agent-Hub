# Fix EMP detection and file browser layering

## Goal

Make the EMP control panel accurately distinguish a running local EMP service from Hub authorization, and make directory selection reliable and informative from inside the Control Center.

## Background

- `EmpService.status()` currently returns before probing when `emp.enabled` is false, so a running service is displayed as "Disabled".
- The filesystem and Control Center overlays share the same z-index, while the Control Center appears later in the DOM and covers the filesystem browser.
- `ali.fsutil.list_dir()` deliberately filters out every non-directory entry, so users cannot inspect the files contained in a selected data folder.

## Requirements

- The status API must probe the configured loopback EMP endpoint even when Hub integration is disabled.
- Status must separately report configured authorization, endpoint reachability, API compatibility, and whether analysis actions are ready.
- The UI must show an online-but-not-enabled state without silently enabling or persisting EMP access.
- EMP scan actions remain unavailable until both authorization and compatibility are true.
- The filesystem browser must always render above the Control Center and remain usable when launched from it.
- Directory listings must contain visible directories and regular files, sort directories first, and keep directory-only selection semantics.
- Hidden entries remain excluded by default, and unreadable or special entries must not break listing.
- Existing workspace and Obsidian directory pickers must retain their behavior.

## Acceptance Criteria

- [ ] With EMP reachable and `emp.enabled=false`, the API reports `reachable=true`, `enabled=false`, `ready=false`, and the UI says the local EMP is online but awaits enablement.
- [ ] With EMP reachable, compatible, and enabled, the API reports `ready=true`, and scanning is enabled.
- [ ] With EMP unreachable, the UI clearly reports that it is waiting for the local service.
- [ ] Clicking the EMP directory browse button opens a visible modal above the Control Center.
- [ ] The browser lists both folders and regular files; folders can be navigated/selected and files are display-only.
- [ ] Backend EMP/service tests, filesystem tests, JavaScript syntax checks, and the full regression suite pass.

## Out of Scope

- Automatically changing the persisted EMP enable setting.
- Selecting a file where a directory path is required.
- Replacing the sidebar project/session model with a general-purpose file manager.
