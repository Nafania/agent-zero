# A1: Plugin System — Implementation Plan

> Phase 2 of the upstream backport project (see `docs/specs/2026-03-28-upstream-backport-design.md`).

## Scope

Implement the full plugin system architecture with `@extensible` decorator, plugin infrastructure (discovery, toggle, config, hooks), and migrate all domain-specific functionality into 16 plugins, preserving fork customizations (Cognee, CDP, skills marketplace).

### User decisions (from planning phase)

- **Migration scope**: Full spec — all 16 plugins, not just the 9 migrated upstream
- **@extensible decorator**: Included in A1 (originally planned for A3)
- **model_config plugin**: Deferred (requires A4/AgentConfig slimming)

---

## Architecture Overview

```mermaid
graph TD
  subgraph core [Core - stays outside plugins]
    agentPy["agent.py"]
    initPy["initialize.py"]
    modelsPy["models.py"]
    runUi["run_ui.py"]
    extPy["helpers/extension.py"]
    filesPy["helpers/files.py"]
    pluginsPy["helpers/plugins.py (NEW)"]
    subagentsPy["helpers/subagents.py"]
    cachePy["helpers/cache.py (NEW)"]
    yamlPy["helpers/yaml.py (NEW)"]
    apiPy["helpers/api.py"]
  end

  subgraph plugins [plugins/ directory]
    mem["memory"]
    codeExec["code_execution"]
    browser["browser"]
    search["search"]
    sched["scheduler"]
    skills["skills"]
    vis["vision"]
    docQ["document_query"]
    a2a["a2a"]
    notif["notifications"]
    infCheck["infection_check"]
    errRetry["error_retry"]
    textEd["text_editor"]
    chatBr["chat_branching"]
    pluginInst["plugin_installer"]
    pluginScan["plugin_scan"]
  end

  pluginsPy -->|discovers| plugins
  subagentsPy -->|"include_plugins=True"| plugins
  extPy -->|loads extensions from| plugins
  runUi -->|serves assets from| plugins
  apiPy -->|dispatches to| plugins
```

## Key Design Decisions

- **Manifest format**: `plugin.yaml` (matches upstream latest)
- **Naming**: no underscore prefix (e.g., `memory` not `_memory`)
- **@extensible**: included in A1 — enables plugin hooks via `start`/`end` extension points
- **API dispatch**: plugin API handlers registered at `/plugins/<name>/<handler>` with backward-compat shims at old routes
- **Toggle system**: `.toggle-0`/`.toggle-1` files, per-project and per-agent overrides
- **Plugin config**: `default_config.yaml` in plugin dir, `config.json` for user overrides
- **Backward compatibility**: Thin re-export shims at old `helpers/*.py` and `api/*.py` locations

## Plugin Directory Convention

```
plugins/<name>/
  plugin.yaml              # manifest (required)
  default_config.yaml      # optional defaults
  hooks.py                 # optional lifecycle hooks
  initialize.py            # optional init script
  tools/                   # tool .py files (discovered via get_paths)
  extensions/python/<hook>/  # python extensions (discovered via get_paths)
  extensions/webui/<hook>/   # webui extensions (HTML/JS)
  helpers/                 # plugin-specific helpers (imported directly)
  api/                     # API handlers
  prompts/                 # prompt templates
  webui/                   # UI components (main.html, config.html)
  agents/                  # agent profiles provided by plugin
```

---

## Tasks

### Sub-phase 1: Infrastructure

| ID | Task | Status |
|----|------|--------|
| infra-new-helpers | Create `helpers/cache.py`, `helpers/yaml.py`, add missing functions to `helpers/files.py` | ✅ |
| infra-plugins-py | Create `helpers/plugins.py` with full plugin discovery, toggle, config, hooks | ✅ |
| infra-extensible | Rewrite `helpers/extension.py`: add `@extensible` decorator, split async/sync, webui extensions, plugin path integration | ✅ |
| infra-subagents | Update `helpers/subagents.py`: add `include_plugins` param, plugin agent merging | ✅ |
| infra-api-dispatch | Update `helpers/api.py` + `run_ui.py`: dynamic API dispatch, plugin asset routes | ✅ |
| infra-api-plugins | Create `api/plugins.py` endpoint for plugin management | ✅ |

#### New files
- **helpers/cache.py** — thread-safe in-memory cache with pattern-based invalidation
- **helpers/yaml.py** — thin wrapper around PyYAML (`loads`, `dumps`, `from_json`, `to_json`)
- **helpers/plugins.py** — full plugin system: `get_plugin_roots()`, `get_plugins_list()`, `get_enhanced_plugins_list()`, `find_plugin_dir()`, `get_plugin_meta()`, `get_enabled_plugins()`, `get_enabled_plugin_paths()`, `toggle_plugin()`, `get_toggle_state()`, `get_plugin_config()`, `save_plugin_config()`, `call_plugin_hook()`, `after_plugin_change()`, `find_plugin_assets()`, `determine_plugin_asset_path()`
- **api/plugins.py** — plugin management API (list, toggle, get/save config, uninstall)

#### Modified files
- **helpers/files.py** — constants `PLUGINS_DIR`, `USER_DIR`, `AGENTS_DIR`; functions `read_file_yaml()`, `read_file_json()`, `is_file()`, `is_dir()`, `delete_file()`
- **helpers/extension.py** — `@extensible` decorator, `call_extensions_async`, `call_extensions_sync`, `get_webui_extensions()`, cache-based extension loading
- **helpers/subagents.py** — `include_plugins` param in `get_paths()`, plugin agent merging in `get_agents_dict()` and `load_agent_data()`, `agent.yaml` support
- **run_ui.py** — plugin asset serving routes, plugin API handler registration

---

### Sub-phase 2: Simple Plugin Migrations (extension-only)

| ID | Task | Status |
|----|------|--------|
| migrate-simple | Create `error_retry` and `infection_check` plugins (new from upstream) | ✅ |

---

### Sub-phase 3: Tool + Helper Plugin Migrations

| ID | Task | Status |
|----|------|--------|
| migrate-memory | Migrate memory plugin (tools + helpers + extensions + API), preserve Cognee customizations | ✅ |
| migrate-code-exec | Migrate code_execution plugin (tools + helpers) | ✅ |
| migrate-browser | Migrate browser plugin (tool + helpers), preserve CDP monkeypatch | ✅ |
| migrate-search | Migrate search plugin (tool + helpers) | ✅ |
| migrate-scheduler | Migrate scheduler plugin (tool + helpers + API) | ✅ |
| migrate-skills | Migrate skills plugin (tool + helpers + API + extensions), preserve marketplace | ✅ |
| migrate-small | Migrate vision, document_query, a2a, notifications plugins | ✅ |

#### Migration approach
- `git mv` for all file moves to preserve history
- Backward-compat shims at old `helpers/*.py` locations (re-export via `from plugins.*.helpers.* import *`)
- Backward-compat shims at old `api/*.py` locations for API handlers
- Cross-plugin references updated (e.g., `from tools.skills_tool import` → `from plugins.skills.tools.skills_tool import`)

#### Plugins migrated (12 existing → plugin directories)
- **memory**: 5 tools, 6 helpers, 6 extensions, 5 API handlers
- **code_execution**: 2 tools, 4 helpers
- **browser**: 1 tool, 3 helpers
- **search**: 1 tool, 3 helpers
- **scheduler**: 1 tool, 2 helpers, 6 API handlers
- **skills**: 1 tool, 3 helpers, 3 API handlers, 3 extensions
- **vision**: 1 tool
- **document_query**: 1 tool, 1 helper
- **a2a**: 1 tool, 2 helpers
- **notifications**: 1 tool, 1 helper, 4 API handlers

---

### Sub-phase 4: New Plugins from Upstream

| ID | Task | Status |
|----|------|--------|
| migrate-upstream-new | Create text_editor, chat_branching, plugin_installer, plugin_scan | ✅ |

- **text_editor**: File read/write/patch tool
- **chat_branching**: Chat branch-from-message API
- **plugin_installer**: ZIP/Git plugin installation helpers
- **plugin_scan**: Plugin scanning/indexing (stub)

---

### Sub-phase 5: Cleanup and Integration

| ID | Task | Status |
|----|------|--------|
| cleanup-tests | Update all test imports, run full test suite, fix failures, update CI/docs | ✅ |

- Updated ~50 test files with new import paths
- Fixed `patch()` targets to point to real modules (not shims)
- Fixed underscore-prefixed name re-exports
- Updated AGENTS.md architecture docs
- Updated `.github/workflows/ci.yml` path triggers to include `plugins/**`
- **Final result: 2556 passed, 2 skipped, 0 failures**

---

## Risk Mitigation (executed)

1. **Backward compatibility**: Thin re-export shims at old `helpers/*.py` and `api/*.py` locations — existing code continues to work
2. **Circular imports**: Plugin helpers import core helpers, never the reverse
3. **Test stability**: Full test suite run after each sub-phase, all 2556 tests pass
4. **Cognee/CDP**: Files moved with `git mv` preserving history, no functional changes
5. **API routes**: Backward-compat shims ensure all 85 existing API endpoints still resolve at old paths

## Files Summary

- **New files**: ~30 (plugins.py, cache.py, yaml.py, api/plugins.py, 16 plugin.yaml manifests, default_config.yaml files, new plugin code)
- **Moved files**: ~45 (tools, helpers, extensions → plugins/)
- **Shim files**: ~43 (25 helper shims + 18 API shims)
- **Modified files**: ~10 (extension.py, subagents.py, files.py, run_ui.py, AGENTS.md, ci.yml)
- **Updated test files**: ~50 (import rewrites, patch target fixes)

---

## Upstream Reference Points

Our goal: achieve API-compatible plugin system so that all future upstream plugins, extensions, and WebUI components work without modification in our fork.

### Upstream branch and commit

- **Branch**: `origin/development`
- **HEAD at time of implementation**: `1b89a0d3` (Add tool request validation and plugin change notifications)
- **Key upstream commits** (chronological):
  - `d02dda36` — BIG PYTHON REFACTOR (initial plugin structure, `@extensible`)
  - `ab9fc4ee` — Refactor extensions to async/sync API
  - `eac0d3bc` — Redesign plugin marketplace; simplify API
  - `9acbf253` — Move input tool and prompt into code_execution plugin
  - `27730153` — Clear plugin cache & add API extension hooks
  - `1b89a0d3` — Add tool request validation and plugin change notifications

### Verification Checklist — API Surface Compatibility

Compare our implementation against upstream `origin/development` HEAD.

#### `helpers/plugins.py` — public functions

| Function | Upstream | Ours | Status |
|----------|----------|------|--------|
| `get_plugin_roots()` | ✅ | ✅ | ✅ compatible |
| `get_plugins_list()` | ✅ | ✅ | ✅ compatible |
| `get_enhanced_plugins_list()` | ✅ | ✅ | ✅ compatible |
| `get_plugin_meta()` | ✅ | ✅ | ✅ compatible |
| `find_plugin_dir()` | ✅ | ✅ | ✅ compatible |
| `delete_plugin()` | ✅ | ✅ | ✅ compatible |
| `get_plugin_paths()` | ✅ | ✅ | ✅ compatible |
| `get_enabled_plugin_paths()` | ✅ | ✅ | ✅ compatible |
| `get_enabled_plugins()` | ✅ | ✅ | ✅ compatible |
| `determined_toggle_from_paths()` | ✅ | ✅ | ✅ compatible |
| `get_toggle_state()` | ✅ | ✅ | ✅ compatible |
| `toggle_plugin()` | ✅ | ✅ | ✅ compatible |
| `get_plugin_config()` | ✅ | ✅ | ✅ compatible |
| `get_default_plugin_config()` | ✅ | ✅ | ✅ compatible |
| `save_plugin_config()` | ✅ | ✅ | ✅ compatible |
| `find_plugin_asset()` | ✅ | ✅ | ✅ compatible |
| `find_plugin_assets()` | ✅ | ✅ | ✅ compatible |
| `determine_plugin_asset_path()` | ✅ | ✅ | ✅ compatible |
| `send_frontend_reload_notification()` | ✅ (no args) | ✅ (optional `plugin_names`) | ✅ compatible (superset) |
| `after_plugin_change()` | ✅ (no args) | ✅ (optional `plugin_names`) | ✅ compatible (superset) |
| `clear_plugin_cache()` | ✅ | ✅ | ✅ compatible |
| `uninstall_plugin()` | ❌ | ✅ | ✅ our extra |
| `call_plugin_hook()` | ❌ | ✅ | ✅ our extra |

#### `helpers/extension.py` — public API

| Symbol | Upstream | Ours | Status |
|--------|----------|------|--------|
| `@extensible` decorator | ✅ | ✅ (applied to 43 functions) | ✅ resolved |
| `Extension` base class | ✅ | ✅ | ✅ compatible |
| `call_extensions_async()` | ✅ | ✅ | ✅ compatible |
| `call_extensions_sync()` | ✅ | ✅ | ✅ compatible |
| `call_extensions()` (legacy) | ❌ (removed) | ✅ (backward compat) | ✅ our extra |
| `get_webui_extensions()` | ✅ | ✅ | ✅ compatible |
| `_get_extension_classes()` | ✅ | ✅ | ✅ compatible |

#### `helpers/subagents.py` — `get_paths()`

| Feature | Upstream | Ours | Status |
|---------|----------|------|--------|
| `include_plugins` param | ✅ | ✅ | ✅ compatible |
| Plugin agent merging | ✅ | ✅ | ✅ compatible |
| `agent.yaml` support | ✅ | ✅ | ✅ compatible |

#### `run_ui.py` — plugin routes

| Feature | Upstream | Ours | Status |
|---------|----------|------|--------|
| `/plugins/<name>/<path>` (builtin) | ✅ | ✅ | ✅ compatible |
| `/usr/plugins/<name>/<path>` (user) | ✅ | ✅ | ✅ compatible |
| `/extensions/webui/<path>` | ✅ | ✅ | ✅ compatible |
| Plugin API handler registration | ✅ | ✅ | ✅ compatible |
| `@extensible` on routes/init | ✅ (5 decorations) | ✅ (5 decorations) | ✅ resolved |

#### `api/plugins.py` — API actions

| Action | Upstream | Ours | Status |
|--------|----------|------|--------|
| `get_config` | ✅ | ✅ | ✅ |
| `save_config` | ✅ | ✅ | ✅ |
| `get_toggle_status` | ✅ | ✅ | ✅ |
| `toggle_plugin` | ✅ | ✅ (`toggle` + `toggle_plugin` alias) | ✅ resolved |
| `get_default_config` | ✅ | ✅ | ✅ |
| `list` | ❌ | ✅ | ✅ our extra |
| `uninstall` | ❌ | ✅ | ✅ our extra |
| `list_configs` | ✅ | ✅ | ✅ resolved |
| `delete_config` | ✅ | ✅ | ✅ resolved |
| `delete_plugin` | ✅ | ✅ | ✅ resolved |
| `get_doc` | ✅ | ✅ | ✅ resolved |
| `run_init_script` | ✅ | ✅ | ✅ resolved |
| `get_init_exec` | ✅ | ✅ | ✅ resolved |

#### Plugins — directory comparison

| Plugin | Upstream | Ours | Notes |
|--------|----------|------|-------|
| `memory` | ✅ | ✅ | + Cognee customizations |
| `code_execution` | ✅ | ✅ | |
| `error_retry` | ✅ | ✅ | |
| `infection_check` | ✅ | ✅ | |
| `text_editor` | ✅ | ✅ | |
| `chat_branching` | ✅ | ✅ | |
| `plugin_installer` | ✅ | ✅ | |
| `plugin_scan` | ✅ | ✅ | |
| `example_agent` | ✅ | ✅ | ✅ resolved |
| `browser` | ❌ | ✅ | Our extra (not yet migrated upstream) |
| `search` | ❌ | ✅ | Our extra |
| `scheduler` | ❌ | ✅ | Our extra |
| `skills` | ❌ | ✅ | Our extra |
| `vision` | ❌ | ✅ | Our extra |
| `document_query` | ❌ | ✅ | Our extra |
| `a2a` | ❌ | ✅ | Our extra |
| `notifications` | ❌ | ✅ | Our extra |

### Identified Gaps — ALL RESOLVED

1. **`@extensible` applied to 43 functions** ✅
   - `agent.py`: 32 methods (AgentContext: 10, LoopData: 1, Agent: 21)
   - `initialize.py`: 6 functions
   - `run_ui.py`: 5 functions
   - Fixed `_get_agent` in decorator to handle mocked Agent classes (TypeError) and spec'd mock instances (hasattr guard)

2. **`api/plugins.py` — all 14 actions now present** ✅
   - Added: `list_configs`, `delete_config`, `delete_plugin`, `get_doc`, `run_init_script`, `get_init_exec`
   - Added `toggle_plugin` alias for upstream compat (original `toggle` kept)
   - Enhanced `get_toggle_status` to match upstream response format (project_name/agent_profile)

3. **`example_agent` plugin added** ✅
   - Copied from upstream: plugin.yaml, agent.yaml, system prompt

### How to verify implementation against upstream

```bash
# 1. Compare helpers/plugins.py function signatures
diff <(git show origin/development:helpers/plugins.py | grep "^def \|^async def " | sort) \
     <(grep "^def \|^async def " helpers/plugins.py | sort)

# 2. Compare helpers/extension.py API
diff <(git show origin/development:helpers/extension.py | grep "^def \|^async def \|^class " | sort) \
     <(grep "^def \|^async def \|^class " helpers/extension.py | sort)

# 3. Compare @extensible usage
diff <(git show origin/development:agent.py | grep -c "@extension.extensible") \
     <(grep -c "@extension.extensible" agent.py)

# 4. Compare plugin list
diff <(git ls-tree origin/development plugins/ --name-only -d | sort) \
     <(ls -d plugins/*/ | sed 's|/$||' | sort)

# 5. Compare api/plugins.py actions
diff <(git show origin/development:api/plugins.py | grep "action ==" | sort) \
     <(grep "action ==" api/plugins.py | sort)

# 6. Compare subagents.py get_paths signature
diff <(git show origin/development:helpers/subagents.py | grep -A20 "def get_paths") \
     <(grep -A20 "def get_paths" helpers/subagents.py)
```
