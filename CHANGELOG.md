# Changelog

## v1.0.0 — 2026-07-13

Initial public release of **Hermes-ALI**.

- Lightweight web terminal for Hermes Agent (Python stdlib + vanilla JS)
- Cross-platform launchers: `start.sh` (macOS/Linux), `start.ps1` (Windows), `ctl.sh`
- Default bind `0.0.0.0:8765` for LAN / IP multi-device access
- Session CRUD + SSE streaming chat
- Optional password auth (`HERMES_ALI_PASSWORD`)
- Auto-discovers Hermes Agent; demo mode when agent is absent
- GitHub Release workflow for source archives
