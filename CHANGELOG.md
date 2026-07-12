# Changelog

## v1.1.0 — 2026-07-13

Campus Office automation depth aligned with Hermes × OpenSquilla handbook.

- **Control Center**: backend (campus OpenAI-compatible / NIM / Ollama), model IDs, routing matrix, Obsidian vault, data policy
- **OpenSquilla-style routing**: C0–C3 + Vision auto/manual tiers with audit metadata
- **Office workflows**: 会议纪要、邮件草稿、文档摘要、长文审核、复杂推理、多模态提取、部署预检、验收清单、SOP 候选
- **Obsidian**: vault status, allowed-root listing, write-only to `AI_Candidates` with approval
- **Security**: no secrets in JSON; `restricted` blocks external fallback; audit.jsonl
- Config schema compatible with `campus-office-ai.example.json`

## v1.0.0 — 2026-07-13

Initial public release of **Hermes-ALI**.

- Lightweight web terminal for Hermes Agent (Python stdlib + vanilla JS)
- Cross-platform launchers: `start.sh` (macOS/Linux), `start.ps1` (Windows), `ctl.sh`
- Default bind `0.0.0.0:8765` for LAN / IP multi-device access
- Session CRUD + SSE streaming chat
- Optional password auth (`HERMES_ALI_PASSWORD`)
- Auto-discovers Hermes Agent; demo mode when agent is absent
- GitHub Release workflow for source archives
