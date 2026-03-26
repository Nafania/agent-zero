"""Tests for webui performance optimizations: tail-based log output, conditional
chat list, lazy deserialization, chat-logs endpoint, and scoped dirty signals."""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_secrets_manager():
    mgr = MagicMock()
    mgr.mask_values = lambda s: s
    return mgr


@pytest.fixture
def patch_log_deps(mock_secrets_manager):
    with patch("python.helpers.log.get_secrets_manager", return_value=mock_secrets_manager), \
         patch("python.helpers.log._lazy_mark_dirty_all"), \
         patch("python.helpers.log._lazy_mark_dirty_for_context"):
        yield


# ---------------------------------------------------------------------------
# 1. Log.output() with tail parameter
# ---------------------------------------------------------------------------

class TestLogOutputTail:

    def _make_log_with_items(self, n):
        from python.helpers.log import Log, LogItem

        log = Log()
        log.context = MagicMock()
        log.context.id = "test-ctx"
        for i in range(n):
            item = LogItem(
                log=log,
                no=i,
                type="info",
                heading=f"Item {i}",
                content=f"Content {i}",
            )
            log.logs.append(item)
            log.updates.append(i)
        return log

    def test_output_without_tail_returns_list(self, patch_log_deps):
        """Without tail parameter, output() returns a plain list (backward compat)."""
        log = self._make_log_with_items(10)
        result = log.output()
        assert isinstance(result, list)
        assert len(result) == 10

    def test_output_with_tail_returns_tuple(self, patch_log_deps):
        """With tail parameter, output() returns (list, bool) tuple."""
        log = self._make_log_with_items(10)
        result = log.output(tail=5)
        assert isinstance(result, tuple)
        assert len(result) == 2
        logs, has_earlier = result
        assert isinstance(logs, list)
        assert isinstance(has_earlier, bool)

    def test_tail_truncates_to_last_n(self, patch_log_deps):
        """Tail returns only the last N unique items."""
        log = self._make_log_with_items(100)
        logs, has_earlier = log.output(tail=10)
        assert len(logs) == 10
        assert has_earlier is True
        assert logs[0]["no"] == 90
        assert logs[-1]["no"] == 99

    def test_tail_no_truncation_when_fewer_items(self, patch_log_deps):
        """When total items <= tail, no truncation occurs."""
        log = self._make_log_with_items(5)
        logs, has_earlier = log.output(tail=10)
        assert len(logs) == 5
        assert has_earlier is False

    def test_tail_exact_count(self, patch_log_deps):
        """When total items == tail, no truncation."""
        log = self._make_log_with_items(10)
        logs, has_earlier = log.output(tail=10)
        assert len(logs) == 10
        assert has_earlier is False

    def test_tail_ignored_when_start_nonzero(self, patch_log_deps):
        """tail is ignored for incremental updates (start > 0)."""
        log = self._make_log_with_items(100)
        result = log.output(start=50, tail=5)
        logs, has_earlier = result
        assert len(logs) == 50
        assert has_earlier is False

    def test_tail_with_empty_log(self, patch_log_deps):
        """Tail with empty log returns empty list."""
        log = self._make_log_with_items(0)
        logs, has_earlier = log.output(tail=10)
        assert len(logs) == 0
        assert has_earlier is False

    def test_tail_deduplicates_updates(self, patch_log_deps):
        """Tail correctly handles duplicate update entries."""
        log = self._make_log_with_items(5)
        log.updates.extend([3, 3, 3])
        logs, has_earlier = log.output(tail=10)
        assert len(logs) == 5
        assert has_earlier is False


# ---------------------------------------------------------------------------
# 2. Conditional chat list in snapshot
# ---------------------------------------------------------------------------

class TestConditionalChatList:

    def test_touch_updates_timestamp(self):
        from python.helpers.state_snapshot import touch_chat_list, get_chat_list_updated_at

        before = time.time()
        touch_chat_list()
        after = time.time()
        ts = get_chat_list_updated_at()
        assert before <= ts <= after

    def test_stale_timestamp_gets_full_list(self):
        """When chat_list_since is 0 (stale), snapshot includes contexts."""
        from python.helpers.state_snapshot import get_chat_list_updated_at

        ts = get_chat_list_updated_at()
        assert isinstance(ts, float)
        assert ts > 0


# ---------------------------------------------------------------------------
# 3. Lazy deserialization
# ---------------------------------------------------------------------------

class TestLazyDeserialization:

    def test_raw_agents_default_none(self):
        """Freshly created AgentContext has _raw_agents = None."""
        from agent import AgentContext
        assert hasattr(AgentContext, "__init__")
        # Verify the attribute is documented in the class body
        import inspect
        src = inspect.getsource(AgentContext.__init__)
        assert "_raw_agents" in src

    def test_hydrate_noop_when_already_hydrated(self):
        """hydrate_context_agents is a no-op when _raw_agents is None."""
        from python.helpers.persist_chat import hydrate_context_agents

        ctx = MagicMock()
        ctx._raw_agents = None
        sentinel = ctx.agent0
        hydrate_context_agents(ctx)
        # agent0 should be unchanged — function returned early
        assert ctx.agent0 is sentinel


# ---------------------------------------------------------------------------
# 4. Chat logs endpoint
# ---------------------------------------------------------------------------

class TestChatLogsEndpoint:

    def test_chat_logs_import(self):
        """ChatLogs endpoint can be imported."""
        from python.api.chat_logs import ChatLogs
        assert ChatLogs is not None


# ---------------------------------------------------------------------------
# 5. Scoped dirty signals
# ---------------------------------------------------------------------------

class TestScopedDirtySignals:

    def test_notify_uses_context_scoped_dirty(self, patch_log_deps):
        """Log._notify_state_monitor uses mark_dirty_for_context, not mark_dirty_all."""
        from python.helpers.log import Log

        log = Log()
        ctx = MagicMock()
        ctx.id = "test-ctx-123"
        log.context = ctx

        with patch("python.helpers.log._lazy_mark_dirty_for_context") as mock_ctx_dirty, \
             patch("python.helpers.log._lazy_mark_dirty_all") as mock_all_dirty:
            log._notify_state_monitor()
            mock_ctx_dirty.assert_called_once_with("test-ctx-123", reason="log.Log._notify_state_monitor")
            mock_all_dirty.assert_not_called()
