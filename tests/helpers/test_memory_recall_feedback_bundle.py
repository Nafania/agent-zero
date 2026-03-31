"""Recall search results → plain texts + feedback rows (memory_id, dataset, context_id)."""

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from plugins._memory.helpers.memory import recall_text_and_feedback_items


def test_recall_bundle_extracts_id_and_dataset_from_meta_prefix():
    meta = {"id": "doc-99", "dataset": "default", "area": "fragments"}
    raw = f"[META:{json.dumps(meta)}]\nrecalled body text"
    texts, items = recall_text_and_feedback_items(
        [raw],
        5,
        context_id="ctx-42",
        fallback_dataset="projects_x",
        kind="memory",
    )
    assert texts == ["recalled body text"]
    assert len(items) == 1
    assert items[0]["memory_id"] == "doc-99"
    assert items[0]["dataset"] == "default"
    assert items[0]["context_id"] == "ctx-42"
    assert items[0]["kind"] == "memory"
    assert items[0]["text"] == "recalled body text"


def test_recall_bundle_uses_fallback_dataset_when_missing_in_metadata():
    texts, items = recall_text_and_feedback_items(
        ["plain chunk without meta"],
        3,
        context_id="c1",
        fallback_dataset="my_ds",
        kind="solution",
    )
    assert items[0]["dataset"] == "my_ds"
    assert items[0]["kind"] == "solution"
