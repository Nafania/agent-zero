"""Tests for connected_providers API handler."""

import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from python.api.connected_providers import ConnectedProviders
from python.helpers.connected_providers import ConnectedProvider


def _make():
    return ConnectedProviders(MagicMock(), threading.Lock())


class TestConnectedProviders:
    @pytest.mark.asyncio
    async def test_returns_connected_providers(self):
        handler = _make()
        mock_connected = [
            ConnectedProvider(provider_id="openrouter", auth_method="api_key", is_active=True),
            ConnectedProvider(provider_id="google", auth_method="oauth", is_active=True),
        ]
        with patch("python.api.connected_providers.ProviderPool") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool.get_connected.return_value = mock_connected
            mock_pool_cls.get_instance.return_value = mock_pool

            result = await handler.process({}, MagicMock())

        assert len(result["providers"]) == 2
        assert result["providers"][0]["provider_id"] == "openrouter"
        assert result["providers"][0]["auth_method"] == "api_key"
        assert result["providers"][0]["is_active"] is True
        assert result["providers"][1]["provider_id"] == "google"
        assert result["providers"][1]["auth_method"] == "oauth"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_providers(self):
        handler = _make()
        with patch("python.api.connected_providers.ProviderPool") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool.get_connected.return_value = []
            mock_pool_cls.get_instance.return_value = mock_pool

            result = await handler.process({}, MagicMock())

        assert result["providers"] == []

    def test_get_methods(self):
        assert "GET" in ConnectedProviders.get_methods()
        assert "POST" in ConnectedProviders.get_methods()
