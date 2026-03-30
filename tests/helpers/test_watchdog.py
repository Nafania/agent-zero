"""Tests for helpers/watchdog.py — pattern matching, normalization, and public API."""

import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from helpers.watchdog import (
    _compile_matcher,
    _compile_single_matcher,
    _covering_roots,
    _normalize_events,
    _normalize_patterns,
    _normalize_debounce,
    _VALID_EVENTS,
    add_watchdog,
    remove_watchdog,
    clear_watchdogs,
)


class TestCompileMatcher:
    """_compile_single_matcher treats empty patterns as 'match all',
    so ignore_patterns=[] means 'ignore everything'. Tests pass realistic
    ignore patterns (the defaults) to exercise the combined matcher."""

    def test_default_patterns_match_everything(self, tmp_path):
        root = str(tmp_path)
        ignore = ["**/__pycache__", "**/__pycache__/*", "**/*.pyc"]
        matcher = _compile_matcher(root, ["**/*"], ignore)
        assert matcher(os.path.join(root, "foo.py")) is True
        assert matcher(os.path.join(root, "sub", "bar.txt")) is True

    def test_ignore_patterns_exclude(self, tmp_path):
        root = str(tmp_path)
        matcher = _compile_matcher(root, ["**/*"], ["*.pyc"])
        assert matcher(os.path.join(root, "mod.py")) is True
        assert matcher(os.path.join(root, "mod.pyc")) is False

    def test_specific_include_pattern(self, tmp_path):
        root = str(tmp_path)
        ignore = ["**/__pycache__", "**/*.pyc"]
        matcher = _compile_matcher(root, ["*.yaml"], ignore)
        assert matcher(os.path.join(root, "config.yaml")) is True
        assert matcher(os.path.join(root, "config.json")) is False

    def test_pycache_ignored_by_default_ignore(self, tmp_path):
        root = str(tmp_path)
        ignore = ["**/__pycache__", "**/__pycache__/*", "**/*.pyc"]
        matcher = _compile_matcher(root, ["**/*"], ignore)
        assert matcher(os.path.join(root, "src", "__pycache__", "mod.cpython-311.pyc")) is False

    def test_nested_path_pattern(self, tmp_path):
        root = str(tmp_path)
        ignore = ["**/__pycache__", "**/*.pyc"]
        matcher = _compile_matcher(root, ["src/**/*.py"], ignore)
        assert matcher(os.path.join(root, "src", "sub", "app.py")) is True
        assert matcher(os.path.join(root, "lib", "sub", "app.py")) is False


class TestCompileSingleMatcher:
    def test_star_star_matches_all(self, tmp_path):
        root = str(tmp_path)
        matcher = _compile_single_matcher(root, ["**"])
        assert matcher(os.path.join(root, "anything")) is True

    def test_star_matches_all(self, tmp_path):
        root = str(tmp_path)
        matcher = _compile_single_matcher(root, ["*"])
        assert matcher(os.path.join(root, "anything")) is True

    def test_empty_patterns_match_all(self, tmp_path):
        root = str(tmp_path)
        matcher = _compile_single_matcher(root, [])
        assert matcher(os.path.join(root, "anything")) is True

    def test_extension_filter(self, tmp_path):
        root = str(tmp_path)
        matcher = _compile_single_matcher(root, ["*.md"])
        assert matcher(os.path.join(root, "README.md")) is True
        assert matcher(os.path.join(root, "README.txt")) is False


class TestCoveringRoots:
    def test_deduplicates_identical(self):
        result = _covering_roots(["/a/b", "/a/b", "/a/b"])
        assert result == {"/a/b"}

    def test_parent_covers_child(self):
        result = _covering_roots(["/a", "/a/b", "/a/b/c"])
        assert result == {"/a"}

    def test_siblings_kept(self):
        result = _covering_roots(["/a/b", "/a/c"])
        assert result == {"/a/b", "/a/c"}

    def test_empty_input(self):
        assert _covering_roots([]) == set()

    def test_no_false_prefix_match(self):
        result = _covering_roots(["/app", "/application"])
        assert result == {"/app", "/application"}


class TestNormalizeEvents:
    def test_all_keyword(self):
        assert _normalize_events("all") == _VALID_EVENTS

    def test_specific_events(self):
        result = _normalize_events(["create", "modify"])
        assert result == frozenset({"create", "modify"})

    def test_aliases_normalized(self):
        result = _normalize_events(["created", "modified", "deleted", "moved"])
        assert result == _VALID_EVENTS

    def test_empty_list_returns_all(self):
        assert _normalize_events([]) == _VALID_EVENTS

    def test_invalid_event_raises(self):
        with pytest.raises(ValueError, match="Unsupported"):
            _normalize_events(["explode"])


class TestNormalizePatterns:
    def test_none_returns_default(self):
        result = _normalize_patterns(None)
        assert result == ["**/*"]

    def test_empty_list_returns_default(self):
        result = _normalize_patterns([])
        assert result == ["**/*"]

    def test_custom_patterns_preserved(self):
        result = _normalize_patterns(["*.py", "*.yaml"])
        assert result == ["*.py", "*.yaml"]

    def test_backslashes_normalized(self):
        result = _normalize_patterns(["src\\helpers\\*.py"])
        assert result == ["src/helpers/*.py"]

    def test_whitespace_stripped(self):
        result = _normalize_patterns(["  *.py  "])
        assert result == ["*.py"]

    def test_custom_default(self):
        result = _normalize_patterns(None, default=["*.txt"])
        assert result == ["*.txt"]


class TestNormalizeDebounce:
    def test_zero_ok(self):
        assert _normalize_debounce(0) == 0

    def test_positive_ok(self):
        assert _normalize_debounce(0.5) == 0.5

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="debounce"):
            _normalize_debounce(-1)


class TestAddWatchdog:
    def test_handler_required(self):
        with pytest.raises(ValueError, match="handler"):
            add_watchdog(id="test-no-handler", roots=["/tmp"])

    def test_add_and_remove(self, tmp_path):
        called = []
        add_watchdog(
            id="test-add-remove",
            roots=[str(tmp_path)],
            handler=lambda items: called.append(items),
        )
        removed = remove_watchdog("test-add-remove")
        assert removed is True

    def test_remove_nonexistent(self):
        removed = remove_watchdog("nonexistent-watch-id")
        assert removed is False

    def test_clear_all(self, tmp_path):
        add_watchdog(
            id="test-clear-1",
            roots=[str(tmp_path)],
            handler=lambda items: None,
        )
        add_watchdog(
            id="test-clear-2",
            roots=[str(tmp_path)],
            handler=lambda items: None,
        )
        clear_watchdogs()
        assert remove_watchdog("test-clear-1") is False
        assert remove_watchdog("test-clear-2") is False

    def test_handler_called_on_file_change(self, tmp_path):
        called = []
        add_watchdog(
            id="test-handler-trigger",
            roots=[str(tmp_path)],
            debounce=0,
            handler=lambda items: called.extend(items),
        )
        try:
            test_file = tmp_path / "trigger.txt"
            test_file.write_text("hello")
            deadline = time.monotonic() + 3
            while not called and time.monotonic() < deadline:
                time.sleep(0.1)
            assert len(called) > 0, "handler was not called within 3 seconds"
        finally:
            remove_watchdog("test-handler-trigger")

    def test_debounce_batches_events(self, tmp_path):
        """Multiple rapid file changes within the debounce window should be
        batched into a single handler call."""
        batches: list[list] = []
        add_watchdog(
            id="test-debounce-batch",
            roots=[str(tmp_path)],
            debounce=0.3,
            handler=lambda items: batches.append(list(items)),
        )
        try:
            for i in range(5):
                (tmp_path / f"file_{i}.txt").write_text(f"content {i}")
                time.sleep(0.02)
            deadline = time.monotonic() + 3
            while not batches and time.monotonic() < deadline:
                time.sleep(0.1)
            assert len(batches) > 0, "handler was never called"
            assert len(batches) <= 2, (
                f"expected batching to collapse events, got {len(batches)} calls"
            )
            total_items = sum(len(b) for b in batches)
            assert total_items >= 2, "expected multiple events in the batch"
        finally:
            remove_watchdog("test-debounce-batch")
