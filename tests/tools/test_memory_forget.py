"""Tests for tools/memory_forget.py — MemoryForget tool."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# memory_forget.py does `from tools.memory_load import DEFAULT_THRESHOLD`
# but tools/memory_load.py was moved to plugins/memory/tools/memory_load.py
# with no shim left behind. Provide the module so the import succeeds.
import types as _types
if "tools.memory_load" not in sys.modules:
    _ml = _types.ModuleType("tools.memory_load")
    _ml.DEFAULT_THRESHOLD = 0.7
    sys.modules["tools.memory_load"] = _ml


@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent.read_prompt = MagicMock(side_effect=lambda t, **kw: f"Deleted: {kw.get('memory_count', 0)}")
    return agent


@pytest.fixture
def tool(mock_agent):
    from plugins.memory.tools.memory_forget import MemoryForget
    return MemoryForget(
        agent=mock_agent,
        name="memory_forget",
        method=None,
        args={"query": "old data"},
        message="",
        loop_data=None,
    )


class TestMemoryForgetExecute:
    @pytest.mark.asyncio
    async def test_forget_returns_count(self, tool):
        mock_db = MagicMock()
        mock_db.delete_documents_by_query = AsyncMock(return_value=["doc1"])
        with patch("plugins.memory.tools.memory_forget.Memory.get", new_callable=AsyncMock, return_value=mock_db):
            resp = await tool.execute(query="forget this", threshold=0.7)
        assert "1" in resp.message or "Deleted" in resp.message
        assert resp.break_loop is False
