# Agent Zero: Memory Settings Cleanup for Cognee

**Date:** 2026-03-25  
**Scope:** Memory settings UI + backend settings + memory runtime pipeline  
**Goal:** Remove obsolete A0 memory knobs that duplicate Cognee behavior and implement working Cognee feedback loop.

---

## Final Product Decision

User decision is explicit:

1. Remove these settings completely (UI + settings schema + user-config references):
   - `agent_memory_subdir` ("Memory Subdirectory")
   - `memory_recall_query_prep` ("Auto-recall AI query preparation")
   - `memory_recall_post_filter` ("Auto-recall AI post-filtering")
   - `memory_memorize_consolidation` ("Auto-memorize AI consolidation")
   - `memory_memorize_replace_threshold` ("Auto-memorize replacement threshold")
2. Remove `memory_recall_similarity_threshold` as user-facing control (no real effect in current runtime).
3. Implement end-to-end working `cognee feedback` flow for recall results.

Principle: memory quality controls should live in Cognee-native mechanisms, not duplicated A0-side heuristics.

---

## Current-State Problems

- A0 has multiple legacy toggles around recall/memorize quality that either:
  - duplicate Cognee logic, or
  - are partially wired and misleading.
- UI communicates semantics that are no longer true after migration to Cognee.
- Feedback capability exists as configuration intent but is not implemented as a clear runtime loop with user signals.

---

## Target Architecture

### A. Remove A0-side quality heuristics

Delete A0 features that perform LLM pre/post processing around recall or replacement heuristics around memorization.

Result:
- Recall pipeline: direct retrieval from Cognee with core limits only.
- Memorize pipeline: direct save flow without A0-side "replace threshold" / "consolidation" toggles.

### A1. Memory path behavior after removing `agent_memory_subdir`

`agent_memory_subdir` is removed as a user-editable setting only.  
Runtime memory isolation by active project must remain via canonical resolver logic:

- if project context is active: use project dataset namespace (`projects/<name>` mapping)
- otherwise: use `default` dataset

No free-form memory path setting remains in UI.

### B. Keep minimal, understandable controls

Keep controls that are still operationally meaningful:
- recall on/off
- delayed recall on/off
- recall interval
- recall history length
- top-k search/use limits

All removed controls disappear from UI and settings output to avoid "dead knobs."

### C. Add working Cognee feedback loop

Implement explicit path:
1. Recall step stores retrievable identifiers for returned results (result metadata).
2. UI/API accepts feedback signal on recalled item (`positive` / `negative`).
3. Backend forwards feedback to Cognee feedback API/store (or fallback persistence queue if immediate Cognee API call unavailable).
4. Feedback data is traceable in logs/metrics.

If Cognee API shape differs by version, add adapter layer with graceful fallback and clear warning logs.

### C1. Feedback data contract

Minimum payload:
- `context_id` (chat/session identifier)
- `dataset` (resolved dataset name)
- `memory_id` (stable id from metadata; synthetic hash only if id missing)
- `feedback` (`positive` or `negative`)
- `reason` (optional short text)

Backend requirements:
- authenticated user only (same auth/CSRF model as existing API handlers)
- reject invalid `feedback` values with 4xx
- structured logs for `forwarded`, `queued`, `failed`

Fallback durability requirement:
- fallback queue must be disk-backed under `usr/`, not in-memory
- target delivery semantics: at-least-once

---

## Component-by-Component Changes

### 1) Settings schema and defaults

Remove keys from:
- `helpers/settings.py` type definitions
- defaults in `get_default_settings()`
- conversions and runtime application paths that reference removed keys

Backward compatibility:
- On read of old `settings.json`, ignore removed keys silently.
- Do not re-emit removed keys in API output.
- On settings save/update, strip removed keys instead of failing validation.

### 2) Memory settings UI

Update `webui/components/settings/agent/memory.html`:
- Remove fields listed in final decision.
- Keep only active controls.
- Add short helper text for feedback feature once endpoint is ready.

### 3) Recall extension cleanup

Update `extensions/python/message_loop_prompts_after/_50_recall_memories.py`:
- Remove query-prep branch and post-filter branch.
- Remove references to removed thresholds.
- Keep retrieval limits and extras injection behavior.

Similarity threshold policy:
- `memory_recall_similarity_threshold` is removed from UI and settings API.
- no hidden fallback threshold is introduced in A0.
- if Cognee internally applies its own relevance threshold, that remains Cognee-native behavior.

### 4) Memorize extension cleanup

Update:
- `extensions/python/monologue_end/_50_memorize_fragments.py`
- `extensions/python/monologue_end/_51_memorize_solutions.py`

Changes:
- remove replacement-threshold behavior and related logic paths.
- remove consolidation-toggle-dependent behavior.
- keep straightforward memorize flow.

### 5) Cognee feedback feature

Add API endpoint/action for feedback submission, expected payload:
- context/chat identifier
- recalled item identifier (or stable synthetic key)
- feedback value (positive/negative)
- optional reason text

Add backend service helper:
- validates payload
- maps to Cognee feedback call
- handles retries/fallback queue/logging

Add UI hook:
- feedback controls on recalled memories/solutions (where displayed)
- confirmation state and error state

---

## Rollout Plan

### Phase 1 (single cleanup release)

- Remove obsolete settings from UI and settings schema.
- Simplify recall/memorize extensions.
- Introduce Cognee feedback API + wiring.
- Add migration notes in changelog.

No dual-mode required because user explicitly requested full removal now.

### Phase 2 (hardening)

- Add telemetry dashboard entries for:
  - recall count
  - feedback submitted count
  - feedback success/fail ratio
- tighten tests around feedback adapter and failure paths.

---

## Risks and Mitigations

- **Risk:** behavior drift after removal of A0 filters.
  - **Mitigation:** verify recall relevance on representative chats; tune Cognee-native parameters instead.

- **Risk:** old configs still contain removed keys.
  - **Mitigation:** tolerant loader ignores unknown/removed fields.

- **Risk:** Cognee feedback API instability/version differences.
  - **Mitigation:** adapter abstraction + fallback queue + explicit warning logs.

---

## Test Plan

1. **Settings/API contract**
   - Removed keys are not returned by settings API.
   - Old settings files with removed keys still load.
   - Settings update endpoints accept payloads containing removed keys by stripping them.

2. **Recall pipeline**
   - Recall works without query-prep/post-filter toggles.
   - Delayed recall and interval behaviors unchanged.

3. **Memorize pipeline**
   - Fragments and solutions still auto-memorize when enabled.
   - No references to removed replacement/consolidation controls remain.

4. **Feedback flow**
   - Submit positive/negative feedback for a recalled item.
   - Backend forwards to Cognee adapter and reports success.
   - Failure path logs and returns actionable error.
   - Auth/CSRF checks are enforced.
   - Fallback queue survives restart and retries delivery.

5. **Regression**
   - Memory dashboard search/delete/update unaffected.

---

## Acceptance Criteria

- Removed settings are gone from UI, settings schema, and runtime paths.
- No dead references to removed keys remain in backend.
- Cognee feedback can be submitted and is persisted/forwarded successfully.
- Tests pass for updated recall/memorize/feedback behavior.

