# Plugin Rename to Upstream Convention — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename all plugin directories and references to match upstream's `_` prefix convention for built-in plugins.

**Architecture:** Batch rename of 18 plugin directories + mass find-replace of all Python imports, string references, plugin.yaml name fields, and test mocks. Single atomic commit.

**Tech Stack:** Python, bash (mv), rg/grep for verification

---

## Rename Map

| Current (fork) | Target (upstream) | Notes |
|----------------|-------------------|-------|
| `browser` | `_browser_agent` | Full rename (upstream name) |
| `chat_branching` | `_chat_branching` | Prefix only |
| `code_execution` | `_code_execution` | Prefix only |
| `error_retry` | `_error_retry` | Prefix only |
| `infection_check` | `_infection_check` | Prefix only |
| `memory` | `_memory` | Prefix only |
| `model_config` | `_model_config` | Prefix only |
| `plugin_installer` | `_plugin_installer` | Prefix only |
| `plugin_scan` | `_plugin_scan` | Prefix only |
| `text_editor` | `_text_editor` | Prefix only |
| `a2a` | `_a2a` | Fork-only, add prefix |
| `document_query` | `_document_query` | Fork-only, add prefix |
| `example_agent` | `_example_agent` | Fork-only, add prefix |
| `notifications` | `_notifications` | Fork-only, add prefix |
| `scheduler` | `_scheduler` | Fork-only, add prefix |
| `search` | `_search` | Fork-only, add prefix |
| `skills` | `_skills` | Fork-only, add prefix |
| `vision` | `_vision` | Fork-only, add prefix |

## Affected Reference Types

1. **Python imports:** `from plugins.memory.` → `from plugins._memory.`
2. **String references in get_plugin_config/find_plugin_dir:** `"memory"` → `"_memory"`
3. **plugin.yaml `name:` field:** `model_config` → `_model_config`
4. **Test mock paths:** `plugins.memory.helpers.memory` → `plugins._memory.helpers.memory`
5. **helpers/plugins.py:** `startswith("_")` logic for built-in detection (already correct after rename)

---

### Task 1: Rename plugin directories

**Files:**
- Rename: all 18 directories under `plugins/`

- [ ] **Step 1: Rename all directories**

```bash
cd /path/to/worktree
mv plugins/browser plugins/_browser_agent
mv plugins/chat_branching plugins/_chat_branching
mv plugins/code_execution plugins/_code_execution
mv plugins/error_retry plugins/_error_retry
mv plugins/infection_check plugins/_infection_check
mv plugins/memory plugins/_memory
mv plugins/model_config plugins/_model_config
mv plugins/plugin_installer plugins/_plugin_installer
mv plugins/plugin_scan plugins/_plugin_scan
mv plugins/text_editor plugins/_text_editor
mv plugins/a2a plugins/_a2a
mv plugins/document_query plugins/_document_query
mv plugins/example_agent plugins/_example_agent
mv plugins/notifications plugins/_notifications
mv plugins/scheduler plugins/_scheduler
mv plugins/search plugins/_search
mv plugins/skills plugins/_skills
mv plugins/vision plugins/_vision
```

- [ ] **Step 2: Verify directories renamed**

```bash
ls plugins/ | grep -v "^_" | grep -v README
```

Expected: empty (all dirs start with `_`)

---

### Task 2: Update all Python imports and string references

**Files:** ~130 Python files across `helpers/`, `api/`, `plugins/`, `extensions/`, `tests/`

- [ ] **Step 1: Replace Python import/from references**

For each rename pair, run find-replace across ALL `.py` files:

```
plugins.browser.    → plugins._browser_agent.
plugins.browser"    → plugins._browser_agent"
"browser"           → "_browser_agent" (only in get_plugin_config/find_plugin_dir calls)

plugins.memory.     → plugins._memory.
plugins.model_config. → plugins._model_config.
plugins.code_execution. → plugins._code_execution.
plugins.search.     → plugins._search.
plugins.skills.     → plugins._skills.
plugins.scheduler.  → plugins._scheduler.
plugins.notifications. → plugins._notifications.
plugins.vision.     → plugins._vision.
plugins.document_query. → plugins._document_query.
plugins.a2a.        → plugins._a2a.
plugins.error_retry. → plugins._error_retry.
plugins.chat_branching. → plugins._chat_branching.
plugins.infection_check. → plugins._infection_check.
plugins.plugin_installer. → plugins._plugin_installer.
plugins.plugin_scan. → plugins._plugin_scan.
plugins.text_editor. → plugins._text_editor.
plugins.example_agent. → plugins._example_agent.
```

- [ ] **Step 2: Update string-based plugin name references**

Files with `get_plugin_config("name")` or `find_plugin_dir("name")`:
- `plugins/_code_execution/tools/code_execution_tool.py` — `"code_execution"` → `"_code_execution"`
- `plugins/_browser_agent/tools/browser_agent.py` — `"browser"` → `"_browser_agent"`
- `plugins/_error_retry/extensions/.../_80_error_retry.py` — `"error_retry"` → `"_error_retry"`
- `plugins/_infection_check/extensions/.../_80_infection_check.py` — `"infection_check"` → `"_infection_check"`
- `plugins/_model_config/helpers/model_config.py` — `"model_config"` → `"_model_config"`
- `api/plugins.py` — any hardcoded plugin names
- `run_ui.py` — any hardcoded plugin names

---

### Task 3: Update plugin.yaml files

- [ ] **Step 1: Add/update `name:` field in all plugin.yaml files**

Every `plugin.yaml` should have `name: _<dirname>` matching the directory name.

---

### Task 4: Update helpers/plugins.py

- [ ] **Step 1: Update `refresh_plugin_modules` to use upstream logic**

The upstream version uses `startswith("_")` to distinguish built-in vs user plugins. After our rename, this logic will work correctly.

---

### Task 5: Verify

- [ ] **Step 1: Run grep for old names**

```bash
rg 'plugins\.(browser|memory|model_config|code_execution|search|skills|scheduler|notifications|vision|document_query|a2a|error_retry|chat_branching|infection_check|plugin_installer|plugin_scan|text_editor|example_agent)\b' --glob '*.py'
```

Expected: 0 results

- [ ] **Step 2: Run full test suite**

```bash
python3 -m pytest --tb=short
```

Expected: all tests pass

- [ ] **Step 3: Docker verification**

Build, run, verify UI loads, chats visible, no errors in logs.

- [ ] **Step 4: Commit and push**
