# Changelog

## v5.0.7 — 2026-07-20

EMP 16S end-to-end hardening and Trellis-controlled task mode.

- Hardened local EMP discovery/planning: metadata grouping variables and reference/test levels from bounded summaries.
- Exposed the full Data → Pairing → Parameters → Plan → Run → Results progress surface before scan, with disabled stages and concrete prerequisites.
- Fixed EMP detection, status reporting, and data file browser selection for the joint-analysis panel.
- Integrated Trellis controlled task mode (specs, agents, workspace journals) for repeatable Hub development.

## v5.0.6 — 2026-07-20

Agent Hub x EasyMultiProfiler local 16S MVP.

- Added bounded omics discovery, versioned manifests/plans/jobs/artifacts and secure allowed-root validation.
- Added a loopback-only EMP client, API capability negotiation, normalized bilingual errors and typed tool schemas.
- Added explicit plan confirmation, input fingerprinting, duplicate-run protection, persistent session mapping, and clear retry state after an interrupted local orchestration.
- Added the Control Center joint-analysis workflow with stable progress, cancellation and artifact access.
- Extended EMP Web with `/api/capabilities`, protected path preview/import and persistent session/job roots.
- Verified the real 16S flow across both services, including taxonomy preparation, Alpha results and PNG/PDF output.

## v4.0.0 — 2026-07-19

Agent Hub experience and autonomy upgrade: structured Markdown delivery, silent main-window orchestration, session folders with isolated cross-session context, and safe nightly maintenance proposals.

## v3.1.0 — 2026-07-18

MiniMax code (minimax_search) search parity — port the core capabilities
of MiniMax AI's MCP search server into Agent-Hub-3.0 as a drop-in upgrade.

- `ali/minimax_search_parity.py` (new) — `parse_query` advanced operator
  parser (`site:`, `inurl:`, `intitle:`, `intext:`, `inanchor:`, `-exclude`,
  `~synonym`, `"exact"`), `parallel_search` ThreadPoolExecutor fan-out with
  per-block timing/errors, `format_brief` MiniMax-style `<title>/<url>/<snippet>`
  blocks preferring `extra_snippets` over `snippet` over `description`,
  `browse_url` / `browse_urls` URL fetch + LLM-synthesized answer with
  token-aware chunking and parallel chunk answering, `search_structured`
  drop-in shim.
- `ali/websearch.py::search_structured` — parses advanced operators from
  the user's query, runs the cleaned body through normal search, and
  post-filters results by `site:`/`inurl:`/`intitle:`/`intext:`/`inanchor:`/
  `-exclude`.  World Cup primary-source fallback is skipped when any
  operator is set (respect user scoping).
- `ali/subagent_planner.py::_gather_sources` — when the planner has more
  than one search query, fans them out through `parallel_search` for a
  wider angle in roughly the same wall-clock time, with graceful
  fallback to serial on import/runtime errors.
- `ali/search_extensions.py` — new `search_minimax_parity` engine
  registered for every intent (event/news/academic/code/general).
  Honours operators, runs cleaned + exact variants in parallel, and
  falls back to the raw query when both come back empty.
- `tests/test_minimax_search_parity.py` (new) — 23 tests covering every
  ported behaviour: operator parser, brief formatter, parallel fan-out
  ordering/errors, char-based chunking with overlap, browse synthesis
  with stub llm/fetch, parity `search_structured`, websearch integration
  with `site:`/`-exclude`, planner parallel + serial-fallback, parity
  engine registration, and an end-to-end world-cup + site:wikipedia.org
  scenario that does NOT fabricate scores when offline.

Companion tests still pass (19 prior) — total 42/42 green.

## v3.0.0 — 2026-07-15

Hermes-WebUI fusion: Agent Hub as control-plane shell with deep Hermes sessions.

- `ali/webui_bridge.py`: discover/start/stop Hermes-WebUI sharing `HERMES_HOME`
- APIs: `GET /api/webui/status`, `POST /api/webui/start|open|stop`
- UI: 「Hermes 深度会话」fullscreen iframe + Claws panel WebUI controls
- Export `{HERMES_HOME}/webui/hub_route_contract.json` for WebUI token optimizer (C0–C3)
- Sync Hub→Hermes before opening deep sessions

Companion WebUI changes live in the hermes-webui checkout (`docs/agent-hub-bridge.md`).

## v2.0.0 — 2026-07-14

Unified model routing, agent configuration, resilient provider settings, and adaptive chat layout.

- One provider/model catalog shared by model settings, C0–C3/Vision routes, Agents, and Subagents
- Agent route inheritance plus per-agent provider/model overrides with legacy fallback
- Persistent LLM TLS verification settings for local MITM proxy environments
- Responsive, resizable sidebar and compact, collapsible task composer
- Model reasoning tags removed from user-visible reply content

## v1.4.59 — 2026-07-14

Public Agent Hub packaging + Appearance presets.

- README / docs screenshots for GitHub (`xielab2017/Agent-Hub`)
- Built-in logos: SUAT color + whiteboard only
- `ctl.sh install-service` durability: idempotent start, no accidental Hub stop on install

## v1.4.58 — 2026-07-14

Subagents ↔ C0/C1/C2/C3 tier models + Soul; parallel auto-pick across tiers.

## v1.4.57 — 2026-07-14

Fix parallel-task switching: parent-only strip, in-place progress, event delegation.

## v1.4.56 — 2026-07-14

Appearance: custom sidebar / empty-state logos (upload or built-in presets).

## v1.4.53–1.4.55

Self-evolution, Excel fill (explicit only), gateway durability / watchdog, UI polish.

## v1.1.3 — 2026-07-13

Fix API key + live model selection for NVIDIA / OpenRouter / etc.

- Save API keys locally to `~/.hermes/ali/secrets.json` (chmod 600); never in campus JSON
- **拉取可用模型** calls provider `GET /v1/models` and fills C0–C3 slots from real catalog
- Without Hermes Agent, chat uses OpenAI-compatible **direct LLM** streaming when key+URL are set
- Pasting a key into env-name field auto-migrates it into the secrets store

## v1.1.2 — 2026-07-13

Dynamic multi-provider catalogs + hybrid fusion.

## v1.1.1 — 2026-07-13

Appearance: zh/en, light/dark, accents.

## v1.1.0 — 2026-07-13

Campus Office control center + workflows.

## v1.0.0 — 2026-07-13

Initial release (as Hermes-ALI).
