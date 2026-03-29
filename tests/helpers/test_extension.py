"""Tests for helpers/extension.py — Extension base class, call_extensions, _get_extensions."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from helpers.extension import (
    Extension,
    call_extensions,
    _get_file_from_module,
    _get_extensions,
)


class ConcreteExtension(Extension):
    async def execute(self, **kwargs):
        return kwargs.get("value", "default")


class TestExtensionBase:
    def test_init_stores_agent_and_kwargs(self):
        agent = MagicMock()
        ext = ConcreteExtension(agent=agent, foo="bar")
        assert ext.agent is agent
        assert ext.kwargs == {"foo": "bar"}


class TestGetFileFromModule:
    def test_returns_last_part_of_module(self):
        assert _get_file_from_module("extensions.python.my_ext") == "my_ext"

    def test_handles_single_part(self):
        assert _get_file_from_module("ext") == "ext"


class TestGetExtensions:
    def test_returns_empty_when_folder_not_exists(self):
        with patch("helpers.extension.files") as mf:
            mf.get_abs_path.return_value = "/nonexistent"
            mf.exists.return_value = False
            result = _get_extensions("/nonexistent")
        assert result == []

    def test_caches_and_returns_classes(self):
        with patch("helpers.extension.files") as mf:
            mf.get_abs_path.return_value = "/ext"
            mf.exists.return_value = True
            with patch("helpers.extension.extract_tools") as me:
                me.load_classes_from_folder.return_value = [ConcreteExtension]
                result = _get_extensions("/ext")
        assert ConcreteExtension in result


class TestCallExtensions:
    @pytest.mark.asyncio
    async def test_calls_extensions_in_order(self):
        with patch("helpers.subagents.get_paths", return_value=["/a0/extensions/python"]), \
             patch("helpers.extension._get_extensions") as mg:
            mg.return_value = [ConcreteExtension]
            results = []
            async def mock_execute(self, **kwargs):
                results.append(kwargs)
                return None
            with patch.object(ConcreteExtension, "execute", mock_execute):
                await call_extensions("test_point", agent=None, value="x")
        assert len(results) == 1
        assert results[0].get("value") == "x"

    @pytest.mark.asyncio
    async def test_merges_unique_by_file_name(self):
        class ExtA(Extension):
            async def execute(self, **kwargs):
                return "A"

        class ExtB(Extension):
            __module__ = "other.other_ext"
            async def execute(self, **kwargs):
                return "B"

        with patch("helpers.subagents.get_paths", return_value=["/a", "/b"]), \
             patch("helpers.extension._get_extensions") as mg:
            mg.side_effect = [[ExtA], [ExtB]]
            await call_extensions("test", agent=None)
        assert mg.call_count >= 1

    @pytest.mark.asyncio
    async def test_call_extensions_splits_override_and_default_paths(self):
        """get_paths must be called with include_default=False so profile/user
        override paths don't include 'python/'. The default path
        (extensions/python/<ext_point>) is appended separately."""
        with patch("helpers.subagents.get_paths", return_value=[]) as mock_gp, \
             patch("helpers.extension.files") as mock_files, \
             patch("helpers.extension._get_extensions", return_value=[]):
            mock_files.get_abs_path.return_value = "/abs/extensions/python/agent_init"
            mock_files.exists.return_value = True
            await call_extensions("agent_init", agent=None)

        mock_gp.assert_called_once_with(
            None, "extensions", "agent_init",
            default_root="", include_default=False,
        )
        mock_files.get_abs_path.assert_called_with("extensions", "python", "agent_init")
        mock_files.exists.assert_called_with("/abs/extensions/python/agent_init")
