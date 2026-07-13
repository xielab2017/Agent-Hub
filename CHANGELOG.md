# Changelog

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

Initial release.
