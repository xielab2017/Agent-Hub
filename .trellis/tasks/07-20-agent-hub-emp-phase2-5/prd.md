# Agent Hub x EMP Phase 2-5

## Goal

实现远程 EMP、多工作流联合分析、可复现项目和受控 R Direct

## Requirements

- Phase 2: support configured remote HTTPS EMP endpoints, secret-backed bearer tokens, explicit external-upload approval, streamed multipart transfer, persistent projects/sessions, ownership checks and cancellation.
- Phase 3: derive the typed tool catalog from capabilities, support validated templates for 16S, transcriptomics, metabolomics, metagenomics and clinical data, and persist dependency-aware step state for retry.
- Phase 4: allow one Hub project to bind multiple manifests and EMP sessions, validate cross-omics sample maps, preserve source provenance, and export reproducible Markdown/HTML reports.
- Phase 5: provide an opt-in local R Direct adapter using fixed JSON contracts and a reviewed function allowlist; never evaluate user/LLM-generated R expressions.
- Keep local Phase 1 behavior backward compatible and disabled-by-default integration settings.
- Do not stage or modify unrelated user omics scripts already present in the Agent Hub worktree.

## Acceptance Criteria

- [x] Local and remote adapters consume the same AnalysisPlan contract.
- [x] Remote upload cannot start without HTTPS, configured endpoint, token and recorded approval; restricted data is denied by default.
- [x] Capabilities control available workflows/tools and plans outside the schema are rejected.
- [x] At least 16S and transcriptomics complete adapter-level integration tests.
- [x] Multi-manifest project state, reports and artifacts survive restart and preserve checksums/source references.
- [x] R Direct runs only allowlisted operations with timeout, process termination and environment preflight.
- [x] Agent Hub and EMP regression tests pass; security review covers path, upload, token, ownership and code-execution boundaries.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
