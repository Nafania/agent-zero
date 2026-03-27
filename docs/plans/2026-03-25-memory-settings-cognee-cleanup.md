# Memory Settings Cognee Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove obsolete A0 memory settings/endpoints from UI and backend, and implement a working end-to-end Cognee feedback submission flow.

**Architecture:** Simplify memory behavior by deleting A0-side recall/memorize quality toggles and relying on Cognee-native retrieval/memify behavior. Add a dedicated feedback API adapter path that records feedback with durable fallback and authenticated access. Keep project-memory isolation via canonical context resolver (project dataset or default).

**Tech Stack:** Python, Flask API handlers, existing Agent Zero extensions, web UI HTML/JS, pytest

**Spec:** `docs/superpowers/specs/2026-03-25-memory-settings-cognee-cleanup-design.md`

---

### Task 1: Remove obsolete memory settings from backend schema

**Files:**
- Modify: `python/helpers/settings.py`
- Test: `tests/helpers/test_settings_memory_cleanup.py`

- [ ] **Step 1: Write failing settings compatibility tests**

Create `tests/helpers/test_settings_memory_cleanup.py` with tests that assert:
- removed keys are not present in default settings output
- loading a settings payload containing removed keys does not fail
- save/update strips removed keys

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/helpers/test_settings_memory_cleanup.py -v`  
Expected: FAIL because removed keys still exist and are emitted.

- [ ] **Step 3: Remove keys from `Settings` TypedDict and defaults**

In `python/helpers/settings.py`:
- remove:
  - `agent_memory_subdir`
  - `memory_recall_query_prep`
  - `memory_recall_post_filter`
  - `memory_recall_similarity_threshold`
  - `memory_memorize_consolidation`
  - `memory_memorize_replace_threshold`
- update `get_default_settings()` accordingly
- ensure normalize/save paths tolerate stale removed keys

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/helpers/test_settings_memory_cleanup.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add python/helpers/settings.py tests/helpers/test_settings_memory_cleanup.py
git commit -m "refactor: remove obsolete memory settings from backend schema"
```

---

### Task 2: Remove obsolete controls from memory settings UI

**Files:**
- Modify: `webui/components/settings/agent/memory.html`
- Test: `tests/webui/test_memory_settings_removed_controls.py`

- [ ] **Step 1: Write failing UI contract test**

Create `tests/webui/test_memory_settings_removed_controls.py` that checks the rendered/served settings template does not include removed labels/controls:
- Memory Subdirectory
- Auto-recall AI query preparation
- Auto-recall AI post-filtering
- Memory auto-recall similarity threshold
- Auto-memorize AI consolidation
- Auto-memorize replacement threshold

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/webui/test_memory_settings_removed_controls.py -v`  
Expected: FAIL because controls still exist.

- [ ] **Step 3: Remove controls from `memory.html`**

In `webui/components/settings/agent/memory.html` remove corresponding field blocks and keep only active controls.

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/webui/test_memory_settings_removed_controls.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add webui/components/settings/agent/memory.html tests/webui/test_memory_settings_removed_controls.py
git commit -m "feat: simplify memory settings UI by removing obsolete controls"
```

---

### Task 3: Simplify recall extension (remove query prep/post-filter/threshold logic)

**Files:**
- Modify: `python/extensions/message_loop_prompts_after/_50_recall_memories.py`
- Modify: `python/extensions/message_loop_prompts_after/_91_recall_wait.py`
- Test: `tests/extensions/test_recall_memories_cleanup.py`

- [ ] **Step 1: Write failing recall behavior tests**

Create `tests/extensions/test_recall_memories_cleanup.py` asserting:
- recall works without `memory_recall_query_prep` and `memory_recall_post_filter`
- removed settings are not read from config
- delayed behavior remains unchanged

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/extensions/test_recall_memories_cleanup.py -v`  
Expected: FAIL due current branches reading removed settings.

- [ ] **Step 3: Remove legacy branches**

In `_50_recall_memories.py`:
- remove utility model query-prep branch
- remove post-filter branch
- remove similarity-threshold references
- keep direct Cognee retrieval + top-k limits + extras injection

In `_91_recall_wait.py`:
- keep delayed-await behavior only
- ensure no dependency on removed settings

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/extensions/test_recall_memories_cleanup.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add python/extensions/message_loop_prompts_after/_50_recall_memories.py python/extensions/message_loop_prompts_after/_91_recall_wait.py tests/extensions/test_recall_memories_cleanup.py
git commit -m "refactor: remove legacy recall query prep and post-filter logic"
```

---

### Task 4: Simplify memorize extensions (remove consolidation/replacement toggles)

**Files:**
- Modify: `python/extensions/monologue_end/_50_memorize_fragments.py`
- Modify: `python/extensions/monologue_end/_51_memorize_solutions.py`
- Test: `tests/extensions/test_memorize_cleanup.py`

- [ ] **Step 1: Write failing memorize tests**

Create `tests/extensions/test_memorize_cleanup.py` asserting:
- memorize flow runs with only `memory_memorize_enabled`
- no usage of `memory_memorize_consolidation`
- no usage of `memory_memorize_replace_threshold`

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/extensions/test_memorize_cleanup.py -v`  
Expected: FAIL due current threshold/consolidation references.

- [ ] **Step 3: Remove replacement/consolidation branches**

Update both memorize files to:
- remove threshold-based deletion/replacement logic
- remove consolidation-flag branches
- keep straightforward extract-and-insert behavior

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/extensions/test_memorize_cleanup.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add python/extensions/monologue_end/_50_memorize_fragments.py python/extensions/monologue_end/_51_memorize_solutions.py tests/extensions/test_memorize_cleanup.py
git commit -m "refactor: simplify auto-memorize flow to cognee-native behavior"
```

---

### Task 5: Implement Cognee feedback backend (API + adapter + durable fallback)

**Files:**
- Create: `python/api/memory_feedback.py`
- Create: `python/helpers/cognee_feedback.py`
- Modify: `python/helpers/memory.py`
- Test: `tests/api/test_memory_feedback.py`
- Test: `tests/helpers/test_cognee_feedback.py`

- [ ] **Step 1: Write failing backend feedback tests**

Create tests that verify:
- authenticated request with valid payload returns success
- invalid feedback value returns 4xx
- adapter forward path invoked
- fallback queue is persisted under `usr/` when forward fails
- queued feedback retries are idempotent-safe

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/api/test_memory_feedback.py tests/helpers/test_cognee_feedback.py -v`  
Expected: FAIL since endpoint/helper do not exist.

- [ ] **Step 3: Pre-flight Cognee feedback API discovery**

Before writing adapter code, verify Cognee surface on the installed version:
- exact module/function used to submit feedback
- required payload shape
- return values and error semantics

If no native feedback API exists, define adapter mode as:
- queue-only with structured logs (`queued`, `failed`)
- explicit TODO marker for native forward integration.

- [ ] **Step 4: Add Cognee feedback helper**

Implement `python/helpers/cognee_feedback.py`:
- payload validation (`context_id`, `dataset`, `memory_id`, `feedback`, optional `reason`)
- adapter call into Cognee feedback surface
- disk-backed queue file in `usr/` for fallback
- retry method with structured status logs (`forwarded`, `queued`, `failed`)

- [ ] **Step 5: Add feedback API handler**

Implement `python/api/memory_feedback.py`:
- inherits `ApiHandler`
- enforces existing auth + CSRF behavior
- exposes action to submit feedback and action to retry queue (optional admin/internal)
- follows auto-discovery convention from `run_ui.py` (`python/api/*.py` -> `/<module_name>`)

- [ ] **Step 6: Ensure recall path carries stable memory IDs**

Update `python/helpers/memory.py` and/or recall extension path so recalled entries provide stable IDs suitable for feedback submission.

- [ ] **Step 7: Run tests to verify pass**

Run: `pytest tests/api/test_memory_feedback.py tests/helpers/test_cognee_feedback.py -v`  
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add python/api/memory_feedback.py python/helpers/cognee_feedback.py python/helpers/memory.py tests/api/test_memory_feedback.py tests/helpers/test_cognee_feedback.py
git commit -m "feat: add cognee feedback api with durable fallback queue"
```

---

### Task 6: Wire feedback controls in UI

**Files:**
- Modify: `webui/components/chat/chat-controls.js`
- Modify: `webui/components/chat/chat-message.html`
- Modify: `webui/components/settings/agent/memory.html`
- Test: `tests/webui/test_memory_feedback_ui.py`

- [ ] **Step 1: Write failing UI interaction test**

Create `tests/webui/test_memory_feedback_ui.py` with repository-realistic scope:
- static source assertions that feedback controls are present in chat UI templates/scripts
- static source assertions that request path targets `/memory_feedback`
- static source assertion that memory settings page includes feedback helper text

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/webui/test_memory_feedback_ui.py -v`  
Expected: FAIL since controls do not exist.

- [ ] **Step 3: Implement UI controls and request path**

Update chat message rendering and controls:
- add thumbs up/down controls for recalled memory items
- call `/memory_feedback` endpoint
- show optimistic pending + success/error feedback state
- add short helper text in `memory.html` describing that user feedback improves recall relevance

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/webui/test_memory_feedback_ui.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add webui/components/chat/chat-controls.js webui/components/chat/chat-message.html tests/webui/test_memory_feedback_ui.py
git commit -m "feat: add user feedback controls for recalled cognee memories"
```

---

### Task 7: End-to-end regression and cleanup sweep

**Files:**
- Verify: `python/helpers/settings.py`
- Verify: `python/extensions/message_loop_prompts_after/_50_recall_memories.py`
- Verify: `python/extensions/monologue_end/_50_memorize_fragments.py`
- Verify: `python/extensions/monologue_end/_51_memorize_solutions.py`
- Verify: `python/api/memory_dashboard.py`
- Verify: `webui/components/settings/agent/memory.html`

- [ ] **Step 1: Grep for removed keys and dead references**

From repo root (`agent-zero/`), run:
`rg "agent_memory_subdir|memory_recall_query_prep|memory_recall_post_filter|memory_recall_similarity_threshold|memory_memorize_consolidation|memory_memorize_replace_threshold" .`

Expected: no runtime references, only migration docs/changelog if any.

- [ ] **Step 2: Run focused memory test suite**

Run:
`pytest tests/api/test_memory_feedback.py tests/helpers/test_cognee_feedback.py tests/extensions/test_recall_memories_cleanup.py tests/extensions/test_memorize_cleanup.py -v`

Expected: PASS.

- [ ] **Step 3: Run broad non-integration suite**

Run: `pytest tests/ -m "not integration" -x -q`  
Expected: PASS.

- [ ] **Step 4: Commit final sweep**

```bash
git add tests/api/test_memory_feedback.py tests/helpers/test_cognee_feedback.py tests/extensions/test_recall_memories_cleanup.py tests/extensions/test_memorize_cleanup.py
git commit -m "test: finalize memory cleanup and cognee feedback integration"
```

- [ ] **Step 5: Add migration/changelog note**

Modify release notes/changelog file used by this repository and include:
- removed memory settings list
- compatibility behavior for old settings payloads
- new `/memory_feedback` endpoint and fallback semantics

