"""Tests for initialize.py — initialization functions."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _minimal_settings():
    return {
        "agent_profile": "",
        "mcp_servers": "",
    }


class TestInitializeAgent:
    def test_initialize_agent_returns_agent_config(self):
        from initialize import initialize_agent

        with (
            patch("initialize.settings.get_settings", return_value=_minimal_settings()),
            patch("initialize.runtime.args", {}),
        ):
            config = initialize_agent()
            assert config is not None
            assert config.knowledge_subdirs == ["default"]
            assert config.mcp_servers == ""
            assert config.profile == ""
            assert config.additional == {}

    def test_initialize_agent_uses_override_settings(self):
        from initialize import initialize_agent

        base = _minimal_settings()
        with (
            patch("initialize.settings.get_settings", return_value=base.copy()),
            patch("initialize.settings.merge_settings") as mock_merge,
            patch("initialize.runtime.args", {}),
        ):
            mock_merge.return_value = {**base, "agent_profile": "custom"}
            config = initialize_agent(override_settings={"agent_profile": "custom"})
            mock_merge.assert_called_once()
            assert config.profile == "custom"


class TestArgsOverride:
    def test_args_override_sets_config_attributes(self):
        from initialize import _args_override

        mock_cfg = MagicMock()
        mock_cfg.profile = "original"
        mock_cfg.mcp_servers = ""

        with patch("initialize.runtime") as mock_runtime:
            mock_runtime.args = {"profile": "overridden"}
            _args_override(mock_cfg)
            assert mock_cfg.profile == "overridden"


class TestInitializeChats:
    def test_initialize_chats_returns_deferred_task(self):
        from initialize import initialize_chats

        with patch("helpers.persist_chat.load_tmp_chats"):
            result = initialize_chats()
            assert result is not None
            assert hasattr(result, "start_task")


class TestInitializeMcp:
    def test_initialize_mcp_returns_deferred_task(self):
        from initialize import initialize_mcp

        result = initialize_mcp()
        assert result is not None
        assert hasattr(result, "start_task")


class TestInitializeJobLoop:
    def test_initialize_job_loop_returns_deferred_task(self):
        from initialize import initialize_job_loop

        with patch("plugins._scheduler.helpers.job_loop.run_loop", AsyncMock()):
            result = initialize_job_loop()
            assert result is not None
            assert hasattr(result, "start_task")


class TestInitializePreload:
    def test_initialize_preload_returns_deferred_task(self):
        from initialize import initialize_preload

        mock_preload_mod = MagicMock()
        mock_preload_mod.preload = AsyncMock()
        with patch.dict("sys.modules", {"preload": mock_preload_mod}):
            result = initialize_preload()
            assert result is not None
            assert hasattr(result, "start_task")


class TestInitializeCognee:
    def test_initialize_cognee_calls_configure_and_starts_task(self):
        from initialize import initialize_cognee

        with (
            patch("helpers.cognee_init.configure_cognee") as mock_configure,
            patch("helpers.cognee_background.CogneeBackgroundWorker") as mock_worker,
        ):
            mock_instance = MagicMock()
            mock_worker.get_instance.return_value = mock_instance
            # Patch migration module so deferred task can import it
            mock_migrate_mod = MagicMock()
            mock_migrate_mod.run_migration = AsyncMock(return_value=True)
            with patch.dict(
                "sys.modules",
                {
                    "scripts": MagicMock(),
                    "scripts.migrate_faiss_to_cognee": mock_migrate_mod,
                },
            ):
                result = initialize_cognee()
            mock_configure.assert_called_once()
            assert result is not None


class TestInitializeMigration:
    def test_initialize_migration_calls_migrate_and_reload(self):
        from initialize import initialize_migration

        with (
            patch("helpers.migration.migrate_user_data") as mock_migrate,
            patch("helpers.dotenv.load_dotenv") as mock_dotenv,
            patch("helpers.settings.reload_settings") as mock_reload,
        ):
            initialize_migration()
            mock_migrate.assert_called()
            mock_dotenv.assert_called()
            mock_reload.assert_called()
