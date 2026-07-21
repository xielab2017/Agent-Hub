# Agent Hub `v5.0.8_Java` — Desktop contract

This branch is the **Agent Hub** stack consumed by the JavaFX desktop shell
([EasyMultiProfiler-Desktop](https://github.com/xielab2017/EasyMultiProfiler-Desktop)
or local `Agent Hub Desktop`).

## Role split

| Layer | Owns |
|-------|------|
| **This repo / branch** | Agent Hub UI + Python gateway (`server.py` :8765), EMP joint-analysis client hooks |
| **EasyMultiProfiler-Web `v8.0.0_Java`** | R/Plumber API + EMP Web UI (:8000 / :8080) |
| **Java Desktop** | One-click install, process lifecycle, WebView chrome, Hub+EMP tabs |

## Desktop environment

When launched by the Java shell:

```bash
AGENT_HUB_DESKTOP=1
HERMES_ALI_HOST=127.0.0.1
HERMES_ALI_PORT=8765
# optional
CAMPUS_LLM_API_KEY=...
HERMES_ALI_PASSWORD=...
```

Recommended launch (already supported by `server.py`):

```bash
python3 server.py --host 127.0.0.1 --port 8765 --no-browser
```

## Health

- `GET http://127.0.0.1:8765/api/health` → JSON with `"ok": true`

## EMP companion

Desktop starts EMP from branch `v8.0.0_Java` and writes joint-analysis settings into
`~/.hermes/ali/campus-office-ai.json` (`emp.local_api_base`, `emp.web_ui_url`, …).

## Version

- Base: Agent Hub **v5.0.7** (`a48abef`)
- Branch tag purpose: Java Desktop packaging line → **v5.0.8_Java**
