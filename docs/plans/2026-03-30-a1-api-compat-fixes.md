# A1 API Compatibility Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all A1 API-compatibility gaps identified in the review so that upstream plugins, extensions, and WebUI components work without modification.

**Architecture:** Align our `api/plugins.py`, `helpers/plugins.py`, and `agent.py` with upstream `origin/development` API surface. No new infrastructure modules (watchdog, modules, functions) — those are deferred to A3.

**Tech Stack:** Python, pytest, upstream `origin/development` as reference

**Branch:** `upstream/a1-plugin-system` (existing PR #29)

**Upstream ref:** `origin/development` HEAD (`1b89a0d3`)

---

## Deferred to A3

These items require new infrastructure modules and are explicitly out of scope:

- `helpers/modules.py` (purge_namespace, refactored import_module)
- `helpers/watchdog.py` (file system watcher)
- `helpers/functions.py` (safe_call)
- `register_watchdogs()` in plugins.py
- `register_extensions_watchdogs()` in extension.py
- `_log_extension_call()` in extension.py
- `refresh_plugin_modules()` in plugins.py
- `get_custom_plugins_updates()` in plugins.py
- `_apply_defaults_from_env()` in plugins.py
- `validate_tool_request()` in agent.py

---

### Task 1: Restructure `api/plugins.py` to per-method `@extensible`

Upstream uses individual `@extensible`-decorated methods dispatched from `process()`. Our implementation uses inline `if/elif` blocks in `process()` with no `@extensible` hooks. This breaks upstream extensions that target `_get_config_start`/`_get_config_end` etc.

Also fixes API action naming: `run_init_script` → `run_execute_script`, `get_init_exec` → `get_execute_record`, `initialize.py` → `execute.py`, `init_exec.json` → `execute_record.json`.

**Files:**
- Modify: `api/plugins.py`
- Test: `tests/api/test_plugins_api.py` (create if needed)

- [ ] **Step 1: Rewrite `api/plugins.py` to match upstream structure**

Replace the monolithic `process()` with upstream's dispatch-to-methods pattern. Each action gets its own `@extensible`-decorated private method. Keep our extras (`list`, `uninstall`, `toggle` backward compat alias) as additional methods.

```python
import json
import subprocess
import sys
from datetime import datetime, timezone

from helpers.api import ApiHandler, Request, Response
from helpers import plugins, files, extension


class Plugins(ApiHandler):
    """Core plugin management API."""

    async def process(self, input: dict, request: Request) -> dict | Response:
        action = input.get("action", "")

        if action == "list":
            return self._list(input)
        if action == "get_config":
            return self._get_config(input)
        if action == "get_toggle_status":
            return self._get_toggle_status(input)
        if action == "list_configs":
            return self._list_configs(input)
        if action == "delete_config":
            return self._delete_config(input)
        if action == "delete_plugin":
            return self._delete_plugin(input)
        if action == "get_default_config":
            return self._get_default_config(input)
        if action == "save_config":
            return self._save_config(input)
        if action == "toggle_plugin":
            return self._toggle_plugin(input)
        if action == "toggle":
            return self._toggle_plugin(input)
        if action == "uninstall":
            return self._uninstall(input)
        if action == "get_doc":
            return self._get_doc(input)
        if action == "run_execute_script":
            return self._run_execute_script(input)
        if action == "get_execute_record":
            return self._get_execute_record(input)

        return Response(status=400, response=f"Unknown action: {action}")

    @extension.extensible
    def _list(self, input: dict) -> dict | Response:
        custom = input.get("custom", True)
        builtin = input.get("builtin", True)
        items = plugins.get_enhanced_plugins_list(custom=custom, builtin=builtin)
        return {"ok": True, "plugins": [item.model_dump() for item in items]}

    @extension.extensible
    def _get_config(self, input: dict) -> dict | Response:
        plugin_name = input.get("plugin_name", "")
        project_name = input.get("project_name", "")
        agent_profile = input.get("agent_profile", "")
        if not plugin_name:
            return Response(status=400, response="Missing plugin_name")
        result = plugins.find_plugin_assets(
            plugins.CONFIG_FILE_NAME,
            plugin_name=plugin_name,
            project_name=project_name,
            agent_profile=agent_profile,
            only_first=True,
        )
        if result:
            entry = result[0]
            path = entry.get("path", "")
            settings = files.read_file_json(path) if path else {}
            loaded_project_name = entry.get("project_name", "")
            loaded_agent_profile = entry.get("agent_profile", "")
        else:
            settings = plugins.get_plugin_config(plugin_name, agent=None) or {}
            plugin_dir = plugins.find_plugin_dir(plugin_name)
            default_path = (
                files.get_abs_path(plugin_dir, plugins.CONFIG_DEFAULT_FILE_NAME)
                if plugin_dir
                else ""
            )
            path = default_path if default_path and files.exists(default_path) else ""
            loaded_project_name = ""
            loaded_agent_profile = ""
        return {
            "ok": True,
            "loaded_path": path,
            "loaded_project_name": loaded_project_name,
            "loaded_agent_profile": loaded_agent_profile,
            "data": settings,
        }

    @extension.extensible
    def _get_toggle_status(self, input: dict) -> dict | Response:
        # ... (keep exact current logic from get_toggle_status action)
        pass

    @extension.extensible
    def _list_configs(self, input: dict) -> dict | Response:
        # ... (keep exact current logic)
        pass

    @extension.extensible
    def _delete_config(self, input: dict) -> dict | Response:
        # ... (keep current logic with files.delete_file fix)
        pass

    @extension.extensible
    def _delete_plugin(self, input: dict) -> dict | Response:
        # ... (keep current logic)
        pass

    @extension.extensible
    def _get_default_config(self, input: dict) -> dict | Response:
        # ... (keep current logic)
        pass

    @extension.extensible
    def _save_config(self, input: dict) -> dict | Response:
        # ... (keep current logic)
        pass

    @extension.extensible
    def _toggle_plugin(self, input: dict) -> dict | Response:
        # ... (merge toggle + toggle_plugin logic, use upstream's validation)
        pass

    @extension.extensible
    def _uninstall(self, input: dict) -> dict | Response:
        # ... (keep current logic)
        pass

    @extension.extensible
    def _get_doc(self, input: dict) -> dict | Response:
        # ... (keep current logic)
        pass

    @extension.extensible
    def _run_execute_script(self, input: dict) -> dict | Response:
        # Renamed from run_init_script. Uses execute.py, execute_record.json
        pass

    @extension.extensible
    def _get_execute_record(self, input: dict) -> dict | Response:
        # Renamed from get_init_exec. Uses execute_record.json
        pass
```

Key changes from current code:
1. Add `from helpers import extension` import
2. Each `if action ==` block becomes a method call in `process()`
3. Each action method is `@extension.extensible`
4. Rename `run_init_script` → `run_execute_script` (action name AND method)
5. Rename `get_init_exec` → `get_execute_record` (action name AND method)
6. Script filename: `initialize.py` → `execute.py`
7. Record filename: `init_exec.json` → `execute_record.json`
8. Remove old `toggle` action as separate block — route it to `_toggle_plugin`
9. Match upstream's `_get_default_config` return: `{"ok": True, "data": settings or {}}` (note `or {}`)
10. Match upstream's `_delete_config` using `os.remove` (upstream does this) — but keep our `files.delete_file` improvement

- [ ] **Step 2: Update tests for api/plugins.py**

Update `tests/api/test_plugins_api.py` (or wherever plugin API tests live) to use the new action names `run_execute_script` and `get_execute_record`.

Run: `cd /Users/ivan/Documents/work/ai-girlfriend-project/ai-team/agent-zero && python -m pytest tests/api/test_plugins_api.py -v --import-mode=importlib 2>&1 | tail -20`

- [ ] **Step 3: Run affected tests and verify**

Run: `cd /Users/ivan/Documents/work/ai-girlfriend-project/ai-team/agent-zero && python -m pytest tests/api/ -v --import-mode=importlib 2>&1 | tail -30`

- [ ] **Step 4: Commit**

```bash
git add api/plugins.py tests/api/
git commit -m "refactor(a1): restructure api/plugins.py to per-method @extensible — match upstream"
```

---

### Task 2: Add `default` parameter to `call_plugin_hook()`

Upstream signature: `call_plugin_hook(plugin_name, hook_name, default=None, *args, **kwargs)`.
Ours is missing `default`. Callers that rely on a non-None default will get wrong behavior.

Note: upstream uses `functions.safe_call()` for error-safe invocation. Since `helpers/functions.py` is deferred to A3, we use a try/except wrapper instead.

**Files:**
- Modify: `helpers/plugins.py:638-674`

- [ ] **Step 1: Update `call_plugin_hook` signature and implementation**

```python
def call_plugin_hook(
    plugin_name: str, hook_name: str, default: Any = None, *args, **kwargs
):
    hooks = None

    if not cache.has(HOOKS_CACHE_AREA, plugin_name):
        plugin_dir = find_plugin_dir(plugin_name)
        if not plugin_dir:
            return default
        hooks_script = files.get_abs_path(plugin_dir, HOOKS_SCRIPT)
        hooks = (
            extract_tools.import_module(hooks_script)
            if files.exists(hooks_script)
            else None
        )
        cache.add(HOOKS_CACHE_AREA, plugin_name, hooks)
    else:
        hooks = cache.get(HOOKS_CACHE_AREA, plugin_name)

    if not hooks:
        return default

    hook = getattr(hooks, hook_name, None)
    if not hook:
        return default

    try:
        if asyncio.iscoroutinefunction(hook):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                import nest_asyncio
                nest_asyncio.apply(loop)
                return loop.run_until_complete(hook(*args, **kwargs))
            else:
                return asyncio.run(hook(*args, **kwargs))

        return hook(*args, **kwargs)
    except Exception:
        return default
```

Changes:
1. Add `default: Any = None` parameter (3rd positional, before *args)
2. Return `default` instead of `None` when plugin_dir not found, hooks not loaded, or hook not found
3. Wrap hook call in try/except, return `default` on error (lightweight safe_call substitute)

- [ ] **Step 2: Verify no callers break**

Existing callers don't pass `default=` so they get `None` (same as before). Search for all `call_plugin_hook` usages and confirm.

Run: `cd /Users/ivan/Documents/work/ai-girlfriend-project/ai-team/agent-zero && grep -rn "call_plugin_hook" --include="*.py" | grep -v __pycache__`

- [ ] **Step 3: Commit**

```bash
git add helpers/plugins.py
git commit -m "fix(a1): add default parameter to call_plugin_hook — match upstream signature"
```

---

### Task 3: Fix `clear_plugin_cache` and `after_plugin_change` parameter signatures

Upstream `clear_plugin_cache(plugin_names)` takes an optional list for targeted cache invalidation.
Upstream `after_plugin_change(plugin_names, python_change=False)` has `python_change` which triggers `refresh_plugin_modules()`. Since `refresh_plugin_modules` is deferred to A3, we accept the param but don't act on it yet.

**Files:**
- Modify: `helpers/plugins.py:87-93`

- [ ] **Step 1: Update signatures**

```python
def after_plugin_change(plugin_names: list[str] | None = None, python_change: bool = False):
    clear_plugin_cache(plugin_names)
    # TODO(a3): if python_change: refresh_plugin_modules(plugin_names)
    send_frontend_reload_notification(plugin_names)


def clear_plugin_cache(plugin_names: list[str] | None = None):
    areas = ["*(plugins)*", "*(extensions)*", "*(api)*"]
    for area in areas:
        cache.clear(area)
```

Changes:
1. `after_plugin_change`: add `python_change: bool = False` parameter, add TODO(a3) for refresh_plugin_modules
2. `clear_plugin_cache`: add `plugin_names: list[str] | None = None` parameter, expand cache clear to match upstream areas

- [ ] **Step 2: Commit**

```bash
git add helpers/plugins.py
git commit -m "fix(a1): align clear_plugin_cache/after_plugin_change signatures with upstream"
```

---

### Task 4: Add `handle_exception` method to `Agent` and `AgentContext`

Upstream has `@extensible async def handle_exception(self, location, exception)` on both `AgentContext` (line ~155) and `Agent` (line ~813). This is the hook that extensions (like `error_retry`) use to intercept exceptions. Our code uses `handle_critical_exception()` instead, which is not extensible.

**Files:**
- Modify: `agent.py`
- Modify: `tests/test_agent.py` (if handle_exception tests exist)

- [ ] **Step 1: Add `handle_exception` to `AgentContext`**

Add after `_process_chain` method (around line 335), before the `except Exception as e` block that currently calls `handle_critical_exception`:

```python
    @extensible
    async def handle_exception(self, location: str, exception: Exception):
        if exception:
            raise exception
```

Update `_process_chain` to call `await self.handle_exception("process_chain", e)` instead of `agent.handle_critical_exception(e)`.

- [ ] **Step 2: Add `handle_exception` to `Agent`**

Add near `handle_critical_exception` (around line 660):

```python
    @extensible
    async def handle_exception(self, location: str, exception: Exception):
        if exception:
            raise exception
```

This provides the extensible hook. The existing `handle_critical_exception` remains as our fork's implementation for non-extensible paths.

- [ ] **Step 3: Run agent tests**

Run: `cd /Users/ivan/Documents/work/ai-girlfriend-project/ai-team/agent-zero && python -m pytest tests/test_agent.py -v --import-mode=importlib 2>&1 | tail -30`

- [ ] **Step 4: Commit**

```bash
git add agent.py
git commit -m "feat(a1): add @extensible handle_exception to Agent/AgentContext — match upstream"
```

---

### Task 5: Fix remaining intra-plugin shim imports

4 plugin files import from backward-compat shims instead of their own plugin module paths. Fix to use direct imports.

**Files:**
- Modify: `plugins/code_execution/helpers/shell_local.py`
- Modify: `plugins/code_execution/tools/code_execution_tool.py`
- Modify: `plugins/document_query/tools/document_query.py`

- [ ] **Step 1: Fix `plugins/code_execution/helpers/shell_local.py`**

```python
# Before:
from helpers.shell_ssh import clean_string
# After:
from plugins.code_execution.helpers.shell_ssh import clean_string
```

- [ ] **Step 2: Fix `plugins/code_execution/tools/code_execution_tool.py`**

```python
# Before:
from helpers.shell_local import LocalInteractiveSession
from helpers.shell_ssh import SSHInteractiveSession
# After:
from plugins.code_execution.helpers.shell_local import LocalInteractiveSession
from plugins.code_execution.helpers.shell_ssh import SSHInteractiveSession
```

- [ ] **Step 3: Fix `plugins/document_query/tools/document_query.py`**

```python
# Before:
from helpers.document_query import DocumentQueryHelper
# After:
from plugins.document_query.helpers.document_query import DocumentQueryHelper
```

- [ ] **Step 4: Update any test patch targets that reference these old paths**

Search for `patch` calls targeting `helpers.shell_local`, `helpers.shell_ssh`, `helpers.document_query` in test files that test these specific plugin modules.

Run: `cd /Users/ivan/Documents/work/ai-girlfriend-project/ai-team/agent-zero && grep -rn "helpers\.shell_local\|helpers\.shell_ssh\|helpers\.document_query" tests/ --include="*.py" | grep -v __pycache__`

- [ ] **Step 5: Run affected tests**

Run: `cd /Users/ivan/Documents/work/ai-girlfriend-project/ai-team/agent-zero && python -m pytest tests/helpers/test_code_execution*.py tests/helpers/test_docker*.py -v --import-mode=importlib 2>&1 | tail -30`

- [ ] **Step 6: Commit**

```bash
git add plugins/code_execution/ plugins/document_query/
git commit -m "fix(a1): switch last 4 intra-plugin imports from shims to direct paths"
```

---

### Task 6: Full test suite + verification

- [ ] **Step 1: Run the full test suite**

Run: `cd /Users/ivan/Documents/work/ai-girlfriend-project/ai-team/agent-zero && python -m pytest tests/ -x --import-mode=importlib 2>&1 | tail -50`

Expected: all tests pass (2556+, 0 failures)

- [ ] **Step 2: Fix any failures**

If tests fail, investigate and fix. Common causes:
- `patch()` targets pointing to old import paths
- New `@extensible` methods changing mock behavior
- Changed action names in API test fixtures

- [ ] **Step 3: Update plan document with verification results**

Update `docs/plans/2026-03-29-a1-plugin-system.md` verification checklist with the resolved gaps.

- [ ] **Step 4: Final commit and push**

```bash
git add -A
git commit -m "fix(a1): all API compat gaps resolved — full test suite passes"
git push origin upstream/a1-plugin-system
```

---

## Verification Commands

After all tasks, verify upstream alignment:

```bash
# api/plugins.py actions should now match upstream
diff <(git show upstream/development:api/plugins.py | grep "action ==" | sort) \
     <(grep "action ==" api/plugins.py | sort)

# api/plugins.py @extensible count should be 11+ (upstream has 11)
grep -c "@extension.extensible" api/plugins.py

# call_plugin_hook signature should have default param
grep "def call_plugin_hook" helpers/plugins.py

# handle_exception should exist in agent.py
grep "def handle_exception" agent.py

# No intra-plugin shim imports for shell_local/shell_ssh/document_query
grep -rn "from helpers\.shell_local\|from helpers\.shell_ssh" plugins/ --include="*.py"
grep -rn "from helpers\.document_query" plugins/ --include="*.py"
```
