# Phase 3: A3-A8 Remaining Architectural Changes

**Date:** 2026-03-30
**Scope:** All remaining architectural backport items (A3-A8) from upstream
**Strategy:** Sequential branches following dependency chain: A3+A4 parallel, then A5+A6 parallel after A3, then A7 after A3, then A8 after A7. Each item gets its own branch/PR.
**Parent spec:** [2026-03-28-upstream-backport-design.md](../specs/2026-03-28-upstream-backport-design.md)

---

## Dependency Graph

```
A3 (@extensible) ──┬──→ A5 (WS extensions)
                   ├──→ A6 (API routing refactor)
                   ├──→ A7 (Extension dir restructuring) ──→ A8 (Prompt split)
A4 (AgentConfig slimming) — parallel with A3
```

## Execution Order

A3 and A4 can proceed in parallel (no cross-dependency). A5, A6, A7 all require A3. A8 requires A7. Practical order: **A3 -> A4 -> A5 -> A6 -> A7 -> A8** (sequential branches, each merged to main before next starts).

---

## A3: @extensible Decorator Completion
**Branch:** `upstream/a3-extensible-decorator` | **Effort:** M | **Upstream ref:** `d82b121bc9` + current `upstream/main`

### Current State
- Core `@extensible` decorator exists in `helpers/extension.py` (from A1)
- Applied to 34 functions in agent.py, 7 in initialize.py, 5 in run_ui.py, 13 in api/plugins.py
- Missing: `helpers/modules.py`, `helpers/functions.py`, `helpers/watchdog.py`, hot-reload infrastructure, `_functions/` path support

### Work Items

**1. Create `helpers/modules.py`** (port from upstream)
- `import_module(file_path)` — load .py by absolute path via `importlib.util`
- `load_classes_from_folder(folder, pattern, base_class)` — discover subclasses in a directory
- `load_classes_from_file(file, base_class)` — discover subclasses in single file
- `purge_namespace(namespace)` — remove module subtree from `sys.modules` for hot-reload
- **Impact:** `helpers/extract_tools.py` currently has `load_classes_from_folder` — refactor to delegate to `modules.py` or keep both (upstream has modules.py as the canonical one)

**2. Create `helpers/functions.py`** (port from upstream)
- `safe_call(func, *args, **kwargs)` — introspect function signature and only pass accepted args/kwargs
- Used by `call_plugin_hook` in helpers/plugins.py (currently has inline try/except)

**3. Create `helpers/watchdog.py`**
- File system watcher using `watchdog` library
- `add_watchdog(paths, callback)` — register FS change handlers
- Used by: `register_extensions_watchdogs()`, `register_watchdogs()` in api.py and plugins.py
- Clears caches on file changes for hot-reload

**4. Update `helpers/extension.py`**
- Add `_log_extension_call()` for debugging/tracing extension execution
- Add `register_extensions_watchdogs()` — clear extension caches on FS changes
- Update `_prepare_inputs()` to support `_functions/<module>/<qualname>/start|end` path resolution (upstream pattern)
- Use `modules.load_classes_from_folder` instead of `extract_tools.load_classes_from_folder`

**5. Update `helpers/plugins.py`**
- Implement `refresh_plugin_modules(plugin_names)` — purge and re-import plugin modules (resolves TODO(a3) at line 89)
- Add `register_watchdogs()` — clear plugin caches on FS changes
- Replace try/except in `call_plugin_hook` with `functions.safe_call`

**6. Add `@extensible` to `models.py`**
- Upstream has `@extensible` on `get_api_key()` — our fork currently has 0 extensible decorators in models.py

**7. Fix `error_retry` TODO(a3)**
- `plugins/error_retry/extensions/python/message_loop_end/_80_error_retry.py` line 21: `call_extensions("message_loop_end", ...)` needs to pass `exception` kwarg so error_retry extension can access it

**8. Add `validate_tool_request()`** to agent.py (upstream commit `1b89a0d3`)

### Upstream Reference Files
- `upstream/main:helpers/modules.py` — full implementation of module loading + purge_namespace
- `upstream/main:helpers/functions.py` — safe_call implementation
- `upstream/main:helpers/extension.py` — evolved @extensible with `_functions/` paths, `_log_extension_call`, `register_extensions_watchdogs`

### Verification
- All existing tests pass (pytest)
- New unit tests for modules.py, functions.py, watchdog.py
- Integration: extension hot-reload works (change extension file -> cache cleared -> new version loaded)
- Docker: application starts, plugins load, extensions fire

---

## A4: AgentConfig Slimming
**Branch:** `upstream/a4-agentconfig-slimming` | **Effort:** M | **Upstream ref:** upstream v1.1

### Current State (fork)
```python
@dataclass
class AgentConfig:
    chat_model: models.ModelConfig        # REMOVE
    utility_model: models.ModelConfig     # REMOVE
    embeddings_model: models.ModelConfig  # REMOVE
    browser_model: models.ModelConfig     # REMOVE
    mcp_servers: str                      # KEEP
    profile: str = ""                     # KEEP
    memory_subdir: str = ""              # REMOVE -> _memory plugin
    knowledge_subdirs: list[str] = ...    # KEEP
    browser_http_headers: dict = ...      # REMOVE -> _browser plugin
    code_exec_ssh_enabled: bool = True    # REMOVE -> _code_execution plugin
    code_exec_ssh_addr/port/user/pass     # REMOVE -> _code_execution plugin
    additional: Dict[str, Any] = ...      # KEEP
```

### Target State (upstream)
```python
@dataclass
class AgentConfig:
    mcp_servers: str
    profile: str = ""
    knowledge_subdirs: list[str] = field(default_factory=lambda: ["default", "custom"])
    additional: Dict[str, Any] = field(default_factory=dict)
```

### Upstream Reference
- `upstream/main:agent.py` — slimmed AgentConfig with 4 fields only
- `upstream/main:plugins/_model_config/` — plugin that manages model configuration via extension hooks on get_chat_model/get_utility_model/get_embedding_model/get_browser_model

### Work Items

**1. Create `_model_config` plugin**
- `plugins/_model_config/plugin.yaml` — manifest
- `plugins/_model_config/extensions/python/_functions/agent/Agent/get_chat_model/start/_10_model_config.py`
- Same for `get_utility_model`, `get_embedding_model`, `get_browser_model`
- Extension reads model settings and returns configured ModelConfig
- This replaces the 4 model fields on AgentConfig

**2. Move SSH/code_exec fields to `_code_execution` plugin**
- Add SSH settings to code_execution plugin config (plugin.yaml defaults + settings override)
- Update `shell_ssh.py` and `shell_local.py` to read from plugin config instead of `agent.config.*`

**3. Move `memory_subdir` to `_memory` plugin**
- Add to memory plugin config
- Update `helpers/memory.py` / context memory functions

**4. Move `browser_http_headers` to `_browser` plugin**
- Add to browser plugin config (or browser_agent plugin)
- Update browser helpers

**5. Slim `AgentConfig`** in agent.py
- Remove all fields listed above
- Keep: `mcp_servers`, `profile`, `knowledge_subdirs`, `additional`

**6. Update `initialize.py`**
- Remove model config construction from `initialize_agent()`
- Model config now handled by `_model_config` plugin extension hooks
- Update `_set_runtime_config()` — SSH fields no longer on AgentConfig

**7. Update `Agent` accessor methods** (~lines 808-840 in agent.py)
- `get_chat_model()`, `get_utility_model()`, `get_browser_model()`, `get_embedding_model()` — no longer read from `self.config.*`; instead rely on `_model_config` extension hooks
- These are already `@extensible`, so the _model_config plugin start hook can inject the model

**8. Update all consumers**
- `persist_chat.py` — loads/saves agent config
- Tests constructing AgentConfig with model fields
- Any code referencing `agent.config.chat_model`, `agent.config.code_exec_ssh_*`, etc.

### Verification
- All tests pass with slimmed AgentConfig
- Docker: models still load correctly, SSH code execution works, memory subdirs work
- Settings UI still configures models correctly

---

## A5: WebSocket Handlers Plugin Support
**Branch:** `upstream/a5-ws-extensions` | **Effort:** S/M | **Upstream ref:** upstream v1.1

### Current State
- 4 handlers in `websocket_handlers/`: `_default.py`, `hello_handler.py`, `state_sync_handler.py`, `dev_websocket_test_handler.py`
- Discovery only from `websocket_handlers/` folder
- Upstream has `webui_handler.py` instead of `state_sync_handler.py`
- Upstream still has `python/websocket_handlers/` (NOT removed — spec was inaccurate)

### Upstream Reference
- `upstream/main:python/websocket_handlers/` — `_default.py`, `dev_websocket_test_handler.py`, `hello_handler.py`, `webui_handler.py`
- `upstream/main:run_ui.py` lines 194-199 — `_build_websocket_handlers_by_namespace` with `handlers_folder="python/websocket_handlers"`

### Work Items

**1. Add `webui_handler.py`** from upstream (compare with our `state_sync_handler.py`, merge/reconcile)

**2. Update WS discovery** to include plugin WS handlers
- `discover_websocket_namespaces()` in `helpers/websocket_namespace_discovery.py`: scan plugin `websocket_handlers/` dirs in addition to core
- Maintain security invariants (auth, CSRF per namespace)

**3. Add `@extensible`** to key WS registration/connection functions in run_ui.py

**4. Add watchdog support** for WS handler cache invalidation (if applicable)

### Verification
- WebSocket connections work (chat, state sync, dev tools)
- Docker: real-time updates in UI still function

---

## A6: API Routing Refactor
**Branch:** `upstream/a6-api-routing` | **Effort:** M/L | **Upstream ref:** `4e243a996c`, upstream `helpers/api.py`

### Current State (fork)
- `register_api_handler()` defined inline in `run_ui.py` lines 543-569
- Eagerly loads ALL handler classes at startup via `load_classes_from_folder("api", "*.py", ApiHandler)`
- Creates one Flask route per handler
- Plugin API handlers registered separately with `/plugins/<name>` prefix

### Target State (upstream)
- `register_api_route()` in `helpers/api.py`
- Single catch-all route: `/api/<path:path>` with dynamic dispatch
- Lazy handler resolution: loads handler class on first request, caches wrapped handler
- Built-in handlers: `api/{path}.py`; plugin handlers: `plugins/{name}/api/{handler}.py`
- Watchdog clears handler cache on file changes (hot-reload)
- Uses `modules.load_classes_from_file` (from A3)

### Upstream Reference
- `upstream/main:helpers/api.py` — `register_api_route(app, lock)` with `_dispatch(path)`, handler caching, `register_watchdogs()`
- `upstream/main:run_ui.py` line 374 — `register_api_route(webapp, lock)`

### Work Items

**1. Move `ApiHandler` class** from the inline definition in helpers/api.py to match upstream's structure (already partially there)

**2. Implement `register_api_route(app, lock)`** in `helpers/api.py`
- Single `/api/<path:path>` catch-all route
- `_dispatch(path)` function: check cache -> resolve handler file -> load class -> wrap with security decorators -> cache -> call
- Built-in resolution: `api/{path}.py`
- Plugin resolution: `plugins/{plugin_name}/api/{handler_name}.py`
- 404 for unresolved paths, 405 for wrong methods

**3. Add `register_watchdogs()`** in helpers/api.py
- Clear handler cache when api/ directory changes (uses helpers/watchdog.py from A3)

**4. Update `run_ui.py`**
- Remove inline `register_api_handler` function and eager loading loop
- Replace with single `register_api_route(webapp, lock)` call
- Import from `helpers.api`

**5. URL scheme change**: current fork uses `/<handler_name>` (e.g. `/message`); upstream uses `/api/<path>` (e.g. `/api/message`). Must add backward-compat redirects or update all frontend API calls.

### Verification
- All API integration tests pass
- Docker: full UI functionality (chat, settings, plugins, skills)
- No 404s for existing endpoints

---

## A7: Extension Directory Restructuring
**Branch:** `upstream/a7-extension-dirs` | **Effort:** M | **Upstream ref:** `7e1d9ad2a4`

### Current State
- Extensions in hook-name directories: `extensions/python/system_prompt/`, `extensions/python/agent_init/`, etc.
- 25 hook-name directories under `extensions/python/`
- @extensible start/end hooks resolve to same hook-name directories

### Target State (upstream)
- BOTH patterns coexist:
  - Hook-name directories (legacy): `extensions/python/system_prompt/`, `extensions/python/banners/`, etc.
  - `_functions/` directories (new, for @extensible): `extensions/python/_functions/agent/Agent/handle_exception/end/`
- Extension discovery merges both sources

### Upstream Reference
- `upstream/main:extensions/python/_functions/` — 3 core _functions extensions (handle_exception handlers, register_watchdogs)
- `upstream/main:plugins/*/extensions/python/_functions/` — plugin _functions extensions (_browser_agent, _error_retry, _model_config)
- `upstream/main:helpers/extension.py` — `_prepare_inputs()` with `_functions/<module>/<qualname>/start|end` path resolution

### Work Items

**1. Update `_prepare_inputs()` in extension.py**
- `@extensible` start/end hooks now resolve to `_functions/<module_path>/<qualname>/start|end` directories
- Module path uses dots-to-slashes (`agent.Agent.monologue` -> `_functions/agent/Agent/monologue`)

**2. Create initial `_functions/` extensions** from upstream
- `extensions/python/_functions/__main__/init_a0/end/_10_register_watchdogs.py` — register all watchdogs on startup
- `extensions/python/_functions/agent/Agent/handle_exception/end/_40_handle_intervention_exception.py`
- `extensions/python/_functions/agent/Agent/handle_exception/end/_50_handle_repairable_exception.py`
- `extensions/python/_functions/agent/Agent/handle_exception/end/_90_handle_critical_exception.py`

**3. Update `subagents.get_paths()`** if needed to support `_functions/` path resolution

**4. Migrate plugin extensions** that should use `_functions/` pattern
- `plugins/error_retry/extensions/python/_functions/agent/Agent/handle_exception/end/_80_retry_critical_exception.py`
- `plugins/error_retry/extensions/python/_functions/agent/Agent/monologue/start/_10_reset_critical_exception_counter.py`
- `plugins/_model_config/extensions/python/_functions/agent/Agent/get_chat_model/start/_10_model_config.py` (created in A4)

### Verification
- All existing extensions still fire in correct order
- New `_functions/` extensions fire for @extensible decorated functions
- Docker: full functionality preserved

---

## A8: System Prompt Split
**Branch:** `upstream/a8-prompt-split` | **Effort:** S | **Upstream ref:** `2566ee134d`

### Current State
- Single monolithic `extensions/python/system_prompt/_10_system_prompt.py` (97 lines)
- Contains `SystemPrompt` class with all logic: main, tools, mcp, secrets, skills, project

### Target State (upstream)
- 6 per-concern Extension files:
  - `_10_main_prompt.py` — main system prompt
  - `_11_tools_prompt.py` — tool descriptions + vision
  - `_12_mcp_prompt.py` — MCP tools prompt
  - `_13_secrets_prompt.py` — secrets injection
  - `_13_skills_prompt.py` — skills catalog
  - `_14_project_prompt.py` — project context

### Upstream Reference
- `upstream/main:extensions/python/system_prompt/` — 6 files + .gitkeep
- Plugin system_prompt extensions: `plugins/_memory/extensions/python/system_prompt/_20_behaviour_prompt.py`, `plugins/_promptinclude/extensions/python/system_prompt/_16_promptinclude.py`, etc.

### Work Items

**1. Split `_10_system_prompt.py`** into 6 files
- Each file: one `Extension` subclass, one `execute()` method, appends its section to `system_prompt` list
- Extract existing helper functions (`get_main_prompt`, `get_tools_prompt`, etc.) into their respective files
- Add `.gitkeep` for empty override support

**2. Delete `_10_system_prompt.py`** (replaced by the 6 new files)

**3. Preserve plugin system_prompt extensions**
- `plugins/skills/extensions/python/message_loop_prompts_after/_65_include_loaded_skills.py` and `_60_skills_catalog.py` — these use the `message_loop_prompts_after` hook, not `system_prompt`, so no changes needed

### Verification
- System prompt output is identical before/after split (order preserved by numeric prefixes)
- Docker: agent behavior unchanged, all prompt sections present

---

## Risk Mitigation

- **A4 is the highest-risk item** — model config touches many call sites. Extensive search for `agent.config.chat_model`, `config.utility_model`, etc. before marking complete.
- **A6 changes URL dispatch** — must verify every API endpoint still works. Run full test suite + manual Docker testing.
- **A7 overlaps with A3** — `_prepare_inputs` in extension.py changes for both. A3 lays groundwork, A7 adds `_functions/` directories.
- **Each branch is atomic** — merge and verify before starting next item.
