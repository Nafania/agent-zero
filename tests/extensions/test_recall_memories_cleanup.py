"""Task 3: recall extension ignores legacy query-prep/post-filter; delayed wait unchanged."""

import asyncio
import sys
import types
from collections import OrderedDict
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent import LoopData
from plugins._memory.extensions.python.message_loop_prompts_after._50_recall_memories import (
    DATA_NAME_ITER,
    DATA_NAME_TASK,
    RecallMemories,
)
from plugins._memory.extensions.python.message_loop_prompts_after._91_recall_wait import RecallWait


@pytest.fixture
def _fake_cognee_node_set_module():
    """Allow _50_recall_memories to import NodeSet without the cognee package installed."""
    leaf = "cognee.modules.engine.models.node_set"
    if leaf in sys.modules:
        yield
        return
    chain = [
        "cognee",
        "cognee.modules",
        "cognee.modules.engine",
        "cognee.modules.engine.models",
        leaf,
    ]
    for name in chain[:-1]:
        if name not in sys.modules:
            m = types.ModuleType(name)
            m.__path__ = []
            sys.modules[name] = m
    ns_mod = types.ModuleType(leaf)
    ns_mod.NodeSet = MagicMock(name="NodeSet")
    sys.modules[leaf] = ns_mod
    yield
    for name in reversed(chain):
        sys.modules.pop(name, None)


def _base_recall_settings(**overrides):
    s = {
        "memory_recall_enabled": True,
        "memory_recall_interval": 1,
        "memory_recall_delayed": False,
        "memory_recall_history_len": 1000,
        "memory_recall_memories_max_search": 12,
        "memory_recall_solutions_max_search": 8,
        "memory_recall_memories_max_result": 5,
        "memory_recall_solutions_max_result": 3,
    }
    s.update(overrides)
    return s


def _make_agent():
    agent = MagicMock()
    agent.context = MagicMock()
    agent.context.id = "ctx-1"
    agent.context.log = MagicMock()
    log_item = MagicMock()
    agent.context.log.log.return_value = log_item
    agent.history.output_text.return_value = "assistant: prior context\n"
    agent.call_utility_model = AsyncMock(
        side_effect=AssertionError("call_utility_model must not be used for legacy recall prep/filter")
    )
    agent.read_prompt = MagicMock(return_value="prompt")
    agent.parse_prompt = MagicMock(side_effect=lambda name, **kw: f"parsed:{name}")
    return agent


def _loop_data_with_user(text: str) -> LoopData:
    um = MagicMock()
    um.output_text.return_value = text
    ld = LoopData()
    ld.user_message = um
    ld.extras_persistent = OrderedDict()
    return ld


@pytest.mark.asyncio
async def test_recall_search_ignores_legacy_memory_recall_query_prep(_fake_cognee_node_set_module):
    """Stale memory_recall_query_prep=True must not trigger utility query preparation."""
    agent = _make_agent()
    loop_data = _loop_data_with_user("find my saved docker notes")
    log_item = MagicMock()

    settings = _base_recall_settings(memory_recall_query_prep=True, memory_recall_post_filter=False)

    db = MagicMock()
    db.get_search_datasets.return_value = ["main_ds"]

    mock_cognee = MagicMock()
    mock_cognee.search = AsyncMock(side_effect=[["mem chunk"], ["sol chunk"]])

    ext = RecallMemories(agent)

    with (
        patch("helpers.settings.get_settings", return_value=settings),
        patch("plugins._memory.helpers.memory.Memory.get", new_callable=AsyncMock, return_value=db),
        patch("plugins._memory.helpers.cognee_init.get_cognee", return_value=(mock_cognee, MagicMock())),
    ):
        await ext.search_memories(log_item=log_item, loop_data=loop_data)

    agent.call_utility_model.assert_not_called()
    mock_cognee.search.assert_awaited()
    assert "memories" in loop_data.extras_persistent or "solutions" in loop_data.extras_persistent


@pytest.mark.asyncio
async def test_recall_search_ignores_legacy_memory_recall_post_filter(_fake_cognee_node_set_module):
    """Stale memory_recall_post_filter=True must not trigger utility post-filtering."""
    agent = _make_agent()
    loop_data = _loop_data_with_user("retry the deployment fix")
    log_item = MagicMock()

    settings = _base_recall_settings(memory_recall_query_prep=False, memory_recall_post_filter=True)

    db = MagicMock()
    db.get_search_datasets.return_value = ["main_ds"]

    mock_cognee = MagicMock()
    mock_cognee.search = AsyncMock(side_effect=[["mem a", "mem b"], ["sol a"]])

    ext = RecallMemories(agent)

    with (
        patch("helpers.settings.get_settings", return_value=settings),
        patch("plugins._memory.helpers.memory.Memory.get", new_callable=AsyncMock, return_value=db),
        patch("plugins._memory.helpers.cognee_init.get_cognee", return_value=(mock_cognee, MagicMock())),
    ):
        await ext.search_memories(log_item=log_item, loop_data=loop_data)

    agent.call_utility_model.assert_not_called()
    assert loop_data.extras_persistent.get("memories") or loop_data.extras_persistent.get("solutions")


@pytest.mark.asyncio
async def test_recall_search_ignores_legacy_memory_recall_similarity_threshold(
    _fake_cognee_node_set_module,
):
    """Stale memory_recall_similarity_threshold must not add A0-side filtering or utility calls."""
    agent = _make_agent()
    loop_data = _loop_data_with_user("look up the nginx config we saved")
    log_item = MagicMock()

    settings = _base_recall_settings(memory_recall_similarity_threshold=0.99)

    db = MagicMock()
    db.get_search_datasets.return_value = ["main_ds"]

    mock_cognee = MagicMock()
    mock_cognee.search = AsyncMock(side_effect=[["mem x"], []])

    ext = RecallMemories(agent)

    with (
        patch("helpers.settings.get_settings", return_value=settings),
        patch("plugins._memory.helpers.memory.Memory.get", new_callable=AsyncMock, return_value=db),
        patch("plugins._memory.helpers.cognee_init.get_cognee", return_value=(mock_cognee, MagicMock())),
    ):
        await ext.search_memories(log_item=log_item, loop_data=loop_data)

    agent.call_utility_model.assert_not_called()
    assert mock_cognee.search.await_count == 2
    calls = mock_cognee.search.await_args_list
    assert calls[0].kwargs["top_k"] == settings["memory_recall_memories_max_search"]
    assert calls[1].kwargs["top_k"] == settings["memory_recall_solutions_max_search"]
    assert loop_data.extras_persistent.get("memories")


@pytest.mark.asyncio
async def test_recall_wait_delayed_same_iteration_does_not_await_task():
    """Delayed recall: same iteration skips await and exposes delay message in extras."""
    agent = MagicMock()
    agent.read_prompt.return_value = "DELAY_MSG_BODY"

    async def slow():
        await asyncio.sleep(30)

    task = asyncio.create_task(slow())

    settings = _base_recall_settings(memory_recall_delayed=True)

    loop_data = LoopData()
    loop_data.iteration = 7
    loop_data.extras_temporary = OrderedDict()

    ext = RecallWait(agent)

    def _get_data(key):
        if key == DATA_NAME_TASK:
            return task
        if key == DATA_NAME_ITER:
            return loop_data.iteration
        return None

    try:
        with (
            patch("helpers.settings.get_settings", return_value=settings),
            patch.object(agent, "get_data", side_effect=_get_data),
        ):
            await ext.execute(loop_data)

        assert not task.done()
        assert loop_data.extras_temporary.get("memory_recall_delayed") == "DELAY_MSG_BODY"
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
