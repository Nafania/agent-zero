# Agent Zero: Full Upstream Backport (v0.9.8 → v1.3)

**Date:** 2026-03-28
**Scope:** All upstream changes — architectural (A1-A8), features (F1-F9), and backlog items (P0-P3) — backported onto our fork
**Strategy:** Scripted migration + manual adaptation. Sequential for architectural changes, parallel for independent items. Each item in a separate branch/worktree.

---

## Golden Rule: Upstream 1:1, No Exceptions

> **Port upstream IDENTICALLY. No backward compatibility. No "keep fork's simpler approach."**
>
> Every change MUST match upstream exactly (code, naming, structure, async/sync, patterns).
> No deviations. Plugin naming uses upstream's `_` prefix convention (PR #36).
>
> **If the fork has a potentially better solution** — the implementor MUST:
> 1. Stop implementation
> 2. Report both approaches (upstream vs fork) to the project owner
> 3. Wait for the owner's decision
> 4. Only then implement the chosen approach
>
> **Never** add backward-compat routes, shims, or wrappers. We control the entire repo.
> **Never** silently keep a fork-specific pattern when upstream has a different one.

---

## Overview

Backport all upstream changes from the 516-commit gap between our fork (v0.9.8) and upstream (v1.3). Our fork is the base; upstream changes are overlaid on top. Items are skipped only where we already have a **better** analog.

### Skipped Items

| # | What | Reason |
|---|------|--------|
| F2 | Self-update system | Our CI/CD via Docker + Hassio addon is automated and safer |
| F8 | Dynamic release notes | Different release flow, not needed |
| #13 | Remove version check | Already in progress (`chore/remove-version-check` branch) |

### Evaluate After Phase 2

| # | What | Our Analog | Decision |
|---|------|-----------|----------|
| F4 | Telegram integration (plugin) | `a0-ext-telegram` | Compare implementations, pick better |
| F7 | Sidebar redesign | `feat/webui-performance-optimization` | Compare scope, merge if complementary |

---

## Execution Phases

```
Phase 1: A2 (Path Restructure)
  │  single branch, merge to main
  ▼
Phase 2: A1 (Plugin System)
  │  single branch, merge to main
  ▼
Phase 3: A3-A8 (Architectural, sequential with internal dependencies)
  │  A3 (@extensible) + A4 (AgentConfig slimming) — parallel
  │  A5 (WS → extensions), A6 (API refactor) — parallel, after A3
  │  A7 (Extension dirs) — after A3
  │  A8 (Prompt split) — after A7
  ▼
Phase 4: Features + Backlog (parallel waves, each item = own branch/worktree)
  │  Wave A: XS/S upstream fixes (~23 items)
  │  Wave B: S/M cherry-picks + small features (~13 items)
  │  Wave C: M/L features + adapted upstream (~19 items)
  │  Wave D: Evaluate F4, F7
  │  Wave E: BUILD items from backlog (~12 items)
```

**Blocking rules:**
- A2 blocks everything (all file paths change)
- A1 blocks Phase 3 and all plugin-dependent Phase 4 items
- Phase 4 items are parallel where dependencies allow; plugin-shaped items (#20, #21, #39, #40, #41, F1, F3, F5, F6) should be sequenced after relevant A3-A8 work is stable
- F6 (Caching) depends on A3 (@extensible) — schedule after A3 is merged
- F5 (Model presets, plugin version) depends on A1 + A4 — **supersedes #14** (per-chat model override); implement #14 first as standalone, then F5 extends it within plugin architecture
- Security fixes (#5-#8) could optionally be fast-tracked before A2 on current paths if urgency demands it

---

## Phase 1: A2 — Path Restructuring

### What Changes

Remove the `python/` prefix from all modules. All subpackages become top-level.

| Current | After |
|---------|-------|
| `python/helpers/` | `helpers/` |
| `python/tools/` | `tools/` |
| `python/api/` | `api/` |
| `python/extensions/` | `extensions/python/` |
| `python/websocket_handlers/` | `websocket_handlers/` |
| `python/__init__.py` | deleted |

### Impact

- **3649 import references** (`python.helpers.*`, `python.tools.*`, etc.) → rewritten
- **242 source files** move physically
- **241 test files** — import rewrites only (tests stay in `tests/`)
- **`run_ui.py`** — 2 folder path strings
- **`.github/workflows/ci.yml`** — path triggers

### Migration Script

**Step 1: Move directories**
```bash
mv python/helpers helpers
mv python/tools tools
mv python/api api
mkdir -p extensions && mv python/extensions extensions/python
mv python/websocket_handlers websocket_handlers
rm python/__init__.py && rmdir python
```

**Step 2: Rewrite imports** (all `.py` files in `helpers/`, `tools/`, `api/`, `extensions/`, `websocket_handlers/`, `tests/`, and root `*.py`)
```bash
# Dot imports: python.helpers → helpers, python.tools → tools, etc.
# String paths: "python/helpers" → "helpers", "python/api" → "api", etc.
```

**Step 3: Update config files**
- `run_ui.py`: `"python/websocket_handlers"` → `"websocket_handlers"`, `"python/api"` → `"api"`
- `.github/workflows/ci.yml`: path triggers `python/**` → `helpers/**`, `tools/**`, `api/**`, `extensions/**`, `websocket_handlers/**`

**Step 4: Verify**
- `python -c "import helpers; import tools; import api"` — modules importable
- `pytest tests/ -x` — all tests pass
- `rg 'python\.(helpers|tools|api|extensions|websocket_handlers)' --glob '*.py'` — 0 results
- `rg '"python/' --glob '*.py' --glob '*.yml'` — 0 results (excluding `extensions/python/` which is intentional)

### Preconditions

- `PYTHONPATH=.` already set in CI and Docker
- No root-level conflicts: `helpers/`, `tools/`, `api/`, `extensions/`, `websocket_handlers/` do not exist at root

### Risks

- All 5 active worktree branches become incompatible — require rebase or recreation after merge
- All open PRs require rebase

---

## Phase 2: A1 — Plugin System

### Architecture

Full plugin architecture: `plugins/` directory, `plugin.yaml` manifests, lifecycle hooks, per-plugin config/tools/extensions/webui/api.

**Plugin directory structure:**
```
plugins/
├── _memory/
│   ├── plugin.yaml          # manifest: name, version, enabled, config schema
│   ├── tools/               # memory_save.py, memory_load.py, etc.
│   ├── extensions/          # recall_memories, memorize_*, memory_init
│   ├── api/                 # memory_dashboard.py, memory_feedback.py
│   └── webui/               # dashboard UI components
├── _code_execution/
│   ├── plugin.yaml
│   ├── tools/               # code_execution_tool.py
│   └── extensions/
├── _browser/
├── _search/
├── _scheduler/
├── _skills/
├── _model_config/
├── _vision/
├── _document_query/
├── _subordinates/
├── _a2a/
├── _notifications/
└── ... (16 built-in plugins)
```

### Plugin Loader (`helpers/plugins.py`)

- **Discovery:** scan `plugins/` → parse `plugin.yaml` manifests
- **Lifecycle:** `init()` → `ready()` → `shutdown()`
- **Registration:** plugins register their tools, extensions, API endpoints, webui components
- **Config:** per-plugin configuration stored in `plugin.yaml` + runtime overrides
- **Toggle:** enable/disable plugins

### Migration Map

| Current Location | Target Plugin | Notes |
|-----------------|---------------|-------|
| `tools/memory_*.py` + `helpers/memory.py` + `helpers/cognee_*.py` + memory extensions | `_memory` | **Preserve Cognee persistence customizations** |
| `tools/code_execution_tool.py` + `helpers/tty_session.py` + `helpers/shell_*.py` | `_code_execution` | |
| `tools/browser_agent.py` + `helpers/browser*.py` | `_browser` | **Preserve CDP migration customizations** |
| `tools/search_engine.py` + `helpers/searxng.py` + `helpers/duckduckgo_search.py` | `_search` | |
| `tools/scheduler.py` + `helpers/task_scheduler.py` | `_scheduler` | |
| `tools/skills_tool.py` + `helpers/skills*.py` | `_skills` | **Preserve skills marketplace** |
| Model settings from `initialize.py` + `models.py` | `_model_config` | Tied to A4 |
| `tools/vision_load.py` | `_vision` | |
| `tools/document_query.py` + `helpers/document_query.py` | `_document_query` | |
| `tools/call_subordinate.py` + `helpers/subagents.py` | `_subordinates` | |
| `tools/a2a_chat.py` + `helpers/fasta2a_*.py` | `_a2a` | |
| `tools/notify_user.py` + `helpers/notification.py` | `_notifications` | |

### Core (remains outside plugins)

- `agent.py` — Agent class, message loop
- `initialize.py` — bootstrap (without model config after A4)
- `models.py` — LLM provider wiring
- `helpers/extension.py` — extension loader (extended for plugin support)
- `helpers/files.py`, `helpers/strings.py`, `helpers/log.py` — base utilities
- `helpers/plugins.py` — **new**, plugin loader
- `helpers/websocket*.py`, `helpers/api.py` — infrastructure
- `run_ui.py` — server

### Custom Features to Preserve

1. **Cognee persistence** — env vars before import, auto re-import, cross-process init, retry on DatabaseNotCreatedError
2. **Skills marketplace** — search, install, manage skills from UI
3. **OAuth provider framework** — provider registry, token management
4. **Metrics collector + dashboard** — token tracking, performance metrics
5. **WebUI performance improvements** — sidebar live timestamps, debounce
6. **Browser CDP migration** — browser-use monkeypatch
7. **All merged bugfixes** — FD leak, slash commands, cognee cross-process, etc.

### Implementation Strategy

1. Add upstream as remote, study commits `54fb4746a4` (initial plugin system) and `a48ac95a29` (hooks)
2. Implement `helpers/plugins.py` — plugin discovery, loading, lifecycle
3. Create `plugin.yaml` schema and loader
4. Migrate one plugin at a time, starting with least customized (search, notifications, vision)
5. Heavily customized plugins (memory, browser, skills) last, with careful preservation of our changes

### Risks

- Custom features may conflict with plugin boundaries
- Extension hook discovery changes (extensions now in `plugins/*/extensions/` too)
- API endpoint registration from plugins needs new infrastructure in `run_ui.py`
- All tests mocking specific paths will break

---

## Phase 3: A3-A8 — Remaining Architectural Changes

All depend on A1. Internal dependency order:

```
A3 (@extensible) ──┬──→ A5 (WS → extensions)
                   ├──→ A6 (API routing refactor)
                   ├──→ A7 (Extension dir restructuring) ──→ A8 (Prompt split)
A4 (AgentConfig slimming) — parallel with A3
```

### A3: `@extensible` Decorator

- Decorator that auto-generates `start`/`end` extension points for any function
- Plugins intercept calls without touching core code
- Applied to ~20 functions in `agent.py`, `models.py`, helpers
- Current `helpers/extension.py` extended, not replaced
- Source: upstream commit `d82b121bc9`

### A4: AgentConfig Slimming

- Fields removed from AgentConfig: `chat_model`, `utility_model`, `embeddings_model`, `browser_model`, SSH settings, `memory_subdir`
- All moved to respective plugin configs (`_model_config`, `_memory`, etc.)
- Source: upstream v1.1, files `initialize.py`, `models.py`, plugin configs

### A5: WebSocket Handlers → Extensions

- `websocket_handlers/` directory removed
- Logic absorbed into extension hooks via `@extensible`
- Dynamic WS endpoint registration
- Source: upstream v1.1

### A6: API Routing Refactor

- New endpoint structure with plugin-scoped endpoints
- Optional per-handler caching
- CSRF improvements (overlaps with #6, #7 — those Wave A fixes are independent and should be applied first; A6 may supersede parts of them, audit after A6 merge)
- Source: upstream v1.1, commit `4e243a996c`

### A7: Extension Directory Restructuring

- Extension folder paths derived from module path + qualname
- Deep module-based directory convention
- Source: upstream commit `7e1d9ad2a4`

### A8: System Prompt Split

- Monolithic system prompt split into per-concern extension files
- `_10_main_prompt.py`, `_11_tools_prompt.py`, `_12_mcp_prompt.py`, `_13_secrets_prompt.py`, etc.
- Modular prompt composition
- Source: upstream commit `2566ee134d`

---

## Phase 4: Features + Backlog Items

Each item is an independent branch/worktree. Parallel where dependencies allow (see blocking rules above for plugin-shaped and A3-dependent items).

### Wave A: XS/S Upstream Fixes (~23 items)

| # | What | Effort | Source |
|---|------|--------|--------|
| 5 | lxml-html-clean XSS bump (CVSS 8.4) | XS | `30835c2ff4`, `dfe691d505` |
| 6 | CSRF Chromium/HTTPS fix | XS | `07f94ef4b5` |
| 7 | CSRF cookie Secure flag | XS | `9e3bbb759f` |
| 8 | Open redirect on login | XS | `da24eb04e0` |
| 10 | Error retry counter reset | XS | `1945555b2d`, `01cdb7b92d` |
| 11 | Skills loading KeyError | XS | `e8abe7101f`, `f821069734` |
| 12 | Settings delta clears auth | XS | `343b141178` |
| 33 | OpenRouter header TypeError | XS | `1f6786575c`, `ac5d4385af` |
| 34 | Vision tool empty content crash | XS | `a7df75a9dd`, `f9743cb736` |
| 35 | Cross-device file move | XS | `0e5e9851d4` |
| 36 | TTY queue event loop mismatch | XS | `0582c51998` |
| 37 | Utility calls non-stream | XS | `d05224b895` |
| 63 | `nest_asyncio` removal | XS | upstream main |
| 52 | Chat input tremor fix | XS | `a0fc9367b7` |
| 53 | Image attachment 404 | XS | `cf8e66529b` |
| 54 | Welcome screen refresh | XS | `48470639ea`, `69cb4f131a` |
| 55 | File browser dropdown fix | XS | `1880eb09d4`, `ec4de76561` |
| 56 | Copy file fallback | XS | `4fa70fcdfb` |
| 57 | SearXNG settings fix | XS | `1f7e3b5a28` |
| 58 | Scheduler API fix | XS | `68e65ae873` |
| 59 | Agent response expansion | XS | `39dfcbcb27` |
| 9 | Context compression deadlock | S | `1db8e3f095` |
| 46 | Model dropdown CSS fix | XS | BUILD |

### Wave B: S/M Cherry-picks + Small Features (~13 items)

| # | What | Effort | Source |
|---|------|--------|--------|
| 3 | Duplicate response loop breaker | S | PR #1265 |
| 4 | Dynamic output truncation | S | PR #857 |
| 2 | Secrets in MCP config | S | PR #1150 |
| 19 | Scheduler update tool | S | PR #1105 |
| 24 | Anthropic OAuth session tokens | S | PR #1315 |
| 26 | Concurrent requests limit | S | PR #1043 |
| 28 | MCP race condition fix + SSH prompt | S | PR #1283 |
| 22 | Parallel MCP initialization | S | `6734b9dc0f` |
| 38 | Secret masking in code execution | S | `6181ac9c20` |
| 40 | Prompt include (adapt from plugin) | S | `785cf33921` |
| 51 | Chat input UX improvements | S | `3485db328f` + others |
| 60 | WebUI `page-head` extension point | S | `abd7ac08bb` |
| 62 | Context window optimization | S | `3dceaca64e` |

### Wave C: M/L Features (~19 items)

| # | What | Effort | Source |
|---|------|--------|--------|
| 14 | Per-chat model override | M | PR #1291 |
| 15 | Dedicated vision model | M | PR #768 |
| 16 | Chat search + keyboard shortcuts + font size | M | PR #1156 |
| 17 | Edit and resend messages | M | PR #1137 |
| 23 | Per-agent MCP config + auto-transport | M | PR #1232 |
| 25 | Subordinate delegation loop prevention | M | PR #778 |
| 27 | Dynamic context pruning | M | PR #1317 |
| 47 | Google models via OAuth | M | PR #905 |
| 20 | Text editor tool (adapt) | M | `1d2425cce1` |
| 21 | Chat compaction (adapt) | M | `5b3240677d` |
| 39 | Infection check (adapt) | M | `6570008557` |
| 41 | Chat branching (adapt) | M | `4633ebdd82` |
| 61 | File system watchdog (adapt) | M | upstream |
| 18 | Browser-based terminal (xterm.js) | L | PR #1279 |
| F1 | Plugin Hub / Installer | XL | upstream v1.1 |
| F3 | Email integration (adapt) | L | `34f2354cb1` |
| F5 | Model presets (plugin version) | L | upstream v1.1 |
| F6 | Caching system | M | upstream |
| F9 | Agent profile JSON → YAML | S | `d02dda3667` (same commit as A2 refactor; separate branch with config migration script, not bundled in A2) |

### Wave D: Evaluate

| # | What | Our Analog | Action |
|---|------|-----------|--------|
| F4 | Telegram integration | `a0-ext-telegram` | Compare, pick better or merge |
| F7 | Sidebar redesign | `feat/webui-performance-optimization` | Compare scope, merge if complementary |

### Wave E: BUILD + Large Items (~12 items)

| # | What | Effort | Type |
|---|------|--------|------|
| 1 | Secrets exposed to LLM | M | INVESTIGATE → BUILD |
| 29 | Organize chats by project (tabs) | L | BUILD |
| 30 | Manual chat renaming | S | BUILD |
| 42 | STOP / interrupt button | L | BUILD |
| 43 | Ollama/local model reliability | S | BUILD |
| 44 | Fallback model chain | M | BUILD |
| 45 | Skills upload path mismatch | S | INVESTIGATE → BUILD |
| 48 | Native ChromaDB/VectorDB | XL | BUILD |
| 49 | Multi-user / multitenancy | XL | CHERRY-PICK (PR #655) |
| 50 | Chat-level prompt subdirectory selector | M | BUILD |
| 31 | Memory editing UI | L | BUILD |
| 32 | Transfer memories between projects | M | BUILD |

---

## Branch / Worktree Strategy

### Naming Convention

- `upstream/a2-path-restructure`
- `upstream/a1-plugin-system`
- `upstream/a3-extensible-decorator`
- `upstream/fix-5-lxml-xss`
- `upstream/fix-10-retry-counter`
- `upstream/feat-14-per-chat-model`
- `upstream/feat-f1-plugin-hub`

### Worktree Management

- Maximum 5-8 worktrees active simultaneously
- Each worktree created from `main` (after Phase 1-3 merges)
- On completion: PR → review → merge → delete worktree

### Merge Strategy

- Phase 1-3 (A2, A1, A3-A8): sequential merge to main, each must pass all tests
- Phase 4 (Waves A-E): each item merges independently, rebase on main before merge

---

## Total Item Count

| Category | IDs | Count |
|----------|-----|-------|
| Architectural | A1, A2, A3, A4, A5, A6, A7, A8 | 8 |
| Features (implement) | F1, F3, F5, F6, F9 | 5 |
| Features (evaluate) | F4, F7 | 2 |
| Features (skip) | F2, F8 | 2 |
| Backlog UPSTREAM (direct commits) | #5-#12, #22, #33-#37, #52-#59, #60, #62, #63, #9, #46 | 24 |
| Backlog CHERRY-PICK (from PRs) | #2-#4, #14-#19, #23-#28, #47, #49 | 16 |
| Backlog UPSTREAM adapt (plugin → extension) | #20, #21, #38-#41, #51, #61 | 8 |
| Backlog BUILD/INVESTIGATE | #1, #29-#32, #42-#45, #48, #50 | 11 |
| Backlog skip | #13 | 1 |
| **Total to implement** | | **74** |
| **Skipped** | F2, F8, #13 | **3** |
