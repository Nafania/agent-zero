"""Tests for /skill_install API endpoint — npx skills add wrapper."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _make_handler():
    from api.skill_install import SkillInstall
    return SkillInstall(app=MagicMock(), thread_lock=MagicMock())


@pytest.fixture
def mock_skills_cli():
    with patch("plugins._skills.api.skill_install.skills_cli") as mock:
        mock.add = AsyncMock(return_value="Installed brainstorming")
        mock.SkillsCLIError = type("SkillsCLIError", (Exception,), {})
        yield mock


class TestInstallViaCLI:
    @pytest.mark.asyncio
    async def test_install_calls_skills_cli_add(self, mock_skills_cli):
        handler = _make_handler()
        result = await handler.process({"source": "obra/superpowers"}, MagicMock())
        assert result["ok"] is True
        assert "output" in result
        mock_skills_cli.add.assert_called_once_with("obra/superpowers")

    @pytest.mark.asyncio
    async def test_install_handles_cli_error(self, mock_skills_cli):
        mock_skills_cli.add.side_effect = Exception("clone failed")
        handler = _make_handler()
        result = await handler.process({"source": "owner/repo"}, MagicMock())
        assert result["ok"] is False
        assert "clone failed" in result["error"]

    @pytest.mark.asyncio
    async def test_install_empty_source_returns_error(self, mock_skills_cli):
        handler = _make_handler()
        result = await handler.process({"source": ""}, MagicMock())
        assert result["ok"] is False
        assert "source" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_install_missing_source_returns_error(self, mock_skills_cli):
        handler = _make_handler()
        result = await handler.process({}, MagicMock())
        assert result["ok"] is False

    @pytest.mark.asyncio
    async def test_install_handles_skills_cli_error(self, mock_skills_cli):
        mock_skills_cli.add.side_effect = mock_skills_cli.SkillsCLIError("npx not found")
        handler = _make_handler()
        result = await handler.process({"source": "owner/repo"}, MagicMock())
        assert result["ok"] is False
        assert "npx" in result["error"]
