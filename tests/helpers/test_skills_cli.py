"""Tests for helpers/skills_cli.py — npx skills CLI wrapper."""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def mock_subprocess():
    """Mock asyncio.create_subprocess_exec."""
    with patch("helpers.skills_cli.asyncio.create_subprocess_exec") as mock_exec:
        process = AsyncMock()
        process.returncode = 0
        process.communicate = AsyncMock(return_value=(b"", b""))
        mock_exec.return_value = process
        yield mock_exec, process


# --- _run_npx ---

class TestRunNpx:
    @pytest.mark.asyncio
    async def test_runs_npx_with_args(self, mock_subprocess):
        from helpers.skills_cli import _run_npx
        mock_exec, process = mock_subprocess
        process.communicate.return_value = (b"output text", b"")

        result = await _run_npx("find", "python")
        assert result == "output text"
        mock_exec.assert_called_once()
        args = mock_exec.call_args[0]
        assert "npx" in args[0]
        assert "skills" in args
        assert "find" in args
        assert "python" in args

    @pytest.mark.asyncio
    async def test_raises_on_nonzero_exit(self, mock_subprocess):
        from helpers.skills_cli import _run_npx, SkillsCLIError
        _, process = mock_subprocess
        process.returncode = 1
        process.communicate.return_value = (b"", b"some error")

        with pytest.raises(SkillsCLIError, match="some error"):
            await _run_npx("find", "nonexistent")

    @pytest.mark.asyncio
    async def test_raises_on_timeout(self, mock_subprocess):
        from helpers.skills_cli import _run_npx, SkillsCLIError
        _, process = mock_subprocess
        process.communicate.side_effect = asyncio.TimeoutError()
        process.wait = AsyncMock()

        with pytest.raises(SkillsCLIError, match="timed out"):
            await _run_npx("add", "owner/repo", timeout=1)
        process.kill.assert_called_once()
        process.wait.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_when_npx_not_found(self, mock_subprocess):
        from helpers.skills_cli import _run_npx, SkillsCLIError
        mock_exec, _ = mock_subprocess
        mock_exec.side_effect = FileNotFoundError("npx not found")

        with pytest.raises(SkillsCLIError, match="Node.js"):
            await _run_npx("find", "test")


# --- parse_find_output ---

class TestParseFindOutput:
    def test_parses_skill_entries(self):
        from helpers.skills_cli import parse_find_output
        output = (
            "obra/superpowers@using-superpowers 26.8K installs\n"
            "└ https://skills.sh/obra/superpowers/using-superpowers\n"
            "\n"
            "makfly/superpowers-symfony@symfony:using-symfony-superpowers 121 installs\n"
            "└ https://skills.sh/makfly/superpowers-symfony/symfony:using-symfony-superpowers\n"
        )
        results = parse_find_output(output)
        assert len(results) == 2
        assert results[0]["name"] == "using-superpowers"
        assert results[0]["source"] == "obra/superpowers@using-superpowers"
        assert results[0]["installs"] == "26.8K installs"
        assert results[0]["description"] == ""
        assert results[0]["url"] == "https://skills.sh/obra/superpowers/using-superpowers"
        assert results[1]["source"] == "makfly/superpowers-symfony@symfony:using-symfony-superpowers"

    def test_parses_ansi_output(self):
        from helpers.skills_cli import parse_find_output
        output = (
            "\x1b[38;5;145mobra/superpowers@using-superpowers\x1b[0m \x1b[36m26.8K installs\x1b[0m\n"
            "\x1b[38;5;102m└ https://skills.sh/obra/superpowers/using-superpowers\x1b[0m\n"
        )
        results = parse_find_output(output)
        assert len(results) == 1
        assert results[0]["name"] == "using-superpowers"
        assert results[0]["source"] == "obra/superpowers@using-superpowers"

    def test_returns_empty_for_no_results(self):
        from helpers.skills_cli import parse_find_output
        results = parse_find_output("No skills found matching 'xyznonexistent'")
        assert results == []

    def test_handles_empty_output(self):
        from helpers.skills_cli import parse_find_output
        assert parse_find_output("") == []


# --- parse_list_output ---

class TestParseListOutput:
    def test_parses_skill_names_and_descriptions(self):
        from helpers.skills_cli import parse_list_output
        output = (
            "│  Available Skills\n"
            "│\n"
            "│    brainstorming\n"
            "│\n"
            "│      You MUST use this before any creative work.\n"
            "│\n"
            "│    writing-plans\n"
            "│\n"
            "│      Use when you have a spec or requirements.\n"
            "│\n"
        )
        result = parse_list_output(output)
        assert len(result) == 2
        assert result["brainstorming"] == "You MUST use this before any creative work."
        assert result["writing-plans"] == "Use when you have a spec or requirements."

    def test_handles_empty_output(self):
        from helpers.skills_cli import parse_list_output
        assert parse_list_output("") == {}

    def test_skips_noise_lines(self):
        from helpers.skills_cli import parse_list_output
        output = (
            "│  Tip: use the --yes flag\n"
            "│  Source: https://github.com/obra/superpowers.git\n"
            "│  Found 2 skills\n"
            "│  Available Skills\n"
            "│    my-skill\n"
            "│      Does something cool.\n"
            "│  Use --skill <name> to install\n"
        )
        result = parse_list_output(output)
        assert len(result) == 1
        assert result["my-skill"] == "Does something cool."


# --- find ---

class TestFind:
    @pytest.mark.asyncio
    async def test_find_returns_parsed_results(self, mock_subprocess):
        from helpers.skills_cli import find
        _, process = mock_subprocess
        process.communicate.return_value = (
            b"obra/superpowers@brainstorming 500 installs\n"
            b"\xe2\x94\x94 https://skills.sh/obra/superpowers/brainstorming\n",
            b"",
        )

        results = await find("brainstorming")
        assert len(results) == 1
        assert results[0]["name"] == "brainstorming"
        assert results[0]["source"] == "obra/superpowers@brainstorming"

    @pytest.mark.asyncio
    async def test_find_uses_cache(self, mock_subprocess):
        from helpers.skills_cli import find, _cache
        _cache.clear()
        _, process = mock_subprocess
        process.communicate.return_value = (
            b"owner/repo@skill1 10 installs\n"
            b"\xe2\x94\x94 https://skills.sh/owner/repo/skill1\n",
            b"",
        )

        r1 = await find("test-query")
        r2 = await find("test-query")
        assert r1 == r2
        assert mock_subprocess[0].call_count == 1
        _cache.clear()

    @pytest.mark.asyncio
    async def test_find_empty_query_returns_empty(self, mock_subprocess):
        from helpers.skills_cli import find
        results = await find("")
        assert results == []


# --- add ---

class TestAdd:
    @pytest.mark.asyncio
    async def test_add_single_skill(self, mock_subprocess):
        from helpers.skills_cli import add, _cache
        _cache.clear()
        _, process = mock_subprocess
        process.communicate.return_value = (b"Installed brainstorming", b"")

        result = await add("obra/superpowers@brainstorming")
        assert "Installed" in result
        args = mock_subprocess[0].call_args[0]
        assert "add" in args
        assert "obra/superpowers@brainstorming" in args

    @pytest.mark.asyncio
    async def test_add_multi_skill_repo(self, mock_subprocess):
        from helpers.skills_cli import add, _cache
        _cache.clear()
        _, process = mock_subprocess
        process.communicate.return_value = (b"ok", b"")

        with patch("helpers.skills_cli.list_repo_skills",
                    return_value={"brainstorming": "desc1", "writing-plans": "desc2"}):
            result = await add("obra/superpowers")
        assert "2 skills" in result
        assert mock_subprocess[0].call_count >= 2

    @pytest.mark.asyncio
    async def test_add_clears_cache(self, mock_subprocess):
        from helpers.skills_cli import add, _cache
        _cache["old-query"] = ([], 0)
        _, process = mock_subprocess
        process.communicate.return_value = (b"ok", b"")

        await add("owner/repo@skill")
        assert len(_cache) == 0


# --- remove ---

class TestRemove:
    @pytest.mark.asyncio
    async def test_remove_calls_npx_skills_remove(self, mock_subprocess):
        from helpers.skills_cli import remove, _cache
        _cache.clear()
        _, process = mock_subprocess
        process.communicate.return_value = (b"Removed skill", b"")

        result = await remove("brainstorming")
        args = mock_subprocess[0].call_args[0]
        assert "remove" in args


# --- check_updates ---

class TestCheckUpdates:
    @pytest.mark.asyncio
    async def test_check_calls_npx_skills_check(self, mock_subprocess):
        from helpers.skills_cli import check_updates
        _, process = mock_subprocess
        process.communicate.return_value = (b"All skills up to date", b"")

        result = await check_updates()
        assert isinstance(result, str)


# --- update ---

class TestUpdate:
    @pytest.mark.asyncio
    async def test_update_calls_npx_skills_update(self, mock_subprocess):
        from helpers.skills_cli import update
        _, process = mock_subprocess
        process.communicate.return_value = (b"Updated 2 skills", b"")

        result = await update()
        assert isinstance(result, str)
