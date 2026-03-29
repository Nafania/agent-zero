"""Task 6: recall log includes memory_feedback_items for UI POST /memory_feedback."""

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
from plugins.memory.extensions.python.message_loop_prompts_after._50_recall_memories import RecallMemories


@pytest.fixture
def _fake_cognee_node_set_module():
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
    agent.context.id = "chat-ctx-7"
    agent.context.log = MagicMock()
    log_item = MagicMock()
    agent.context.log.log.return_value = log_item
    agent.history.output_text.return_value = "assistant: prior\n"
    agent.parse_prompt = MagicMock(side_effect=lambda name, **kw: f"parsed:{name}")
    return agent, log_item


def _loop_data_with_user(text: str) -> LoopData:
    um = MagicMock()
    um.output_text.return_value = text
    ld = LoopData()
    ld.user_message = um
    ld.extras_persistent = OrderedDict()
    return ld


@pytest.mark.asyncio
async def test_recall_log_includes_feedback_items_with_ids(_fake_cognee_node_set_module):
    import json

    agent, log_item = _make_agent()
    loop_data = _loop_data_with_user("docker tips")
    settings = _base_recall_settings()
    db = MagicMock()
    db.get_search_datasets.return_value = ["default"]
    db.dataset_name = "default"

    meta_m = json.dumps({"id": "m1", "dataset": "default", "area": "main"})
    meta_s = json.dumps({"id": "s1", "dataset": "default", "area": "solutions"})
    mock_cognee = MagicMock()
    mock_cognee.search = AsyncMock(
        side_effect=[
            [f"[META:{meta_m}]\nmemory text a"],
            [f"[META:{meta_s}]\nsolution text b"],
        ]
    )

    ext = RecallMemories(agent)
    with (
        patch("helpers.settings.get_settings", return_value=settings),
        patch("plugins.memory.helpers.memory.Memory.get", new_callable=AsyncMock, return_value=db),
        patch("helpers.cognee_init.get_cognee", return_value=(mock_cognee, MagicMock())),
    ):
        await ext.search_memories(log_item=log_item, loop_data=loop_data)

    fb_calls = [
        c.kwargs.get("memory_feedback_items")
        for c in log_item.update.call_args_list
        if c.kwargs and "memory_feedback_items" in c.kwargs
    ]
    assert fb_calls, "expected log_item.update(memory_feedback_items=...)"
    bundle = fb_calls[-1]
    assert isinstance(bundle, list)
    assert len(bundle) == 2
    kinds = {x["kind"] for x in bundle}
    assert kinds == {"memory", "solution"}
    for row in bundle:
        assert row["context_id"] == "chat-ctx-7"
        assert row["dataset"] == "default"
        assert row["memory_id"] in ("m1", "s1")
        assert "text" in row
