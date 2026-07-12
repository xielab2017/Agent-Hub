# Hermes-ALI

**Lightweight, cross-platform terminal for [Hermes Agent](https://hermes-agent.nousresearch.com/) — with Campus Office automation depth.**

Run once on a Mac / Linux / Windows machine, then open the same chat from any phone or computer on the network via IP — no app install on clients.

Inspired by [hermes-webui](https://github.com/nesquena/hermes-webui), but focused on **office workflows**: Hermes owns tasks/skills, OpenSquilla-style routing picks models, campus HPC / NIM runs inference, Obsidian stores reviewed knowledge.

## Features

- **Cross-platform** — macOS, Linux, Windows (native)
- **IP access** — binds `0.0.0.0:8765` by default; open `http://<server-ip>:8765` on phone / another PC
- **Control Center** — campus API, model IDs, C0–C3 routing, Obsidian vault, data policy
- **Office workflows** — meeting minutes, email draft, SOP candidates, deploy preflight, acceptance checklist, …
- **OpenSquilla-style routing** — Auto / C0–C3 / Vision with audit trail
- **Obsidian** — read allowed roots; AI writes only to `AI_Candidates` after approval
- **Streaming chat** — SSE (Hermes Agent `AIAgent` when installed)
- **Optional password** — `HERMES_ALI_PASSWORD` for remote protection
- **Demo mode** — UI works before Hermes Agent is installed

## Quick start

### macOS / Linux

```bash
git clone https://github.com/xielab2017/Hermes-ALI.git
cd Hermes-ALI
chmod +x start.sh
./start.sh
```

### Windows (PowerShell)

```powershell
git clone https://github.com/xielab2017/Hermes-ALI.git
cd Hermes-ALI
.\start.ps1
```

Then open:

| From | URL |
|------|-----|
| Same machine | http://127.0.0.1:8765 |
| Phone / other PC (same LAN) | http://`<server-ip>`:8765 |

## Campus Office setup

1. Open **控制中心** in the UI (or edit `~/.hermes/ali/campus-office-ai.json`).
2. Fill Base URL + exact model IDs from campus `GET /v1/models` (see `assets/campus-office-ai.example.json`).
3. Set API key in the OS only — never in JSON or chat:

```bash
# macOS / Linux
export CAMPUS_LLM_API_KEY='…'

# Windows PowerShell
[Environment]::SetEnvironmentVariable("CAMPUS_LLM_API_KEY", "…", "User")
```

4. Point Obsidian `vault_path` at your vault; AI output goes to `00_Inbox/AI_Candidates`.
5. Use sidebar **工作流** for 会议纪要 / 邮件草稿 / 部署预检 / 验收清单, etc.

Role split (from the campus handbook):

| Component | Responsibility |
|-----------|----------------|
| Hermes-ALI / Hermes | Tasks, skills, workflows, tools |
| OpenSquilla-style router | Model tier selection only |
| Campus HPC / NIM | Inference |
| Obsidian | Reviewed long-term knowledge |

When `data_policy` is `restricted`, external cloud fallback is refused.

## Configuration

| Variable | Default | Meaning |
|----------|---------|---------|
| `HERMES_ALI_HOST` | `0.0.0.0` | Bind address |
| `HERMES_ALI_PORT` | `8765` | Port |
| `HERMES_ALI_PASSWORD` | _(empty)_ | Optional shared password |
| `HERMES_ALI_STATE_DIR` | `~/.hermes/ali` | Sessions, campus config, audit |
| `HERMES_ALI_AGENT_DIR` | auto-discover | Path to hermes-agent |
| `CAMPUS_LLM_API_KEY` | — | Campus API key (name configurable) |

## Version

**v1.1.0** — Campus Office control center + workflows.

## License

MIT © Xie Lab

## Credits

- [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)
- [nesquena/hermes-webui](https://github.com/nesquena/hermes-webui)
- Campus Office AI Skill (`deploy-campus-office-ai`) — Hermes × OpenSquilla handbook
