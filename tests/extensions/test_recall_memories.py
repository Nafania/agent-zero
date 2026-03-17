"""Tests for _50_recall_memories.py — session-isolated cognee.search."""

import sys
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from python.extensions.message_loop_prompts_after._50_recall_memories import (
    _to_strings,
    _write_extras,
    SEARCH_TIMEOUT,
)


# --- _to_strings ---

class TestToStrings:
    def test_empty_results(self):
        assert _to_strings(None, 10) == []
        assert _to_strings([], 10) == []

    def test_string_results(self):
        results = ["Hello", "World"]
        texts = _to_strings(results, 10)
        assert texts == ["Hello", "World"]

    def test_strips_meta_header(self):
        meta_text = '[META:{"id": "abc"}]\nActual content'
        texts = _to_strings([meta_text], 10)
        assert texts == ["Actual content"]

    def test_respects_limit(self):
        results = [f"item_{i}" for i in range(20)]
        texts = _to_strings(results, 5)
        assert len(texts) == 5

    def test_object_results_converted_to_str(self):
        obj = SimpleNamespace(search_result="inner text")
        texts = _to_strings([obj], 10)
        assert len(texts) == 1
        assert "inner text" in texts[0]

    def test_meta_without_newline_kept_as_is(self):
        text = "[META:no closing bracket"
        texts = _to_strings([text], 10)
        assert texts == [text]


# --- _write_extras ---

class TestWriteExtras:
    def test_no_results_clears_extras(self):
        agent = MagicMock()
        extras = {}
        log_item = MagicMock()
        _write_extras(agent, extras, [], [], log_item)
        assert "memories" not in extras
        assert "solutions" not in extras
        log_item.update.assert_called_with(heading="No memories or solutions found")

    def test_memories_written(self):
        agent = MagicMock()
        agent.parse_prompt.return_value = "parsed_memories"
        extras = {}
        log_item = MagicMock()
        _write_extras(agent, extras, ["mem1", "mem2"], [], log_item)
        assert extras["memories"] == "parsed_memories"
        assert "solutions" not in extras

    def test_solutions_written(self):
        agent = MagicMock()
        agent.parse_prompt.return_value = "parsed_solutions"
        extras = {}
        log_item = MagicMock()
        _write_extras(agent, extras, [], ["sol1"], log_item)
        assert "memories" not in extras
        assert extras["solutions"] == "parsed_solutions"

    def test_both_memories_and_solutions(self):
        agent = MagicMock()
        agent.parse_prompt.side_effect = lambda tmpl, **kw: f"parsed_{tmpl}"
        extras = {}
        log_item = MagicMock()
        _write_extras(agent, extras, ["mem1"], ["sol1"], log_item)
        assert "memories" in extras
        assert "solutions" in extras


# --- SEARCH_TIMEOUT ---

class TestConstants:
    def test_search_timeout_is_positive(self):
        assert SEARCH_TIMEOUT > 0
