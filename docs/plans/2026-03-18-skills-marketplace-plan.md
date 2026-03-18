# Skills Marketplace Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the skills system with a marketplace backed by `npx skills` CLI, with catalog search in settings UI and automatic context-based skill activation in chats.

**Architecture:** `npx skills` CLI as backend for catalog search, install, remove, and update. Existing `python/helpers/skills.py` stays for disk-based SKILL.md parsing. New extension injects skill catalog into system prompt for auto-activation.

**Tech Stack:** Python 3.12+, Alpine.js (webui), `npx skills` CLI (Node.js), pytest

---

## Prerequisites

- Design doc: `docs/plans/2026-03-18-skills-marketplace-design.md`
- Current branch: `fix/cognee-cross-process-init` — must create new branch from `main`

---

### Task 0: Create feature branch

**Step 1: Create and switch to feature branch from main**

```bash
cd /Users/ivan/Documents/work/ai-girlfriend-project/ai-team/agent-zero
git checkout main
git pull origin main
git checkout -b feat/skills-marketplace
```

**Step 2: Cherry-pick the design doc commit**

```bash
git cherry-pick e218452f
```

If conflict, just `git add docs/plans/ && git cherry-pick --continue`.

**Step 3: Push branch**

```bash
git push -u origin feat/skills-marketplace
```

---

### Task 1: Rewrite `python/helpers/skills_cli.py` — npx wrapper

The current `skills_cli.py` is an old local CLI tool with `list_skills`, `create_skill`, `parse_skill_file`, etc. Replace it entirely with an async wrapper over `npx skills`.

**Files:**
- Rewrite: `python/helpers/skills_cli.py`
- Test: `tests/helpers/test_skills_cli.py` (rewrite)

**Step 1: Write failing tests for the npx wrapper**

File: `tests/helpers/test_skills_cli.py`

```python
"""Tests for python/helpers/skills_cli.py — npx skills CLI wrapper."""

import asyncio
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def mock_subprocess():
    """Mock asyncio.create_subprocess_exec."""
    with patch("python.helpers.skills_cli.asyncio.create_subprocess_exec") as mock_exec:
        process = AsyncMock()
        process.returncode = 0
        process.communicate = AsyncMock(return_value=(b"", b""))
        mock_exec.return_value = process
        yield mock_exec, process


# --- _run_npx ---

class TestRunNpx:
    @pytest.mark.asyncio
    async def test_runs_npx_with_args(self, mock_subprocess):
        from python.helpers.skills_cli import _run_npx
        mock_exec, process = mock_subprocess
        process.communicate.return_value = (b"output text", b"")

        result = await _run_npx("find", "python")
        assert result == "output text"
        mock_exec.assert_called_once()
        args = mock_exec.call_args[0]
        assert "npx" in args[0]
        assert "skills" in args
        assert "find" in args
        assert "python" in args

    @pytest.mark.asyncio
    async def test_raises_on_nonzero_exit(self, mock_subprocess):
        from python.helpers.skills_cli import _run_npx, SkillsCLIError
        _, process = mock_subprocess
        process.returncode = 1
        process.communicate.return_value = (b"", b"some error")

        with pytest.raises(SkillsCLIError, match="some error"):
            await _run_npx("find", "nonexistent")

    @pytest.mark.asyncio
    async def test_raises_on_timeout(self, mock_subprocess):
        from python.helpers.skills_cli import _run_npx, SkillsCLIError
        _, process = mock_subprocess
        process.communicate.side_effect = asyncio.TimeoutError()

        with pytest.raises(SkillsCLIError, match="timed out"):
            await _run_npx("add", "owner/repo", timeout=1)

    @pytest.mark.asyncio
    async def test_raises_when_npx_not_found(self, mock_subprocess):
        from python.helpers.skills_cli import _run_npx, SkillsCLIError
        mock_exec, _ = mock_subprocess
        mock_exec.side_effect = FileNotFoundError("npx not found")

        with pytest.raises(SkillsCLIError, match="Node.js"):
            await _run_npx("find", "test")


# --- parse_find_output ---

class TestParseFindOutput:
    def test_parses_skill_entries(self):
        from python.helpers.skills_cli import parse_find_output
        output = """brainstorming (obra/superpowers)
  Use before any creative work — creating features, building components
test-driven-development (obra/superpowers)
  Use when implementing any feature or bugfix"""

        results = parse_find_output(output)
        assert len(results) >= 2
        assert results[0]["name"] == "brainstorming"
        assert results[0]["source"] == "obra/superpowers"
        assert "creative work" in results[0]["description"]

    def test_returns_empty_for_no_results(self):
        from python.helpers.skills_cli import parse_find_output
        results = parse_find_output("No skills found matching 'xyznonexistent'")
        assert results == []

    def test_handles_empty_output(self):
        from python.helpers.skills_cli import parse_find_output
        assert parse_find_output("") == []


# --- find ---

class TestFind:
    @pytest.mark.asyncio
    async def test_find_returns_parsed_results(self, mock_subprocess):
        from python.helpers.skills_cli import find
        _, process = mock_subprocess
        process.communicate.return_value = (
            b"brainstorming (obra/superpowers)\n  Use before any creative work\n",
            b"",
        )

        results = await find("brainstorming")
        assert len(results) >= 1
        assert results[0]["name"] == "brainstorming"

    @pytest.mark.asyncio
    async def test_find_uses_cache(self, mock_subprocess):
        from python.helpers.skills_cli import find, _cache
        _cache.clear()
        _, process = mock_subprocess
        process.communicate.return_value = (b"skill1 (owner/repo)\n  desc\n", b"")

        r1 = await find("test-query")
        r2 = await find("test-query")
        assert r1 == r2
        # subprocess called only once due to cache
        assert mock_subprocess[0].call_count == 1
        _cache.clear()

    @pytest.mark.asyncio
    async def test_find_empty_query_returns_empty(self, mock_subprocess):
        from python.helpers.skills_cli import find
        results = await find("")
        assert results == []


# --- add ---

class TestAdd:
    @pytest.mark.asyncio
    async def test_add_calls_npx_skills_add(self, mock_subprocess):
        from python.helpers.skills_cli import add, _cache
        _cache.clear()
        _, process = mock_subprocess
        process.communicate.return_value = (b"Installed brainstorming", b"")

        result = await add("obra/superpowers")
        assert "Installed" in result
        args = mock_subprocess[0].call_args[0]
        assert "add" in args
        assert "obra/superpowers" in args

    @pytest.mark.asyncio
    async def test_add_clears_cache(self, mock_subprocess):
        from python.helpers.skills_cli import add, _cache
        _cache["old-query"] = ([], 0)
        _, process = mock_subprocess
        process.communicate.return_value = (b"ok", b"")

        await add("owner/repo")
        assert len(_cache) == 0


# --- remove ---

class TestRemove:
    @pytest.mark.asyncio
    async def test_remove_calls_npx_skills_remove(self, mock_subprocess):
        from python.helpers.skills_cli import remove, _cache
        _cache.clear()
        _, process = mock_subprocess
        process.communicate.return_value = (b"Removed skill", b"")

        result = await remove("brainstorming")
        args = mock_subprocess[0].call_args[0]
        assert "remove" in args


# --- check_updates ---

class TestCheckUpdates:
    @pytest.mark.asyncio
    async def test_check_calls_npx_skills_check(self, mock_subprocess):
        from python.helpers.skills_cli import check_updates
        _, process = mock_subprocess
        process.communicate.return_value = (b"All skills up to date", b"")

        result = await check_updates()
        assert isinstance(result, str)


# --- update ---

class TestUpdate:
    @pytest.mark.asyncio
    async def test_update_calls_npx_skills_update(self, mock_subprocess):
        from python.helpers.skills_cli import update
        _, process = mock_subprocess
        process.communicate.return_value = (b"Updated 2 skills", b"")

        result = await update()
        assert isinstance(result, str)
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/helpers/test_skills_cli.py -v
```

Expected: FAIL — module has old code, new functions don't exist.

**Step 3: Implement the npx wrapper**

File: `python/helpers/skills_cli.py` (complete rewrite)

```python
"""
Async wrapper over the `npx skills` CLI.

Provides: find, add, remove, check_updates, update.
Caches find results in memory with 1-hour TTL.
"""
from __future__ import annotations

import asyncio
import re
import time
from collections import OrderedDict
from typing import Any

CACHE_TTL = 3600  # 1 hour
CACHE_MAX = 50
TIMEOUT_FIND = 30
TIMEOUT_ADD = 60
TIMEOUT_DEFAULT = 30


class SkillsCLIError(Exception):
    pass


_cache: OrderedDict[str, tuple[list[dict[str, str]], float]] = OrderedDict()


async def _run_npx(*args: str, timeout: int = TIMEOUT_DEFAULT) -> str:
    cmd = ["npx", "skills", *args]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        raise SkillsCLIError(
            "Node.js/npx not found. Install Node.js to use Skills marketplace."
        )

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        proc.kill()
        raise SkillsCLIError(f"Command timed out after {timeout}s: {' '.join(cmd)}")

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="replace").strip()
        raise SkillsCLIError(err or f"npx skills exited with code {proc.returncode}")

    return stdout.decode("utf-8", errors="replace").strip()


def parse_find_output(output: str) -> list[dict[str, str]]:
    if not output or not output.strip():
        return []

    results: list[dict[str, str]] = []
    lines = output.strip().splitlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        m = re.match(r"^(.+?)\s*\(([^)]+)\)\s*$", line)
        if m:
            name = m.group(1).strip()
            source = m.group(2).strip()
            desc = ""
            if i + 1 < len(lines) and lines[i + 1].startswith("  "):
                desc = lines[i + 1].strip()
                i += 1
            results.append({"name": name, "source": source, "description": desc})
        i += 1

    return results


async def find(query: str) -> list[dict[str, str]]:
    query = (query or "").strip()
    if not query:
        return []

    now = time.monotonic()
    if query in _cache:
        results, ts = _cache[query]
        if now - ts < CACHE_TTL:
            _cache.move_to_end(query)
            return results

    output = await _run_npx("find", query, timeout=TIMEOUT_FIND)
    results = parse_find_output(output)

    _cache[query] = (results, now)
    _cache.move_to_end(query)
    while len(_cache) > CACHE_MAX:
        _cache.popitem(last=False)

    return results


async def add(source: str) -> str:
    source = (source or "").strip()
    if not source:
        raise SkillsCLIError("source is required")

    result = await _run_npx("add", source, timeout=TIMEOUT_ADD)
    _cache.clear()
    return result


async def remove(skill_name: str) -> str:
    skill_name = (skill_name or "").strip()
    if not skill_name:
        raise SkillsCLIError("skill_name is required")

    result = await _run_npx("remove", skill_name, timeout=TIMEOUT_DEFAULT)
    _cache.clear()
    return result


async def check_updates() -> str:
    return await _run_npx("check", timeout=TIMEOUT_DEFAULT)


async def update() -> str:
    result = await _run_npx("update", timeout=TIMEOUT_ADD)
    _cache.clear()
    return result
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/helpers/test_skills_cli.py -v
```

Expected: ALL PASS

**Step 5: Commit**

```bash
git add python/helpers/skills_cli.py tests/helpers/test_skills_cli.py
git commit -m "feat: rewrite skills_cli.py as async npx wrapper"
```

---

### Task 2: New API endpoint `/skills_catalog`

**Files:**
- Create: `python/api/skills_catalog.py`
- Test: `tests/api/test_skills_catalog.py`

**Step 1: Write failing tests**

File: `tests/api/test_skills_catalog.py`

```python
"""Tests for /skills_catalog API endpoint."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def mock_skills_cli():
    with patch("python.api.skills_catalog.skills_cli") as mock:
        mock.find = AsyncMock(return_value=[])
        mock.SkillsCLIError = type("SkillsCLIError", (Exception,), {})
        yield mock


class TestSkillsCatalog:
    @pytest.mark.asyncio
    async def test_search_returns_results(self, mock_skills_cli):
        from python.api.skills_catalog import SkillsCatalog

        mock_skills_cli.find.return_value = [
            {"name": "brainstorming", "source": "obra/superpowers", "description": "Use before creative work"},
        ]

        handler = SkillsCatalog()
        result = await handler.process({"query": "brainstorming"}, MagicMock())
        assert result["ok"] is True
        assert len(result["results"]) == 1
        assert result["results"][0]["name"] == "brainstorming"

    @pytest.mark.asyncio
    async def test_empty_query_returns_error(self, mock_skills_cli):
        from python.api.skills_catalog import SkillsCatalog

        handler = SkillsCatalog()
        result = await handler.process({"query": ""}, MagicMock())
        assert result["ok"] is False

    @pytest.mark.asyncio
    async def test_cli_error_returns_error(self, mock_skills_cli):
        from python.api.skills_catalog import SkillsCatalog

        mock_skills_cli.find.side_effect = Exception("npx not found")
        handler = SkillsCatalog()
        result = await handler.process({"query": "test"}, MagicMock())
        assert result["ok"] is False
        assert "npx" in result["error"]
```

**Step 2: Run tests — expect FAIL**

```bash
pytest tests/api/test_skills_catalog.py -v
```

**Step 3: Implement**

File: `python/api/skills_catalog.py`

```python
from __future__ import annotations

from python.helpers.api import ApiHandler, Input, Output, Request, Response
from python.helpers import skills_cli


class SkillsCatalog(ApiHandler):
    async def process(self, input: Input, request: Request) -> Output:
        query = (input.get("query") or "").strip()
        if not query:
            return {"ok": False, "error": "query is required"}

        try:
            results = await skills_cli.find(query)
            return {"ok": True, "results": results}
        except Exception as e:
            return {"ok": False, "error": str(e)}
```

**Step 4: Run tests — expect PASS**

```bash
pytest tests/api/test_skills_catalog.py -v
```

**Step 5: Register the endpoint**

Find where API routes are registered (likely `run_ui.py` or an api registry file) and add:

```python
from python.api.skills_catalog import SkillsCatalog
```

Register route: `"/skills_catalog"` → `SkillsCatalog`

**Step 6: Commit**

```bash
git add python/api/skills_catalog.py tests/api/test_skills_catalog.py
git commit -m "feat: add /skills_catalog API endpoint for marketplace search"
```

---

### Task 3: Refactor `skill_install.py` to use `npx skills add`

**Files:**
- Modify: `python/api/skill_install.py`
- Test: `tests/api/test_skill_install.py` (update)

**Step 1: Update tests**

Replace the git-clone tests with tests that verify `npx skills add` is called. Keep `_parse_source` tests since source parsing is still needed for validation.

Add new test:

```python
class TestInstallViaCLI:
    @pytest.mark.asyncio
    async def test_install_calls_skills_cli_add(self):
        with patch("python.api.skill_install.skills_cli") as mock_cli:
            mock_cli.add = AsyncMock(return_value="Installed brainstorming")

            handler = SkillInstall()
            result = await handler.process({"source": "obra/superpowers"}, MagicMock())
            assert result["ok"] is True
            mock_cli.add.assert_called_once_with("obra/superpowers")

    @pytest.mark.asyncio
    async def test_install_handles_cli_error(self):
        with patch("python.api.skill_install.skills_cli") as mock_cli:
            mock_cli.add = AsyncMock(side_effect=Exception("clone failed"))

            handler = SkillInstall()
            result = await handler.process({"source": "owner/repo"}, MagicMock())
            assert result["ok"] is False
```

**Step 2: Run tests — expect FAIL**

**Step 3: Refactor `skill_install.py`**

Replace the git clone logic with `skills_cli.add()`. Keep source validation. Remove `_find_skills`, `_resolve_target`, `_normalize_skill_md`, git subprocess calls.

```python
from __future__ import annotations

from python.helpers.api import ApiHandler, Input, Output, Request, Response
from python.helpers import skills_cli


class SkillInstall(ApiHandler):
    async def process(self, input: Input, request: Request) -> Output:
        source = (input.get("source") or "").strip()
        if not source:
            return {"ok": False, "error": "source is required"}

        try:
            output = await skills_cli.add(source)
            return {"ok": True, "output": output, "source": source}
        except skills_cli.SkillsCLIError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:
            return {"ok": False, "error": str(e)}
```

**Step 4: Run tests — expect PASS**

**Step 5: Commit**

```bash
git add python/api/skill_install.py tests/api/test_skill_install.py
git commit -m "refactor: skill_install uses npx skills add instead of git clone"
```

---

### Task 4: Add update/remove actions to skills API

**Files:**
- Modify: `python/api/skills.py`
- Test: `tests/api/test_skills.py` (update)

**Step 1: Write new tests**

Add tests for `update` and `check_updates` actions. Update `delete` tests to verify `npx skills remove` is called.

```python
class TestSkillsUpdate:
    @pytest.mark.asyncio
    async def test_check_updates(self):
        with patch("python.api.skills.skills_cli") as mock_cli:
            mock_cli.check_updates = AsyncMock(return_value="All up to date")
            handler = Skills()
            result = await handler.process({"action": "check_updates"}, MagicMock())
            assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_update_all(self):
        with patch("python.api.skills.skills_cli") as mock_cli:
            mock_cli.update = AsyncMock(return_value="Updated 2 skills")
            handler = Skills()
            result = await handler.process({"action": "update"}, MagicMock())
            assert result["ok"] is True
```

**Step 2: Run — expect FAIL**

**Step 3: Add actions to `skills.py`**

Add `check_updates` and `update` actions. Keep `list` and `delete` as-is (delete still uses disk-based removal via `skills.delete_skill` — this is fine since skills are stored locally).

**Step 4: Run — expect PASS**

**Step 5: Commit**

```bash
git add python/api/skills.py tests/api/test_skills.py
git commit -m "feat: add check_updates and update actions to /skills API"
```

---

### Task 5: New extension `_60_skills_catalog.py`

**Files:**
- Create: `python/extensions/message_loop_prompts_after/_60_skills_catalog.py`
- Create: `prompts/agent.system.skills.catalog.md`
- Test: `tests/extensions/test_skills_catalog_ext.py`

**Step 1: Write failing tests**

```python
"""Tests for _60_skills_catalog extension."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent.read_prompt.return_value = "formatted prompt"
    return agent


class TestSkillsCatalogExtension:
    @pytest.mark.asyncio
    async def test_injects_catalog_when_skills_exist(self, mock_agent):
        from python.helpers.skills import Skill
        mock_skills = [
            Skill(
                name="brainstorming",
                description="Use before creative work",
                path=Path("/x"),
                skill_md_path=Path("/x/SKILL.md"),
            ),
        ]
        with patch("python.extensions.message_loop_prompts_after._60_skills_catalog.skills.list_skills", return_value=mock_skills):
            from python.extensions.message_loop_prompts_after._60_skills_catalog import SkillsCatalogPrompt
            ext = SkillsCatalogPrompt.__new__(SkillsCatalogPrompt)
            ext.agent = mock_agent
            loop_data = MagicMock()
            loop_data.extras_persistent = {}
            await ext.execute(loop_data=loop_data)

            assert "available_skills" in loop_data.extras_persistent
            mock_agent.read_prompt.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_when_no_skills(self, mock_agent):
        with patch("python.extensions.message_loop_prompts_after._60_skills_catalog.skills.list_skills", return_value=[]):
            from python.extensions.message_loop_prompts_after._60_skills_catalog import SkillsCatalogPrompt
            ext = SkillsCatalogPrompt.__new__(SkillsCatalogPrompt)
            ext.agent = mock_agent
            loop_data = MagicMock()
            loop_data.extras_persistent = {}
            await ext.execute(loop_data=loop_data)

            assert "available_skills" not in loop_data.extras_persistent
```

**Step 2: Run — expect FAIL**

**Step 3: Create prompt template**

File: `prompts/agent.system.skills.catalog.md`

```markdown
# Installed skills
- use skills_tool method=load to activate a skill when relevant
- skill descriptions tell you WHEN to use each skill

{{skills}}
```

**Step 4: Implement extension**

File: `python/extensions/message_loop_prompts_after/_60_skills_catalog.py`

```python
from python.helpers.extension import Extension
from python.helpers import skills
from agent import LoopData


class SkillsCatalogPrompt(Extension):
    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        extras = loop_data.extras_persistent

        all_skills = skills.list_skills(agent=self.agent, include_content=False)
        if not all_skills:
            return

        lines = []
        for s in sorted(all_skills, key=lambda x: x.name.lower()):
            desc = (s.description or "").strip()
            if len(desc) > 200:
                desc = desc[:200].rstrip() + "…"
            lines.append(f"- **{s.name}**: {desc}")

        catalog_text = "\n".join(lines)

        extras["available_skills"] = self.agent.read_prompt(
            "agent.system.skills.catalog.md",
            skills=catalog_text,
        )
```

**Step 5: Run — expect PASS**

**Step 6: Update existing prompt `agent.system.skills.md`**

The old `agent.system.skills.md` prompt listed skills in the system prompt section. Now `_60_skills_catalog.py` handles this, so check if there's a duplicate extension that uses `agent.system.skills.md` and remove it or ensure no conflict. The `_60_` prefix ensures it runs before `_65_include_loaded_skills.py`.

**Step 7: Commit**

```bash
git add python/extensions/message_loop_prompts_after/_60_skills_catalog.py \
        prompts/agent.system.skills.catalog.md \
        tests/extensions/test_skills_catalog_ext.py
git commit -m "feat: add _60_skills_catalog extension for auto skill activation"
```

---

### Task 6: Replace Settings UI — Skills tab

**Files:**
- Rewrite: `webui/components/settings/skills/skills-settings.html`
- Delete: `webui/components/settings/skills/list.html`
- Delete: `webui/components/settings/skills/import.html`
- Rewrite: `webui/components/settings/skills/skills-list-store.js` → `skills-store.js`
- Delete: `webui/components/settings/skills/skills-install-store.js`

**Step 1: Delete old files**

```bash
rm webui/components/settings/skills/list.html
rm webui/components/settings/skills/import.html
rm webui/components/settings/skills/skills-install-store.js
```

**Step 2: Create unified store**

File: `webui/components/settings/skills/skills-store.js`

Replace `skills-list-store.js` with a unified store that handles:
- `searchCatalog(query)` → calls `/skills_catalog`
- `install(source)` → calls `/skill_install`
- `loadInstalled()` → calls `/skills` action=list
- `deleteSkill(skill)` → calls `/skills` action=delete
- `checkUpdates()` → calls `/skills` action=check_updates
- `updateAll()` → calls `/skills` action=update

State: `catalogResults`, `catalogLoading`, `catalogError`, `installed`, `installedLoading`, `searchQuery`, `directSource`, `installLoading`, `updateStatus`

Use `createStore("skillsStore", model)` pattern matching existing stores. Reference `skills-install-store.js` and `skills-list-store.js` for API call patterns (`fetchApi`, `callJsonApi`).

**Step 3: Create unified HTML**

File: `webui/components/settings/skills/skills-settings.html`

Two sections in one page:
1. **Catalog search** — search input, results list with Add buttons, direct install input
2. **Installed skills** — list with delete and update buttons

Follow the styling patterns from the existing `list.html` (`.skill-card`, `.skill-header`, etc.) and `import.html` (`.install-input-row`).

Reference: `webui/components/settings/settings.html` line 77 — the Skills tab already loads `settings/skills/skills-settings.html` via `x-component`.

**Step 4: Delete old list store**

```bash
rm webui/components/settings/skills/skills-list-store.js
```

**Step 5: Verify by visual inspection**

Open Agent Zero UI, go to Settings → Skills tab. Verify:
- Search field works and shows catalog results
- "Add" button installs a skill
- Installed skills list shows correctly
- Delete button works
- Check for updates works

**Step 6: Commit**

```bash
git add webui/components/settings/skills/
git commit -m "feat: replace Skills settings UI with marketplace search and management"
```

---

### Task 7: Docker — Add Node.js

**Files:**
- Modify: `Dockerfile` (or `docker/run/Dockerfile`)

**Step 1: Find the Dockerfile**

```bash
find . -name "Dockerfile" -not -path "./.git/*"
```

**Step 2: Add Node.js installation**

Add after OS dependencies section:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs npm \
    && rm -rf /var/lib/apt/lists/*
```

Or if Alpine-based:

```dockerfile
RUN apk add --no-cache nodejs npm
```

**Step 3: Commit**

```bash
git add Dockerfile
git commit -m "feat: add Node.js to Docker image for npx skills CLI"
```

---

### Task 8: Update existing tests

**Files:**
- Update: `tests/helpers/test_skills.py` — if skills.py interface changes
- Update: `tests/tools/test_skills_tool.py` — if skills_tool interface changes
- Update: `tests/extensions/test_prompt_after.py` — add coverage for new `_60_` extension

**Step 1: Run all existing skill-related tests**

```bash
pytest tests/helpers/test_skills.py tests/tools/test_skills_tool.py tests/api/test_skills.py tests/extensions/test_prompt_after.py -v
```

Fix any failures caused by the refactoring.

**Step 2: Commit fixes**

```bash
git add tests/
git commit -m "fix: update existing skill tests for marketplace refactoring"
```

---

### Task 9: Run full test suite and fix

**Step 1: Run all tests**

```bash
pytest tests/ -m "not integration" -v --timeout=30
```

**Step 2: Fix any failures**

**Step 3: Commit**

```bash
git commit -am "fix: resolve test failures from skills marketplace changes"
```

---

### Task 10: Push and create PR

**Step 1: Push all changes**

```bash
git push origin feat/skills-marketplace
```

**Step 2: Create PR**

```bash
gh pr create \
  --title "feat: skills marketplace with npx CLI integration" \
  --body "## Summary
- Replace skills management with npx skills CLI backend
- Add catalog search in Settings UI via /skills_catalog endpoint
- Automatic skill activation: catalog injected into system prompt
- New unified Settings > Skills tab with search, install, remove, update
- Node.js added to Docker image for npx support

## Design
See docs/plans/2026-03-18-skills-marketplace-design.md

## Test plan
- [ ] Unit tests for skills_cli.py (npx wrapper, parsing, caching)
- [ ] Unit tests for /skills_catalog API
- [ ] Unit tests for refactored /skill_install API
- [ ] Unit tests for _60_skills_catalog extension
- [ ] Updated existing skill tests pass
- [ ] Full test suite passes
- [ ] Manual: install skill via Settings UI, verify agent sees it in chat"
```
