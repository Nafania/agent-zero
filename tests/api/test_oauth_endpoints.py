"""Tests for OAuth API endpoints."""

import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.oauth_authorize import OAuthAuthorize, _pending_states
from api.oauth_callback import OAuthCallback
from api.oauth_disconnect import OAuthDisconnect
from api.oauth_providers import OAuthProviders
from api.oauth_exchange import OAuthExchange
from api.oauth_status import OAuthStatus


def _make(cls, app=None, lock=None):
    return cls(app=app or MagicMock(), thread_lock=lock or threading.Lock())


class TestOAuthAuthorize:
    @pytest.mark.asyncio
    async def test_returns_authorization_url(self):
        handler = _make(OAuthAuthorize)
        with patch("api.oauth_authorize.get_oauth_provider") as mock_get:
            mock_provider = MagicMock()
            mock_provider.get_authorization_url.return_value = (
                "https://accounts.google.com/auth?client_id=test"
            )
            mock_provider.supports_pkce = False
            mock_get.return_value = mock_provider

            with patch("api.oauth_authorize.dotenv"):
                result = await handler.process(
                    {
                        "provider_id": "google",
                        "client_id": "test-cid",
                        "client_secret": "test-cs",
                        "redirect_uri": "http://localhost/oauth_callback",
                    },
                    MagicMock(),
                )

        assert "authorization_url" in result
        assert "google.com" in result["authorization_url"]
        assert "state" in result

    @pytest.mark.asyncio
    async def test_returns_error_for_unknown_provider(self):
        handler = _make(OAuthAuthorize)
        with patch("api.oauth_authorize.get_oauth_provider", return_value=None):
            result = await handler.process({"provider_id": "unknown"}, MagicMock())
        assert "error" in result

    @pytest.mark.asyncio
    async def test_stores_pending_state(self):
        handler = _make(OAuthAuthorize)
        _pending_states.clear()
        with patch("api.oauth_authorize.get_oauth_provider") as mock_get:
            mock_provider = MagicMock()
            mock_provider.get_authorization_url.return_value = "https://example.com/auth"
            mock_provider.supports_pkce = True
            mock_get.return_value = mock_provider

            with patch("api.oauth_authorize.dotenv"):
                result = await handler.process(
                    {"provider_id": "anthropic", "flow": "manual"},
                    MagicMock(),
                )

        state = result["state"]
        assert state in _pending_states
        assert _pending_states[state]["provider_id"] == "anthropic"
        assert _pending_states[state]["code_verifier"] is not None
        assert result["flow"] == "manual"
        _pending_states.clear()

    @pytest.mark.asyncio
    async def test_default_flow_is_redirect(self):
        handler = _make(OAuthAuthorize)
        with patch("api.oauth_authorize.get_oauth_provider") as mock_get:
            mock_provider = MagicMock()
            mock_provider.get_authorization_url.return_value = "https://example.com/auth"
            mock_provider.supports_pkce = False
            mock_get.return_value = mock_provider
            with patch("api.oauth_authorize.dotenv"):
                result = await handler.process({"provider_id": "google"}, MagicMock())
        assert result["flow"] == "redirect"
        _pending_states.clear()


class TestOAuthCallback:
    def test_get_methods(self):
        assert OAuthCallback.get_methods() == ["GET"]

    def test_requires_no_csrf(self):
        assert OAuthCallback.requires_csrf() is False

    @pytest.mark.asyncio
    async def test_returns_html_on_oauth_error(self):
        handler = _make(OAuthCallback)
        request = MagicMock()
        request.args = {"error": "access_denied", "state": "", "code": ""}

        with patch("api.oauth_callback.FlaskResponse") as mock_resp:
            await handler.process({}, request)

        mock_resp.assert_called_once()
        html = mock_resp.call_args[0][0]
        assert "cancelled" in html.lower()
        assert mock_resp.call_args[1]["content_type"] == "text/html"

    @pytest.mark.asyncio
    async def test_returns_400_on_invalid_state(self):
        handler = _make(OAuthCallback)
        request = MagicMock()
        request.args = {"code": "abc", "state": "bad-state", "error": ""}

        with patch("api.oauth_callback.FlaskResponse") as mock_resp:
            await handler.process({}, request)

        mock_resp.assert_called_once()
        assert mock_resp.call_args[1]["status"] == 400
        assert "Invalid" in mock_resp.call_args[0][0]

    @pytest.mark.asyncio
    async def test_returns_400_for_unknown_provider(self):
        handler = _make(OAuthCallback)
        _pending_states["unk-state"] = {
            "provider_id": "nonexistent",
            "redirect_uri": "http://localhost/cb",
            "code_verifier": None,
            "flow": "redirect",
            "created": 9999999999,
        }
        request = MagicMock()
        request.args = {"code": "abc", "state": "unk-state", "error": ""}

        with patch("api.oauth_callback.get_oauth_provider", return_value=None):
            with patch("api.oauth_callback.FlaskResponse") as mock_resp:
                await handler.process({}, request)

        mock_resp.assert_called_once()
        assert mock_resp.call_args[1]["status"] == 400
        assert "Unknown provider" in mock_resp.call_args[0][0]
        _pending_states.clear()

    @pytest.mark.asyncio
    async def test_exchanges_code_and_saves_tokens(self):
        handler = _make(OAuthCallback)
        _pending_states["cb-state"] = {
            "provider_id": "google",
            "redirect_uri": "http://localhost/oauth_callback",
            "code_verifier": None,
            "flow": "redirect",
            "created": 9999999999,
        }
        mock_tokens = MagicMock()
        request = MagicMock()
        request.args = {"code": "auth-code", "state": "cb-state", "error": ""}

        with patch("api.oauth_callback.get_oauth_provider") as mock_get:
            mock_provider = MagicMock()
            mock_provider.exchange_code = AsyncMock(return_value=mock_tokens)
            mock_get.return_value = mock_provider
            with patch("api.oauth_callback.dotenv"):
                with patch("api.oauth_callback.ProviderPool") as mock_pool_cls:
                    mock_pool = MagicMock()
                    mock_pool_cls.get_instance.return_value = mock_pool
                    with patch("api.oauth_callback.FlaskResponse") as mock_resp:
                        await handler.process({}, request)

        html = mock_resp.call_args[0][0]
        assert "Connected" in html
        mock_pool.store.save.assert_called_once_with("google", mock_tokens)
        assert "cb-state" not in _pending_states


class TestOAuthExchange:
    @pytest.mark.asyncio
    async def test_exchange_with_valid_state(self):
        handler = _make(OAuthExchange)
        _pending_states["test-state"] = {
            "provider_id": "google",
            "redirect_uri": "http://localhost/cb",
            "code_verifier": None,
            "flow": "manual",
            "created": 9999999999,
        }

        mock_tokens = MagicMock()
        with patch("api.oauth_exchange.get_oauth_provider") as mock_get:
            mock_provider = MagicMock()
            mock_provider.exchange_code = AsyncMock(return_value=mock_tokens)
            mock_get.return_value = mock_provider
            with patch("api.oauth_exchange.dotenv"):
                with patch("api.oauth_exchange.ProviderPool") as mock_pool_cls:
                    mock_pool = MagicMock()
                    mock_pool_cls.get_instance.return_value = mock_pool
                    result = await handler.process(
                        {
                            "provider_id": "google",
                            "code": "test-code",
                            "state": "test-state",
                        },
                        MagicMock(),
                    )

        assert result["status"] == "connected"
        assert result["provider_id"] == "google"
        mock_pool.store.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_exchange_with_invalid_state(self):
        handler = _make(OAuthExchange)
        result = await handler.process(
            {
                "provider_id": "google",
                "code": "test-code",
                "state": "nonexistent-state",
            },
            MagicMock(),
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_exchange_unknown_provider(self):
        handler = _make(OAuthExchange)
        _pending_states["up-state"] = {
            "provider_id": "unknown",
            "redirect_uri": "",
            "code_verifier": None,
            "flow": "manual",
            "created": 9999999999,
        }
        with patch("api.oauth_exchange.get_oauth_provider", return_value=None):
            result = await handler.process(
                {"provider_id": "unknown", "code": "c", "state": "up-state"},
                MagicMock(),
            )
        assert "error" in result


class TestOAuthDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_calls_pool(self):
        handler = _make(OAuthDisconnect)
        with patch("api.oauth_disconnect.ProviderPool") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool_cls.get_instance.return_value = mock_pool

            result = await handler.process({"provider_id": "google"}, MagicMock())

        mock_pool.disconnect.assert_called_once_with("google")
        assert result["status"] == "disconnected"
        assert result["provider_id"] == "google"


class TestOAuthProviders:
    @pytest.mark.asyncio
    async def test_returns_provider_list_with_status(self):
        handler = _make(OAuthProviders)
        with patch("api.oauth_providers.get_oauth_providers") as mock_providers:
            mock_providers.return_value = [
                {
                    "provider_id": "google",
                    "name": "Google",
                    "enabled": True,
                    "strategy": "google",
                },
            ]
            with patch("api.oauth_providers.ProviderPool") as mock_pool_cls:
                mock_pool = MagicMock()
                mock_pool.is_connected.return_value = True
                mock_pool_cls.get_instance.return_value = mock_pool

                result = await handler.process({}, MagicMock())

        assert len(result["providers"]) == 1
        assert result["providers"][0]["connected"] is True
        assert result["providers"][0]["provider_id"] == "google"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_providers(self):
        handler = _make(OAuthProviders)
        with patch("api.oauth_providers.get_oauth_providers", return_value=[]):
            with patch("api.oauth_providers.ProviderPool") as mock_pool_cls:
                mock_pool_cls.get_instance.return_value = MagicMock()
                result = await handler.process({}, MagicMock())
        assert result["providers"] == []

    def test_get_methods_includes_get_and_post(self):
        assert "GET" in OAuthProviders.get_methods()
        assert "POST" in OAuthProviders.get_methods()


class TestOAuthStatus:
    @pytest.mark.asyncio
    async def test_connected_provider_returns_token_info(self):
        handler = _make(OAuthStatus)
        mock_tokens = MagicMock()
        mock_tokens.expires_at.isoformat.return_value = "2026-12-31T00:00:00+00:00"
        mock_tokens.scope = "read write"

        with patch("api.oauth_status.ProviderPool") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool.store.load.return_value = mock_tokens
            mock_pool_cls.get_instance.return_value = mock_pool

            result = await handler.process({"provider_id": "google"}, MagicMock())

        assert result["provider_id"] == "google"
        assert result["connected"] is True
        assert result["expires_at"] == "2026-12-31T00:00:00+00:00"
        assert result["scope"] == "read write"

    @pytest.mark.asyncio
    async def test_disconnected_provider(self):
        handler = _make(OAuthStatus)
        with patch("api.oauth_status.ProviderPool") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool.store.load.return_value = None
            mock_pool_cls.get_instance.return_value = mock_pool

            result = await handler.process({"provider_id": "openai"}, MagicMock())

        assert result["provider_id"] == "openai"
        assert result["connected"] is False
        assert result["expires_at"] is None
        assert result["scope"] is None
