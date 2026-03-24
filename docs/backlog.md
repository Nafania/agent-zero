# Agent Zero Backlog

Curated from [GitHub issues](https://github.com/agent0ai/agent-zero/issues) and [PRs](https://github.com/agent0ai/agent-zero/pulls) on 2026-03-24.
Verified against fork codebase. Items not reproducible in our fork are excluded.

Legend: `CHERRY-PICK` = open PR exists, review and adapt. `BUILD` = implement from scratch. `INVESTIGATE` = research first.

---

## Already Done in Our Fork

| What | Details |
|------|---------|
| **Token/perf tracking** ([#660](https://github.com/agent0ai/agent-zero/issues/660)) | `metrics_collector.py` + `metrics_dashboard.py` + dashboard UI. Tokens done, USD cost not yet. |
| **Ollama TypeError** ([#970](https://github.com/agent0ai/agent-zero/issues/970)) | Defensive `or ""` parsing in `_parse_chunk` in `models.py`. |
| **FastMCP compat** ([#1006](https://github.com/agent0ai/agent-zero/issues/1006)) | Bumped to `fastmcp==3.1.1`. |
| **Browser CDP migration** ([#723](https://github.com/agent0ai/agent-zero/issues/723)) | Migrated from Playwright to CDP. `max_steps=50`, timeouts, stuck-task `kill_task`. |
| **Browser agent hang** | `fix/browser-agent-hang` branch merged. |
| **Too many open files** | `fix/too-many-open-files` branch merged (LanceDB/Cognee FD leak). |
| **Slash commands mid-text** | `fix/slash-commands-mid-text` branch merged. |
| **Memory dashboard area filter** | `fix/memory-dashboard-area-filter` branch merged. |
| **Skills marketplace** | `feat/skills-marketplace` — search, install, manage skills from UI. |
| **Cognee cross-process init** | `fix/cognee-cross-process-init` branch merged. |
| **Dependency bump** | `chore/bump-all-dependencies` — all major deps updated. |

---

## Backlog

### P0 — Security & Stability

| # | What | Source | How | Effort |
|---|------|--------|-----|--------|
| 1 | **Secrets exposed to LLM in system prompt** — `§§secret()` placeholders not resolved before sending to LLM. Masking exists in browser_agent/print_style but not in prompt pipeline. | [#1107](https://github.com/agent0ai/agent-zero/issues/1107) | INVESTIGATE then BUILD | M |
| 2 | **Secrets not resolved in MCP server config** — `§§secret()` in MCP env/headers/url passed as literal string. | [PR #1150](https://github.com/agent0ai/agent-zero/pull/1150) | CHERRY-PICK | S |
| 3 | **Duplicate response loop breaker** — agent stuck in "same message" infinite loop. Add `duplicate_retries` counter, break after 3 identical responses. 13-line fix in `agent.py`. | [PR #1265](https://github.com/agent0ai/agent-zero/pull/1265), fixes [#1056](https://github.com/agent0ai/agent-zero/issues/1056) | CHERRY-PICK | S |
| 4 | **Dynamic output truncation** — `ContextWindowExceededError` when tool output is huge. Calculate threshold as 12.5% of available context instead of hardcoded 1MB. | [PR #857](https://github.com/agent0ai/agent-zero/pull/857), fixes [#833](https://github.com/agent0ai/agent-zero/issues/833) | CHERRY-PICK | S |

### P1 — High-Impact Features (PRs exist)

| # | What | Source | How | Effort |
|---|------|--------|-----|--------|
| 5 | **Per-chat model override** — toggle custom model per chat without changing global settings. Backend + sidebar tune button + modal. Includes tests. | [PR #1291](https://github.com/agent0ai/agent-zero/pull/1291), addresses [#669](https://github.com/agent0ai/agent-zero/issues/669)/[#869](https://github.com/agent0ai/agent-zero/issues/869) | CHERRY-PICK | M |
| 6 | **Dedicated vision model** — separate `vision_model` config in `AgentConfig`. Factory function, settings UI, vision strategy (native vs dedicated). | [PR #768](https://github.com/agent0ai/agent-zero/pull/768), fixes [#698](https://github.com/agent0ai/agent-zero/issues/698) | CHERRY-PICK | M |
| 7 | **Chat search + keyboard shortcuts + font size** — sidebar filter, `/` focus, `Alt+N` new chat, `Alt+K` search, S/M/L/XL font, file browser filter. Pure frontend. | [PR #1156](https://github.com/agent0ai/agent-zero/pull/1156), fixes [#704](https://github.com/agent0ai/agent-zero/issues/704) | CHERRY-PICK | M |
| 8 | **Edit and resend previous messages** — pencil icon on user messages, inline editor, Ctrl+Enter to save & resend (truncates history at edit point). | [PR #1137](https://github.com/agent0ai/agent-zero/pull/1137) | CHERRY-PICK | M |
| 9 | **Browser-based terminal (xterm.js)** — multi-tab terminal in web UI with persistent PTY sessions. Survives page refresh. htop/vim/nano reattach. | [PR #1279](https://github.com/agent0ai/agent-zero/pull/1279), fixes [#897](https://github.com/agent0ai/agent-zero/issues/897) | CHERRY-PICK | L |
| 10 | **Agent can update scheduled tasks** — add `scheduler:update_task` tool to scheduler prompt and tools. Fixes "agent says it can't update tasks". | [PR #1105](https://github.com/agent0ai/agent-zero/pull/1105), relates to [#677](https://github.com/agent0ai/agent-zero/issues/677) | CHERRY-PICK | S |

### P2 — Medium-Impact Features

| # | What | Source | How | Effort |
|---|------|--------|-----|--------|
| 11 | **Per-agent MCP config + auto-detect transport** — subordinate agents can have own MCP servers. Auto-detect: try streamable-HTTP, fallback to SSE. | [PR #1232](https://github.com/agent0ai/agent-zero/pull/1232), fixes [#473](https://github.com/agent0ai/agent-zero/issues/473) | CHERRY-PICK | M |
| 12 | **Anthropic OAuth session tokens** — use Claude Pro/Max subscription via `ANTHROPIC_SESSION_TOKEN`. Adds `anthropic_oauth` provider. | [PR #1315](https://github.com/agent0ai/agent-zero/pull/1315), fixes [#1308](https://github.com/agent0ai/agent-zero/issues/1308) | CHERRY-PICK | S |
| 13 | **Subordinate delegation loop prevention** — depth limits (`max_agent_depth=5`), same-profile warning, 3-question decision framework for delegation. | [PR #778](https://github.com/agent0ai/agent-zero/pull/778) | CHERRY-PICK | M |
| 14 | **Concurrent requests limit** — semaphore-based cap on simultaneous requests per model type. Useful for parallel chats + local models. | [PR #1043](https://github.com/agent0ai/agent-zero/pull/1043) | CHERRY-PICK | S |
| 15 | **Dynamic context pruning** — auto-detect token limits, intelligent pruning of old history for long sessions. | [PR #1317](https://github.com/agent0ai/agent-zero/pull/1317) | CHERRY-PICK | M |
| 16 | **MCP race condition fix + SSH prompt detection** | [PR #1283](https://github.com/agent0ai/agent-zero/pull/1283) | CHERRY-PICK | S |
| 17 | **Organize chats by project (tabs)** — projects as tabs with chat lists, active task indicator. | [#1189](https://github.com/agent0ai/agent-zero/issues/1189) | BUILD | L |
| 18 | **Manual chat renaming** — rename chats, optionally disable auto-rename. | [#702](https://github.com/agent0ai/agent-zero/issues/702) | BUILD | S |
| 19 | **Memory editing UI** — view, edit, delete memories from web UI. | [#701](https://github.com/agent0ai/agent-zero/issues/701) | BUILD | L |
| 20 | **Transfer memories between projects** | [#883](https://github.com/agent0ai/agent-zero/issues/883) | BUILD | M |

### P3 — Nice to Have

| # | What | Source | How | Effort |
|---|------|--------|-----|--------|
| 21 | **STOP / interrupt button** — hard-stop active agent run from UI without wiping chat. | [#1099](https://github.com/agent0ai/agent-zero/issues/1099) | BUILD | L |
| 22 | **Ollama/local model reliability** — configurable recall search timeout (currently hardcoded 30s), graceful empty `reasoning_delta`. | [#865](https://github.com/agent0ai/agent-zero/issues/865) | BUILD | S |
| 23 | **Fallback model chain** — on primary model failure, switch to backup model (not just retry). | [#1052](https://github.com/agent0ai/agent-zero/issues/1052) | BUILD | M |
| 24 | **Skills upload path mismatch** — `/a0/usr/skills` vs `/a0/skills`. | [#1045](https://github.com/agent0ai/agent-zero/issues/1045) | INVESTIGATE | S |
| 25 | **Model search dropdown CSS** — missing color on `.model-search-item`. | [#1294](https://github.com/agent0ai/agent-zero/issues/1294) | BUILD | XS |
| 26 | **Google models via OAuth** | [PR #905](https://github.com/agent0ai/agent-zero/pull/905), [#928](https://github.com/agent0ai/agent-zero/issues/928) | CHERRY-PICK | M |
| 27 | **Native ChromaDB/VectorDB** — alternative to Cognee for distributed deployments. | [#1092](https://github.com/agent0ai/agent-zero/issues/1092) | BUILD | XL |
| 28 | **Multi-user / multitenancy** | [PR #655](https://github.com/agent0ai/agent-zero/pull/655) | CHERRY-PICK | XL |
| 29 | **Chat-level prompt subdirectory selector** | [#537](https://github.com/agent0ai/agent-zero/issues/537) | BUILD | M |

---

## Recommended Execution Order

**Wave 1 — Quick cherry-picks (S effort, high value):**
- #3 Loop breaker (PR #1265) — 13 lines, prevents infinite loops
- #4 Output truncation (PR #857) — prevents context overflow crash
- #2 Secrets in MCP config (PR #1150) — security fix
- #10 Scheduler update tool (PR #1105) — small prompt/tool change
- #12 Anthropic OAuth (PR #1315) — new provider
- #14 Concurrent request limit (PR #1043) — rate protection
- #16 MCP race condition (PR #1283) — stability
- #25 Model dropdown CSS (#1294) — trivial CSS fix

**Wave 2 — Medium cherry-picks (M effort, high value):**
- #5 Per-chat model override (PR #1291) — most-requested feature area
- #7 Chat search + shortcuts (PR #1156) — pure frontend UX
- #8 Edit/resend messages (PR #1137) — standard chat UX
- #6 Vision model (PR #768) — enables cheap text models + vision
- #11 Per-agent MCP + auto-transport (PR #1232)
- #13 Delegation loop prevention (PR #778)
- #15 Dynamic context pruning (PR #1317)

**Wave 3 — Build from scratch:**
- #1 Investigate secrets leak (#1107)
- #18 Manual chat renaming
- #22 Ollama timeout tuning
- #17 Project tabs for chats
- #21 STOP button

**Wave 4 — Large features:**
- #9 Web terminal (PR #1279)
- #19 Memory editing UI
- #20 Memory transfer
- #23 Fallback model chain
- #27 VectorDB support
- #28 Multitenancy
