# Agent Zero Backlog

Curated from [GitHub issues](https://github.com/agent0ai/agent-zero/issues), [PRs](https://github.com/agent0ai/agent-zero/pulls), and upstream `main` branch analysis (v0.9.8 → v1.3, 516 commits).
Last updated: 2026-03-27. Verified against fork codebase.

Legend: `CHERRY-PICK` = open PR exists, review and adapt. `UPSTREAM` = merged in upstream main, backport from commit. `BUILD` = implement from scratch. `INVESTIGATE` = research first.

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

## Upstream Architectural Changes (v0.9.8 → v1.3)

Large-scale changes from upstream. Each is listed with effort and dependencies so you can decide what's worth taking.

| # | What | Source | Depends on | Effort | Notes |
|---|------|--------|------------|--------|-------|
| A1 | **Plugin system** — full plugin architecture: `plugins/` dir, `plugin.yaml`, lifecycle hooks, per-plugin config/tools/extensions/webui/api. 16 built-in plugins extract memory, code exec, browser, model config into modular units. | Upstream v1.1. Commits: `54fb4746a4` (initial), `a48ac95a29` (hooks). Dir: `plugins/`, `helpers/plugins.py`. | A2 (path restructure) | XL | Fundamental architecture change. Touches every file. Everything below marked "plugin-dependent" requires this. |
| A2 | **Path restructuring** — Repo-root packages: `helpers/`, `tools/`, `api/`, `extensions/python/`, `websocket_handlers/` (matches upstream post–`d02dda3667`). | Upstream commit `d02dda3667` "BIG PYTHON REFACTOR". | — | L | Done in fork. Cherry-picking any upstream commit after this requires import translation. |
| A3 | **`@extensible` decorator** — any function with `@extensible` gets auto-generated `start`/`end` extension points. Plugins intercept calls without touching core code. | Upstream commit `d82b121bc9`. File: `helpers/extension.py`. | A1 (plugins) | L | Core to plugin system. Applied to ~20 functions in agent.py, models.py, and helpers. |
| A4 | **AgentConfig slimming** — fields removed: `chat_model`, `utility_model`, `embeddings_model`, `browser_model`, SSH settings, `memory_subdir`. All moved to plugin configs. | Upstream v1.1. Files: `initialize.py`, `models.py`, plugin configs. | A1 (plugins) | L | Config/settings system would need rework. |
| A5 | **WebSocket handlers → extensions** — Upstream removes dedicated `websocket_handlers/`; logic moves into extension hooks with dynamic WS registration. | Upstream v1.1. | A1, A3 | M | Coupled to plugin system and @extensible. |
| A6 | **API routing refactor** — new endpoint structure, optional per-handler caching, plugin-scoped endpoints, CSRF improvements. | Upstream v1.1. Dir: `api/`. Commit `4e243a996c`. | A1, A2 | L | Coupled to plugin system. Security fixes (#6, #7, #8) are independent. |
| A7 | **Extension directory restructuring** — extension folder paths derived from module path + qualname. Deep module-based dirs. | Upstream commit `7e1d9ad2a4`. | A1, A3 | M | New convention for where extension hooks live on disk. |
| A8 | **System prompt split** — monolithic system prompt split into per-concern extension files: `_10_main_prompt.py`, `_11_tools_prompt.py`, `_12_mcp_prompt.py`, `_13_secrets_prompt.py`, etc. | Upstream commit `2566ee134d`. | A7 | M | Modular prompt composition. Could be useful independently. |

## Upstream Features (v0.9.8 → v1.3)

Features introduced in upstream that could be backported independently or adapted.

| # | What | Source | Depends on | Effort | Notes |
|---|------|--------|------------|--------|-------|
| F1 | **Plugin Hub / Installer** — app-store-like plugin management: browse index, install from ZIP/Git/Hub, toggle, configure, scan, validate. | Upstream v1.1. Commits: `99aea498b9` (tabs), various. Dir: `plugins/_plugin_installer/`, `plugins/_plugin_scan/`, `plugins/_plugin_validator/`, `webui/components/plugins/`. | A1 (plugins) | XL | No plugin system = no plugin management. |
| F2 | **Self-update system** — native git-based self-update with UI overlay, version selector, branch support, backup config. | Upstream v1.1+. Files: `helpers/self_update.py`, `docker/run/fs/exe/self_update_manager.py`, `api/self_update_*.py`. | A2 | L | We deploy via Docker/Hassio CI/CD. Alternative approach to same problem. |
| F3 | **Email integration** — IMAP/Exchange inbox polling, SMTP replies, file attachments, dispatcher model for routing, whitelist with spoofing prevention, self-reply loop prevention. | Upstream commit `34f2354cb1`. Dir: `plugins/_email_integration/`. | A1 (plugins) | L | Plugin-dependent in upstream. Could be rebuilt as extension in our format. |
| F4 | **Telegram integration** — polling/webhook modes, per-user sessions, group chat, model routing, attachment handling. | Upstream commit `83ffa27d13`. Dir: `plugins/_telegram_integration/`. | A1 (plugins) | L | We have our own `a0-ext-telegram`. Compare approaches. |
| F5 | **Model presets / per-chat model switching (plugin version)** — preset management UI, per-chat model override, API key management, models summary in store. | Upstream v1.1. Dir: `plugins/_model_config/`. | A1, A4 | L | Plugin-dependent. PR #1291 in backlog offers a simpler standalone version. |
| F6 | **Caching system** — centralized cache with area toggles, glob clearing, frontend cache integration via extensions. | Upstream: `helpers/cache.py`. | A3 (@extensible) | M | Useful for perf but coupled to new extension system. |
| F7 | **Sidebar redesign** — refactored sidebar header with dropdown, full logo, hide unavailable quick actions, plus menu for chat actions, collapsible wrapper. | Upstream commits `c7b97c17f0`, `848937f1ce`, `ad736a831e`, `8333f5b276`, `1cc055c7d8`. | — | M | Standalone UI work, but significant amount of WebUI changes. |
| F8 | **Dynamic release notes** — release notes generated via OpenRouter API instead of static markdown. | Upstream v1.2. Dir: `scripts/`. | — | S | Our release flow is different. |
| F9 | **Agent profile JSON → YAML** — `agents/*/agent.json` → `agents/*/agent.yaml`. | Upstream commit `d02dda3667`. | — | S | Would break existing agent configs unless migrated. |

---

## Backlog

### P0 — Security & Stability

| # | What | Source | How | Effort |
|---|------|--------|-----|--------|
| 1 | **Secrets exposed to LLM in system prompt** — `§§secret()` placeholders not resolved before sending to LLM. Masking exists in browser_agent/print_style but not in prompt pipeline. | [#1107](https://github.com/agent0ai/agent-zero/issues/1107) | INVESTIGATE then BUILD | M |
| 2 | **Secrets not resolved in MCP server config** — `§§secret()` in MCP env/headers/url passed as literal string. | [PR #1150](https://github.com/agent0ai/agent-zero/pull/1150) | CHERRY-PICK | S |
| 3 | **Duplicate response loop breaker** — agent stuck in "same message" infinite loop. Add `duplicate_retries` counter, break after 3 identical responses. 13-line fix in `agent.py`. | [PR #1265](https://github.com/agent0ai/agent-zero/pull/1265), fixes [#1056](https://github.com/agent0ai/agent-zero/issues/1056) | CHERRY-PICK | S |
| 4 | **Dynamic output truncation** — `ContextWindowExceededError` when tool output is huge. Calculate threshold as 12.5% of available context instead of hardcoded 1MB. | [PR #857](https://github.com/agent0ai/agent-zero/pull/857), fixes [#833](https://github.com/agent0ai/agent-zero/issues/833) | CHERRY-PICK | S |
| 5 | **lxml-html-clean XSS vulnerability** — bump 0.3.1 → 0.4.0. CVSS 8.4 (CWE-79). Also add security floor pins for 6 transitive deps. | Upstream commits `30835c2ff4`, `dfe691d505`. File: `requirements.txt`. | UPSTREAM | XS |
| 6 | **CSRF fails on Chromium over HTTPS** — WebSocket CSRF validation broken on Chrome when using HTTPS. Fix validates origin correctly. | Upstream commit `07f94ef4b5`. File: `helpers/security.py` (upstream: `helpers/security.py`). | UPSTREAM | XS |
| 7 | **CSRF cookie missing Secure flag** — cookie sent without `Secure` flag on HTTPS connections, allowing MitM interception. | Upstream commit `9e3bbb759f`. File: `helpers/security.py`. | UPSTREAM | XS |
| 8 | **Open redirect on login** — login redirect URL not validated, allows redirect to external sites. | Upstream commit `da24eb04e0`. File: `helpers/login.py`. | UPSTREAM | XS |
| 9 | **Context compression deadlock** — agent freezes when context window compression is triggered under certain conditions. | Upstream commit `1db8e3f095`. File: `helpers/history.py` or `helpers/tokens.py`. | UPSTREAM | S |
| 10 | **Error retry counter never resets** — `error_retries` increments on failure but never resets on success. After enough errors across sessions, agent stops retrying permanently. | Upstream commits `1945555b2d`, `01cdb7b92d`. File: `agent.py`. | UPSTREAM | XS |
| 11 | **Skills loading KeyError** — `loaded_skills` accessed with direct key lookup before it's populated; crashes on first skill use. Fix: use `.get()`. | Upstream commits `e8abe7101f`, `f821069734`. File: `tools/skills_tool.py`. | UPSTREAM | XS |
| 12 | **Settings delta clears authentication** — saving any setting resets auth state, logging the user out. | Upstream commit `343b141178`. File: `api/settings_set.py`. | UPSTREAM | XS |
| 13 | **Remove version check** — `update_check.py` calls `api.agent-zero.ai` to check for original Agent Zero updates. Irrelevant for fork, potentially confusing (suggests updating to original). | Files: `helpers/update_check.py`, `extensions/python/user_message_ui/_10_update_check.py`, `helpers/settings.py` (`update_check_enabled`), tests. | BUILD (remove) | S |

### P1 — High-Impact Features

| # | What | Source | How | Effort |
|---|------|--------|-----|--------|
| 14 | **Per-chat model override** — toggle custom model per chat without changing global settings. Backend + sidebar tune button + modal. Includes tests. | [PR #1291](https://github.com/agent0ai/agent-zero/pull/1291), addresses [#669](https://github.com/agent0ai/agent-zero/issues/669)/[#869](https://github.com/agent0ai/agent-zero/issues/869) | CHERRY-PICK | M |
| 15 | **Dedicated vision model** — separate `vision_model` config in `AgentConfig`. Factory function, settings UI, vision strategy (native vs dedicated). | [PR #768](https://github.com/agent0ai/agent-zero/pull/768), fixes [#698](https://github.com/agent0ai/agent-zero/issues/698) | CHERRY-PICK | M |
| 16 | **Chat search + keyboard shortcuts + font size** — sidebar filter, `/` focus, `Alt+N` new chat, `Alt+K` search, S/M/L/XL font, file browser filter. Pure frontend. | [PR #1156](https://github.com/agent0ai/agent-zero/pull/1156), fixes [#704](https://github.com/agent0ai/agent-zero/issues/704) | CHERRY-PICK | M |
| 17 | **Edit and resend previous messages** — pencil icon on user messages, inline editor, Ctrl+Enter to save & resend (truncates history at edit point). | [PR #1137](https://github.com/agent0ai/agent-zero/pull/1137) | CHERRY-PICK | M |
| 18 | **Browser-based terminal (xterm.js)** — multi-tab terminal in web UI with persistent PTY sessions. Survives page refresh. htop/vim/nano reattach. | [PR #1279](https://github.com/agent0ai/agent-zero/pull/1279), fixes [#897](https://github.com/agent0ai/agent-zero/issues/897) | CHERRY-PICK | L |
| 19 | **Agent can update scheduled tasks** — add `scheduler:update_task` tool to scheduler prompt and tools. Fixes "agent says it can't update tasks". | [PR #1105](https://github.com/agent0ai/agent-zero/pull/1105), relates to [#677](https://github.com/agent0ai/agent-zero/issues/677) | CHERRY-PICK | S |
| 20 | **Text editor tool** — native file read/write/patch tool for agents. Read with line numbers, write, patch specific ranges. Mtime checks prevent stale edits. Agents get a proper file editor instead of shelling out to `cat`/`sed`. | Upstream commit `1d2425cce1`. Dir: `plugins/_text_editor/` (needs adaptation to our extension format). | UPSTREAM (adapt) | M |
| 21 | **Chat compaction** — compress entire chat history into a single LLM-generated summary. Model selection, min-token validation, conversation backup before compaction. Solves long-session context overflow. | Upstream commit `5b3240677d`. Dir: `plugins/_chat_compaction/` (needs adaptation). | UPSTREAM (adapt) | M |
| 22 | **Parallel MCP initialization** — MCP servers init in parallel instead of sequentially. Cuts startup time with multiple MCP servers configured. | Upstream commit `6734b9dc0f`. File: `helpers/mcp_handler.py`. | UPSTREAM | S |

### P2 — Medium-Impact Features

| # | What | Source | How | Effort |
|---|------|--------|-----|--------|
| 23 | **Per-agent MCP config + auto-detect transport** — subordinate agents can have own MCP servers. Auto-detect: try streamable-HTTP, fallback to SSE. | [PR #1232](https://github.com/agent0ai/agent-zero/pull/1232), fixes [#473](https://github.com/agent0ai/agent-zero/issues/473) | CHERRY-PICK | M |
| 24 | **Anthropic OAuth session tokens** — use Claude Pro/Max subscription via `ANTHROPIC_SESSION_TOKEN`. Adds `anthropic_oauth` provider. | [PR #1315](https://github.com/agent0ai/agent-zero/pull/1315), fixes [#1308](https://github.com/agent0ai/agent-zero/issues/1308) | CHERRY-PICK | S |
| 25 | **Subordinate delegation loop prevention** — depth limits (`max_agent_depth=5`), same-profile warning, 3-question decision framework for delegation. | [PR #778](https://github.com/agent0ai/agent-zero/pull/778) | CHERRY-PICK | M |
| 26 | **Concurrent requests limit** — semaphore-based cap on simultaneous requests per model type. Useful for parallel chats + local models. | [PR #1043](https://github.com/agent0ai/agent-zero/pull/1043) | CHERRY-PICK | S |
| 27 | **Dynamic context pruning** — auto-detect token limits, intelligent pruning of old history for long sessions. | [PR #1317](https://github.com/agent0ai/agent-zero/pull/1317) | CHERRY-PICK | M |
| 28 | **MCP race condition fix + SSH prompt detection** | [PR #1283](https://github.com/agent0ai/agent-zero/pull/1283) | CHERRY-PICK | S |
| 29 | **Organize chats by project (tabs)** — projects as tabs with chat lists, active task indicator. | [#1189](https://github.com/agent0ai/agent-zero/issues/1189) | BUILD | L |
| 30 | **Manual chat renaming** — rename chats, optionally disable auto-rename. | [#702](https://github.com/agent0ai/agent-zero/issues/702) | BUILD | S |
| 31 | **Memory editing UI** — view, edit, delete memories from web UI. | [#701](https://github.com/agent0ai/agent-zero/issues/701) | BUILD | L |
| 32 | **Transfer memories between projects** | [#883](https://github.com/agent0ai/agent-zero/issues/883) | BUILD | M |
| 33 | **OpenRouter header TypeError** — `extra_headers` passed as list instead of dict, causes `TypeError` in httpx. Breaks all OpenRouter calls for affected configs. | Upstream commits `1f6786575c`, `ac5d4385af`. File: `models.py`. | UPSTREAM | XS |
| 34 | **Vision tool empty content crash** — `_convert_messages` crashes on empty content from vision tool. Fix: skip empty content, add text to vision results. | Upstream commits `a7df75a9dd`, `f9743cb736`. File: `helpers/call_llm.py`, `tools/vision_load.py`. | UPSTREAM | XS |
| 35 | **Cross-device file move fails** — `os.rename` fails across Docker volume mount points. Fallback to `shutil.move`. Affects chat/project operations in Docker. | Upstream commit `0e5e9851d4`. File: `helpers/files.py`. | UPSTREAM | XS |
| 36 | **TTY queue event loop mismatch** — event loop mismatch in TTY queue causes code execution failures in async contexts. | Upstream commit `0582c51998`. File: `helpers/tty_session.py`. | UPSTREAM | XS |
| 37 | **Utility calls non-stream** — switch utility model calls (title generation, memory ops) from streaming to non-stream mode. Less overhead, faster responses for short outputs. | Upstream commit `d05224b895`. File: `helpers/call_llm.py`. | UPSTREAM | XS |
| 38 | **Secret masking in code execution** — mask `§§secret()` values in terminal output so agents don't leak credentials in conversation history. Also increases code output truncation limit. | Upstream commit `6181ac9c20`. File: `tools/code_execution_tool.py`. | UPSTREAM | S |
| 39 | **Infection check** — scans external tool output for prompt injection attempts. Async scanning with FIFO queue and progress bar. Safety net for web scraping and file processing. | Upstream commit `6570008557`. Dir: `plugins/_infection_check/` (needs adaptation). | UPSTREAM (adapt) | M |
| 40 | **Prompt include** — persistent system prompt files auto-injected into every conversation. User can define standing rules/preferences in files that survive across chats. | Upstream commit `785cf33921`. Dir: `plugins/_promptinclude/` (needs adaptation). | UPSTREAM (adapt) | S |
| 41 | **Chat branching** — fork a chat from any message into a new conversation. Useful for exploring alternative approaches without losing the original thread. | Upstream commit `4633ebdd82`. Dir: `plugins/_chat_branching/` (needs adaptation). | UPSTREAM (adapt) | M |

### P3 — Nice to Have

| # | What | Source | How | Effort |
|---|------|--------|-----|--------|
| 42 | **STOP / interrupt button** — hard-stop active agent run from UI without wiping chat. | [#1099](https://github.com/agent0ai/agent-zero/issues/1099) | BUILD | L |
| 43 | **Ollama/local model reliability** — configurable recall search timeout (currently hardcoded 30s), graceful empty `reasoning_delta`. | [#865](https://github.com/agent0ai/agent-zero/issues/865) | BUILD | S |
| 44 | **Fallback model chain** — on primary model failure, switch to backup model (not just retry). | [#1052](https://github.com/agent0ai/agent-zero/issues/1052) | BUILD | M |
| 45 | **Skills upload path mismatch** — `/a0/usr/skills` vs `/a0/skills`. | [#1045](https://github.com/agent0ai/agent-zero/issues/1045) | INVESTIGATE | S |
| 46 | **Model search dropdown CSS** — missing color on `.model-search-item`. | [#1294](https://github.com/agent0ai/agent-zero/issues/1294) | BUILD | XS |
| 47 | **Google models via OAuth** | [PR #905](https://github.com/agent0ai/agent-zero/pull/905), [#928](https://github.com/agent0ai/agent-zero/issues/928) | CHERRY-PICK | M |
| 48 | **Native ChromaDB/VectorDB** — alternative to Cognee for distributed deployments. | [#1092](https://github.com/agent0ai/agent-zero/issues/1092) | BUILD | XL |
| 49 | **Multi-user / multitenancy** | [PR #655](https://github.com/agent0ai/agent-zero/pull/655) | CHERRY-PICK | XL |
| 50 | **Chat-level prompt subdirectory selector** | [#537](https://github.com/agent0ai/agent-zero/issues/537) | BUILD | M |
| 51 | **Chat input UX improvements** — increased input height, auto-resize, full-screen input toolbar polish, auto-focus on new chat and context switch. | Upstream commits `3485db328f`, `f2e96742bd`, `4b3666aa35`, `dae502bc1d`. Files: `webui/index.html`, `webui/css/`. | UPSTREAM | S |
| 52 | **Chat input tremor fix** — input field jitters/shakes during typing due to CSS resize conflict. | Upstream commit `a0fc9367b7`. File: WebUI CSS/JS. | UPSTREAM | XS |
| 53 | **Image attachment 404** — attached images return 404 when rendering in message history. | Upstream commit `cf8e66529b`. File: WebUI message rendering. | UPSTREAM | XS |
| 54 | **Welcome screen refresh** — welcome screen doesn't update when settings change; requires manual page reload. | Upstream commits `48470639ea`, `69cb4f131a`. File: WebUI. | UPSTREAM | XS |
| 55 | **File browser dropdown fix** — file browser dropdown broken; context ID not validated before fetching chat files path. | Upstream commits `1880eb09d4`, `ec4de76561`. Files: `helpers/file_browser.py`, `api/chat_files_path_get.py`. | UPSTREAM | XS |
| 56 | **Copy file fallback** — no fallback when file copy encounters OS errors (permissions, cross-device). | Upstream commit `4fa70fcdfb`. File: `helpers/files.py`. | UPSTREAM | XS |
| 57 | **SearXNG settings fix** — SearXNG search engine configuration not applied correctly. | Upstream commit `1f7e3b5a28`. File: `helpers/searxng.py`. | UPSTREAM | XS |
| 58 | **Scheduler API fix** — scheduler API calls broken, tasks not triggering correctly. | Upstream commit `68e65ae873`. File: `api/scheduler_*.py`. | UPSTREAM | XS |
| 59 | **Agent response expansion** — expand full agent response text in ALL display mode instead of truncated preview. | Upstream commit `39dfcbcb27`. File: WebUI. | UPSTREAM | XS |
| 60 | **WebUI `page-head` extension point** — `<x-extension id="page-head">` in `<head>` for clean injection of scripts/styles by extensions (mermaid.js, custom fonts). No more DOM manipulation hacks. | Upstream commit `abd7ac08bb`. File: `webui/index.html`. | UPSTREAM | S |
| 61 | **File system watchdog** — hot-reload API handlers, extensions, and config files on change. No restart needed during development. Uses `watchdog` library. | Upstream: `helpers/watchdog.py`, extension `_functions/init_a0/end/_10_register_watchdogs.py`. | UPSTREAM (adapt) | M |
| 62 | **Context window optimization** — faster default memory settings, improved context utilization. | Upstream commit `3dceaca64e`. | UPSTREAM | S |
| 63 | **`nest_asyncio` removal** — removed from `agent.py` imports. One less dependency. | Upstream main branch. File: `agent.py`. | UPSTREAM | XS |

---

## Recommended Execution Order

**Wave 1 — XS/S upstream fixes (security + stability, minimal risk):**
- #5 lxml-html-clean XSS (CVSS 8.4) — `requirements.txt` version bump
- #6 CSRF Chromium/HTTPS fix — blocks Chrome users over HTTPS
- #7 CSRF cookie Secure flag — security hardening
- #8 Open redirect on login — security fix
- #10 Error retry counter reset — agent stops working after enough errors
- #11 Skills loading KeyError — crashes on skill use
- #12 Settings delta clears auth — UX-breaking bug
- #13 Remove version check — irrelevant for fork
- #33 OpenRouter header TypeError — breaks OpenRouter calls
- #34 Vision tool empty content — crashes vision tool
- #35 Cross-device file move — breaks Docker file operations
- #36 TTY queue loop mismatch — code execution failures
- #37 Utility calls non-stream — easy perf win
- #9 Context compression deadlock — agent freezes
- #63 `nest_asyncio` removal — cleanup

**Wave 2 — Quick cherry-picks from PRs (S effort, high value):**
- #3 Loop breaker (PR #1265) — 13 lines, prevents infinite loops
- #4 Output truncation (PR #857) — prevents context overflow crash
- #2 Secrets in MCP config (PR #1150) — security fix
- #19 Scheduler update tool (PR #1105) — small prompt/tool change
- #24 Anthropic OAuth (PR #1315) — new provider
- #26 Concurrent request limit (PR #1043) — rate protection
- #28 MCP race condition (PR #1283) — stability
- #22 Parallel MCP init — faster startup
- #46 Model dropdown CSS (#1294) — trivial CSS fix

**Wave 3 — Medium cherry-picks and upstream features (M effort, high value):**
- #14 Per-chat model override (PR #1291) — most-requested feature area
- #16 Chat search + shortcuts (PR #1156) — pure frontend UX
- #17 Edit/resend messages (PR #1137) — standard chat UX
- #15 Vision model (PR #768) — enables cheap text models + vision
- #23 Per-agent MCP + auto-transport (PR #1232)
- #25 Delegation loop prevention (PR #778)
- #27 Dynamic context pruning (PR #1317)
- #20 Text editor tool — proper file editing for agents
- #21 Chat compaction — long session management
- #38 Secret masking in code execution

**Wave 4 — Adapted upstream features (M effort, new capabilities):**
- #39 Infection check — prompt injection safety
- #40 Prompt include — persistent behavior rules
- #41 Chat branching — conversation forking UX

**Wave 5 — Build from scratch:**
- #1 Investigate secrets leak (#1107)
- #30 Manual chat renaming
- #43 Ollama timeout tuning
- #29 Project tabs for chats
- #42 STOP button

**Wave 6 — Large features:**
- #18 Web terminal (PR #1279)
- #31 Memory editing UI
- #32 Memory transfer
- #44 Fallback model chain
- #48 VectorDB support
- #49 Multitenancy

**Wave 7 — UI polish (grab bag, do anytime):**
- #51 Chat input UX improvements
- #52 Chat input tremor fix
- #53 Image attachment 404
- #54 Welcome screen refresh
- #55 File browser dropdown fix
- #56 Copy file fallback
- #57 SearXNG settings fix
- #58 Scheduler API fix
- #59 Agent response expansion
- #60 WebUI page-head extension
- #62 Context window optimization
