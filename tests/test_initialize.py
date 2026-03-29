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
        "chat_model_provider": "openai",
        "chat_model_name": "gpt-4",
        "chat_model_api_base": "",
        "chat_model_ctx_length": 4096,
        "chat_model_vision": False,
        "chat_model_rl_requests": 0,
        "chat_model_rl_input": 0,
        "chat_model_rl_output": 0,
        "chat_model_kwargs": {},
        "util_model_provider": "openai",
        "util_model_name": "gpt-4",
        "util_model_api_base": "",
        "util_model_ctx_length": 4096,
        "util_model_rl_requests": 0,
        "util_model_rl_input": 0,
        "util_model_rl_output": 0,
        "util_model_kwargs": {},
        "embed_model_provider": "openai",
        "embed_model_name": "text-embedding-3-small",
        "embed_model_api_base": "",
        "embed_model_rl_requests": 0,
        "embed_model_kwargs": {},
        "browser_model_provider": "openai",
        "browser_model_name": "gpt-4",
        "browser_model_api_base": "",
        "browser_model_vision": False,
        "browser_model_kwargs": {},
        "agent_profile": "",
        "mcp_servers": "",
        "browser_http_headers": {},
    }


class TestInitializeAgent:
    def test_initialize_agent_returns_agent_config(self):
        from initialize import initialize_agent

        with (
            patch("initialize.settings.get_settings", return_value=_minimal_settings()),
            patch("initialize.settings.get_runtime_config", return_value={}),
            patch("initialize.runtime.args", {}),
        ):
            config = initialize_agent()
            assert config is not None
            assert config.chat_model is not None
            assert config.utility_model is not None
            assert config.embeddings_model is not None
            assert config.browser_model is not None
            assert config.knowledge_subdirs == ["default"]
            assert config.mcp_servers == ""

    def test_initialize_agent_uses_override_settings(self):
        from initialize import initialize_agent

        base = _minimal_settings()
        with (
            patch("initialize.settings.get_settings", return_value=base.copy()),
            patch("initialize.settings.merge_settings") as mock_merge,
            patch("initialize.settings.get_runtime_config", return_value={}),
            patch("initialize.runtime.args", {}),
        ):
            mock_merge.return_value = {**base, "agent_profile": "custom"}
            config = initialize_agent(override_settings={"agent_profile": "custom"})
            mock_merge.assert_called_once()
            assert config.profile == "custom"

    def test_initialize_agent_with_chat_id_overrides_chat_model(self):
        from initialize import initialize_agent

        base = _minimal_settings()
        mock_pool = MagicMock()
        mock_pool.is_connected.return_value = True

        with (
            patch("initialize.settings.get_settings", return_value=base.copy()),
            patch("initialize.settings.get_runtime_config", return_value={}),
            patch("initialize.runtime.args", {}),
            patch("api.chat_model_override._load_override", return_value={"provider": "google", "model": "gemini-2.5-pro"}),
            patch("helpers.connected_providers.ProviderPool.get_instance", return_value=mock_pool),
            patch("helpers.providers.get_provider_config", return_value={"name": "Google", "litellm_provider": "gemini"}),
        ):
            config = initialize_agent(chat_id="test-chat-123")
            assert config.chat_model.provider == "google"
            assert config.chat_model.name == "gemini-2.5-pro"

    def test_initialize_agent_chat_override_uses_api_base_from_kwargs(self):
        from initialize import initialize_agent

        base = _minimal_settings()
        mock_pool = MagicMock()
        mock_pool.is_connected.return_value = True
        provider_cfg = {"name": "Venice.ai", "litellm_provider": "openai", "kwargs": {"api_base": "https://api.venice.ai/api/v1"}}

        with (
            patch("initialize.settings.get_settings", return_value=base.copy()),
            patch("initialize.settings.get_runtime_config", return_value={}),
            patch("initialize.runtime.args", {}),
            patch("api.chat_model_override._load_override", return_value={"provider": "a0_venice", "model": "venice-model"}),
            patch("helpers.connected_providers.ProviderPool.get_instance", return_value=mock_pool),
            patch("helpers.providers.get_provider_config", return_value=provider_cfg),
        ):
            config = initialize_agent(chat_id="test-chat-456")
            assert config.chat_model.api_base == "https://api.venice.ai/api/v1"
            assert config.chat_model.provider == "a0_venice"

    def test_initialize_agent_chat_id_no_override_keeps_default(self):
        from initialize import initialize_agent

        base = _minimal_settings()
        with (
            patch("initialize.settings.get_settings", return_value=base.copy()),
            patch("initialize.settings.get_runtime_config", return_value={}),
            patch("initialize.runtime.args", {}),
            patch("api.chat_model_override._load_override", return_value=None),
        ):
            config = initialize_agent(chat_id="test-chat-123")
            assert config.chat_model.provider == "openai"
            assert config.chat_model.name == "gpt-4"

    def test_initialize_agent_chat_id_disconnected_provider_keeps_default(self):
        from initialize import initialize_agent

        base = _minimal_settings()
        mock_pool = MagicMock()
        mock_pool.is_connected.return_value = False

        with (
            patch("initialize.settings.get_settings", return_value=base.copy()),
            patch("initialize.settings.get_runtime_config", return_value={}),
            patch("initialize.runtime.args", {}),
            patch("api.chat_model_override._load_override", return_value={"provider": "google", "model": "gemini-2.5-pro"}),
            patch("helpers.connected_providers.ProviderPool.get_instance", return_value=mock_pool),
        ):
            config = initialize_agent(chat_id="test-chat-123")
            assert config.chat_model.provider == "openai"
            assert config.chat_model.name == "gpt-4"

    def test_initialize_agent_normalizes_model_kwargs_string_numbers(self):
        from initialize import initialize_agent

        base = _minimal_settings()
        base["chat_model_kwargs"] = {"temperature": "0.7", "max_tokens": "1024"}
        with (
            patch("initialize.settings.get_settings", return_value=base),
            patch("initialize.settings.get_runtime_config", return_value={}),
            patch("initialize.runtime.args", {}),
        ):
            config = initialize_agent()
            assert config.chat_model.kwargs["temperature"] == 0.7
            assert config.chat_model.kwargs["max_tokens"] == 1024


class TestArgsOverride:
    def test_args_override_sets_config_attributes(self):
        from initialize import _args_override

        mock_cfg = MagicMock()
        mock_cfg.profile = "original"
        mock_cfg.chat_model = None
        mock_cfg.utility_model = None
        mock_cfg.embeddings_model = None
        mock_cfg.browser_model = None
        mock_cfg.mcp_servers = ""

        with patch("initialize.runtime") as mock_runtime:
            mock_runtime.args = {"profile": "overridden"}
            _args_override(mock_cfg)
            assert mock_cfg.profile == "overridden"

    def test_args_override_converts_bool(self):
        from initialize import _args_override

        mock_cfg = MagicMock()
        mock_cfg.code_exec_ssh_enabled = True
        mock_cfg.chat_model = None
        mock_cfg.utility_model = None
        mock_cfg.embeddings_model = None
        mock_cfg.browser_model = None
        mock_cfg.mcp_servers = ""

        with patch("initialize.runtime") as mock_runtime:
            mock_runtime.args = {"code_exec_ssh_enabled": "false"}
            _args_override(mock_cfg)
            assert mock_cfg.code_exec_ssh_enabled is False

    def test_args_override_converts_int(self):
        from initialize import _args_override

        mock_cfg = MagicMock()
        mock_cfg.code_exec_ssh_port = 55022
        mock_cfg.chat_model = None
        mock_cfg.utility_model = None
        mock_cfg.embeddings_model = None
        mock_cfg.browser_model = None
        mock_cfg.mcp_servers = ""

        with patch("initialize.runtime") as mock_runtime:
            mock_runtime.args = {"code_exec_ssh_port": "12345"}
            _args_override(mock_cfg)
            assert mock_cfg.code_exec_ssh_port == 12345


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

        with patch("plugins.scheduler.helpers.job_loop.run_loop", AsyncMock()):
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
