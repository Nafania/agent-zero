"""Tests for subordinate delegation depth limits and loop prevention."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _mock_agent(number=0, profile="default", max_depth=5, data=None):
    agent = MagicMock()
    agent.number = number
    agent.config = MagicMock()
    agent.config.profile = profile
    agent.config.max_agent_depth = max_depth
    agent.agent_name = f"A{number}"
    _data = data or {}
    agent.get_data = MagicMock(side_effect=lambda k, default=None: _data.get(k, default))
    agent.set_data = MagicMock(side_effect=lambda k, v: _data.__setitem__(k, v))
    agent.context = MagicMock()
    agent.context.log = MagicMock()
    agent.context.log.log = MagicMock(return_value=MagicMock())
    return agent


class TestDepthLimit:
    @pytest.mark.asyncio
    async def test_refuses_at_max_depth(self):
        from tools.call_subordinate import Delegation

        agent = _mock_agent(number=4, max_depth=5)
        tool = Delegation.__new__(Delegation)
        tool.agent = agent
        tool.args = {}
        result = await tool.execute(message="do something")
        assert "depth limit reached" in result.message

    @pytest.mark.asyncio
    async def test_allows_under_max_depth(self):
        from tools.call_subordinate import Delegation, _SAME_PROFILE_STREAK_KEY
        from agent import Agent

        data_store = {}
        agent = _mock_agent(number=2, max_depth=5, data=data_store)

        tool = Delegation.__new__(Delegation)
        tool.agent = agent
        tool.args = {}

        with patch("tools.call_subordinate.initialize_agent") as mock_init, \
             patch("tools.call_subordinate.Agent") as MockAgent:
            mock_config = MagicMock()
            mock_config.profile = "default"
            mock_init.return_value = mock_config
            sub_agent = MagicMock()
            sub_agent.monologue = AsyncMock(return_value="result text")
            sub_agent.history = MagicMock()
            sub_agent.set_data = MagicMock()
            MockAgent.return_value = sub_agent

            result = await tool.execute(message="do something")
            assert "depth limit" not in result.message
            assert result.message == "result text"


class TestSameProfileLoopDetection:
    @pytest.mark.asyncio
    async def test_refuses_after_3_same_profile_delegations(self):
        from tools.call_subordinate import Delegation, _SAME_PROFILE_STREAK_KEY
        from agent import Agent

        agent = _mock_agent(number=2, profile="researcher", max_depth=10)
        data = {_SAME_PROFILE_STREAK_KEY: 2}
        agent.get_data = MagicMock(side_effect=lambda k, default=None: data.get(k))
        agent.set_data = MagicMock()

        tool = Delegation.__new__(Delegation)
        tool.agent = agent
        tool.args = {}

        with patch("tools.call_subordinate.initialize_agent") as mock_init:
            mock_config = MagicMock()
            mock_config.profile = "researcher"
            mock_init.return_value = mock_config

            result = await tool.execute(message="research this", profile="researcher")
            assert "loop" in result.message.lower() or "delegation refused" in result.message.lower()

    @pytest.mark.asyncio
    async def test_allows_different_profile(self):
        from tools.call_subordinate import Delegation, _SAME_PROFILE_STREAK_KEY

        data_store = {_SAME_PROFILE_STREAK_KEY: 2}
        agent = _mock_agent(number=1, profile="researcher", max_depth=10, data=data_store)

        tool = Delegation.__new__(Delegation)
        tool.agent = agent
        tool.args = {}

        with patch("tools.call_subordinate.initialize_agent") as mock_init, \
             patch("tools.call_subordinate.Agent") as MockAgent:
            mock_config = MagicMock()
            mock_config.profile = "developer"
            mock_init.return_value = mock_config
            sub_agent = MagicMock()
            sub_agent.monologue = AsyncMock(return_value="code result")
            sub_agent.history = MagicMock()
            sub_agent.set_data = MagicMock()
            MockAgent.return_value = sub_agent

            result = await tool.execute(message="write code", profile="developer")
            assert "loop" not in result.message.lower()
