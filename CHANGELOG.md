# Changelog

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
