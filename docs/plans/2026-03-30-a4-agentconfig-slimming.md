# A4: AgentConfig Slimming — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove model, SSH, memory, and browser fields from `AgentConfig`, moving them to their respective plugin configs via the `@extensible` mechanism from A3.

**Architecture:** Upstream `AgentConfig` has 4 fields: `mcp_servers`, `profile`, `knowledge_subdirs`, `additional`. Model configuration is handled by a `_model_config` plugin that provides extension hooks on `get_*_model()`. SSH config moves to `_code_execution` plugin config, `memory_subdir` to `_memory`, `browser_http_headers` to `_browser`.

**Parent spec:** [2026-03-28-upstream-backport-design.md](../specs/2026-03-28-upstream-backport-design.md) § A4
**Upstream refs:** `upstream/main:agent.py` (lines 310-315), `upstream/main:plugins/_model_config/`

---

## File Structure

### New Files
- `plugins/model_config/plugin.yaml` — manifest (always_enabled)
- `plugins/model_config/default_config.yaml` — default model settings (chat, utility, embedding)
- `plugins/model_config/helpers/model_config.py` — `build_chat_model()`, `build_utility_model()`, `build_embedding_model()`, `get_config()`, `get_chat_model_config()` etc.
- `plugins/model_config/extensions/python/_functions/agent/Agent/get_chat_model/start/_10_model_config.py`
- `plugins/model_config/extensions/python/_functions/agent/Agent/get_utility_model/start/_10_model_config.py`
- `plugins/model_config/extensions/python/_functions/agent/Agent/get_embedding_model/start/_10_model_config.py`
- `tests/plugins/test_model_config.py`

### Modified Files
- `agent.py` — slim AgentConfig (remove 10 fields), change `get_*_model()` to return `None`
- `initialize.py` — remove model config construction, remove `_set_runtime_config` SSH fields
- `plugins/code_execution/default_config.yaml` — add SSH settings
- `plugins/code_execution/tools/code_execution_tool.py` — read SSH from plugin config
- `plugins/memory/default_config.yaml` — add `memory_subdir`
- `plugins/memory/helpers/memory.py` — read `memory_subdir` from plugin config
- `plugins/browser/default_config.yaml` — add `browser_http_headers`
- `plugins/browser/tools/browser_agent.py` — read headers from plugin config
- `extensions/python/system_prompt/_10_system_prompt.py` — use model_config helper
- `extensions/python/message_loop_prompts_after/_70_include_agent_info.py` — use model_config helper
- `extensions/python/monologue_start/_60_rename_chat.py` — use model_config helper
- `extensions/python/agent_init/_15_load_profile_settings.py` — remove model field rewiring
- `helpers/settings.py` — move model settings to model_config plugin defaults
- `tests/test_agent.py` — update AgentConfig fixture
- `tests/test_initialize.py` — update assertions
- `tests/conftest.py` — update mock config
- `tests/extensions/test_system_prompt.py` — update mocks
- `tests/extensions/test_prompt_after.py` — update mocks
- `tests/extensions/test_monologue.py` — update mocks
- `tests/extensions/test_agent_init.py` — update mocks
- `tests/tools/test_browser_agent.py` — update mocks
- `tests/tools/test_code_execution_tool.py` — update mocks
- `tests/helpers/test_memory.py` — update mocks
- `tests/helpers/test_webui_performance.py` — update mocks

---

## Task 1: Create `_model_config` Plugin

**Files:**
- Create: `plugins/model_config/plugin.yaml`
- Create: `plugins/model_config/default_config.yaml`
- Create: `plugins/model_config/helpers/model_config.py`
- Create: `plugins/model_config/extensions/python/_functions/agent/Agent/get_chat_model/start/_10_model_config.py`
- Create: `plugins/model_config/extensions/python/_functions/agent/Agent/get_utility_model/start/_10_model_config.py`
- Create: `plugins/model_config/extensions/python/_functions/agent/Agent/get_embedding_model/start/_10_model_config.py`
- Create: `tests/plugins/test_model_config.py`

- [ ] **Step 1:** Create plugin manifest and default config
- [ ] **Step 2:** Create `helpers/model_config.py` with `get_config()`, `get_chat_model_config()`, `get_utility_model_config()`, `get_embedding_model_config()`, `build_model_config()`, `build_chat_model()`, `build_utility_model()`, `build_embedding_model()`
- [ ] **Step 3:** Create extension hooks for `get_chat_model`, `get_utility_model`, `get_embedding_model`
- [ ] **Step 4:** Write tests for `model_config.py` helpers
- [ ] **Step 5:** Run tests, commit

## Task 2: Slim AgentConfig and Agent Accessor Methods

**Files:**
- Modify: `agent.py:348-367` (AgentConfig), `agent.py:809-843` (get_*_model)

- [ ] **Step 1:** Remove model fields, SSH fields, `memory_subdir`, `browser_http_headers` from `AgentConfig` — keep only `mcp_servers`, `profile`, `knowledge_subdirs`, `additional`
- [ ] **Step 2:** Change `get_chat_model()`, `get_utility_model()`, `get_browser_model()`, `get_embedding_model()` to return `None` (extension hooks inject the model)
- [ ] **Step 3:** Commit

## Task 3: Update `initialize.py`

**Files:**
- Modify: `initialize.py`

- [ ] **Step 1:** Remove model config construction (chat_llm, utility_llm, embedding_llm, browser_llm) from `initialize_agent()`
- [ ] **Step 2:** Remove model fields from `AgentConfig(...)` constructor call
- [ ] **Step 3:** Remove SSH fields from `_set_runtime_config()` (they move to plugin config)
- [ ] **Step 4:** Remove `browser_http_headers` from constructor
- [ ] **Step 5:** Commit

## Task 4: Migrate SSH Config to `_code_execution` Plugin

**Files:**
- Create: `plugins/code_execution/default_config.yaml`
- Modify: `plugins/code_execution/tools/code_execution_tool.py`
- Modify: `helpers/settings.py` (move SSH runtime config to plugin)

- [ ] **Step 1:** Create `default_config.yaml` with SSH defaults (enabled, addr, port, user, pass)
- [ ] **Step 2:** Update `code_execution_tool.py` to read SSH settings from `plugins.get_plugin_config("code_execution")` instead of `self.agent.config.code_exec_ssh_*`
- [ ] **Step 3:** Update `settings.py` `get_runtime_config()` — SSH settings go into code_execution plugin config
- [ ] **Step 4:** Commit

## Task 5: Migrate `memory_subdir` to `_memory` Plugin

**Files:**
- Create: `plugins/memory/default_config.yaml`
- Modify: `plugins/memory/helpers/memory.py`

- [ ] **Step 1:** Create `default_config.yaml` with `memory_subdir: "default"`
- [ ] **Step 2:** Update `memory.py` `get_context_memory_subdir()` to read from `plugins.get_plugin_config("memory")` instead of `context.config.memory_subdir`
- [ ] **Step 3:** Commit

## Task 6: Migrate `browser_http_headers` to `_browser` Plugin

**Files:**
- Create: `plugins/browser/default_config.yaml`
- Modify: `plugins/browser/tools/browser_agent.py`

- [ ] **Step 1:** Create `default_config.yaml` with `http_headers: {}`
- [ ] **Step 2:** Update `browser_agent.py` to read `extra_http_headers` from plugin config
- [ ] **Step 3:** Commit

## Task 7: Update Extension Consumers

**Files:**
- Modify: `extensions/python/system_prompt/_10_system_prompt.py`
- Modify: `extensions/python/message_loop_prompts_after/_70_include_agent_info.py`
- Modify: `extensions/python/monologue_start/_60_rename_chat.py`
- Modify: `extensions/python/agent_init/_15_load_profile_settings.py`

- [ ] **Step 1:** `_10_system_prompt.py` — replace `agent.config.chat_model.vision` with `model_config.get_chat_model_config(agent).get("vision", False)`
- [ ] **Step 2:** `_70_include_agent_info.py` — replace `agent.config.chat_model.provider/name` with `model_config.get_chat_model_config(agent)`
- [ ] **Step 3:** `_60_rename_chat.py` — replace `agent.config.utility_model.ctx_length` with `model_config.get_utility_model_config(agent).get("ctx_length", 128000)`
- [ ] **Step 4:** `_15_load_profile_settings.py` — remove model field rewiring (model config now in plugin)
- [ ] **Step 5:** Commit

## Task 8: Update All Tests

**Files:** All test files referencing removed AgentConfig fields

- [ ] **Step 1:** `tests/test_agent.py` — update `mock_agent_config` fixture to only have 4 fields, update model accessor tests
- [ ] **Step 2:** `tests/test_initialize.py` — update assertions (config no longer has model fields)
- [ ] **Step 3:** `tests/conftest.py` — update mock config
- [ ] **Step 4:** `tests/extensions/test_system_prompt.py`, `test_prompt_after.py`, `test_monologue.py`, `test_agent_init.py` — mock `model_config` helper instead of `agent.config.*`
- [ ] **Step 5:** `tests/tools/test_browser_agent.py`, `test_code_execution_tool.py` — mock plugin config
- [ ] **Step 6:** `tests/helpers/test_memory.py`, `test_webui_performance.py` — update mocks
- [ ] **Step 7:** Run full test suite, fix any remaining failures
- [ ] **Step 8:** Commit

## Task 9: Verification

- [ ] **Step 1:** Run `python3 -m pytest tests/ -x -q --timeout=30` — all tests pass
- [ ] **Step 2:** Docker build and run with UI verification (per `.cursor/rules/docker-verification.mdc`)
- [ ] **Step 3:** Verify model switching works (chat, utility, embedding)
- [ ] **Step 4:** Verify memory save/recall
- [ ] **Step 5:** Create PR

---

## Risk Notes

- **A4 is highest-risk item** in Phase 3 — model config touches many call sites
- Extensions reading `agent.config.chat_model.*` must ALL be migrated — any missed reference = AttributeError at runtime
- `persist_chat.py` does NOT serialize AgentConfig (confirmed) — safe to slim
- Settings UI reads from settings system, not AgentConfig directly — should still work after migration
- `browser_model` has no `_functions/` extension in upstream (browser plugin uses a different path) — we keep `get_browser_model()` returning `None` and let the browser plugin handle it directly
