# Changelog

## v5.3.6 — 2026-09-25

Tested against the real MiniMax API from GitHub runners (workflow
"MiniMax live check", key from the `MINIMAX_KEY` repository secret, runs on
a push tagged `[minimax-live]` or manually). Final run: region, chat, web
search + evidence, memory, a 4-step scientific task, Hermes Agent chat /
`read_file` tool call / memory, and error handling all pass with
**MiniMax-M3**, now the default MiniMax model (the key belongs to the China
region, `api.minimaxi.com/v1`; the account lists M2 … M2.7-highspeed and M3).

Fixed on the way:
- **Tool-call markup as the answer.** MiniMax-M2 answered a search request
  with its own `<minimax:tool_call><invoke …>` text. Direct mode now says no
  tools exist (search is already done), hides tool-call markup and retries a
  tool-call-only reply once.
- **No article read.** DOI links lead to publisher pages that block
  automated readers; PubMed / DOI sources are now read through Europe PMC
  abstracts (0 → 3 of 3 papers read).
- **Newest-first PubMed.** E-utilities default to newest-first; the search
  asks for relevance (it had returned last week's unrelated papers).
- **Chinese research questions reached no English database.** When a question
  has no English term, the configured model writes a short English keyword
  query first (reasoning models get room to think); it is used for search,
  passage selection and evidence. Task steps search their topic (goal + step),
  not the whole step prompt.
- **Unrelated papers as sources.** A research query whose English terms no
  result mentions now reports "no relevant results" instead of passing e.g.
  reporting guidelines to the model.
- **Reviewer.** Numbers the reply sets itself in a design (power, dropout,
  CI level, HRmax / VO₂max, CV, LOA, per-group n — also inside table rows)
  are design parameters, not untraceable facts; a named reference ("Jensen et
  al. 2015") that no retrieved source mentions is flagged — it caught one
  made-up citation. Evidence records why a page could not be read.

## v5.3.5 — 2026-09-25

- **Anthropic-compatible endpoints.** A base URL ending in `/anthropic`
  (MiniMax `https://api.minimax.cn/anthropic` — the address Coding Plan /
  Claude Code setups use — `api.minimaxi.com/anthropic`,
  `api.minimax.io/anthropic`) is spoken to with the Messages API: system
  prompt and history mapped to it, streamed text only (thinking blocks are not
  shown), truncation, retries and errors handled like the OpenAI path.
- MiniMax presets list their alternative endpoints; a chosen one is kept by
  routing and the direct path (stale or foreign URLs still snap back to the
  catalog). The region probe tries every endpoint of a region and reports the
  one that works; "refresh models" suggests it.
- `scripts/minimax_live_check.py` also reads `ANTHROPIC_BASE_URL` /
  `ANTHROPIC_API_KEY`, tries that endpoint first, and warns when a
  `${sk-cp-…}` shell expansion has dropped the `sk-` prefix.

## v5.3.4 — 2026-09-25

- `scripts/minimax_live_check.py`: one command checks a real MiniMax account
  end to end in a throw-away state directory — region and models, a streamed
  reply with review and provenance, web search with evidence, memory across
  turns, a 3-step scientific task, and a wrong model coming back as a clear
  error. The key is read from `MINIMAX_KEY` and masked in all output.
- Region probe: when `GET /v1/models` is unavailable (not an auth error), a
  one-line chat request decides which region accepts the key.
- MiniMax's error envelope in an HTTP 200 reply (`base_resp.status_code` ≠ 0,
  e.g. 1004 login fail) is reported as an error with a region hint instead of
  an empty reply.

## v5.3.3 — 2026-09-25

Search, problem handling, scientific tasks and continuity, tested end to end
against a real Agent Hub server on a simulated network: search engines,
PubMed / Europe PMC / Crossref / OpenAlex and article pages served from real
PubMed records on the circulating-irisin measurement controversy, plus a stub
model that answers only from the context the Hub sends it. Everything it
exposed is fixed.

**Search**
- The chat command is stripped before searching ("搜索一下：…？" → the topic).
- Chinese research questions ("人血浆中鸢尾素的浓度") route to the literature
  databases; English-only APIs (PubMed / OpenAlex / arXiv) get the question's
  English terms, and skip the request when there are none.
- The same paper returned by several indexes is listed once; literature hosts
  are no longer capped at two results.
- Sources are numbered by credibility (papers / official first, forums last).
- A Chinese question answered by English papers is no longer flagged
  "low relevance — do not state numbers".
- The search deadline now covers the whole engine cascade (slow engines
  could hold a request for ~50 s).
- Search runs inside the stream: the chat request returns at once and progress
  shows live. A failed search says so ("N 个引擎失败…") instead of
  "检索完成 · 0 条来源".

**Evidence and review**
- Concentrations are understood: `ng/ml`, `pg/mL`, `mg/dL`, `µg/L`, molar
  units, ranges (`0.26–1.86 ng/ml`), normalised to one unit and keyed by
  analyte and sample (blood / CSF / urine…). A ≥5× disagreement between
  sources is reported as a conflict (3.6 vs 100 ng/ml); cohort variation
  (3.6 vs 4.3) is not. Assay names (ELISA, MS…) are never taken as the analyte.
- A reply that states both conflicting values is noted, not warned — it did
  what the evidence digest asked; silently picking one side is still a warning.
- Reviewer labels for evidence issues in the UI (they showed raw keys).

**Problem handling**
- Rate limits (429), provider 5xx and dropped connections are retried with
  backoff (Retry-After honoured) before any token streams; a bad key is not.
- A stream that ends without a finish marker is marked
  "回复可能不完整"; malformed streams fall back to a normal request.
- Stop really stops: the run aborts its provider stream, the reply keeps what
  was streamed (marked stopped), and a run replaced by a newer message is
  dropped instead of landing after the newer answer.
- No model reply → the message is stored as an error (or demo), never as an
  answer: tasks stop there instead of "completing" a step, and the diagnostic
  is not reviewed or fed back to the model. A missing model falls back to the
  backend's model; a missing model / key is named in the reply.
- 401 hints name the vendor / MiniMax region instead of always listing
  OpenRouter / NVIDIA prefixes.

**Scientific tasks and continuity**
- Numbered steps written after "？" are recognised (the user's plan was being
  replaced by a generic template).
- A task step no longer triggers web search because an earlier step's title
  in its prompt says "检索".
- One source numbering per task: [n] means the same source in every step;
  steps that do not search get the task's source list and are reviewed
  against it.
- After a reload or gateway restart, "继续" re-issues a step whose prompt was
  never sent or whose run died.
- A turn left unanswered by a gateway restart gets an "interrupted" note.
- Model history is bounded (newest turns within a size budget, a note when
  older ones are left out) and excludes failed replies.

## v5.3.2 — 2026-09-25

MiniMax provider brought up to date.

- **Two regions.** `minimax` is now the global endpoint
  (`https://api.minimax.io/v1`, `MINIMAX_API_KEY`); the new `minimax-cn`
  preset is the mainland-China endpoint (`https://api.minimaxi.com/v1`,
  `MINIMAX_CN_API_KEY`). The retired `api.minimax.chat` host is gone. The
  China office combo uses `minimax-cn`.
- **M2-series models.** Slots default to `MiniMax-M2`; suggestions list
  M2.7 / M2.7-highspeed / M2.5 / M2.5-highspeed / M2.1 / M2 (Text-01 kept
  for old configs).
- **Coding / Token Plan keys** (`sk-cp-…`) are detected as MiniMax instead
  of OpenAI.
- **Hermes / OpenClaw.** `minimax-cn` maps to Hermes's native `minimax-cn`
  provider (China keys previously hit the global endpoint and failed auth);
  the matching `MINIMAX_API_KEY` / `MINIMAX_CN_API_KEY` is written to the
  managed `.env` and subprocess env, and stale vendor keys are not inherited.
- **Region probe.** When "refresh models" fails for a MiniMax provider, the
  Hub checks the other region's `/v1/models` and suggests switching if the key
  works there (errors are masked; the key is never echoed).
- `data_policy: restricted` blocks `minimax-cn` like other external vendors.

## v5.3.1 — 2026-09-25

Hermes fusion verified against the real **Hermes Agent v0.19.0** (in-process
`run_agent.AIAgent` and the `hermes` CLI) driven through Agent Hub with a
local OpenAI-compatible model — and the problems it exposed fixed.

- **Tool calls were invisible.** Hermes ≥0.19 calls
  `tool_progress_callback("tool.started", name, preview, args)` /
  `("tool.completed", …, duration=, is_error=)` / reasoning events; the Hub's
  callback expected `(name, preview)`, raised, and Hermes swallowed the error —
  so tools never reached the UI or provenance. The callback now understands
  both styles; tool start / finish (with duration and success) stream live and
  are recorded in provenance.
- **Hub context was sent as the user's message.** The in-process path now
  passes it as `ephemeral_system_prompt` (older Hermes: legacy concatenation),
  so Hermes keeps a clean user turn in its own session history and memory.
- **`config.yaml` got two `mcp_servers` keys** (the TLS patch's YAML
  round-trip erased the MCP marker comments) and a user's own MCP servers could
  be dropped. MCP sync is now YAML-aware: user servers are kept, disabled Hub
  servers removed, one key only; broken files are repaired.
- Connect wrote Hermes' hardcoded default model when only the Backend model was
  set; it now falls back to that model first.
- **CLI path:** Hermes notices printed before the answer (`⚠ tirith …`),
  carriage returns and the `session_id:` line no longer leak into replies; the
  last turns are included in the prompt so follow-ups keep context (the CLI has
  no history argument); the Hermes session id is recorded in provenance.
- **Skills:** skills saved or installed after Connect (incl. 「存为技能」) are
  linked into `~/.hermes/skills` immediately; uninstall removes the link;
  dangling links are repaired. Verified with Hermes' own skill discovery.
- Removed an unused duplicate `_provider_fallback` with undefined names.
- Tests: `tests/test_hermes_integration.py` (incl. an end-to-end run through the
  real Hub code path with a fake `run_agent` on the discovery path); tests never
  touch real claw skill dirs — 171 passing.

## v5.3.0 — 2026-09-25

Type a task in the chat box → search → check the data → summarise → move on
to the next step automatically.

- **Tasks & auto next step** — `ali/task_runner.py` (new). `/task …` (or a
  message with explicit steps: `1. … 2. …`, `第一步…`, `首先…然后…最后…`)
  becomes a multi-step task; otherwise a research / general template is used
  (max 8 steps; a final "汇总与下一步" step is added when missing). Each step
  runs through the normal chat pipeline with the goal, earlier step
  conclusions and open issues in its prompt. After every step the reviewer
  gate decides: **auto** mode continues unless the reviewer raised warnings;
  **confirm** mode waits for 「继续下一步」. Tasks persist
  (`STATE_DIR/tasks/`) and the dock restores after reload. APIs:
  `POST /api/tasks`, `POST /api/tasks/preview`, `GET /api/tasks/<id>`,
  `POST /api/tasks/<id>/advance|stop|mode`, `GET /api/sessions/<id>/task`.
- **Composer** — slash commands with a hint menu: `/task`, `/search`, `/deep`,
  `/summary`, `/verify`, `/next`, `/stop`, `/help`; the 深度搜索 toggle is now
  actually sent (`deep_search`); guidance typed while a run is going ("steer")
  is carried into the next turn / task step instead of being dropped.
- **External search engines** — `ali/search_engines.py` (new): DuckDuckGo,
  百度 (best-effort), SearXNG (your instance), Brave Search API, Tavily; per-engine
  switches, new keys, provider choices and page-reading options in Control
  Center → 搜索. (Bing Web Search API was retired in 2025 and is not used.)
- **Read the pages** — `ali/page_fetch.py` (new): deep search opens the top
  results (default 3, parallel, 10 s budget) and keeps the passages that answer
  the query. Only public addresses are fetched; redirects to localhost / LAN /
  metadata endpoints are refused (SSRF guard).
- **Data accuracy** — `ali/source_quality.py` (new) grades every source
  (official / database / academic / preprint / news / user content) and dates
  it; `ali/evidence.py` (new) extracts the numbers the sources state, counts how
  many independent domains agree and detects conflicting values. The reviewer
  now also reports `conflicting_number` (warn), `single_source_number` and
  forum-only evidence. Form / Excel web-fill picks the value most domains agree
  on (confidence high / medium / low).
- **Summaries** — an evidence digest (graded sources, key passages, cross-checked
  numbers, conflicts) goes into the prompt with a required answer structure
  (结论摘要 / 关键数据表 / 分歧与不确定 / 下一步); replies show a 「来源与证据」
  panel and clickable 「下一步」 suggestions; `/summary` restructures the last
  reply; provenance records and reports include the evidence.
- **Fixes** — search `_fetch` ignored `verify_tls` and its relaxed-TLS retry
  (opener built without SSL context); the MiniMax-parity engine could recurse
  when the provider was not `auto`; `search.max_results` was unused; the OpenClaw
  reply path crashed with a NameError (`resolve_backend_verify_tls` not
  imported); finished SSE streams kept their connection open (keep-alive with no
  length), which after a few runs exhausted the browser's per-host connection
  pool and stalled other requests; Control Center rendered the search tab last.
- Tests: `test_search_engines.py`, `test_evidence.py`, `test_task_runner.py`
  (new, incl. a 4-step task end to end), `tests/conftest.py` blocks real network
  in every in-process test — 163 passing.

## v5.2.0 — 2026-09-25

The rest of the Claude Science standard: a background reviewer, scientific
database connectors, and "save any pipeline as a reusable skill".

- **Reviewer** — `ali/reviewer.py` (new). Deterministic, offline, runs on every
  reply: numbered citations that point at no retrieved source, URLs not among
  the sources or evidence, malformed DOIs / PMIDs, identifiers not in the
  sources, and **untraceable numbers** (percentages, p-values, statistics,
  n=, quantities with units) that appear in none of the evidence (sources,
  user message, workspace excerpts, tool output). Results go on the message,
  into SSE `done`, and are sealed into the provenance record.
  `POST /api/review/<session>/<message>` re-runs it; `{"online": true}` also
  resolves DOIs (Crossref) and PMIDs (NCBI) — unreachable services count as
  unknown, never as wrong. Web-search sources are now numbered `[1]…[n]` in the
  prompt (same order as the provenance record) and the model is asked to cite
  by number.
- **Science database connectors** — `ali/science_connectors.py` (new):
  UniProt, RCSB PDB, Ensembl, ChEMBL, ClinicalTrials.gov, NCBI GEO, ClinVar,
  Reactome, Europe PMC, Crossref (public, read-only, key-free). Routed from
  identifiers (UniProt / PDB / ENSG / CHEMBL / NCT / rsID / GSE / DOI / PMID),
  gene symbols and topic keywords, fanned out in parallel, merged in stable
  order; a failing database never blocks the others and never yields
  placeholder hits. Registered first in the academic search intent (no network
  when nothing science-like is detected). Per-database switches in Control
  Center → **科学数据库** (with a test box); `data_policy=restricted` disables
  all; every query is audited. APIs: `GET/POST /api/science/connectors`,
  `GET /api/science/search?q=`.
- **Save as skill** — `ali/skill_capture.py` (new). 「存为技能」 on a reply
  drafts a SKILL.md from the session and its provenance (when to use, inputs,
  steps incl. route/skills/sources/tools, output format from the reply's
  headings, quality checks, provenance hash); editable before saving; never
  overwrites an existing skill (auto `-2`, `-3`…); loads into the Hub. Captured
  skills carry `triggers:` and re-activate automatically on matching requests
  in future sessions, with their steps injected into the prompt. APIs:
  `POST /api/skills/from-session`, `POST /api/skills/from-session/save`.
- **Fix** — `subagent_planner.plan_lanes`: short sport/event questions were
  answered directly by the "short message" shortcut instead of being planned
  into lanes (4 tests had been failing since v5.0.0).
- **CI** — `.github/workflows/tests.yml` runs the suite on Python 3.9 and 3.12
  for every push and pull request.
- Tests: `test_reviewer.py`, `test_science_connectors.py`,
  `test_skill_capture.py` (new) and a longer end-to-end run — 119 passing on Python 3.9 / 3.11 / 3.12.

## v5.1.0 — 2026-09-25

Auditable provenance for every reply, modelled on Claude Science's
standard that "every output carries an auditable history of how it was made".

- `ali/provenance.py` (new) — per-reply provenance record
  (`agent-hub.provenance/1`): request hash, provider/model/tier/route,
  engine/runtime/soul/subagent, skills, workspace grounding, system-prompt
  hash + text, numbered web sources (title/url/domain/engine), tool calls,
  output hash, path-check result, timing, environment (app version, Python,
  platform, git commit), run-journal path, and a deterministic zh/en
  "how this was made" sentence.  A SHA-256 over the canonical record makes
  edits detectable.  Secrets are never stored (secret keys dropped,
  key-like strings masked, `base_url` reduced to host).
- `ali/streaming.py` — web search now keeps the structured source list
  (prompt context unchanged); both the normal and the self-heal finalize
  paths write a record, store a compact `provenance` summary on the
  message, include it in the SSE `done` payload, and log
  `provenance_recorded` to the audit trail.  Best-effort: never breaks chat.
- API: `GET /api/provenance/<session>/<message>` (record + `verified`),
  `GET /api/provenance/<session>/<message>/report` (Markdown),
  `GET /api/sessions/<id>/provenance` (list),
  `GET /api/sessions/<id>/reproducibility-bundle` (zip: session, records,
  run journals, `REPORT.md`, `MANIFEST.json` with per-file SHA-256).
  `/api/health` reports the provenance schema.
- UI: 「溯源 / Provenance」 button on assistant replies opens a dialog
  (how it was made, model & route, context, sources, tools, output checks,
  environment, integrity badge, JSON / report download); 🧾 in the session
  list exports the reproducibility bundle; the workspace path warning now
  also shows on reloaded messages.
- `tests/test_provenance.py` (new) — 8 tests, including an isolated
  end-to-end `start_chat` run.

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
