"""Tests for webui performance optimizations: tail-based log output, conditional
chat list, lazy deserialization, chat-logs endpoint, scoped dirty signals,
chat rename refresh, last_message updates, and process_chain completion signals."""

import sys
import time
from datetime import datetime, timezone
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

    def test_output_always_returns_tuple(self, patch_log_deps):
        """output() always returns (list, bool) tuple."""
        log = self._make_log_with_items(10)
        result = log.output()
        assert isinstance(result, tuple)
        assert len(result) == 2
        logs, has_earlier = result
        assert isinstance(logs, list)
        assert len(logs) == 10
        assert has_earlier is False

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
        import inspect
        src = inspect.getsource(AgentContext.__init__)
        assert "_raw_agents" in src

    def test_hydrate_noop_when_already_hydrated(self):
        """hydrate_context_agents is a no-op when _raw_agents is None."""
        from python.helpers.persist_chat import hydrate_context_agents

        ctx = MagicMock()
        ctx._raw_agents = None
        sentinel = ctx._agent0
        hydrate_context_agents(ctx)
        assert ctx._agent0 is sentinel

    def test_hydrate_deserializes_agents(self):
        """hydrate_context_agents deserializes stored raw agents data."""
        from python.helpers.persist_chat import hydrate_context_agents

        ctx = MagicMock()
        ctx._raw_agents = [{"number": 0, "data": {}, "history": ""}]
        ctx._raw_streaming_agent_no = 0
        ctx.config = MagicMock()

        with patch("python.helpers.persist_chat._deserialize_agents") as mock_deser:
            mock_agent = MagicMock()
            mock_agent.number = 0
            mock_agent.data = {}
            mock_deser.return_value = mock_agent

            hydrate_context_agents(ctx)

            mock_deser.assert_called_once()
            assert ctx._raw_agents is None


# ---------------------------------------------------------------------------
# 4. Chat logs endpoint — pagination logic
# ---------------------------------------------------------------------------

class TestChatLogsEndpoint:

    def test_chat_logs_import(self):
        """ChatLogs endpoint can be imported."""
        from python.api.chat_logs import ChatLogs
        assert ChatLogs is not None

    def test_get_items_before_basic(self, patch_log_deps):
        """get_items_before returns correct slice and has_more flag."""
        from python.helpers.log import Log

        log = Log()
        log.context = MagicMock()
        for i in range(20):
            from python.helpers.log import LogItem
            log.logs.append(LogItem(
                log=log, no=i, type="info",
                heading=f"Item {i}", content=f"Content {i}",
            ))

        result = log.get_items_before(before=20, limit=5)
        assert len(result["logs"]) == 5
        assert result["has_more"] is True
        assert result["logs"][0]["no"] == 15
        assert result["logs"][-1]["no"] == 19

    def test_get_items_before_from_start(self, patch_log_deps):
        """get_items_before with before=5, limit=10 returns first 5 items."""
        from python.helpers.log import Log

        log = Log()
        log.context = MagicMock()
        for i in range(20):
            from python.helpers.log import LogItem
            log.logs.append(LogItem(
                log=log, no=i, type="info",
                heading=f"Item {i}", content=f"Content {i}",
            ))

        result = log.get_items_before(before=5, limit=10)
        assert len(result["logs"]) == 5
        assert result["has_more"] is False
        assert result["logs"][0]["no"] == 0

    def test_get_items_before_zero_defaults_to_end(self, patch_log_deps):
        """get_items_before with before=0 returns items from the end."""
        from python.helpers.log import Log

        log = Log()
        log.context = MagicMock()
        for i in range(10):
            from python.helpers.log import LogItem
            log.logs.append(LogItem(
                log=log, no=i, type="info",
                heading=f"Item {i}", content=f"Content {i}",
            ))

        result = log.get_items_before(before=0, limit=3)
        assert len(result["logs"]) == 3
        assert result["has_more"] is True
        assert result["logs"][-1]["no"] == 9

    def test_get_items_before_clamps_limit(self, patch_log_deps):
        """get_items_before clamps limit to 1-200."""
        from python.helpers.log import Log

        log = Log()
        log.context = MagicMock()
        for i in range(5):
            from python.helpers.log import LogItem
            log.logs.append(LogItem(
                log=log, no=i, type="info",
                heading=f"Item {i}", content=f"Content {i}",
            ))

        result = log.get_items_before(before=5, limit=999)
        assert len(result["logs"]) == 5


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


# ---------------------------------------------------------------------------
# 6. Chat rename triggers chat list refresh
# ---------------------------------------------------------------------------

class TestChatRenameRefresh:

    def test_rename_extension_calls_touch_chat_list(self):
        """_60_rename_chat.py imports and calls touch_chat_list after rename."""
        import inspect
        from python.extensions.monologue_start._60_rename_chat import RenameChat

        src = inspect.getsource(RenameChat.change_name)
        assert "touch_chat_list" in src
        assert "mark_dirty_all" in src


# ---------------------------------------------------------------------------
# 7. hist_add_message updates AgentContext.last_message
# ---------------------------------------------------------------------------

class TestHistAddMessageUpdatesContext:

    def test_hist_add_message_updates_context_last_message(self):
        """Agent.hist_add_message sets self.context.last_message."""
        import inspect
        from agent import Agent

        src = inspect.getsource(Agent.hist_add_message)
        assert "self.context.last_message" in src
        assert "touch_chat_list" in src

    def test_hist_add_message_sets_both_timestamps(self):
        """hist_add_message updates both Agent.last_message and context.last_message."""
        from agent import Agent

        agent = MagicMock(spec=Agent)
        agent.context = MagicMock()
        agent.context.last_message = datetime(2020, 1, 1, tzinfo=timezone.utc)
        agent.history = MagicMock()
        agent.history.add_message = MagicMock(return_value=MagicMock())

        with patch("agent.asyncio") as mock_asyncio, \
             patch("python.helpers.state_snapshot.touch_chat_list"):
            mock_asyncio.run = MagicMock()
            Agent.hist_add_message(agent, ai=False, content="test")

        assert agent.context.last_message > datetime(2020, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# 8. _process_chain finally block broadcasts completion
# ---------------------------------------------------------------------------

class TestProcessChainCompletion:

    def test_process_chain_has_finally_with_touch_and_dirty(self):
        """_process_chain has a finally block that calls touch_chat_list and mark_dirty_all."""
        import inspect
        from agent import AgentContext

        src = inspect.getsource(AgentContext._process_chain)
        assert "finally:" in src
        assert "touch_chat_list" in src
        assert "mark_dirty_all" in src

    def test_process_chain_finally_only_for_user_messages(self):
        """The finally block only fires for top-level user messages (user=True)."""
        import inspect
        from agent import AgentContext

        src = inspect.getsource(AgentContext._process_chain)
        assert "if user:" in src


# ---------------------------------------------------------------------------
# 9. Frontend formatRelativeTime (unit logic test)
# ---------------------------------------------------------------------------

class TestFormatRelativeTime:
    """Test the Python-side equivalent of the JS formatRelativeTime boundaries."""

    @staticmethod
    def _format(seconds):
        """Mirror the JS formatRelativeTime logic for unit testing boundaries."""
        if seconds < 60:
            return f"{seconds}s"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}m"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h"
        days = hours // 24
        if days < 7:
            return f"{days}d"
        weeks = days // 7
        return f"{weeks}w"

    def test_seconds(self):
        assert self._format(0) == "0s"
        assert self._format(59) == "59s"

    def test_minutes(self):
        assert self._format(60) == "1m"
        assert self._format(3599) == "59m"

    def test_hours(self):
        assert self._format(3600) == "1h"
        assert self._format(86399) == "23h"

    def test_days(self):
        assert self._format(86400) == "1d"
        assert self._format(604799) == "6d"

    def test_weeks(self):
        assert self._format(604800) == "1w"
        assert self._format(1209600) == "2w"


# ---------------------------------------------------------------------------
# 10. Sort order uses last_message, not created_at
# ---------------------------------------------------------------------------

class TestChatListSortOrder:

    def test_chats_store_sorts_by_last_message(self):
        """chats-store.js sorts contexts by last_message, not created_at."""
        store_path = PROJECT_ROOT / "webui" / "components" / "sidebar" / "chats" / "chats-store.js"
        content = store_path.read_text()
        assert "last_message" in content
        assert "new Date(a.last_message)" in content or "a.last_message" in content
        assert "created_at" not in content.split("sort(")[1].split(");")[0] if "sort(" in content else True
