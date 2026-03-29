"""Tests for recall extension helpers and memory.recall_text_and_feedback_items."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from extensions.python.message_loop_prompts_after._50_recall_memories import (
    _write_extras,
    SEARCH_TIMEOUT,
)
from helpers.memory import recall_text_and_feedback_items

_FB_KW = {"context_id": "ctx", "fallback_dataset": "fd", "kind": "memory"}


class TestRecallTextAndFeedbackItems:
    def test_empty_results(self):
        assert recall_text_and_feedback_items(None, 10, **_FB_KW) == ([], [])
        assert recall_text_and_feedback_items([], 10, **_FB_KW) == ([], [])

    def test_string_results(self):
        results = ["Hello", "World"]
        texts, items = recall_text_and_feedback_items(results, 10, **_FB_KW)
        assert texts == ["Hello", "World"]
        assert len(items) == 2
        assert all(i["kind"] == "memory" for i in items)

    def test_strips_meta_header(self):
        meta = {"id": "abc", "dataset": "fd"}
        meta_text = f'[META:{json.dumps(meta)}]\nActual content'
        texts, _ = recall_text_and_feedback_items([meta_text], 10, **_FB_KW)
        assert texts == ["Actual content"]

    def test_respects_limit(self):
        results = [f"item_{i}" for i in range(20)]
        texts, _ = recall_text_and_feedback_items(results, 5, **_FB_KW)
        assert len(texts) == 5

    def test_object_results_converted_to_str(self):
        obj = SimpleNamespace(search_result="inner text")
        texts, _ = recall_text_and_feedback_items([obj], 10, **_FB_KW)
        assert len(texts) == 1
        assert "inner text" in texts[0]

    def test_meta_without_newline_kept_as_is(self):
        text = "[META:no closing bracket"
        texts, _ = recall_text_and_feedback_items([text], 10, **_FB_KW)
        assert texts == [text]


class TestWriteExtras:
    def test_no_results_clears_extras(self):
        agent = MagicMock()
        extras = {}
        log_item = MagicMock()
        _write_extras(agent, extras, [], [], log_item, [])
        assert "memories" not in extras
        assert "solutions" not in extras
        log_item.update.assert_called_with(heading="No memories or solutions found")

    def test_memories_written(self):
        agent = MagicMock()
        agent.parse_prompt.return_value = "parsed_memories"
        extras = {}
        log_item = MagicMock()
        _write_extras(agent, extras, ["mem1", "mem2"], [], log_item, [])
        assert extras["memories"] == "parsed_memories"
        assert "solutions" not in extras

    def test_solutions_written(self):
        agent = MagicMock()
        agent.parse_prompt.return_value = "parsed_solutions"
        extras = {}
        log_item = MagicMock()
        _write_extras(agent, extras, [], ["sol1"], log_item, [])
        assert "memories" not in extras
        assert extras["solutions"] == "parsed_solutions"

    def test_both_memories_and_solutions(self):
        agent = MagicMock()
        agent.parse_prompt.side_effect = lambda tmpl, **kw: f"parsed_{tmpl}"
        extras = {}
        log_item = MagicMock()
        _write_extras(agent, extras, ["mem1"], ["sol1"], log_item, [])
        assert "memories" in extras
        assert "solutions" in extras

    def test_feedback_items_passed_to_log(self):
        agent = MagicMock()
        agent.parse_prompt.return_value = "x"
        extras = {}
        log_item = MagicMock()
        fb = [{"memory_id": "m1", "dataset": "d", "context_id": "", "kind": "memory", "text": "t"}]
        _write_extras(agent, extras, ["a"], [], log_item, fb)
        log_item.update.assert_any_call(memory_feedback_items=fb)


class TestConstants:
    def test_search_timeout_is_positive(self):
        assert SEARCH_TIMEOUT > 0
