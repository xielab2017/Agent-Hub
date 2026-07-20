# Implementation Plan

1. Refactor EMP status probing to bypass only the enable gate, add normalized `ready`, and cover disabled-online, enabled-online, incompatible, and failure states.
2. Extend filesystem directory listing with regular file metadata and deterministic directory-first sorting; add focused tests.
3. Update the shared filesystem browser renderer for directory and file rows, preserving directory-only selection.
4. Raise the filesystem overlay above the Control Center and update EMP badge/button logic to consume the normalized status contract.
5. Run focused tests, `node --check static/app.js`, the full Python suite, and desktop/mobile visual checks with the local app.
6. Review the diff for unrelated changes, record any durable cross-layer contract, commit only task-owned files, and archive the Trellis task.
