# Cognee Search Fix Design

## Problem

Memory recall returns documentation/README chunks instead of personal memories. Root cause analysis from debug logs:

- `CHUNKS_LEXICAL` (Phase 1, fast): returns 12 results in 0.71s — all README content. Lexical/Jaccard matching favours long documentation over short personal fragments like "User's name is Иван".
- `GRAPH_COMPLETION` (Phase 2, background): finds the correct answer ("Вас зовут Иван Каздым") but either times out (31.89s) or completes after the agent already responded.
- `CHUNKS` (vector/semantic search) is not configured — the one search type that would find personal memories by embedding similarity is missing entirely.
- `default_solutions` dataset does not exist, causing `DatasetNotFoundError` spam on every search.
- `node_name` filter mismatch: recall extension passes `['main', 'fragments']` but data is stored with NodeSet names `['default_main', 'default_fragments']`.

## Solution

### 1. Add CHUNKS to default search types

Change default `cognee_search_types` from `"GRAPH_COMPLETION,CHUNKS_LEXICAL"` to `"GRAPH_COMPLETION,CHUNKS,CHUNKS_LEXICAL"`.

- `CHUNKS` uses vector/embedding similarity — will find "User's name is Иван" by semantic match to queries like "как зовут пользователя".
- Runs in Phase 1 (fast, no LLM call) alongside `CHUNKS_LEXICAL`, ~0.5-1s.
- `GRAPH_COMPLETION` stays in Phase 2 (background) for graph-context enrichment.

Files: `_50_recall_memories.py`, `memory.py`.

### 2. Graceful handling of non-existent datasets

Before calling `cognee.search(datasets=...)`, filter out datasets that don't exist. If all datasets are filtered out, return `[]` without calling search.

Cache the list of existing dataset names on Memory initialization; invalidate on insert/delete.

Files: `_50_recall_memories.py`, `memory.py`.

### 3. Fix node_name mismatch

Change recall extension to use `db._area_dataset(area)` (e.g. `"default_main"`) instead of raw `Memory.Area.MAIN.value` (e.g. `"main"`) for the `node_name` parameter.

Apply fix, verify with debug logs. If behaviour worsens (some search types ignore node_name), revert.

Files: `_50_recall_memories.py`.

### 4. Remove debug prints

After confirming fixes work, remove all `PrintStyle.hint(f"DEBUG ...")` from `_50_recall_memories.py` and `memory.py`.

## Implementation Steps

1. Commit all current changes to a separate branch to preserve work.
2. Add `CHUNKS` to default search types in both files.
3. Implement dataset existence check with caching.
4. Fix `node_name` values in recall extension.
5. Remove all debug prints.
6. Update/write tests covering the new behaviour.
7. Verify in Docker: restart, ask question, check logs.
