# Agent Zero (Fork)

Custom fork of [agent0ai/agent-zero](https://github.com/agent0ai/agent-zero) — autonomous AI agent framework with Cognee-powered memory, MCP integration, and Home Assistant addon deployment.

## What is Agent Zero

Agent Zero is a **general-purpose personal AI assistant** that uses the computer as a tool. It is not pre-programmed for specific tasks — give it a task and it will write code, use the terminal, search the web, cooperate with subordinate agents, and memorize solutions for future use.

### Core Principles

- **Dynamic and organic** — not a predefined agentic framework; grows and learns as you use it
- **Fully transparent** — nothing is hidden; every prompt, tool, and message template is readable and customizable
- **Computer as a tool** — no single-purpose tools pre-programmed; the agent writes its own code and creates its own tools
- **Multi-agent cooperation** — agents create subordinate agents for subtasks, each with clean focused context
- **Prompt-driven behavior** — the entire framework is guided by prompts in the `prompts/` folder; change the prompt, change the framework

### Tools (via Plugins)

| Tool | Plugin | Purpose |
|------|--------|---------|
| `code_execution_tool` | code_execution | Execute Python/bash code in sandboxed environment |
| `browser_agent` | browser | Browser automation via browser-use (CDP) |
| `search_engine` | search | Web search (DuckDuckGo, SearxNG, Perplexity) |
| `memory_save/load/delete/forget` | memory | Persistent memory operations via Cognee |
| `document_query` | document_query | Query PDFs, CSVs, HTML, text files |
| `scheduler` | scheduler | Cron-based task scheduling |
| `skills_tool` | skills | Discover and install Skills (SKILL.md standard) |
| `notify_user` | notifications | Send notifications to the user |
| `a2a_chat` | a2a | Agent-to-Agent protocol communication |
| `vision_load` | vision | Image analysis |
| `behaviour_adjustment` | memory | Runtime behaviour tuning |
| `text_editor` | text_editor | Native file read/write/patch |

### Core Tools (not in plugins)

| Tool | Purpose |
|------|---------|
| `call_subordinate` | Create subordinate agent for subtasks |
| `response` | Agent response handler |
| `wait` | Pause execution |

### Skills System

Skills are portable, structured agent capabilities using the open **SKILL.md** standard (compatible with Claude Code, Cursor, Codex, GitHub Copilot). Skills are contextual expertise loaded dynamically when relevant. Can be installed via `/skill-install` chat command or through the UI.

### Plugin System

Plugins are self-contained directories under `plugins/` with a `plugin.yaml` manifest. Each plugin can provide tools, helpers, extensions, API handlers, prompts, and webui components. Plugin discovery, toggle, and config management is handled by `helpers/plugins.py`.

Key concepts:
- **Toggle system**: `.toggle-0`/`.toggle-1` files, per-project and per-agent overrides
- **`@extensible` decorator**: Automatically generates `_start`/`_end` extension points around functions
- **Plugin config**: `default_config.yaml` in plugin dir, `config.json` for user overrides
- **Dynamic API dispatch**: Plugin API handlers served at `/plugins/<name>/<handler>`
- **Asset serving**: Plugin webui assets served at `/plugins/<name>/<path>`

Custom plugins go to `usr/plugins/` and take priority over built-in ones.

### Extension Hooks

The behavior is fully extensible via `extensions/python/` (core) and `plugins/*/extensions/python/` (per-plugin). Available hook points:

- Agent lifecycle: `agent_init`, `banners`, `user_message_ui`
- Message loop: `message_loop_start`, `message_loop_end`, `message_loop_prompts_before`, `message_loop_prompts_after`
- LLM: `before_main_llm_call`, `util_model_call_before`
- Streaming: `reasoning_stream`, `response_stream` (+ `_chunk`, `_end` variants)
- Tools: `tool_execute_before`, `tool_execute_after`
- History: `hist_add_before`, `hist_add_tool_result`
- Monologue: `monologue_start`, `monologue_end`
- System: `system_prompt`, `error_format`, `process_chain_end`

### Multi-Agent Architecture

Every agent has a superior (human user for Agent 0) and can create subordinate agents. Subordinates can have dedicated prompts, tools, and system extensions configured via subagent profiles. Agent number tracking in backend enables multi-agent identification.

### LLM Providers

Powered by LiteLLM with support for: OpenRouter (default), OpenAI, Anthropic, Google Gemini, Ollama, LM Studio, Venice.ai, CometAPI, Z.AI, Moonshot AI, AWS Bedrock, Azure, HuggingFace, and custom endpoints. Providers configured via `providers.yaml`.

## Architecture

```
agent-zero/
├── agent.py              ← Core Agent class, message loop, tool execution
├── initialize.py         ← Agent initialization: settings, model config
├── models.py             ← Data models, LLM provider wiring (litellm)
├── run_ui.py             ← Flask + uvicorn server, WebSocket, API routes, plugin asset serving
├── prepare.py            ← One-time setup: runtime init, env prep
├── prompts/              ← All agent prompts and message templates (fully customizable)
├── helpers/              ← Core utilities + backward-compat shims for plugin helpers
│   ├── cache.py          ← Thread-safe in-memory cache with pattern invalidation
│   ├── yaml.py           ← Thin PyYAML wrapper
│   ├── plugins.py        ← Plugin system: discovery, toggle, config, hooks
│   ├── extension.py      ← @extensible decorator, async/sync call_extensions, webui extensions
│   ├── subagents.py      ← Agent profiles, get_paths() with include_plugins support
│   └── api.py            ← ApiHandler base class
├── tools/                ← Core tools (call_subordinate, response, unknown, wait)
├── api/                  ← Core API endpoints + backward-compat shims for plugin APIs
├── plugins/              ← Plugin system (16 built-in plugins)
│   ├── memory/           ← Memory tools, helpers (Cognee), extensions, API
│   ├── code_execution/   ← Code execution tool, shell/SSH/Docker helpers
│   ├── browser/          ← Browser automation (CDP monkeypatch preserved)
│   ├── search/           ← Web search (SearXNG, DuckDuckGo, Perplexity)
│   ├── scheduler/        ← Task scheduling, job loop, scheduler API
│   ├── skills/           ← Skills marketplace, installation, catalog extensions
│   ├── vision/           ← Vision/image tool
│   ├── document_query/   ← Document analysis tool + helper
│   ├── a2a/              ← Agent-to-Agent protocol (fasta2a client/server)
│   ├── notifications/    ← Notification tool, helpers, API
│   ├── error_retry/      ← Critical exception retry extension
│   ├── infection_check/  ← Prompt injection safety check extension
│   ├── text_editor/      ← Native file read/write/patch tool
│   ├── chat_branching/   ← Chat branch-from-message API
│   ├── plugin_installer/ ← ZIP/Git plugin installation
│   └── plugin_scan/      ← Plugin scanning/indexing
├── extensions/
│   └── python/           ← Core extension hooks (agent_init, banners, message_loop, etc.)
├── websocket_handlers/   ← WebSocket handlers
├── tests/                ← Unit + integration tests (pytest, ~2556 tests)
├── requirements.txt      ← Main dependencies
├── requirements2.txt     ← Override deps (litellm, openai, cognee) — installed after requirements.txt
└── requirements.dev.txt  ← Test dependencies (pytest, pytest-cov, pytest-timeout)
```

## Versioning & Release

- Current: **v0.9.8.N** (auto-incremented)
- Tags follow: `v0.9.8.N` increments
- The hassio addon version MUST match the fork tag

Automated release flow (on merge to `main`):
1. CI runs unit tests → integration tests
2. Auto-determines next version from latest git tag
3. Builds Docker image `ghcr.io/nafania/agent-zero:v0.9.8.N`
4. Creates and pushes git tag `v0.9.8.N`
5. Triggers `repository_dispatch` in `Nafania/agent-zero-hassio`

Required secrets:
- `HASSIO_DISPATCH_TOKEN` — PAT with `repo` scope for hassio repo
- `OPENROUTER_API_KEY` — for integration tests

## Addon Deployment (agent-zero-hassio)

The addon builds FROM `ghcr.io/nafania/agent-zero:latest` (see `build.yaml`).

**Persistent volume:** `/a0/usr` (mapped via `addon_config` in `config.yaml`). Everything outside `/a0/usr` is ephemeral — lost on container rebuild.

**Critical:** All databases, caches, and user data MUST be stored under `/a0/usr/`. Cognee SQLite is at `/a0/usr/cognee/cognee_system/`.

Environment configured via `config.yaml`: `HOME=/a0/usr`, XDG dirs, extension auto-install, SearxNG, ports (80→50001).

## Cognee Memory System

Cognee provides vector search, knowledge graphs, and document storage. Persistent memory allows agents to memorize solutions, code, facts, and instructions to solve tasks faster in future sessions.

| Component | Path | Purpose |
|-----------|------|---------|
| `cognee_init.py` | `plugins/memory/helpers/` | Config: env vars (BEFORE `import cognee`), LLM/embedding, storage dirs |
| `memory.py` | `plugins/memory/helpers/` | Memory class: search, insert, delete, knowledge preload, auto re-import |
| `cognee_background.py` | `plugins/memory/helpers/` | Background cognify/memify pipeline on dirty datasets |
| `memory_dashboard.py` | `plugins/memory/api/` | Dashboard API for browsing/editing memories |

Backward-compat shims in `helpers/` re-export from `plugins/memory/helpers/`.

Memory areas: `MAIN`, `FRAGMENTS`, `SOLUTIONS`. Per-agent subdirs (`default`, `projects/<name>`).

Knowledge files in `usr/knowledge/` are auto-imported into Cognee on first agent use. If Cognee DB is empty but knowledge index exists, full re-import is triggered automatically.

**Env var order matters:** `SYSTEM_ROOT_DIRECTORY`, `DB_PROVIDER`, `DB_NAME` must be set before `import cognee`. See `cognee_init.py`.

Search types: `GRAPH_COMPLETION`, `CHUNKS_LEXICAL`, `RAG_COMPLETION`, `TRIPLET_COMPLETION`, and more. Multi-search enabled by default — queries multiple search types and deduplicates results.

Background worker (`CogneeBackgroundWorker`) runs `cognify` + `memify` on dirty datasets, triggered by time interval or insert count threshold.

## MCP Integration

- **Client** (`mcp_handler.py`): Connects to external MCP servers via stdio, SSE, or streamable HTTP. Handles tool discovery and execution. Supports both local (stdio) and remote (SSE/HTTP) servers.
- **Server** (`mcp_server.py`): Exposes Agent Zero as a FastMCP server with `send_message` tool. Other agents/clients can talk to Agent Zero via MCP protocol.
- **API endpoints**: `mcp_servers_status`, `mcp_servers_apply`, `mcp_server_get_detail`, `mcp_server_get_log`.
- **A2A Protocol**: Agent-to-Agent communication via `fasta2a` — Agent Zero can act as both A2A server and client.

## Projects System

Git-based projects with clone authentication for public/private repositories. Each project gets:
- Isolated workspace directory
- Project-scoped memory and knowledge
- Project-specific secrets and MCP/A2A config
- Custom instructions

## Fork Changes vs Upstream

Key additions over [agent0ai/agent-zero](https://github.com/agent0ai/agent-zero):
- **Plugin system** with 16 built-in plugins, `@extensible` decorator, dynamic API dispatch
- **A2 path restructure** — `python/` prefix removed, aligned with upstream v1.1
- Cognee memory persistence on addon volume (env vars before import)
- Auto re-import knowledge when Cognee DB is empty
- `cognee.setup()` with retry on `DatabaseNotCreatedError`
- Task self-recovery (ERROR and stuck RUNNING states)
- Skill installation via `/skill-install` chat command
- Structured RFC 3339 logging
- Accurate token counting via `litellm.token_counter`
- Truncation detection and retry for LLM streams
- Metrics persistence across container restarts
- Home Assistant addon packaging

## Testing

- **Framework:** pytest + pytest-asyncio + pytest-mock + pytest-cov + pytest-timeout
- **Markers:** `integration` (real services), `slow` (>5s), `regression` (fixed bugs)
- **CI:** GitHub Actions (`ci.yml`) on push to `main`/`develop`, runs `pytest tests/ -m "not integration"`. On merge to `main`: integration tests → Docker build → auto-tag → notify hassio.
- **Dependencies in CI:** `requirements.txt` + `requirements2.txt` + `requirements.dev.txt`
- **Coverage:** ~76% line coverage, ~2400 tests
- **Structure:** mirrors top-level packages — `tests/helpers/`, `tests/api/`, `tests/extensions/`, `tests/tools/`, `tests/integration/`

## Origin

- Originally forked from [agent0ai/agent-zero](https://github.com/agent0ai/agent-zero) v0.9.8
- Upstream remote removed — this is now an independent repository
- No further upstream syncs planned; fork diverges significantly in memory, MCP, and addon areas
