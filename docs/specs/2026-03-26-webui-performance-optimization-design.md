# Web UI Performance Optimization

## Problem

The Agent Zero web interface becomes slow and memory-heavy with many chats or long chat histories. Root causes:

1. Every `state_push` includes the full `contexts[]` and `tasks[]` arrays — even when the chat list hasn't changed.
2. Switching chats triggers `forceFull` (`log_from: 0`), sending all log items in a single JSON payload and rendering them synchronously.
3. `load_tmp_chats()` at startup fully deserializes every `chat.json` including heavy `History` objects.
4. `Log._notify_state_monitor()` calls `mark_dirty_all` on every new log item, pushing to all connected clients regardless of which chat they're viewing.
5. Frontend renders the entire log array synchronously on mass render, causing UI freezes.

## Constraints

- 10–30 chats, 100+ messages per chat.
- All three pain points matter: initial load, chat switching, long-session degradation.
- Only the web UI consumes the API — no backward-compatibility requirement.

## Design

Five coordinated changes across backend and frontend.

### 1. Conditional chat list in snapshots

**Goal:** Stop sending `contexts[]`/`tasks[]` when the list hasn't changed.

Backend holds a module-level `_chat_list_updated_at: float` timestamp, updated by operations that change the chat list: create, remove, rename, running-status change.

`StateRequestV1` gains a field `chat_list_since: float`. The client sends the timestamp of its last received chat list update. On first load, hard refresh, or new tab, the client sends `chat_list_since: 0`, which always triggers a full list. `build_snapshot_from_request` compares: if `chat_list_since >= _chat_list_updated_at`, it sets `contexts` and `tasks` to `None` in the snapshot and skips the `AgentContext.all()` iteration + sort entirely.

`SnapshotV1` gains `chat_list_updated_at: float`. The client stores this and passes it back in subsequent requests.

Frontend `applySnapshot` checks: if `contexts` is `null`, leave the sidebar list unchanged. Otherwise apply as today.

Both `contexts` and `tasks` follow the same conditional logic — they are either both included or both `null`. The `has_earlier_logs` field in the snapshot and the `has_more` field in the `/chat_logs` response represent the same concept (whether older log items exist) for their respective contexts.

**Files:** `state_snapshot.py`, `index.js`, `sync-store.js`, `chats-store.js`, `tasks-store.js`.

### 2. Log pagination on chat load

**Goal:** Load only the tail of the conversation when switching chats; fetch older messages on demand.

#### Backend

`Log.output()` gains an optional `tail: int | None` parameter. When `tail` is set and `start == 0` (full load), the method collects all unique log item numbers from `updates`, takes only the last `tail` items, and returns their outputs. When `start != 0` (incremental push), `tail` is ignored. The snapshot includes a new field `has_earlier_logs: bool` indicating whether there are log items before the returned window.

Default tail size: `INITIAL_LOG_TAIL = 50`.

Incremental pushes (`log_from > 0`) are unaffected — they continue returning all updates since the cursor, which is already incremental and small during streaming.

#### New endpoint: `POST /chat_logs`

Request body:

```json
{
  "context_id": "abc123",
  "before": 42,
  "limit": 50
}
```

- `before`: the `no` of the oldest currently loaded log item.
- `limit`: max items to return (default 50).

Response:

```json
{
  "logs": [ ... ],
  "has_more": true
}
```

Returns log items with `no < before`, sorted oldest-to-newest. `has_more` indicates whether there are still earlier items.

#### Frontend

On chat switch, `setMessages` receives at most 50 items. If `has_earlier_logs` is true, a "Load earlier messages" indicator appears at the top of `#chat-history`. Clicking it (or scrolling to top) triggers `POST /chat_logs`. Returned items are prepended to the DOM with scroll-position preservation (`scrollHeight` delta applied to `scrollTop`).

**Files:** `log.py`, `state_snapshot.py`, new `api/chat_logs.py`, `index.js`, `messages.js`.

### 3. Lazy deserialization at startup

**Goal:** Reduce server startup time and initial RAM by deferring heavy `History` deserialization.

`load_tmp_chats()` currently calls `_deserialize_context()` for each chat, which includes `_deserialize_agents()` → `History.deserialize_history()`. This is the most expensive part per chat.

Split into two phases:

1. **Phase 1 (startup):** Read `chat.json`, parse top-level JSON, deserialize metadata fields (`id`, `name`, `type`, `created_at`, `last_message`) and `log`. Store the `agents` JSON fragment as a raw string in `AgentContext._raw_agents: str | None`. Skip `_deserialize_agents()`.

2. **Phase 2 (on demand):** When a chat is actually accessed (user opens it, agent starts working), call `AgentContext._ensure_hydrated()`. This deserializes `_raw_agents` into full Agent/History objects and sets `_raw_agents = None` to free the raw string.

`AgentContext.output()` (used for the sidebar list) works without hydration — it only needs metadata and log fields available after phase 1.

Any code path that accesses `agent0` or the agent chain must call `_ensure_hydrated()` first. Key entry points: `use_context()` (before message processing), `chat_export`, `persist_chat.save_tmp_chat`.

**Files:** `persist_chat.py`, `agent.py`.

### 4. Scoped dirty signals

**Goal:** Stop broadcasting push updates to clients not viewing the active chat.

Currently `Log._notify_state_monitor()` calls `mark_dirty_all` when a new log item is created. This was necessary because `contexts[]` (with updated `log_version`) was included in every push — other tabs needed it to update their sidebar.

After change 1 (conditional chat list), sidebar metadata is decoupled from log pushes. Therefore:

- `Log._notify_state_monitor()` switches from `mark_dirty_all` to `mark_dirty_for_context`. Only clients projecting this context receive a push.
- `Log._notify_state_monitor_for_context_update()` (existing item updates during streaming) remains unchanged — already uses `mark_dirty_for_context`.
- Operations that actually change the chat list (create, remove, rename, running-status toggle) call `mark_dirty_all` and update `_chat_list_updated_at`. These are infrequent events.

**Files:** `log.py`, API handlers that mutate the chat list (`chat_create.py`, `chat_remove.py`, `chat_reset.py`, and others that trigger `mark_dirty_all` today).

### 5. Batched DOM rendering

**Goal:** Eliminate UI freezes during mass render of large chat histories.

When `_massRender` is true (chat switch, initial load), instead of synchronously iterating all messages in `setMessages`, process them in batches of 20 via `requestAnimationFrame`. The first batch renders immediately so the user sees content instantly; subsequent batches render across frames without blocking input.

The prepend path for `/chat_logs` responses inserts DOM nodes before existing content and preserves scroll position by measuring `scrollHeight` before and after insertion and adjusting `scrollTop`.

A loading indicator at the top of `#chat-history` appears when `has_earlier_logs` is true and disappears when all earlier logs have been loaded or the request completes.

**Files:** `messages.js`, `index.js`, minimal CSS for the loading indicator.

## Files changed (summary)

| File | Changes |
|------|---------|
| `helpers/state_snapshot.py` | `chat_list_since` in request, conditional `contexts`/`tasks`, `chat_list_updated_at` + `has_earlier_logs` in snapshot, `tail` parameter passthrough |
| `helpers/log.py` | `tail` param in `output()`, switch `_notify_state_monitor` to `mark_dirty_for_context` |
| `helpers/state_monitor.py` | No structural changes; existing `mark_dirty_for_context` and `mark_dirty_all` used as-is |
| `helpers/persist_chat.py` | Two-phase deserialization: metadata-only in `load_tmp_chats`, lazy `_deserialize_agents` |
| `agent.py` | `_raw_agents` field, `_ensure_hydrated()` method; `output()` works without hydration, guards on paths accessing `agent0`/chain |
| `api/chat_logs.py` | New endpoint for paginated log history |
| `api/chat_create.py`, `chat_remove.py`, `chat_reset.py` | Update `_chat_list_updated_at` on list mutations |
| `run_ui.py` | No edit needed — new `chat_logs.py` is auto-discovered by `load_classes_from_folder` in `run_ui.py` |
| `webui/index.js` | Track `chat_list_updated_at`, pass `chat_list_since`, handle `has_earlier_logs`, call `/chat_logs` |
| `webui/js/messages.js` | Batched `requestAnimationFrame` rendering, prepend logic with scroll preservation |
| `webui/components/sync/sync-store.js` | Pass `chat_list_since` in state request payload |
| `webui/components/sidebar/chats/chats-store.js` | Handle `null` contexts gracefully |
| `webui/components/sidebar/tasks/tasks-store.js` | Handle `null` tasks gracefully |

## Testing

- **Unit tests** for `Log.output(tail=N)`: verify correct tail slicing, `has_earlier_logs` flag, edge cases (empty log, tail > total items).
- **Unit tests** for `build_snapshot_from_request`: verify `contexts` is `None` when `chat_list_since` is current, full list when stale.
- **Unit tests** for lazy deserialization: verify `output()` works without hydration, `_ensure_hydrated()` produces valid agents.
- **Unit tests** for `/chat_logs` endpoint: pagination correctness, boundary conditions.
- **Integration test**: start server with multiple chats, verify startup time improvement (no full History deserialization).
- **Manual testing**: verify chat switching speed, scroll-up loading, no regressions in streaming, sidebar updates on chat create/remove.

## Out of scope

- Virtual scrolling / DOM virtualization (disproportionate complexity for 10–30 chats).
- SQLite index for chat metadata (unnecessary at current scale).
- LRU eviction of inactive `AgentContext` from memory (can be added later if needed).
- Chat list pagination in the sidebar (30 items is fine).
