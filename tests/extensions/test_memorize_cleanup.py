"""Task 4: memorize extensions ignore legacy replace/consolidation settings; insert-only flow."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent import LoopData
from extensions.python.monologue_end._50_memorize_fragments import MemorizeMemories
from extensions.python.monologue_end._51_memorize_solutions import MemorizeSolutions
from helpers.memory import Memory


def _stale_memorize_settings(**overrides):
    s = {
        "memory_memorize_enabled": True,
        "memory_memorize_consolidation": True,
        "memory_memorize_replace_threshold": 0.95,
    }
    s.update(overrides)
    return s


def _make_agent_for_memorize(utility_json: str):
    agent = MagicMock()
    agent.context = MagicMock()
    agent.context.log = MagicMock()
    agent.history = MagicMock()
    agent.concat_messages = MagicMock(return_value="user: hello\nassistant: hi\n")
    agent.call_utility_model = AsyncMock(return_value=utility_json)
    agent.read_prompt = MagicMock(return_value="sys prompt")
    return agent


@pytest.mark.asyncio
async def test_memorize_fragments_ignores_legacy_replace_and_consolidation_settings():
    """Stale consolidation/replace settings must not trigger delete_documents_by_query."""
    agent = _make_agent_for_memorize('["note alpha", "note beta"]')
    loop_data = LoopData()
    log_item = MagicMock()

    db = MagicMock()
    db.insert_text = AsyncMock(return_value="id")
    db.delete_documents_by_query = AsyncMock(
        side_effect=AssertionError("delete_documents_by_query must not run for removed replace-threshold")
    )

    ext = MemorizeMemories(agent)
    with patch("helpers.settings.get_settings", return_value=_stale_memorize_settings()):
        await ext.memorize(loop_data, log_item, db)

    db.delete_documents_by_query.assert_not_called()
    assert db.insert_text.await_count == 2
    calls = db.insert_text.await_args_list
    assert calls[0].kwargs["text"] == "note alpha"
    assert calls[0].kwargs["metadata"]["area"] == Memory.Area.FRAGMENTS.value
    assert calls[1].kwargs["text"] == "note beta"


@pytest.mark.asyncio
async def test_memorize_solutions_ignores_legacy_replace_and_consolidation_settings():
    """Stale consolidation/replace settings must not trigger delete_documents_by_query."""
    agent = _make_agent_for_memorize('["fixed the bug by restarting"]')
    loop_data = LoopData()
    log_item = MagicMock()

    db = MagicMock()
    db.insert_text = AsyncMock(return_value="id")
    db.delete_documents_by_query = AsyncMock(
        side_effect=AssertionError("delete_documents_by_query must not run for removed replace-threshold")
    )

    ext = MemorizeSolutions(agent)
    with patch("helpers.settings.get_settings", return_value=_stale_memorize_settings()):
        await ext.memorize(loop_data, log_item, db)

    db.delete_documents_by_query.assert_not_called()
    assert db.insert_text.await_count == 1
    assert "restart" in db.insert_text.await_args.kwargs["text"]
    assert db.insert_text.await_args.kwargs["metadata"]["area"] == Memory.Area.SOLUTIONS.value


@pytest.mark.asyncio
async def test_memorize_fragments_inserts_without_legacy_keys():
    """Minimal settings still memorizes parsed list entries."""
    agent = _make_agent_for_memorize('["only one"]')
    loop_data = LoopData()
    log_item = MagicMock()
    db = MagicMock()
    db.insert_text = AsyncMock(return_value="id")
    db.delete_documents_by_query = AsyncMock()

    ext = MemorizeMemories(agent)
    minimal = {"memory_memorize_enabled": True}
    with patch("helpers.settings.get_settings", return_value=minimal):
        await ext.memorize(loop_data, log_item, db)

    db.delete_documents_by_query.assert_not_called()
    db.insert_text.assert_awaited_once()
