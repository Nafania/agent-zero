# Session Cache Isolation Design

## Problem

Project-specific memories leak into the default dataset during search. Data saved in a project chat (e.g. `projects_muza_live`) appears when searching from a non-project chat (`default`).

### Root Cause

Cognee's `GRAPH_COMPLETION` search uses a **session cache** that stores previous Q&A pairs and injects them as "Previous conversation:" into the LLM prompt. The session cache is keyed by `(user_id, session_id)`. When `session_id` is not passed, Cognee defaults to `"default_session"` — a single global session shared across all datasets and all chats.

Result: an answer from a project search (e.g. "Фамилия Егора — Крокодилянский") gets cached, and when a subsequent search runs from a different dataset context, the LLM sees the cached answer in its prompt and repeats it, even though the graph context contains unrelated data.

### Evidence

- SQLite `dataset_data` table: "Крокодилянский" data exists ONLY in `projects_muza_live` dataset.
- LanceDB vector search (dashboard): NOT found in `default`, found in `projects_muza_live`.
- `cognee.search` with `GRAPH_COMPLETION` for `default`: RETURNS "Крокодилянский" — sourced from session cache, not from graph.
- Cognee log shows the LLM prompt includes "Previous conversation:" with cross-dataset Q&A history.
- Session cache DB (`cache.db`): single entry `agent_sessions:<user_id>:default_session` containing 274 Q&A entries from ALL datasets.

## Solution

Pass `session_id=context.id` (Agent Zero's per-chat context identifier) to every `cognee.search()` call. Each chat gets its own isolated session history.

### Changes

**`_50_recall_memories.py`** — add `session_id=self.agent.context.id` to both `cognee.search` calls in `search_memories()`.

**`memory.py`** — add optional `session_id` parameter to `search_similarity_threshold()`, forward to `cognee.search()`. Default `None` (no session for dashboard/one-off searches).

### Why context.id

- Each Agent Zero chat has a unique `context.id` (generated at context creation).
- Session history is conversational — it should be scoped to a conversation (chat), not a dataset.
- Multiple chats can share a dataset but have independent conversations.
- Per [Cognee docs](https://docs.cognee.ai/guides/sessions): "Each session_id maintains its own conversation history. Sessions are isolated from each other."
