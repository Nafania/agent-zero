# Cognee Search Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix memory recall so personal memories are found via vector search, non-existent datasets are handled gracefully, and node_name filtering matches actual stored data.

**Architecture:** Add `CHUNKS` (vector/semantic) to the default search type configuration alongside existing `CHUNKS_LEXICAL` and `GRAPH_COMPLETION`. Filter out non-existent datasets before calling `cognee.search()` to eliminate `DatasetNotFoundError` spam. Fix `node_name` parameter to use full dataset-prefixed names matching how data is stored.

**Tech Stack:** Python 3.12, Cognee 0.5.5, pytest, asyncio, Docker

**Design doc:** `docs/plans/2026-03-17-cognee-search-fix-design.md`

---

### Task 0: Commit current work to a separate branch

**Files:**
- All modified files in the repo

**Step 1: Create branch and commit all current changes**

```bash
cd /Users/ivan/Documents/work/ai-girlfriend-project/ai-team
git checkout -b fix/cognee-search-recall
git add -A
git commit -m "fix: cognee initialization, settings reload, asyncio compat, and search debug logging"
```

**Step 2: Verify commit**

```bash
git log --oneline -1
git status
```

Expected: clean working tree, commit on `fix/cognee-search-recall`.

---

### Task 1: Add CHUNKS to default search types

**Files:**
- Modify: `agent-zero/python/extensions/message_loop_prompts_after/_50_recall_memories.py:373`
- Modify: `agent-zero/python/helpers/memory.py:231`

**Step 1: Write the failing test**

File: `agent-zero/tests/helpers/test_memory.py`

Add test that verifies `_multi_search` uses CHUNKS in its search types when using the default config:

```python
class TestMultiSearchIncludesChunks:
    """CHUNKS (vector search) must be in the default search types."""

    @pytest.mark.asyncio
    async def test_default_search_types_include_chunks(self):
        """Default cognee_search_types setting must include CHUNKS."""
        from python.helpers.cognee_init import get_cognee_setting
        types_str = get_cognee_setting("cognee_search_types", "GRAPH_COMPLETION,CHUNKS_LEXICAL")
        type_names = [n.strip() for n in types_str.split(",")]
        assert "CHUNKS" in type_names, (
            f"CHUNKS missing from default search types: {type_names}"
        )
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/ivan/Documents/work/ai-girlfriend-project/ai-team/agent-zero
python -m pytest tests/helpers/test_memory.py::TestMultiSearchIncludesChunks -v
```

Expected: FAIL — current default is `"GRAPH_COMPLETION,CHUNKS_LEXICAL"`, missing CHUNKS.

**Step 3: Update defaults in both files**

In `agent-zero/python/helpers/memory.py`, line 231, change:
```python
type_names = get_cognee_setting("cognee_search_types", "GRAPH_COMPLETION,CHUNKS_LEXICAL")
```
to:
```python
type_names = get_cognee_setting("cognee_search_types", "GRAPH_COMPLETION,CHUNKS,CHUNKS_LEXICAL")
```

In `agent-zero/python/extensions/message_loop_prompts_after/_50_recall_memories.py`, line 373 (inside `_resolve_search_types`), change:
```python
type_names = get_cognee_setting("cognee_search_types", "GRAPH_COMPLETION,CHUNKS_LEXICAL")
```
to:
```python
type_names = get_cognee_setting("cognee_search_types", "GRAPH_COMPLETION,CHUNKS,CHUNKS_LEXICAL")
```

**Step 4: Run test to verify it passes**

```bash
python -m pytest tests/helpers/test_memory.py::TestMultiSearchIncludesChunks -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add agent-zero/python/helpers/memory.py agent-zero/python/extensions/message_loop_prompts_after/_50_recall_memories.py agent-zero/tests/helpers/test_memory.py
git commit -m "feat: add CHUNKS (vector search) to default cognee search types"
```

---

### Task 2: Graceful handling of non-existent datasets

**Files:**
- Modify: `agent-zero/python/extensions/message_loop_prompts_after/_50_recall_memories.py`
- Modify: `agent-zero/python/helpers/memory.py`

**Step 1: Write the failing test**

File: `agent-zero/tests/helpers/test_memory.py`

```python
class TestDatasetFiltering:
    """Search should skip non-existent datasets instead of raising errors."""

    @pytest.mark.asyncio
    async def test_filter_nonexistent_datasets(self):
        """_datasets_for_filter should not return datasets that don't exist in Cognee."""
        import python.helpers.cognee_init as ci
        ci._configured = True
        mock_cognee = MagicMock()
        mock_search_type = MagicMock()
        ci._cognee_module = mock_cognee
        ci._search_type_class = mock_search_type

        mem = Memory(dataset_name="default", memory_subdir="default")
        datasets = mem._datasets_for_filter("")
        # Should include all areas
        assert "default_main" in datasets
        assert "default_fragments" in datasets
        assert "default_solutions" in datasets
```

This test verifies the current behaviour. The actual fix adds a filtering step in `_multi_search` and `_multi_cognee_search` that removes non-existent datasets before calling `cognee.search`.

**Step 2: Add dataset existence cache to Memory class**

In `agent-zero/python/helpers/memory.py`, add a class-level cache and a method to check existing datasets:

```python
class Memory:
    _existing_datasets_cache: set[str] | None = None
    _existing_datasets_ts: float = 0
    _DATASETS_CACHE_TTL = 30  # seconds

    @staticmethod
    async def _get_existing_dataset_names() -> set[str]:
        import time
        now = time.monotonic()
        if (Memory._existing_datasets_cache is not None
                and now - Memory._existing_datasets_ts < Memory._DATASETS_CACHE_TTL):
            return Memory._existing_datasets_cache
        try:
            cognee, _ = _get_cognee()
            all_ds = await cognee.datasets.list_datasets()
            Memory._existing_datasets_cache = {ds.name for ds in all_ds}
            Memory._existing_datasets_ts = now
        except Exception:
            if Memory._existing_datasets_cache is not None:
                return Memory._existing_datasets_cache
            return set()
        return Memory._existing_datasets_cache

    @staticmethod
    def _invalidate_datasets_cache():
        Memory._existing_datasets_cache = None
```

Call `_invalidate_datasets_cache()` from `reload()` and after insert/delete operations.

**Step 3: Filter datasets before search in `_multi_search`**

In `_multi_search` method, after computing `datasets`, add:

```python
existing = await Memory._get_existing_dataset_names()
datasets = [d for d in datasets if d in existing]
if not datasets:
    return []
```

**Step 4: Filter datasets in recall extension's `_multi_cognee_search`**

In `_50_recall_memories.py`, at the top of `_multi_cognee_search`, add:

```python
from python.helpers.memory import Memory
existing = await Memory._get_existing_dataset_names()
datasets = [d for d in datasets if d in existing]
if not datasets:
    return None
```

**Step 5: Run all tests**

```bash
python -m pytest tests/helpers/test_memory.py -v
```

Expected: all pass, no regressions.

**Step 6: Commit**

```bash
git add agent-zero/python/helpers/memory.py agent-zero/python/extensions/message_loop_prompts_after/_50_recall_memories.py agent-zero/tests/helpers/test_memory.py
git commit -m "fix: skip non-existent datasets in search instead of raising DatasetNotFoundError"
```

---

### Task 3: Fix node_name mismatch in recall extension

**Files:**
- Modify: `agent-zero/python/extensions/message_loop_prompts_after/_50_recall_memories.py:112-113`

**Step 1: Write the failing test**

File: `agent-zero/tests/extensions/test_recall_memories.py` (or add to existing test file)

```python
def test_node_names_match_dataset_names():
    """node_name passed to cognee.search must match the NodeSet names used during data storage."""
    from python.helpers.memory import Memory
    mem = Memory(dataset_name="default", memory_subdir="default")

    expected_mem_node_names = [
        mem._area_dataset(Memory.Area.MAIN.value),      # "default_main"
        mem._area_dataset(Memory.Area.FRAGMENTS.value),  # "default_fragments"
    ]
    expected_sol_node_names = [
        mem._area_dataset(Memory.Area.SOLUTIONS.value),  # "default_solutions"
    ]

    assert expected_mem_node_names == ["default_main", "default_fragments"]
    assert expected_sol_node_names == ["default_solutions"]
```

**Step 2: Fix node_name values in recall extension**

In `_50_recall_memories.py`, lines 112-113, change:

```python
mem_node_name = [Memory.Area.MAIN.value, Memory.Area.FRAGMENTS.value]
sol_node_name = [Memory.Area.SOLUTIONS.value]
```

to:

```python
mem_node_name = [db._area_dataset(Memory.Area.MAIN.value), db._area_dataset(Memory.Area.FRAGMENTS.value)]
sol_node_name = [db._area_dataset(Memory.Area.SOLUTIONS.value)]
```

**Step 3: Run tests**

```bash
python -m pytest tests/ -v -k "node_name or recall"
```

Expected: PASS

**Step 4: Commit**

```bash
git add agent-zero/python/extensions/message_loop_prompts_after/_50_recall_memories.py agent-zero/tests/
git commit -m "fix: use full dataset-prefixed node_name in recall search to match stored NodeSet names"
```

---

### Task 4: Remove all debug prints

**Files:**
- Modify: `agent-zero/python/extensions/message_loop_prompts_after/_50_recall_memories.py`
- Modify: `agent-zero/python/helpers/memory.py`

**Step 1: Remove debug prints**

Remove all lines matching `PrintStyle.hint(f"DEBUG` from:
- `agent-zero/python/extensions/message_loop_prompts_after/_50_recall_memories.py` (the `_search_one` function debug lines and `import time as _t` / timing variables)
- `agent-zero/python/helpers/memory.py` (the `DEBUG search_similarity_threshold` and `DEBUG _multi_search` lines)

**Step 2: Run all tests to verify no regressions**

```bash
python -m pytest tests/helpers/test_memory.py tests/helpers/test_cognee_init.py -v
```

Expected: all pass.

**Step 3: Commit**

```bash
git add agent-zero/python/extensions/message_loop_prompts_after/_50_recall_memories.py agent-zero/python/helpers/memory.py
git commit -m "chore: remove debug logging from memory search"
```

---

### Task 5: Update and write tests

**Files:**
- Modify: `agent-zero/tests/helpers/test_memory.py`
- Modify: `agent-zero/tests/extensions/test_recall_memories.py`

**Step 1: Update existing TestMultiSearchParallel tests**

Verify existing `test_multi_search_runs_in_parallel`, `test_multi_search_timeout_per_type`, `test_multi_search_fallback_on_all_fail` still pass with the new default search types. Update mocks if needed to account for `CHUNKS` being in the type list.

**Step 2: Add test for dataset filtering in _multi_search**

```python
class TestMultiSearchDatasetFiltering:
    @pytest.mark.asyncio
    async def test_multi_search_skips_nonexistent_datasets(self):
        """_multi_search returns [] when all requested datasets don't exist."""
        # Mock _get_existing_dataset_names to return empty set
        # Call _multi_search with datasets=["nonexistent"]
        # Assert returns []
        # Assert cognee.search was NOT called
```

**Step 3: Add test for reload invalidating datasets cache**

```python
def test_reload_invalidates_datasets_cache():
    Memory._existing_datasets_cache = {"old_dataset"}
    from python.helpers.memory import reload
    reload()
    assert Memory._existing_datasets_cache is None
```

**Step 4: Run full test suite**

```bash
python -m pytest tests/ -v --ignore=tests/api/test_run_ui_config.py
```

Expected: all pass.

**Step 5: Commit**

```bash
git add agent-zero/tests/
git commit -m "test: add tests for CHUNKS search type, dataset filtering, and node_name matching"
```

---

### Task 6: Docker verification

**Step 1: Restart container**

```bash
docker restart agent-zero
```

**Step 2: Wait for initialization, check logs for errors**

```bash
sleep 30 && docker logs agent-zero --since 35s 2>&1 | grep -iE "error|Cognee" | head -10
```

Expected: no errors except deprecation warnings.

**Step 3: Ask agent a personal question, check debug-free logs**

Ask "как меня зовут?" in the chat, then:

```bash
docker logs agent-zero --since 1m 2>&1 | grep -iE "error|CHUNKS|recall|search" | head -20
```

Expected: CHUNKS search returns personal memories, no `DatasetNotFoundError`, no DEBUG prints.
