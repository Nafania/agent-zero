# Migration: memory settings cleanup (Cognee)

**Branch:** `feat/memory-cognee-cleanup`  
**Date:** 2026-03-26

## Removed settings

These keys are no longer defined in settings or exposed in the WebUI. Legacy values may still exist in saved `settings.json`; they are ignored at runtime.

| Key | Notes |
|-----|--------|
| `agent_memory_subdir` | Removed as a user control. Memory namespace follows active project / default dataset resolution only. |
| `memory_recall_query_prep` | Legacy A0-side recall preprocessing; ignored. |
| `memory_recall_post_filter` | Legacy A0-side recall post-filtering; ignored. |
| `memory_recall_similarity_threshold` | Removed as a user-facing control (no longer applied in the recall pipeline). |
| `memory_memorize_consolidation` | Legacy memorize consolidation toggle; ignored. |
| `memory_memorize_replace_threshold` | Legacy replacement threshold; ignored. |

## New behavior: `/memory_feedback`

Recall attaches structured rows (`memory_feedback_items`) to the util log entry. The UI can submit per-item feedback (`positive` / `negative`, optional `reason`) to **`POST /memory_feedback`**, which forwards signals to Cognee (with disk-backed queuing when forwarding is deferred).

Payload fields include: `context_id`, `dataset`, `memory_id`, `feedback`, optional `reason`, and `kind` (`memory` | `solution`).

## Action for operators

- Remove obsolete keys from custom settings templates or automation if you copy `settings.json` between environments.
- Tune retrieval quality in Cognee-native configuration rather than the removed A0 knobs.
