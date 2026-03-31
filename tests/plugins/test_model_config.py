import pytest
from unittest.mock import patch, MagicMock
import models
from plugins._model_config.helpers.model_config import (
    build_model_config,
    _normalize_kwargs,
    get_config,
    get_chat_model_config,
    get_utility_model_config,
    get_embedding_model_config,
    get_browser_model_config,
    get_ctx_history,
    get_ctx_input,
)


class TestNormalizeKwargs:
    def test_string_int_values_coerced(self):
        assert _normalize_kwargs({"temperature": "1"}) == {"temperature": 1}

    def test_string_float_values_coerced(self):
        assert _normalize_kwargs({"temperature": "0.7"}) == {"temperature": 0.7}

    def test_non_numeric_strings_kept(self):
        assert _normalize_kwargs({"api_base": "http://x"}) == {"api_base": "http://x"}

    def test_non_string_values_passed_through(self):
        assert _normalize_kwargs({"top_k": 10, "flag": True}) == {"top_k": 10, "flag": True}

    def test_empty_dict(self):
        assert _normalize_kwargs({}) == {}

    def test_mixed_types(self):
        result = _normalize_kwargs({"a": "42", "b": "3.14", "c": "hello", "d": 99})
        assert result == {"a": 42, "b": 3.14, "c": "hello", "d": 99}


class TestBuildModelConfig:
    def test_minimal_config(self):
        mc = build_model_config({}, models.ModelType.CHAT)
        assert mc.type == models.ModelType.CHAT
        assert mc.provider == ""
        assert mc.name == ""
        assert mc.vision is False
        assert mc.kwargs == {}

    def test_full_config(self):
        cfg = {
            "provider": "openai",
            "name": "gpt-4o",
            "api_base": "https://api.openai.com",
            "ctx_length": 128000,
            "vision": True,
            "rl_requests": 100,
            "rl_input": 50,
            "rl_output": 25,
            "kwargs": {"temperature": "0.5"},
        }
        mc = build_model_config(cfg, models.ModelType.CHAT)
        assert mc.provider == "openai"
        assert mc.name == "gpt-4o"
        assert mc.api_base == "https://api.openai.com"
        assert mc.ctx_length == 128000
        assert mc.vision is True
        assert mc.limit_requests == 100
        assert mc.limit_input == 50
        assert mc.limit_output == 25
        assert mc.kwargs == {"temperature": 0.5}

    def test_embedding_type(self):
        mc = build_model_config({"provider": "huggingface"}, models.ModelType.EMBEDDING)
        assert mc.type == models.ModelType.EMBEDDING
        assert mc.provider == "huggingface"

    def test_string_numeric_fields_coerced(self):
        cfg = {"ctx_length": "4096", "rl_requests": "10", "vision": 1}
        mc = build_model_config(cfg, models.ModelType.CHAT)
        assert mc.ctx_length == 4096
        assert mc.limit_requests == 10
        assert mc.vision is True

    def test_kwargs_string_in_config_treated_as_empty(self):
        cfg = {"kwargs": "invalid"}
        mc = build_model_config(cfg, models.ModelType.CHAT)
        assert mc.kwargs == {}


class TestGetConfigHelpers:
    @patch("plugins._model_config.helpers.model_config.plugins.get_plugin_config")
    def test_get_config_delegates_to_plugins(self, mock_get):
        mock_get.return_value = {"chat_model": {"provider": "openai"}}
        result = get_config(agent=None)
        mock_get.assert_called_once_with("_model_config", agent=None, project_name=None, agent_profile=None)
        assert result == {"chat_model": {"provider": "openai"}}

    @patch("plugins._model_config.helpers.model_config.plugins.get_plugin_config")
    def test_get_config_returns_empty_dict_when_none(self, mock_get):
        mock_get.return_value = None
        assert get_config() == {}

    @patch("plugins._model_config.helpers.model_config.get_config")
    def test_get_chat_model_config(self, mock_cfg):
        mock_cfg.return_value = {"chat_model": {"provider": "anthropic"}}
        assert get_chat_model_config() == {"provider": "anthropic"}

    @patch("plugins._model_config.helpers.model_config.get_config")
    def test_get_utility_model_config(self, mock_cfg):
        mock_cfg.return_value = {"utility_model": {"provider": "openai"}}
        assert get_utility_model_config() == {"provider": "openai"}

    @patch("plugins._model_config.helpers.model_config.get_config")
    def test_get_embedding_model_config(self, mock_cfg):
        mock_cfg.return_value = {"embedding_model": {"name": "all-MiniLM-L6-v2"}}
        assert get_embedding_model_config() == {"name": "all-MiniLM-L6-v2"}

    @patch("plugins._model_config.helpers.model_config.get_config")
    def test_get_browser_model_config(self, mock_cfg):
        mock_cfg.return_value = {"browser_model": {"vision": True}}
        assert get_browser_model_config() == {"vision": True}

    @patch("plugins._model_config.helpers.model_config.get_config")
    def test_missing_section_returns_empty_dict(self, mock_cfg):
        mock_cfg.return_value = {}
        assert get_chat_model_config() == {}
        assert get_utility_model_config() == {}
        assert get_embedding_model_config() == {}
        assert get_browser_model_config() == {}


class TestCtxHelpers:
    @patch("plugins._model_config.helpers.model_config.get_chat_model_config")
    def test_get_ctx_history_default(self, mock_cfg):
        mock_cfg.return_value = {}
        assert get_ctx_history() == 0.7

    @patch("plugins._model_config.helpers.model_config.get_chat_model_config")
    def test_get_ctx_history_from_config(self, mock_cfg):
        mock_cfg.return_value = {"ctx_history": 0.5}
        assert get_ctx_history() == 0.5

    @patch("plugins._model_config.helpers.model_config.get_utility_model_config")
    def test_get_ctx_input_default(self, mock_cfg):
        mock_cfg.return_value = {}
        assert get_ctx_input() == 0.7

    @patch("plugins._model_config.helpers.model_config.get_utility_model_config")
    def test_get_ctx_input_from_config(self, mock_cfg):
        mock_cfg.return_value = {"ctx_input": 0.3}
        assert get_ctx_input() == 0.3
