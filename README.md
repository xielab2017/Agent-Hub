# Hermes-ALI

**Lightweight, cross-platform terminal for [Hermes Agent](https://hermes-agent.nousresearch.com/).**

Run once on a Mac / Linux / Windows machine, then open the same chat from any phone or computer on the network via IP — no app install on clients.

Inspired by [hermes-webui](https://github.com/nesquena/hermes-webui), but intentionally smaller: chat + sessions + remote LAN access. No build step, no framework, no bundler — Python stdlib + vanilla JS.

## Features

- **Cross-platform** — macOS, Linux, Windows (native)
- **IP access** — binds `0.0.0.0:8765` by default; open `http://<server-ip>:8765` on phone / another PC
- **Multi-device** — same sessions from multiple browsers
- **Streaming chat** — SSE token stream (Hermes Agent `AIAgent` when installed)
- **Session sidebar** — create / switch / delete chats
- **Optional password** — `HERMES_ALI_PASSWORD` for remote protection
- **Demo mode** — UI works even before Hermes Agent is installed

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

### Or directly

```bash
python3 server.py --host 0.0.0.0 --port 8765
```

Then open:

| From | URL |
|------|-----|
| Same machine | http://127.0.0.1:8765 |
| Phone / other PC (same LAN) | http://`<server-ip>`:8765 |

The startup banner prints your LAN IP automatically.

## Enable full Hermes Agent

Hermes-ALI uses your existing Hermes Agent install (same approach as hermes-webui).

```bash
# Install agent (macOS / Linux)
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash

# Windows PowerShell
iex (irm https://hermes-agent.nousresearch.com/install.ps1)

# Configure a model provider
hermes model
```

If the agent lives outside the default `~/.hermes/hermes-agent` (or `%LOCALAPPDATA%\hermes\hermes-agent` on Windows):

```bash
export HERMES_ALI_AGENT_DIR=/path/to/hermes-agent
```

Without an agent, Hermes-ALI runs in **demo mode** so you can still verify remote access.

## Secure remote access

```bash
# Require a password for /api/* (recommended when binding 0.0.0.0)
export HERMES_ALI_PASSWORD='your-secret'
./start.sh --no-browser
```

Windows:

```powershell
.\start.ps1 -Password "your-secret" -NoBrowser
```

For internet exposure, prefer a reverse proxy / Tailscale / SSH tunnel over raw public ports.

### SSH tunnel example

```bash
ssh -L 8765:127.0.0.1:8765 user@your-server
# then open http://127.0.0.1:8765 locally
```

## Configuration

| Variable | Default | Meaning |
|----------|---------|---------|
| `HERMES_ALI_HOST` | `0.0.0.0` | Bind address (`127.0.0.1` for local-only) |
| `HERMES_ALI_PORT` | `8765` | Port |
| `HERMES_ALI_PASSWORD` | _(empty)_ | Optional shared password |
| `HERMES_ALI_STATE_DIR` | `~/.hermes/ali` | Sessions / settings |
| `HERMES_ALI_AGENT_DIR` | auto-discover | Path to hermes-agent checkout |
| `HERMES_HOME` | `~/.hermes` | Hermes Agent home |

## API (v1)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/status` | Version, LAN IPs, agent status |
| POST | `/api/login` | `{ "password": "..." }` → token |
| GET/POST | `/api/sessions` | List / create sessions |
| GET/PATCH/DELETE | `/api/sessions/:id` | Read / update / delete |
| POST | `/api/sessions/:id/chat` | Start stream → `{ stream_id }` |
| GET | `/api/stream/:id` | SSE (`token`, `tool`, `done`, `error`) |
| POST | `/api/sessions/:id/cancel` | Cancel active run |

## Project layout

```
Hermes-ALI/
  server.py          # HTTP entry
  bootstrap.py       # Cross-platform launcher
  start.sh           # macOS / Linux
  start.ps1          # Windows
  ali/               # Backend (config, sessions, streaming, auth, routes)
  static/            # index.html + style.css + app.js
```

## Requirements

- Python **3.9+** (stdlib only — no pip packages required for the terminal itself)
- Optional: [Hermes Agent](https://hermes-agent.nousresearch.com/) for real agent runs

## Version

**v1.0.0** — initial public release.

## License

MIT © Xie Lab

## Credits

- [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)
- [nesquena/hermes-webui](https://github.com/nesquena/hermes-webui) — design inspiration
