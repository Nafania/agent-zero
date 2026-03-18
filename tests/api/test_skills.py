"""Tests for /skills API endpoint."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _make_handler():
    from python.api.skills import Skills
    return Skills(app=MagicMock(), thread_lock=MagicMock())


class TestCheckUpdates:
    @pytest.mark.asyncio
    @patch("python.api.skills.skills_cli")
    async def test_check_updates(self, mock_cli):
        mock_cli.check_updates = AsyncMock(return_value="All skills up to date.")

        handler = _make_handler()
        result = await handler.process({"action": "check_updates"}, MagicMock())

        assert result["ok"] is True
        assert result["data"]["output"] == "All skills up to date."
        mock_cli.check_updates.assert_awaited_once()


class TestUpdate:
    @pytest.mark.asyncio
    @patch("python.api.skills.skills_cli")
    async def test_update_all(self, mock_cli):
        mock_cli.update = AsyncMock(return_value="Updated 2 skills.")

        handler = _make_handler()
        result = await handler.process({"action": "update"}, MagicMock())

        assert result["ok"] is True
        assert result["data"]["output"] == "Updated 2 skills."
        mock_cli.update.assert_awaited_once()


class TestMoveSkill:
    @pytest.mark.asyncio
    @patch("python.api.skills.os.path.exists", return_value=False)
    @patch("python.api.skills.os.makedirs")
    @patch("python.api.skills.shutil.move")
    @patch("python.api.skills.os.path.isdir", return_value=True)
    @patch("python.api.skills.projects")
    async def test_move_skill(self, mock_projects, mock_isdir, mock_move, mock_makedirs, mock_exists):
        mock_projects.get_project_meta_folder.return_value = "/a0/projects/myproj/.meta/skills"

        handler = _make_handler()
        result = await handler.process(
            {"action": "move", "skill_path": "/a0/usr/skills/my_skill", "target_project": "myproj"},
            MagicMock(),
        )

        assert result["ok"] is True
        assert result["data"]["moved_to"] == "myproj"
        assert result["data"]["skill_path"] == "/a0/projects/myproj/.meta/skills/my_skill"
        mock_move.assert_called_once()

    @pytest.mark.asyncio
    async def test_move_skill_missing_path(self):
        handler = _make_handler()
        result = await handler.process(
            {"action": "move", "skill_path": "", "target_project": "myproj"},
            MagicMock(),
        )

        assert result["ok"] is False
        assert "skill_path is required" in result["error"]

    @pytest.mark.asyncio
    @patch("python.api.skills.os.path.isdir", return_value=False)
    async def test_move_skill_dir_not_found(self, mock_isdir):
        handler = _make_handler()
        result = await handler.process(
            {"action": "move", "skill_path": "/nonexistent/skill", "target_project": "proj"},
            MagicMock(),
        )

        assert result["ok"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    @patch("python.api.skills.os.path.exists", return_value=True)
    @patch("python.api.skills.os.makedirs")
    @patch("python.api.skills.os.path.isdir", return_value=True)
    @patch("python.api.skills.files")
    async def test_move_skill_to_global(self, mock_files, mock_isdir, mock_makedirs, mock_exists):
        mock_files.get_abs_path.return_value = "/a0/usr/skills"

        handler = _make_handler()
        result = await handler.process(
            {"action": "move", "skill_path": "/a0/projects/proj/.meta/skills/my_skill"},
            MagicMock(),
        )

        assert result["ok"] is False
        assert "already exists" in result["error"]

    @pytest.mark.asyncio
    @patch("python.api.skills.os.path.exists", return_value=False)
    @patch("python.api.skills.os.makedirs")
    @patch("python.api.skills.shutil.move")
    @patch("python.api.skills.os.path.isdir", return_value=True)
    @patch("python.api.skills.files")
    async def test_move_skill_to_global_success(self, mock_files, mock_isdir, mock_move, mock_makedirs, mock_exists):
        mock_files.get_abs_path.return_value = "/a0/usr/skills"

        handler = _make_handler()
        result = await handler.process(
            {"action": "move", "skill_path": "/a0/projects/proj/.meta/skills/my_skill"},
            MagicMock(),
        )

        assert result["ok"] is True
        assert result["data"]["moved_to"] == "global"
        assert result["data"]["skill_path"] == "/a0/usr/skills/my_skill"


class TestInvalidAction:
    @pytest.mark.asyncio
    async def test_invalid_action(self):
        handler = _make_handler()
        result = await handler.process({"action": "bogus"}, MagicMock())

        assert result["ok"] is False
        assert "Invalid action" in result["error"]
