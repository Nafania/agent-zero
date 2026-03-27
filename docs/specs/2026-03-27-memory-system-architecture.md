# Agent Zero: Memory System Architecture

**Date:** 2026-03-27
**Scope:** Full memory pipeline — from Cognee initialization through recall, memorize, feedback, and dashboard.

---

## Overview

Agent Zero's memory system is built on top of **Cognee** — a library providing vector search, knowledge graphs, and document storage. The system gives agents persistent memory that survives across sessions: agents memorize facts, code fragments, and successful solutions, then recall them in future conversations.

The memory stack has six layers:

1. **Cognee init** — configure storage, LLM, embeddings before Cognee import
2. **Memory class** — core CRUD abstraction over Cognee datasets
3. **Recall pipeline** — automatic retrieval during agent message loop
4. **Memorize pipeline** — automatic extraction at monologue end
5. **Background worker** — deferred cognify/memify on dirty datasets
6. **Feedback loop** — user signals on recall quality, forwarded to Cognee

---

## 1. Cognee Initialization (`python/helpers/cognee_init.py`)

### Why order matters

Cognee reads `SYSTEM_ROOT_DIRECTORY`, `DB_PROVIDER`, `DB_NAME` at import time. If env vars are set after `import cognee`, the library uses default paths and the SQLite DB ends up inside an ephemeral container — data lost on rebuild.

### Initialization sequence

```
configure_cognee()
├── 1. Set env vars (DATA_ROOT_DIRECTORY, SYSTEM_ROOT_DIRECTORY, CACHE_ROOT_DIRECTORY, DB_PROVIDER=sqlite, DB_NAME=cognee_db)
├── 2. import cognee  (now safe — env vars already set)
├── 3. Configure LLM via cognee.config.set_llm_config() using A0's util_model_* settings
├── 4. Configure embeddings via env vars (EMBEDDING_PROVIDER, EMBEDDING_MODEL, EMBEDDING_API_KEY)
├── 5. Set chunk size/overlap via cognee.config
└── 6. Set directory paths via cognee.config.data_root_directory() / system_root_directory()
```

### Storage layout

All Cognee data lives under `usr/cognee/` (configurable via `cognee_data_dir` setting):

```
usr/cognee/
├── data_storage/       ← raw data files
├── cognee_system/      ← SQLite database (cognee_db)
└── cognee_cache/       ← query/session cache
```

In Docker/addon: `usr/` maps to persistent volume `/a0/usr/`. Everything else is ephemeral.

### Startup (`initialize.py`)

```python
initialize_cognee()
├── configure_cognee()
├── run FAISS→Cognee migration (legacy, one-time)
└── CogneeBackgroundWorker.get_instance().start()
```

### Settings source

Cognee uses A0's **utility model** for LLM operations and A0's **embedding model** for vector search. API keys come from A0's settings/dotenv. When embedding or LLM settings change, `memory.reload()` is called to reconfigure Cognee.

---

## 2. Memory Class (`python/helpers/memory.py`)

### Core abstraction

`Memory` is the central class. It wraps Cognee's `add()`, `search()`, and `datasets.*` APIs into a document-oriented interface using LangChain's `Document` objects.

### Memory areas

```python
class Area(Enum):
    MAIN = "main"          # general knowledge, imported files
    FRAGMENTS = "fragments" # auto-memorized conversation fragments
    SOLUTIONS = "solutions" # auto-memorized problem/solution pairs
```

Areas are stored as Cognee `node_set` values. Search queries filter by area using `node_name`.

### Dataset naming and isolation

Memory isolation is based on **datasets** (Cognee's logical namespace):

| Context | memory_subdir | dataset_name |
|---------|---------------|--------------|
| No project active | `"default"` | `"default"` |
| Project with `memory: "own"` | `"projects/myproject"` | `"projects_myproject"` |
| Project with `memory: "global"` | `"default"` | `"default"` |

Resolution chain:

```
get_context_memory_subdir(context)
├── Is a project active?
│   ├── Yes + project.memory == "own" → "projects/<name>"
│   └── Yes + project.memory == "global" → None (falls through)
└── No → config.memory_subdir (default: "default")
```

### Search always includes "default"

`get_search_datasets()` returns `["default"]` plus the current project dataset (if different). This means project agents always see global memories too.

### Data format

Documents are stored with a metadata header prepended to the text:

```
[META:{"id":"aBcDeFgHiJ","timestamp":"2026-03-27 14:30:00","area":"fragments"}]
Actual memory content here...
```

On retrieval, `_extract_metadata_from_text()` parses this header back into metadata dict + clean content.

### Insert flow

```
Memory.insert_documents(docs)
├── For each doc:
│   ├── Generate 10-char random ID
│   ├── Set metadata (id, timestamp, area)
│   ├── Build enriched text: [META:{json}]\n{content}
│   ├── cognee.add(enriched_text, dataset_name=..., node_set=[area])
│   └── Mark dataset dirty in CogneeBackgroundWorker
└── Invalidate dashboard cache
```

### Search flow

```
Memory.search_similarity_threshold(query, limit, threshold, filter)
├── Parse filter string to node_names (area values)
├── Determine datasets: [default] + [project dataset if any]
├── cognee.search(query_text, top_k, datasets, node_type=NodeSet, node_name, session_id)
└── _results_to_documents(results, limit)
    ├── For each result:
    │   ├── Extract search_result if wrapper object
    │   ├── Parse [META:...] header → content + metadata
    │   ├── Set fallback ID via stable_memory_id_fallback() if missing
    │   └── Build Document(page_content, metadata)
    └── Return capped at limit
```

### Delete flow

```
Memory.delete_documents_by_ids(ids)
├── cognee.datasets.list_datasets() → find target dataset
├── cognee.datasets.list_data(dataset.id) → iterate all data items
├── For each item: check if any target ID appears in item text
│   └── If match: cognee.datasets.delete_data(dataset_id, data_id)
└── Invalidate dashboard cache
```

The delete logic is a string-contains scan over raw_data_location/name — not an indexed lookup. This is the source of the known bug where dashboard delete fails with "Memory with ID not found" when the ID format doesn't match.

### Knowledge preload

On first agent use per session, `Memory.get(agent)` triggers knowledge preload:

```
preload_knowledge(kn_dirs, memory_subdir)
├── Load import index from usr/cognee_state/<subdir>/knowledge_import.json
├── If index exists but Cognee DB is empty → force full re-import
├── Scan knowledge directories for changed/new/removed files
├── For changed files: delete old data, insert new via cognee.add()
├── For removed files: delete data
├── Save updated index
```

Knowledge directories:
- `knowledge/` (built-in defaults)
- `usr/knowledge/` (user-added)
- `projects/<name>/.a0proj/knowledge/` (project-specific)

Each directory has sub-folders matching `Memory.Area` values (main, fragments, solutions).

---

## 3. Recall Pipeline (`python/extensions/message_loop_prompts_after/_50_recall_memories.py`)

### When it runs

- Extension hook: `message_loop_prompts_after`
- Controlled by `memory_recall_enabled` (on/off) and `memory_recall_interval` (every N iterations)
- Runs as an async task — non-blocking to the main loop

### Query construction

```python
query = user_instruction + "\n\n" + history[-memory_recall_history_len:]
```

Uses the current user message plus recent conversation history (trimmed to `memory_recall_history_len` chars, default 10000).

### Parallel search

Two Cognee searches run concurrently via `asyncio.gather`:

| Search | Areas | top_k setting |
|--------|-------|--------------|
| Memories | `MAIN` + `FRAGMENTS` | `memory_recall_memories_max_search` (default 12) |
| Solutions | `SOLUTIONS` | `memory_recall_solutions_max_search` (default 8) |

Both search across `get_search_datasets()` (default + project dataset).

### Result processing

```
recall_text_and_feedback_items(answers, limit, context_id, fallback_dataset, kind)
├── Convert raw Cognee results → Documents via _results_to_documents()
├── For each doc:
│   ├── Extract content text
│   ├── Resolve memory_id (from metadata or stable hash fallback)
│   └── Build feedback item: {text, memory_id, dataset, context_id, kind}
└── Return (plain_texts[], feedback_items[])
```

Results are capped by `memory_recall_memories_max_result` (default 5) and `memory_recall_solutions_max_result` (default 3).

### Injection into agent context

Found memories/solutions are injected into `loop_data.extras_persistent`:

```python
extras["memories"] = agent.parse_prompt("agent.system.memories.md", memories=memories_txt)
extras["solutions"] = agent.parse_prompt("agent.system.solutions.md", solutions=solutions_txt)
```

These become part of the system prompt for subsequent LLM calls. The log entry also stores `memory_feedback_items` for the UI to render thumbs-up/down controls.

---

## 4. Memorize Pipeline (`python/extensions/monologue_end/`)

### When it runs

- Extension hook: `monologue_end` — fires when the agent finishes processing a conversation turn
- Controlled by `memory_memorize_enabled` (on/off)
- Runs as background `DeferredTask` (non-blocking)

### Two parallel memorize extensions

#### `_50_memorize_fragments.py` — General memory

1. Calls utility model with `memory.memories_sum.sys.md` system prompt
2. Input: full conversation history (`agent.history`)
3. Model returns JSON array of memory fragments
4. Each fragment is inserted into Cognee with `area: "fragments"`

#### `_51_memorize_solutions.py` — Problem/solution pairs

1. Calls utility model with `memory.solutions_sum.sys.md` system prompt
2. Input: full conversation history
3. Model returns JSON array of `{problem, solution}` objects
4. Each solution is formatted as:
   ```
   # Problem
   <problem text>
   # Solution
   <solution text>
   ```
5. Inserted into Cognee with `area: "solutions"`

### Storage

Both use `Memory.insert_text()` which prepends metadata header and calls `cognee.add()`. The background worker later runs `cognify` + `memify` to build knowledge graphs from the raw data.

---

## 5. Background Worker (`python/helpers/cognee_background.py`)

### Purpose

Raw data added via `cognee.add()` is just stored text. The background worker runs Cognee's graph-building pipelines to make it searchable via graph-based queries.

### Trigger conditions (OR logic)

| Condition | Default |
|-----------|---------|
| Time since last run ≥ `cognee_cognify_interval` | 5 minutes |
| Insert count ≥ `cognee_cognify_after_n_inserts` | 10 inserts |

### Pipeline

```
CogneeBackgroundWorker.run_pipeline()
├── cognee.cognify(datasets=dirty_datasets, temporal_cognify=temporal_enabled)
│   └── Builds knowledge graph, entity extraction, relationships
├── For each dataset:
│   └── cognee.memify(dataset=ds)
│       └── Creates memory associations/embeddings
├── Clear dirty set, reset insert counter
└── Update last run timestamp
```

### Lifecycle

- Singleton instance via `CogneeBackgroundWorker.get_instance()`
- Started at app boot via `initialize_cognee()` → `worker.start()`
- Main loop: checks every 60 seconds if pipeline should run
- Datasets are marked dirty on every `Memory.insert_documents()` call

---

## 6. Feedback Loop (`python/helpers/cognee_feedback.py`)

### Purpose

Users can rate recalled memories (positive/negative) to improve future recall quality. Feedback is forwarded to Cognee's `session.add_feedback()` API.

### Payload contract

```json
{
  "context_id": "chat/session identifier",
  "dataset": "dataset name",
  "memory_id": "stable ID from recall metadata",
  "feedback": "positive | negative",
  "reason": "optional text"
}
```

### Flow

```
submit_memory_feedback(payload)
├── Validate payload (required fields, feedback ∈ {positive, negative})
├── Schedule background drain of pending queue
├── If feedback disabled in settings → enqueue to disk, return "queued"
├── Discover Cognee feedback callable:
│   ├── cognee.session.add_feedback (preferred)
│   └── cognee.add_feedback (fallback)
├── If no callable found → enqueue to disk, return "queued"
├── Try forward to Cognee:
│   ├── Map feedback to score: positive=5, negative=1
│   ├── Call add_feedback(session_id, qa_id, feedback_text, feedback_score)
│   ├── Success → return "forwarded"
│   └── Failure → enqueue to disk, return "queued"
```

### Durable queue

Fallback persistence at `usr/cognee_feedback_queue/`:

```
usr/cognee_feedback_queue/
├── pending/    ← JSON files awaiting delivery
└── failed/     ← quarantined after MAX_RETRY_ATTEMPTS (5)
```

- At-least-once delivery semantics
- `drain_feedback_queue()` processes pending files, retries forwarding
- Invalid payloads are quarantined to `failed/` to prevent retry loops
- Drain is triggered opportunistically on each new feedback submission

---

## 7. Memory Dashboard API (`python/api/memory_dashboard.py`)

### Endpoint: `/memory_dashboard`

Auto-discovered via `run_ui.py` file scanning convention.

### Actions

| Action | Description |
|--------|-------------|
| `get_memory_subdirs` | List available memory namespaces (default + projects/*) |
| `get_current_memory_subdir` | Resolve active memory namespace for a context |
| `search` | Similarity search via Cognee or full dataset listing |
| `delete` | Delete single memory by ID |
| `bulk_delete` | Delete multiple memories by IDs |
| `update` | Update memory content (delete + re-insert) |
| `cognify_status` | Background worker status (running, dirty datasets, last error) |
| `knowledge_graph` | Cognee graph visualization (if available) |

### Listing vs searching

- **No search query**: Lists all data items from Cognee dataset directly via `cognee.datasets.list_data()`, parses `[META:...]` headers, formats for dashboard. Cached for 60 seconds.
- **With search query**: Uses `Memory.search_similarity_threshold()` for vector similarity search. No caching.

### Cache invalidation

`invalidate_dashboard_cache()` is called after every insert, delete, or update operation in `Memory`.

---

## 8. VectorDB (`python/helpers/vector_db.py`)

Separate from the main memory system. Used by `document_query` tool for per-session document search (PDFs, CSVs, etc.).

- Creates ephemeral Cognee dataset per session (`docquery_<id>_<counter>`)
- Uses `[DOCMETA:{json}]` header format (different from memory's `[META:...]`)
- Supports metadata-based filtering via `simpleeval`
- Not persisted across sessions — purely in-memory doc index with Cognee backend

---

## 9. Settings (`python/helpers/settings.py`)

### Memory recall settings

| Setting | Default | Purpose |
|---------|---------|---------|
| `memory_recall_enabled` | `true` | Master on/off for auto-recall |
| `memory_recall_delayed` | `false` | Delay recall to avoid blocking first response |
| `memory_recall_interval` | `3` | Run recall every N loop iterations |
| `memory_recall_history_len` | `10000` | Chars of history to include in search query |
| `memory_recall_memories_max_search` | `12` | top_k for memory search |
| `memory_recall_solutions_max_search` | `8` | top_k for solution search |
| `memory_recall_memories_max_result` | `5` | Max memories injected into prompt |
| `memory_recall_solutions_max_result` | `3` | Max solutions injected into prompt |
| `memory_memorize_enabled` | `true` | Master on/off for auto-memorize |

### Cognee settings

| Setting | Default | Purpose |
|---------|---------|---------|
| `cognee_search_type` | `GRAPH_COMPLETION` | Search algorithm |
| `cognee_cognify_interval` | `5` | Minutes between cognify runs |
| `cognee_cognify_after_n_inserts` | `10` | Insert count trigger |
| `cognee_temporal_enabled` | `true` | Temporal cognify |
| `cognee_memify_enabled` | `true` | Run memify after cognify |
| `cognee_feedback_enabled` | `true` | Forward user feedback to Cognee |
| `cognee_session_cache` | `filesystem` | Cache adapter |
| `cognee_data_dir` | `usr/cognee` | Root storage directory |

All settings support `.env` override via `A0_SET_<name>` prefix.

### Settings reload

When embedding/LLM model settings change → `memory.reload()`:
1. Reset Cognee config state (`_configured = False`)
2. Clear module cache
3. Re-run `configure_cognee()` with new settings

---

## 10. Data Flow Diagram

```
User message
    │
    ▼
┌─────────────────────────────────┐
│  Message Loop (iteration N)     │
│                                 │
│  if N % recall_interval == 0:   │
│    ┌──────────────────────┐     │
│    │  Recall Extension    │     │
│    │  query = msg+history │     │
│    │                      │     │
│    │  ┌─── asyncio.gather ──┐   │
│    │  │ cognee.search       │   │
│    │  │  (MAIN+FRAGMENTS)   │   │
│    │  │ cognee.search       │   │
│    │  │  (SOLUTIONS)        │   │
│    │  └─────────────────────┘   │
│    │                      │     │
│    │  → extras_persistent │     │
│    │    (system prompt)   │     │
│    │  → feedback_items    │     │
│    │    (UI controls)     │     │
│    └──────────────────────┘     │
│                                 │
│  Main LLM call (with memories  │
│  and solutions in prompt)       │
│                                 │
│  Agent response                 │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│  Monologue End                  │
│                                 │
│  ┌──────────────────────┐       │
│  │ Memorize Fragments   │ (bg)  │
│  │ util_model → extract │       │
│  │ → cognee.add(FRAG)   │       │
│  └──────────────────────┘       │
│  ┌──────────────────────┐       │
│  │ Memorize Solutions   │ (bg)  │
│  │ util_model → extract │       │
│  │ → cognee.add(SOL)    │       │
│  └──────────────────────┘       │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│  Background Worker (every 60s)  │
│                                 │
│  if dirty_datasets:             │
│    cognee.cognify(datasets)     │
│    cognee.memify(dataset)       │
│    → knowledge graph built      │
│    → embeddings updated         │
└─────────────────────────────────┘
    │
    ▼
  (Data now searchable in next recall)
```

---

## 11. Known Issues

### Delete by ID mismatch

`delete_documents_by_ids()` uses string-contains matching over `raw_data_location`/`name` fields of Cognee data items. The IDs stored in `[META:...]` headers may not appear in these fields, causing "Memory with ID not found" errors in the dashboard.

### No indexed delete

Every delete operation requires listing all data items in a dataset and scanning them linearly. No direct ID-based lookup exists in the current Cognee integration.

### Knowledge preload is per-session singleton

`Memory._initialized` is a class-level flag. Knowledge preload runs once per process lifetime, not per agent or per context. Restart required to pick up new knowledge files (unless `Memory.reload()` is called).

### Stable ID fallback

When Cognee results lack an `id` in metadata, a deterministic hash is computed from content + dataset (`syn_<sha256[:32]>`). This works for feedback correlation but may collide if content is identical across datasets.

---

## 12. File Map

| File | Layer | Purpose |
|------|-------|---------|
| `python/helpers/cognee_init.py` | Init | Env vars, import, LLM/embed config |
| `python/helpers/memory.py` | Core | Memory class, CRUD, knowledge preload |
| `python/helpers/cognee_background.py` | Pipeline | Background cognify/memify worker |
| `python/helpers/cognee_feedback.py` | Feedback | Feedback validation, forwarding, queue |
| `python/helpers/vector_db.py` | Document | Per-session document search (separate from memory) |
| `python/helpers/settings.py` | Config | Settings schema, defaults, apply logic |
| `python/helpers/projects.py` | Isolation | Project memory subdir resolution |
| `python/api/memory_dashboard.py` | API | Dashboard list/search/delete/update |
| `python/extensions/.../recall_memories.py` | Recall | Auto-recall during message loop |
| `python/extensions/.../memorize_fragments.py` | Memorize | Auto-memorize conversation fragments |
| `python/extensions/.../memorize_solutions.py` | Memorize | Auto-memorize problem/solution pairs |
| `initialize.py` | Boot | Cognee startup, migration, worker launch |
