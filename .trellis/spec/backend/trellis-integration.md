# Trellis Integration Contract

## 1. Scope / Trigger

Use this contract when changing Agent Hub's controlled Trellis task mode, session-task bindings, planning approval, validation records, task context injection, or project skill discovery.

`ali/trellis.py` is the sole owner of Trellis file parsing and state transitions. Routes and prompt assembly must consume its normalized outputs and must not parse `.trellis` files directly.

## 2. Signatures

Backend service signatures:

```python
status(session_id: str = "", workspace: str = "") -> dict
suggest(message: str) -> dict
create_task(session_id: str, workspace: str, title: str, description: str = "") -> dict
bind_task(session_id: str, workspace: str, task_id: str) -> dict
approve(session_id: str, identity: str = "local-user", summary: str = "") -> dict
transition(session_id: str, target: str, reason: str = "") -> dict
record_validation(session_id: str, command: str, ok: bool, summary: str = "") -> dict
read_artifact(session_id: str, name: str) -> dict
context_block(session_id: str) -> tuple[str, dict]
unbind_task(session_id: str) -> dict
```

HTTP routes:

```text
GET  /api/trellis/status
GET  /api/trellis/artifact
POST /api/trellis/suggest
POST /api/trellis/tasks
POST /api/trellis/bind
POST /api/trellis/approve
POST /api/trellis/transition
POST /api/trellis/validation
POST /api/trellis/unbind
```

## 3. Contracts

Configuration:

```json
{
  "trellis": {
    "enabled": true,
    "context_budget_chars": 18000,
    "artifact_budget_chars": 7000,
    "suggest_for_complex_tasks": true
  }
}
```

Session documents may contain a backward-compatible `trellis` object with `workspace`, `task_id`, `bound_at`, and `status`. Missing or empty objects mean no binding. Hidden Fusion child sessions inherit a copy of the parent binding.

Task status is one of `planning`, `pending_approval`, `in_progress`, `quality_check`, `blocked`, or `completed`. Agent Hub approval and validations live under `task.json.meta.agent_hub`.

Only `prd.md`, `design.md`, and `implement.md` are readable artifacts. Persisted task IDs are safe direct-child slugs, never absolute paths. Project-owned `.agents/skills/trellis-*` entries are discoverable but have `managed=false`, so Control Center cannot delete them.

## 4. Validation & Error Matrix

| Condition | Required behavior |
|---|---|
| Empty or missing workspace | Raise `TrellisError("workspace is required")` |
| Workspace lacks `.trellis` | Return an actionable initialization message; do not initialize automatically |
| `.trellis` or `tasks` is a symlink | Reject before reading task data |
| Task ID contains traversal or separators | Reject as invalid task ID |
| `task.json` or planning artifact is a symlink | Reject or skip it |
| Approval lacks a regular `prd.md` | Reject approval |
| Validation is submitted before execution | Reject; do not change status |
| Completion lacks the latest successful validation | Reject completion |
| Integration is disabled or no task is bound | Return an empty context block; preserve normal chat |
| Secret-like content appears in artifacts | Replace with `[REDACTED]` before API or prompt output |

## 5. Good / Base / Bad Cases

- Good: the user explicitly creates or binds a task, approves planning, runs implementation, records a successful check, then completes it.
- Base: a simple chat has no binding and proceeds without creating files or injecting Trellis context.
- Bad: a client sends `../outside`, binds a symlinked task root, records a fake passing check during planning, or tries to complete directly from planning. Every case must fail without modifying the task phase.

## 6. Tests Required

- Assert create/bind persistence survives a session reload.
- Assert legacy sessions without `trellis` still deserialize.
- Assert traversal, task-root symlink, task symlink, and artifact symlink rejection.
- Assert planning approval is required before validation.
- Assert failed validation cannot lead to completion.
- Assert context is deterministic, bounded, redacted, and empty before approval.
- Assert hidden child sessions inherit the binding.
- Assert simple messages neither create nor suggest a task.
- Assert project Trellis skills are discoverable and non-removable.
- Run the full Python suite and `node --check static/app.js` after cross-layer changes.

## 7. Wrong vs Correct

### Wrong

```python
# Route code parses arbitrary user paths and injects full files.
task = json.loads(Path(body["task_path"]).read_text())
system += Path(task["prd"]).read_text()
```

### Correct

```python
# The service owns validation, redaction, budgets, and normalized metadata.
block, meta = trellis.context_block(session_id)
route_info["trellis"] = meta
if block:
    extra_system = f"{extra_system}\n\n{block}".strip()
```
