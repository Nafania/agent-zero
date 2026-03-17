# Design: Switch to GRAPH_COMPLETION-only search

## Problem

Agent Zero's memory recall uses a two-phase architecture:
- Phase 1 (blocking): CHUNKS + CHUNKS_LEXICAL — fast vector/lexical search
- Phase 2 (fire-and-forget): GRAPH_COMPLETION — graph + LLM search

Personal facts (name, wife, location) stored in `solutions` area are never found
in Phase 1 because CHUNKS/CHUNKS_LEXICAL search a shared LanceDB table
(`DocumentChunk_text`) without any node_name or dataset filtering. The agent
responds before Phase 2 completes.

## Root cause analysis

1. LanceDB has a single shared `DocumentChunk_text` table for all datasets.
   No per-dataset isolation exists despite `backend_access_control` being enabled.
2. `ChunksRetriever` is initialized with only `top_k` — it receives neither
   `node_name` nor `node_type`. This is by design in Cognee: CHUNKS is a raw
   vector search without filtering.
3. `_create_vector_engine` uses `@lru_cache`, so even with per-dataset ContextVar
   configs, the same LanceDB adapter is returned when URL params match.
4. GRAPH_COMPLETION is the only retriever that receives and uses `node_name` for
   filtering via `belongs_to_set` graph edges.
5. Cognee documentation shows `node_name` filtering exclusively with
   GRAPH_COMPLETION. CHUNKS is described as "retrieves raw chunks of memory".

## Decision

Remove CHUNKS and CHUNKS_LEXICAL from search. Use GRAPH_COMPLETION as the sole
search type. Eliminate the Phase 1 / Phase 2 split.

## Changes

### `_50_recall_memories.py`

- Remove `_SLOW_SEARCH_NAMES` frozenset.
- Simplify `_resolve_search_types` to always return `[GRAPH_COMPLETION]` (no
  fast/slow split).
- Remove `_slow_search_and_merge` function and the Phase 2 `asyncio.create_task`.
- `search_memories` runs a single `asyncio.gather` with two GRAPH_COMPLETION
  searches (memories + solutions), then writes extras immediately.
- Keep fallback to `search_similarity_threshold` if GRAPH_COMPLETION returns None.

### `cognee_init.py`

- Change `_COGNEE_DEFAULTS["cognee_search_types"]` from
  `"GRAPH_COMPLETION,CHUNKS,CHUNKS_LEXICAL"` to `"GRAPH_COMPLETION"`.

### No changes to

- Data storage (`cognee.add` with `node_set` and `dataset_name`) — correct.
- `node_name` passing in recall extension — already correct.
- `_extract_texts` — works for GRAPH_COMPLETION string results.
- `memory.py` — no changes needed.

## Expected outcome

- **Quality**: Personal facts reliably found before agent responds.
- **Latency**: ~5-8s per recall (was ~3s Phase 1 + ~6s background Phase 2).
  Net user-perceived latency may increase by ~3-5s since Phase 2 was invisible.
- **Cost**: +1 LLM call per recall (GRAPH_COMPLETION uses LLM internally).
- **Simplicity**: Single-phase architecture, no background tasks, no race
  conditions.

## Risks

- Latency increase may be noticeable. Mitigated by: this is an experiment to
  measure real latency and quality. Can re-add CHUNKS later if needed.
- GRAPH_COMPLETION timeout during cognify pipeline contention. Mitigated by:
  existing PER_SEARCH_TIMEOUT (15s) and fallback to similarity search.
