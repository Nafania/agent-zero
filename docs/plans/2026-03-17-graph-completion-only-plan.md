# GRAPH_COMPLETION-only Search Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace CHUNKS/CHUNKS_LEXICAL with GRAPH_COMPLETION as the sole search type, eliminating the broken Phase 1/Phase 2 split.

**Architecture:** Remove the fast/slow search type classification. Run GRAPH_COMPLETION searches for memories and solutions in parallel via `asyncio.gather`, blocking until both complete. Remove `_slow_search_and_merge` background task entirely.

**Tech Stack:** Python, asyncio, Cognee 0.5.5, pytest

---

### Task 1: Update default search types in cognee_init.py

**Files:**
- Modify: `python/helpers/cognee_init.py:12` (`_COGNEE_DEFAULTS`)
- Test: `tests/helpers/test_memory.py` (existing `TestDefaultSearchTypesIncludeChunks`)

**Step 1: Update the failing test**

In `tests/helpers/test_memory.py`, find `TestDefaultSearchTypesIncludeChunks` and replace it:

```python
class TestDefaultSearchTypesGraphOnly:
    def test_default_search_types_is_graph_completion(self):
        from python.helpers.cognee_init import _COGNEE_DEFAULTS
        val = _COGNEE_DEFAULTS["cognee_search_types"]
        assert val == "GRAPH_COMPLETION", f"Expected 'GRAPH_COMPLETION', got '{val}'"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/helpers/test_memory.py::TestDefaultSearchTypesGraphOnly -v`
Expected: FAIL — current value is `"GRAPH_COMPLETION,CHUNKS,CHUNKS_LEXICAL"`

**Step 3: Update _COGNEE_DEFAULTS**

In `python/helpers/cognee_init.py`, change line 12:

```python
_COGNEE_DEFAULTS: dict[str, Any] = {
    "cognee_search_type": "GRAPH_COMPLETION",
    "cognee_search_types": "GRAPH_COMPLETION",  # was "GRAPH_COMPLETION,CHUNKS,CHUNKS_LEXICAL"
    "cognee_multi_search_enabled": True,
    # ... rest unchanged
}
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/helpers/test_memory.py::TestDefaultSearchTypesGraphOnly -v`
Expected: PASS

**Step 5: Commit**

```bash
git add python/helpers/cognee_init.py tests/helpers/test_memory.py
git commit -m "feat: change default search type to GRAPH_COMPLETION only"
```

---

### Task 2: Remove Phase 1/Phase 2 split in recall extension

**Files:**
- Modify: `python/extensions/message_loop_prompts_after/_50_recall_memories.py`
- Test: `tests/extensions/test_recall_memories.py`

**Step 1: Update tests for single-phase search**

In `tests/extensions/test_recall_memories.py`, update `TestMultiCogneeSearch` tests:
- Remove any tests that assert Phase 2 / slow search behavior
- Update `_mock_existing_datasets` fixture if it references datasets that Phase 2 used
- Add test `test_graph_completion_runs_in_phase1` that verifies GRAPH_COMPLETION is in the fast list (not slow)

```python
class TestSearchTypesAllFast:
    def test_graph_completion_is_not_slow(self):
        """GRAPH_COMPLETION should NOT be in _SLOW_SEARCH_NAMES."""
        from python.extensions.message_loop_prompts_after._50_recall_memories import _SLOW_SEARCH_NAMES
        assert "GRAPH_COMPLETION" not in _SLOW_SEARCH_NAMES
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/extensions/test_recall_memories.py::TestSearchTypesAllFast -v`
Expected: FAIL — GRAPH_COMPLETION is currently in `_SLOW_SEARCH_NAMES`

**Step 3: Modify _50_recall_memories.py**

3a. Empty `_SLOW_SEARCH_NAMES` (or remove it):

```python
_SLOW_SEARCH_NAMES = frozenset()  # no search types are "slow" anymore
```

3b. Remove `_slow_search_and_merge` function entirely (lines 282-330).

3c. In `search_memories`, remove the Phase 2 block (lines 176-196) that calls `asyncio.create_task(_slow_search_and_merge(...))`.

3d. Update `_resolve_search_types` — since `_SLOW_SEARCH_NAMES` is empty, all types land in `fast`. The function still works correctly without changes, but verify the default fallback string matches Task 1.

In `_resolve_search_types`, update the default parameter:

```python
type_names = get_cognee_setting("cognee_search_types", "GRAPH_COMPLETION")
```

**Step 4: Run all recall tests**

Run: `pytest tests/extensions/test_recall_memories.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add python/extensions/message_loop_prompts_after/_50_recall_memories.py tests/extensions/test_recall_memories.py
git commit -m "feat: remove Phase 2, run GRAPH_COMPLETION in Phase 1"
```

---

### Task 3: Run full test suite and fix breakage

**Step 1: Run all tests**

Run: `pytest tests/ -v --tb=short 2>&1 | tail -40`
Expected: identify any tests that relied on CHUNKS/CHUNKS_LEXICAL or Phase 2

**Step 2: Fix any broken tests**

Common fixes needed:
- Tests in `test_memory.py` that assert `CHUNKS` is in default types
- Tests in `test_recall_memories.py` that mock CHUNKS-specific behavior
- Update `TestMultiCogneeSearch` dataset filtering tests if they reference CHUNKS

**Step 3: Verify all tests pass**

Run: `pytest tests/ -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add -A
git commit -m "fix: update tests for GRAPH_COMPLETION-only search"
```

---

### Task 4: Docker verification

**Step 1: Restart container**

```bash
docker restart agent-zero
```

**Step 2: Wait for startup, check logs**

```bash
sleep 15 && docker logs agent-zero --since=30s 2>&1 | grep -E "DIAG|ERROR|initialized"
```

**Step 3: Send test message to agent**

Ask: "как меня зовут и где я живу?"

**Step 4: Check DIAG logs**

```bash
docker logs agent-zero --since=1m 2>&1 | grep -E "DIAG"
```

Verify:
- Only GRAPH_COMPLETION searches appear (no CHUNKS/CHUNKS_LEXICAL)
- Results include personal facts
- Agent responds correctly

**Step 5: Measure latency**

From DIAG logs, note time between search start and agent response.
Compare with previous ~3s (CHUNKS-only Phase 1).

**Step 6: Commit any final adjustments**

```bash
git add -A
git commit -m "chore: verified GRAPH_COMPLETION-only search in Docker"
```
