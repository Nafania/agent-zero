"""Tests for provider_models API."""

import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.provider_models import ProviderModels
from helpers.oauth import ModelInfo


def _make():
    return ProviderModels(MagicMock(), threading.Lock())


class TestProviderModels:
    @pytest.mark.asyncio
    async def test_returns_model_list(self):
        handler = _make()
        mock_models = [
            ModelInfo(id="gemini-2.5-pro", name="Gemini 2.5 Pro", context_length=1048576, supports_vision=True),
            ModelInfo(id="gemini-2.0-flash", name="Gemini 2.0 Flash", context_length=1048576, supports_vision=True),
        ]
        with patch("api.provider_models.ProviderPool") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool.list_models = AsyncMock(return_value=mock_models)
            mock_pool_cls.get_instance.return_value = mock_pool

            result = await handler.process({"provider_id": "google"}, MagicMock())

        assert len(result["models"]) == 2
        assert result["models"][0]["id"] == "gemini-2.5-pro"
        assert result["models"][0]["context_length"] == 1048576

    @pytest.mark.asyncio
    async def test_returns_empty_for_disconnected(self):
        handler = _make()
        with patch("api.provider_models.ProviderPool") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool.list_models = AsyncMock(return_value=[])
            mock_pool_cls.get_instance.return_value = mock_pool

            result = await handler.process({"provider_id": "unknown"}, MagicMock())

        assert result["models"] == []

    @pytest.mark.asyncio
    async def test_get_methods_includes_get(self):
        assert "GET" in ProviderModels.get_methods()
        assert "POST" in ProviderModels.get_methods()
