"""Tests for /skills_catalog API endpoint."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _make_handler():
    from python.api.skills_catalog import SkillsCatalog
    return SkillsCatalog(app=MagicMock(), thread_lock=MagicMock())


@pytest.fixture
def mock_skills_cli():
    with patch("python.api.skills_catalog.skills_cli") as mock:
        mock.find = AsyncMock(return_value=[])
        mock.SkillsCLIError = type("SkillsCLIError", (Exception,), {})
        yield mock


class TestSkillsCatalog:
    @pytest.mark.asyncio
    async def test_search_returns_results(self, mock_skills_cli):
        mock_skills_cli.find.return_value = [
            {"name": "brainstorming", "source": "obra/superpowers", "description": "Use before creative work"},
        ]

        handler = _make_handler()
        result = await handler.process({"query": "brainstorming"}, MagicMock())
        assert result["ok"] is True
        assert len(result["results"]) == 1
        assert result["results"][0]["name"] == "brainstorming"

    @pytest.mark.asyncio
    async def test_empty_query_returns_error(self, mock_skills_cli):
        handler = _make_handler()
        result = await handler.process({"query": ""}, MagicMock())
        assert result["ok"] is False

    @pytest.mark.asyncio
    async def test_missing_query_returns_error(self, mock_skills_cli):
        handler = _make_handler()
        result = await handler.process({}, MagicMock())
        assert result["ok"] is False

    @pytest.mark.asyncio
    async def test_cli_error_returns_error(self, mock_skills_cli):
        mock_skills_cli.find.side_effect = Exception("npx not found")
        handler = _make_handler()
        result = await handler.process({"query": "test"}, MagicMock())
        assert result["ok"] is False
        assert "npx" in result["error"]
