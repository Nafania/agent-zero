# A2: Path Restructuring — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the `python/` prefix from all module directories so `python.helpers` becomes `helpers`, `python.tools` becomes `tools`, etc. — aligning with upstream's v1.1 path structure.

**Architecture:** Scripted migration in 3 phases: directory moves, automated import rewriting (sed), manual fixups for dynamic path references. All existing tests serve as the verification suite (2400+ tests, 76% coverage).

**Tech Stack:** Python, bash (find/sed), pytest, git

**Spec:** `docs/specs/2026-03-28-upstream-backport-design.md` (Phase 1: A2)

---

### Task 1: Create Branch

**Files:**
- None (git operations only)

- [ ] **Step 1: Create branch from main**

```bash
cd /Users/ivan/Documents/work/ai-girlfriend-project/ai-team/agent-zero
git checkout main
git pull origin main
git checkout -b upstream/a2-path-restructure
```

- [ ] **Step 2: Verify clean state**

Run: `git status`
Expected: clean working tree, on branch `upstream/a2-path-restructure`

---

### Task 2: Move Directories

**Files:**
- Move: `python/helpers/` → `helpers/`
- Move: `python/tools/` → `tools/`
- Move: `python/api/` → `api/`
- Move: `python/extensions/` → `extensions/python/`
- Move: `python/websocket_handlers/` → `websocket_handlers/`
- Delete: `python/__init__.py`

- [ ] **Step 1: Move all directories**

```bash
git mv python/helpers helpers
git mv python/tools tools
git mv python/api api
mkdir -p extensions
git mv python/extensions extensions/python
git mv python/websocket_handlers websocket_handlers
git rm python/__init__.py
```

Note: `git mv` preserves history. If `python/__pycache__/` exists, remove it: `rm -rf python/__pycache__`

- [ ] **Step 2: Remove empty python/ directory**

```bash
rmdir python 2>/dev/null || rm -rf python/__pycache__ && rmdir python
```

- [ ] **Step 3: Verify new structure**

Run: `ls -d helpers/ tools/ api/ extensions/python/ websocket_handlers/`
Expected: all 5 directories listed, no errors

Run: `test -d python && echo "ERROR: python/ still exists" || echo "OK: python/ removed"`
Expected: `OK: python/ removed`

- [ ] **Step 4: Commit directory moves**

```bash
git add -A
git commit -m "refactor(a2): move python/* to top-level directories

python/helpers/ → helpers/
python/tools/ → tools/
python/api/ → api/
python/extensions/ → extensions/python/
python/websocket_handlers/ → websocket_handlers/
python/__init__.py removed

Imports will be fixed in next commit."
```

---

### Task 3: Rewrite All Python Imports (Automated)

**Files:**
- Modify: all `.py` files in `helpers/`, `tools/`, `api/`, `extensions/`, `websocket_handlers/`, `tests/`, and root (`agent.py`, `initialize.py`, `models.py`, `run_ui.py`, `prepare.py`, `scripts/`)

This task uses `find + sed` to do a global search-and-replace. The order matters — `python.extensions` must be replaced before shorter prefixes to avoid partial matches.

- [ ] **Step 1: Replace dot-imports in all .py files**

Run from repo root. macOS `sed` requires `-i ''`; Linux uses `-i`.

```bash
# Detect sed flavor
if sed --version 2>/dev/null | grep -q GNU; then SED_I="sed -i"; else SED_I="sed -i ''"; fi

# Order matters: longest prefix first to avoid partial replacement
# 1. python.websocket_handlers → websocket_handlers
find . -name '*.py' -not -path './.venv/*' -not -path './.worktrees/*' -not -path './.git/*' | \
  xargs $SED_I 's/python\.websocket_handlers/websocket_handlers/g'

# 2. python.extensions → extensions.python
find . -name '*.py' -not -path './.venv/*' -not -path './.worktrees/*' -not -path './.git/*' | \
  xargs $SED_I 's/python\.extensions/extensions.python/g'

# 3. python.helpers → helpers
find . -name '*.py' -not -path './.venv/*' -not -path './.worktrees/*' -not -path './.git/*' | \
  xargs $SED_I 's/python\.helpers/helpers/g'

# 4. python.tools → tools
find . -name '*.py' -not -path './.venv/*' -not -path './.worktrees/*' -not -path './.git/*' | \
  xargs $SED_I 's/python\.tools/tools/g'

# 5. python.api → api
find . -name '*.py' -not -path './.venv/*' -not -path './.worktrees/*' -not -path './.git/*' | \
  xargs $SED_I 's/python\.api/api/g'
```

- [ ] **Step 2: Verify no remaining dot-imports**

Run: `rg 'python\.(helpers|tools|api|extensions|websocket_handlers)' --glob '*.py' --glob '!.venv/**' --glob '!.worktrees/**' | head -20`
Expected: 0 results

If any remain, fix them manually.

- [ ] **Step 3: Commit import rewrites**

```bash
git add -A
git commit -m "refactor(a2): rewrite all python.* dot-imports to new paths"
```

---

### Task 4: Update String Path References

**Files:**
- Modify: `helpers/extension.py`
- Modify: `agent.py`
- Modify: `run_ui.py`
- Modify: `helpers/subagents.py` (if `default_root` usage needs updating)
- Modify: `.github/workflows/ci.yml`
- Modify: `tests/conftest.py`

These are string-based path references (not Python imports) that the sed in Task 3 won't catch.

- [ ] **Step 0: Clean stale bytecode**

After large directory moves, stale `__pycache__` dirs can cause confusing tracebacks:

```bash
find . -path './.venv' -prune -o -path './.worktrees' -prune -o -name '__pycache__' -type d -print | xargs rm -rf
```

- [ ] **Step 1: Update `helpers/extension.py`**

The extension loader has hardcoded paths. Change:

```python
# OLD
DEFAULT_EXTENSIONS_FOLDER = "python/extensions"

# NEW
DEFAULT_EXTENSIONS_FOLDER = "extensions/python"
```

And in `call_extensions()`:

```python
# OLD
paths = subagents.get_paths(agent, "extensions", extension_point, default_root="python")

# NEW
paths = subagents.get_paths(agent, "python", extension_point, default_root="extensions")
```

Verify: the constructed path should be `extensions/python/<extension_point>` (matching the new on-disk location).

- [ ] **Step 2: Update `agent.py` tool loading**

Find the tool loading call (around line 1046):

```python
# OLD
paths = subagents.get_paths(self, "tools", name + ".py", default_root="python")

# NEW
paths = subagents.get_paths(self, "tools", name + ".py", default_root="")
```

With `default_root=""`, `get_paths()` will construct `tools/<name>.py` (top-level).

Note: check `helpers/subagents.py` `get_paths()` to verify it handles empty `default_root` correctly. If it prepends a `/`, use `default_root="."` instead or adjust the function.

- [ ] **Step 3: Update `run_ui.py` folder paths**

Two string references to update (search for `"python/` to find exact lines):

```python
# OLD
handlers_folder="python/websocket_handlers",
# NEW
handlers_folder="websocket_handlers",
```

```python
# OLD
handlers = load_classes_from_folder("python/api", "*.py", ApiHandler)
# NEW
handlers = load_classes_from_folder("api", "*.py", ApiHandler)
```

- [ ] **Step 3b: Update `helpers/websocket_namespace_discovery.py`**

This file has a default argument referencing the old path:

```python
# OLD
def discover_websocket_namespaces(*, handlers_folder: str = "python/websocket_handlers", ...):
# NEW
def discover_websocket_namespaces(*, handlers_folder: str = "websocket_handlers", ...):
```

- [ ] **Step 4: Update `.github/workflows/ci.yml`**

Replace path triggers in **both** `push` and `pull_request` blocks:

```yaml
# OLD (push block)
paths: ['python/**', 'tests/**', 'requirements*.txt', 'agent.py', 'initialize.py', 'models.py', 'Dockerfile', 'docker/**', '.github/workflows/**']

# NEW (push block)
paths: ['helpers/**', 'tools/**', 'api/**', 'extensions/**', 'websocket_handlers/**', 'tests/**', 'requirements*.txt', 'agent.py', 'initialize.py', 'models.py', 'run_ui.py', 'prepare.py', 'Dockerfile', 'docker/**', '.github/workflows/**']
```

```yaml
# OLD (pull_request block)
paths: ['python/**', 'tests/**', 'requirements*.txt', '.github/workflows/**']

# NEW (pull_request block)
paths: ['helpers/**', 'tools/**', 'api/**', 'extensions/**', 'websocket_handlers/**', 'tests/**', 'requirements*.txt', 'agent.py', 'initialize.py', 'models.py', 'run_ui.py', 'prepare.py', '.github/workflows/**']
```

- [ ] **Step 5: Update `tests/conftest.py`**

```python
# OLD
with patch("python.helpers.settings.get_settings", return_value=mock_settings):

# NEW
with patch("helpers.settings.get_settings", return_value=mock_settings):
```

This should already be caught by Task 3 sed, but verify.

- [ ] **Step 6: Update string paths in docstrings and comments (all source + tests)**

Many files have docstrings/comments referencing `python/tools/`, `python/helpers/`, etc. Update in ALL `.py` files, not just tests:

```bash
find . -name '*.py' -not -path './.venv/*' -not -path './.worktrees/*' -not -path './.git/*' -not -path '*__pycache__*' | \
  xargs $SED_I 's|python/tools/|tools/|g; s|python/helpers/|helpers/|g; s|python/api/|api/|g; s|python/extensions/|extensions/python/|g; s|python/websocket_handlers/|websocket_handlers/|g'
```

- [ ] **Step 7: Scan for any remaining `python/` string references**

Run both quoted and unquoted patterns:

```bash
rg 'python/(helpers|tools|api|extensions|websocket_handlers)' --glob '*.py' --glob '!.venv/**' --glob '!.worktrees/**'
```

Expected: 0 results. Note: `extensions/python/` is **intentional** (new path) — don't flag those.

- [ ] **Step 8: Commit string path updates**

```bash
git add -A
git commit -m "refactor(a2): update string path references and dynamic loaders"
```

---

### Task 5: Verify `get_paths()` Compatibility

**Files:**
- Modify (if needed): `helpers/subagents.py`

- [ ] **Step 1: Read `helpers/subagents.py` `get_paths()` function**

Understand how it constructs paths from `default_root` and `subpaths`. Specifically:
- What happens when `default_root=""` (empty string)?
- Does `files.get_abs_path("", "tools", "code_execution_tool.py")` produce the correct path?

- [ ] **Step 2: Test path construction manually**

```bash
cd /Users/ivan/Documents/work/ai-girlfriend-project/ai-team/agent-zero
python3 -c "
from helpers.files import get_abs_path
# Tools path (default_root='')
print('tools path:', get_abs_path('', 'tools', 'code_execution_tool.py'))
print('tools path (no root):', get_abs_path('tools', 'code_execution_tool.py'))
# Extensions path (default_root='extensions')
print('ext path:', get_abs_path('extensions', 'python', 'agent_init'))
"
```

Expected: paths should resolve to existing files/directories.

- [ ] **Step 3: Fix `get_paths()` if needed**

If empty `default_root` produces wrong paths, either:
a) Change `default_root=""` to `default_root="."` in calling code, or
b) Add a guard in `get_paths()`:

```python
if default_root:
    path = files.get_abs_path(default_root, *subpaths)
else:
    path = files.get_abs_path(*subpaths)
```

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix(a2): handle empty default_root in get_paths()"
```

(Skip this commit if no changes were needed.)

---

### Task 6: Run Full Test Suite

**Files:**
- Modify: any files with remaining import errors

- [ ] **Step 1: Run tests**

```bash
pytest tests/ -m "not integration" -x -q --tb=short
```

Expected: all tests pass. If failures, read the error output and fix.

- [ ] **Step 2: Fix import errors (if any)**

Common issues:
- Missed `python.` references in mock patches (`patch("python.helpers.xxx")` → `patch("helpers.xxx")`)
- Relative imports that relied on `python` package
- `__init__.py` missing in new directories (check: `ls helpers/__init__.py tools/__init__.py api/__init__.py extensions/__init__.py extensions/python/__init__.py websocket_handlers/__init__.py`)

If `__init__.py` files are needed in new dirs, create empty ones:
```bash
touch extensions/__init__.py
```

- [ ] **Step 3: Re-run tests until green**

```bash
pytest tests/ -m "not integration" -x -q
```

Expected: `XXXX passed` with 0 failures.

- [ ] **Step 4: Commit any test fixes**

```bash
git add -A
git commit -m "fix(a2): resolve remaining import issues after path restructure"
```

(Skip if no fixes were needed.)

---

### Task 7: Update Documentation

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Update AGENTS.md architecture section**

The architecture diagram references `python/` paths. Update:

```
# OLD
├── python/
│   ├── api/
│   ├── extensions/
│   ├── helpers/
│   ├── tools/
│   └── websocket_handlers/

# NEW
├── helpers/              ← (was python/helpers/)
├── tools/                ← (was python/tools/)
├── api/                  ← (was python/api/)
├── extensions/
│   └── python/           ← (was python/extensions/)
├── websocket_handlers/   ← (was python/websocket_handlers/)
```

Also update any references to paths like `python/helpers/memory.py` → `helpers/memory.py` throughout the file.

- [ ] **Step 2: Search for other docs with stale paths**

```bash
rg 'python/(helpers|tools|api|extensions|websocket_handlers)' docs/ AGENTS.md README.md --glob '*.md' 2>/dev/null
```

Fix any found references.

- [ ] **Step 3: Commit doc updates**

```bash
git add -A
git commit -m "docs(a2): update path references in AGENTS.md and docs"
```

---

### Task 8: Final Verification

- [ ] **Step 1: Full grep verification**

```bash
# No remaining Python dot-imports to old paths
rg 'python\.(helpers|tools|api|extensions|websocket_handlers)' --glob '*.py' --glob '!.venv/**' --glob '!.worktrees/**'
# Expected: 0 results

# No remaining string path references
rg '"python/(helpers|tools|api|extensions|websocket_handlers)' --glob '*.py' --glob '!.venv/**' --glob '!.worktrees/**'
# Expected: 0 results

# No remaining CI references
rg "python/" .github/ --glob '*.yml'
# Expected: 0 results (only PYTHONPATH: . which is fine)
```

- [ ] **Step 2: Import smoke test**

```bash
cd /Users/ivan/Documents/work/ai-girlfriend-project/ai-team/agent-zero
PYTHONPATH=. python3 -c "
import helpers.files
import helpers.extension
import helpers.log
import tools.code_execution_tool
import api.health
import websocket_handlers.hello_handler
print('All imports OK')
"
```

Expected: `All imports OK`

- [ ] **Step 3: Full test suite (final run)**

```bash
pytest tests/ -m "not integration" -q
```

Expected: all tests pass, 0 failures.

- [ ] **Step 4: Verify git status is clean**

```bash
git status
git log --oneline -5
```

Expected: clean working tree, 3-5 commits on `upstream/a2-path-restructure` branch.

---

### Task 9: Create PR

- [ ] **Step 1: Push branch**

```bash
git push -u origin upstream/a2-path-restructure
```

- [ ] **Step 2: Create PR**

```bash
gh pr create --title "refactor: A2 path restructure — remove python/ prefix" --body "$(cat <<'EOF'
## Summary

Removes the `python/` prefix from all module directories, aligning with upstream v1.1 structure:

- `python/helpers/` → `helpers/`
- `python/tools/` → `tools/`
- `python/api/` → `api/`
- `python/extensions/` → `extensions/python/`
- `python/websocket_handlers/` → `websocket_handlers/`

3649 import references updated across 447 files. All tests pass.

## Part of

Upstream backport project — see `docs/specs/2026-03-28-upstream-backport-design.md` (Phase 1).

## Breaking Changes

- All worktree branches require rebase after merge
- All open PRs require rebase after merge
- Any external code importing `python.helpers.*` etc. must update imports

## Test plan

- [x] All 2400+ unit tests pass
- [x] Zero remaining `python.(helpers|tools|api|extensions|websocket_handlers)` references
- [x] Import smoke test from new paths
- [x] CI path triggers updated

EOF
)"
```

- [ ] **Step 3: Note PR URL for tracking**

Record the PR URL. After merge, all other branches will need rebasing.
