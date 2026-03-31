"""Tests for system_prompt and before_main_llm_call extensions."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TestSystemPrompt:
    """Tests for the split system_prompt extension files."""

    @pytest.mark.asyncio
    async def test_appends_main_and_tools(self, mock_agent, mock_loop_data):
        system_prompt = []

        def read_prompt(p, **kw):
            return f"prompt:{p}"

        mock_agent.read_prompt.side_effect = read_prompt
        mock_agent.context.get_data = MagicMock(return_value=None)
        mock_agent.get_data = MagicMock(return_value=None)

        with patch(
            "plugins.model_config.helpers.model_config.get_chat_model_config",
            return_value={"vision": False},
        ), patch(
            "extensions.python.system_prompt._11_tools_prompt.subagents.get_paths",
            return_value=["prompts"],
        ), patch(
            "extensions.python.system_prompt._11_tools_prompt.files.get_unique_filenames_in_dirs",
            return_value=["/fake/agent.system.tool.code_execution.md"],
        ):
            from extensions.python.system_prompt._10_main_prompt import MainPrompt
            from extensions.python.system_prompt._11_tools_prompt import ToolsPrompt

            main_ext = MainPrompt(agent=mock_agent)
            await main_ext.execute(system_prompt=system_prompt, loop_data=mock_loop_data)

            tools_ext = ToolsPrompt(agent=mock_agent)
            await tools_ext.execute(system_prompt=system_prompt, loop_data=mock_loop_data)

        assert len(system_prompt) >= 2
        assert any("main" in p for p in system_prompt)
        assert any("tools" in p for p in system_prompt)


    @pytest.mark.asyncio
    async def test_main_skips_empty_prompt(self, mock_agent, mock_loop_data):
        system_prompt = []
        mock_agent.read_prompt.return_value = ""

        from extensions.python.system_prompt._10_main_prompt import MainPrompt

        ext = MainPrompt(agent=mock_agent)
        await ext.execute(system_prompt=system_prompt, loop_data=mock_loop_data)

        assert system_prompt == []

    @pytest.mark.asyncio
    async def test_tools_skips_empty_prompt(self, mock_agent, mock_loop_data):
        system_prompt = []
        mock_agent.read_prompt.return_value = ""
        mock_agent.get_data.return_value = None

        with patch(
            "plugins.model_config.helpers.model_config.get_chat_model_config",
            return_value={"vision": False},
        ), patch(
            "extensions.python.system_prompt._11_tools_prompt.subagents.get_paths",
            return_value=[],
        ), patch(
            "extensions.python.system_prompt._11_tools_prompt.files.get_unique_filenames_in_dirs",
            return_value=[],
        ):
            from extensions.python.system_prompt._11_tools_prompt import ToolsPrompt

            ext = ToolsPrompt(agent=mock_agent)
            await ext.execute(system_prompt=system_prompt, loop_data=mock_loop_data)

        assert system_prompt == []

    @pytest.mark.asyncio
    async def test_main_no_agent(self, mock_loop_data):
        system_prompt = []
        from extensions.python.system_prompt._10_main_prompt import MainPrompt

        ext = MainPrompt(agent=None)
        await ext.execute(system_prompt=system_prompt, loop_data=mock_loop_data)
        assert system_prompt == []

    @pytest.mark.asyncio
    async def test_tools_no_agent(self, mock_loop_data):
        system_prompt = []
        from extensions.python.system_prompt._11_tools_prompt import ToolsPrompt

        ext = ToolsPrompt(agent=None)
        await ext.execute(system_prompt=system_prompt, loop_data=mock_loop_data)
        assert system_prompt == []


class TestMcpPrompt:
    """Tests for system_prompt/_12_mcp_prompt.py."""

    @pytest.mark.asyncio
    async def test_no_agent(self, mock_loop_data):
        system_prompt = []
        from extensions.python.system_prompt._12_mcp_prompt import McpPrompt

        ext = McpPrompt(agent=None)
        await ext.execute(system_prompt=system_prompt, loop_data=mock_loop_data)
        assert system_prompt == []

    @pytest.mark.asyncio
    async def test_appends_when_servers_exist(self, mock_agent, mock_loop_data):
        system_prompt = []

        mock_mcp = MagicMock()
        mock_mcp.servers = [MagicMock()]
        mock_mcp.get_tools_prompt.return_value = "mcp tools prompt"

        with patch(
            "extensions.python.system_prompt._12_mcp_prompt.MCPConfig.get_instance",
            return_value=mock_mcp,
        ):
            from extensions.python.system_prompt._12_mcp_prompt import McpPrompt

            ext = McpPrompt(agent=mock_agent)
            await ext.execute(system_prompt=system_prompt, loop_data=mock_loop_data)

        assert "mcp tools prompt" in system_prompt

    @pytest.mark.asyncio
    async def test_skips_when_no_servers(self, mock_agent, mock_loop_data):
        system_prompt = []

        mock_mcp = MagicMock()
        mock_mcp.servers = []

        with patch(
            "extensions.python.system_prompt._12_mcp_prompt.MCPConfig.get_instance",
            return_value=mock_mcp,
        ):
            from extensions.python.system_prompt._12_mcp_prompt import McpPrompt

            ext = McpPrompt(agent=mock_agent)
            await ext.execute(system_prompt=system_prompt, loop_data=mock_loop_data)

        assert system_prompt == []


class TestSecretsPrompt:
    """Tests for system_prompt/_13_secrets_prompt.py."""

    @pytest.mark.asyncio
    async def test_no_agent(self, mock_loop_data):
        system_prompt = []
        from extensions.python.system_prompt._13_secrets_prompt import SecretsPrompt

        ext = SecretsPrompt(agent=None)
        await ext.execute(system_prompt=system_prompt, loop_data=mock_loop_data)
        assert system_prompt == []

    @pytest.mark.asyncio
    async def test_appends_when_prompt_nonempty(self, mock_agent, mock_loop_data):
        system_prompt = []
        mock_agent.read_prompt.return_value = "secrets prompt text"

        mock_secrets_mgr = MagicMock()
        mock_secrets_mgr.get_secrets_for_prompt.return_value = "API_KEY=***"

        with patch(
            "helpers.secrets.get_secrets_manager",
            return_value=mock_secrets_mgr,
        ), patch(
            "helpers.settings.get_settings",
            return_value={"variables": {"foo": "bar"}},
        ):
            from extensions.python.system_prompt._13_secrets_prompt import (
                SecretsPrompt,
            )

            ext = SecretsPrompt(agent=mock_agent)
            await ext.execute(system_prompt=system_prompt, loop_data=mock_loop_data)

        assert len(system_prompt) == 1
        assert "secrets prompt text" in system_prompt[0]

    @pytest.mark.asyncio
    async def test_skips_when_exception(self, mock_agent, mock_loop_data):
        system_prompt = []

        with patch(
            "helpers.secrets.get_secrets_manager",
            side_effect=Exception("no secrets module"),
        ):
            from extensions.python.system_prompt._13_secrets_prompt import (
                SecretsPrompt,
            )

            ext = SecretsPrompt(agent=mock_agent)
            await ext.execute(system_prompt=system_prompt, loop_data=mock_loop_data)

        assert system_prompt == []


class TestSkillsPrompt:
    """Tests for system_prompt/_13_skills_prompt.py."""

    @pytest.mark.asyncio
    async def test_no_agent(self, mock_loop_data):
        system_prompt = []
        from extensions.python.system_prompt._13_skills_prompt import SkillsPrompt

        ext = SkillsPrompt(agent=None)
        await ext.execute(system_prompt=system_prompt, loop_data=mock_loop_data)
        assert system_prompt == []

    @pytest.mark.asyncio
    async def test_appends_when_skills_exist(self, mock_agent, mock_loop_data):
        system_prompt = []
        mock_agent.read_prompt.return_value = "skills prompt text"

        mock_skill = MagicMock()
        mock_skill.name = "test_skill"
        mock_skill.description = "A test skill"

        with patch(
            "extensions.python.system_prompt._13_skills_prompt.skills_helper.list_skills",
            return_value=[mock_skill],
        ):
            from extensions.python.system_prompt._13_skills_prompt import SkillsPrompt

            ext = SkillsPrompt(agent=mock_agent)
            await ext.execute(system_prompt=system_prompt, loop_data=mock_loop_data)

        assert len(system_prompt) == 1
        assert "skills prompt text" in system_prompt[0]

    @pytest.mark.asyncio
    async def test_skips_when_no_skills(self, mock_agent, mock_loop_data):
        system_prompt = []

        with patch(
            "extensions.python.system_prompt._13_skills_prompt.skills_helper.list_skills",
            return_value=[],
        ):
            from extensions.python.system_prompt._13_skills_prompt import SkillsPrompt

            ext = SkillsPrompt(agent=mock_agent)
            await ext.execute(system_prompt=system_prompt, loop_data=mock_loop_data)

        assert system_prompt == []


class TestProjectPrompt:
    """Tests for system_prompt/_14_project_prompt.py."""

    @pytest.mark.asyncio
    async def test_no_agent(self, mock_loop_data):
        system_prompt = []
        from extensions.python.system_prompt._14_project_prompt import ProjectPrompt

        ext = ProjectPrompt(agent=None)
        await ext.execute(system_prompt=system_prompt, loop_data=mock_loop_data)
        assert system_prompt == []

    @pytest.mark.asyncio
    async def test_appends_when_prompt_nonempty(self, mock_agent, mock_loop_data):
        system_prompt = []
        mock_agent.read_prompt.return_value = "project prompt text"
        mock_agent.context.get_data.return_value = None

        from extensions.python.system_prompt._14_project_prompt import ProjectPrompt

        ext = ProjectPrompt(agent=mock_agent)
        await ext.execute(system_prompt=system_prompt, loop_data=mock_loop_data)

        assert len(system_prompt) == 1

    @pytest.mark.asyncio
    async def test_always_appends(self, mock_agent, mock_loop_data):
        """Project prompt always produces output (concatenates main + inactive/active)."""
        system_prompt = []
        mock_agent.read_prompt.return_value = ""
        mock_agent.context.get_data.return_value = None

        from extensions.python.system_prompt._14_project_prompt import ProjectPrompt

        ext = ProjectPrompt(agent=mock_agent)
        await ext.execute(system_prompt=system_prompt, loop_data=mock_loop_data)

        assert len(system_prompt) == 1

    @pytest.mark.asyncio
    async def test_includes_active_project(self, mock_agent, mock_loop_data):
        system_prompt = []
        mock_agent.read_prompt.return_value = "project prompt"
        mock_agent.context.get_data.return_value = "my-project"

        with patch(
            "extensions.python.system_prompt._14_project_prompt.projects.build_system_prompt_vars",
            return_value={"name": "my-project"},
        ):
            from extensions.python.system_prompt._14_project_prompt import (
                ProjectPrompt,
            )

            ext = ProjectPrompt(agent=mock_agent)
            await ext.execute(system_prompt=system_prompt, loop_data=mock_loop_data)

        assert len(system_prompt) == 1


class TestBehaviourPrompt:
    """Tests for system_prompt/_20_behaviour_prompt.py."""

    @pytest.mark.asyncio
    async def test_inserts_behaviour_at_front(self, mock_agent, mock_loop_data):
        system_prompt = ["existing"]
        mock_agent.read_prompt.return_value = "behaviour rules"

        with patch(
            "plugins.memory.extensions.python.system_prompt._20_behaviour_prompt.memory.get_memory_subdir_abs",
            return_value="/mem",
        ), patch(
            "plugins.memory.extensions.python.system_prompt._20_behaviour_prompt.files.get_abs_path",
            return_value="/mem/behaviour.md",
        ), patch(
            "plugins.memory.extensions.python.system_prompt._20_behaviour_prompt.files.exists",
            return_value=True,
        ), patch(
            "plugins.memory.extensions.python.system_prompt._20_behaviour_prompt.files.read_file",
            return_value="custom rules",
        ):
            from plugins.memory.extensions.python.system_prompt._20_behaviour_prompt import (
                BehaviourPrompt,
            )

            ext = BehaviourPrompt(agent=mock_agent)
            await ext.execute(system_prompt=system_prompt, loop_data=mock_loop_data)

        assert system_prompt[0] == "behaviour rules"
        assert "existing" in system_prompt


class TestLogForStream:
    """Tests for before_main_llm_call/_10_log_for_stream.py."""

    @pytest.mark.asyncio
    async def test_creates_log_item(self, mock_agent, mock_loop_data):
        mock_loop_data.params_temporary = {}
        mock_log_item = MagicMock()
        mock_agent.context.log.log.return_value = mock_log_item

        from extensions.python.before_main_llm_call._10_log_for_stream import (
            LogForStream,
            build_heading,
            build_default_heading,
        )

        ext = LogForStream(agent=mock_agent)
        await ext.execute(loop_data=mock_loop_data)

        assert "log_item_generating" in mock_loop_data.params_temporary

    def test_build_heading_includes_agent_prefix(self, mock_agent):
        from extensions.python.before_main_llm_call._10_log_for_stream import (
            build_heading,
        )

        mock_agent.agent_name = "A0"
        result = build_heading(mock_agent, "Thinking")
        assert "A0" in result
        assert "Thinking" in result
