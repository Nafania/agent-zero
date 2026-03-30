"""Tests for _60_skills_catalog extension."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent.read_prompt.return_value = "formatted prompt"
    return agent


class TestSkillsCatalogExtension:
    @pytest.mark.asyncio
    async def test_injects_catalog_when_skills_exist(self, mock_agent):
        from plugins.skills.helpers.skills import Skill
        mock_skills = [
            Skill(
                name="brainstorming",
                description="Use before creative work",
                path=Path("/x"),
                skill_md_path=Path("/x/SKILL.md"),
            ),
        ]
        with patch("plugins.skills.extensions.python.message_loop_prompts_after._60_skills_catalog.skills.list_skills", return_value=mock_skills):
            from plugins.skills.extensions.python.message_loop_prompts_after._60_skills_catalog import SkillsCatalogPrompt
            ext = SkillsCatalogPrompt.__new__(SkillsCatalogPrompt)
            ext.agent = mock_agent
            loop_data = MagicMock()
            loop_data.extras_persistent = {}
            await ext.execute(loop_data=loop_data)

            assert "available_skills" in loop_data.extras_persistent
            mock_agent.read_prompt.assert_called_once()
            call_args = mock_agent.read_prompt.call_args
            assert call_args[0][0] == "agent.system.skills.catalog.md"
            assert "brainstorming" in call_args[1]["skills"]

    @pytest.mark.asyncio
    async def test_skips_when_no_skills(self, mock_agent):
        with patch("plugins.skills.extensions.python.message_loop_prompts_after._60_skills_catalog.skills.list_skills", return_value=[]):
            from plugins.skills.extensions.python.message_loop_prompts_after._60_skills_catalog import SkillsCatalogPrompt
            ext = SkillsCatalogPrompt.__new__(SkillsCatalogPrompt)
            ext.agent = mock_agent
            loop_data = MagicMock()
            loop_data.extras_persistent = {}
            await ext.execute(loop_data=loop_data)

            assert "available_skills" not in loop_data.extras_persistent

    @pytest.mark.asyncio
    async def test_truncates_long_descriptions(self, mock_agent):
        from plugins.skills.helpers.skills import Skill
        long_desc = "A" * 300
        mock_skills = [
            Skill(
                name="verbose-skill",
                description=long_desc,
                path=Path("/y"),
                skill_md_path=Path("/y/SKILL.md"),
            ),
        ]
        with patch("plugins.skills.extensions.python.message_loop_prompts_after._60_skills_catalog.skills.list_skills", return_value=mock_skills):
            from plugins.skills.extensions.python.message_loop_prompts_after._60_skills_catalog import SkillsCatalogPrompt
            ext = SkillsCatalogPrompt.__new__(SkillsCatalogPrompt)
            ext.agent = mock_agent
            loop_data = MagicMock()
            loop_data.extras_persistent = {}
            await ext.execute(loop_data=loop_data)

            call_args = mock_agent.read_prompt.call_args
            skills_text = call_args[1]["skills"]
            assert len(skills_text) < 300

    @pytest.mark.asyncio
    async def test_sorts_skills_alphabetically(self, mock_agent):
        from plugins.skills.helpers.skills import Skill
        mock_skills = [
            Skill(name="zeta", description="Last", path=Path("/z"), skill_md_path=Path("/z/SKILL.md")),
            Skill(name="alpha", description="First", path=Path("/a"), skill_md_path=Path("/a/SKILL.md")),
            Skill(name="middle", description="Mid", path=Path("/m"), skill_md_path=Path("/m/SKILL.md")),
        ]
        with patch("plugins.skills.extensions.python.message_loop_prompts_after._60_skills_catalog.skills.list_skills", return_value=mock_skills):
            from plugins.skills.extensions.python.message_loop_prompts_after._60_skills_catalog import SkillsCatalogPrompt
            ext = SkillsCatalogPrompt.__new__(SkillsCatalogPrompt)
            ext.agent = mock_agent
            loop_data = MagicMock()
            loop_data.extras_persistent = {}
            await ext.execute(loop_data=loop_data)

            call_args = mock_agent.read_prompt.call_args
            skills_text = call_args[1]["skills"]
            alpha_pos = skills_text.index("alpha")
            middle_pos = skills_text.index("middle")
            zeta_pos = skills_text.index("zeta")
            assert alpha_pos < middle_pos < zeta_pos
