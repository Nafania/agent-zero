import secrets
from contextlib import asynccontextmanager

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from helpers.oauth import (
    AnthropicOAuth,
    GoogleOAuth,
    OAUTH_STRATEGIES,
    OpenAIOAuth,
    get_oauth_provider,
)


def _mock_async_client(post_response=None, get_response=None):
    mock_client = MagicMock()
    if post_response is not None:
        mock_client.post = AsyncMock(return_value=post_response)
    if get_response is not None:
        mock_client.get = AsyncMock(return_value=get_response)

    @asynccontextmanager
    async def fake_client(*args, **kwargs):
        yield mock_client

    return fake_client, mock_client


class TestGoogleOAuth:
    def setup_method(self):
        self.provider = GoogleOAuth()

    def test_provider_id(self):
        assert self.provider.provider_id == "google"

    def test_get_authorization_url_contains_required_params(self):
        url = self.provider.get_authorization_url(
            client_id="test-client-id",
            redirect_uri="http://localhost:50001/oauth_callback",
            state="test-state-123",
        )
        assert "client_id=test-client-id" in url
        assert "redirect_uri=" in url
        assert "state=test-state-123" in url
        assert "response_type=code" in url
        assert "scope=" in url
        assert "access_type=offline" in url
        assert "prompt=consent" in url
        assert "accounts.google.com" in url

    def test_get_authorization_url_includes_scopes(self):
        url = self.provider.get_authorization_url(
            client_id="test-client-id",
            redirect_uri="http://localhost:50001/oauth_callback",
            state="abc",
        )
        assert "generative-language" in url

    @pytest.mark.asyncio
    async def test_exchange_code_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "ya29.test-token",
            "refresh_token": "1//test-refresh",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "https://www.googleapis.com/auth/generative-language",
        }
        mock_response.raise_for_status = MagicMock()
        factory, _ = _mock_async_client(post_response=mock_response)

        with patch("helpers.oauth.httpx.AsyncClient", side_effect=factory):
            tokens = await self.provider.exchange_code(
                code="4/test-auth-code",
                client_id="test-client-id",
                client_secret="test-secret",
                redirect_uri="http://localhost:50001/oauth_callback",
            )
        assert tokens.access_token == "ya29.test-token"
        assert tokens.refresh_token == "1//test-refresh"
        assert tokens.token_type == "Bearer"

    @pytest.mark.asyncio
    async def test_exchange_code_error_raises(self):
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"error": "invalid_grant"}
        mock_response.raise_for_status.side_effect = Exception("400 Bad Request")
        factory, _ = _mock_async_client(post_response=mock_response)

        with patch("helpers.oauth.httpx.AsyncClient", side_effect=factory):
            with pytest.raises(Exception):
                await self.provider.exchange_code(
                    code="bad-code",
                    client_id="cid",
                    client_secret="cs",
                    redirect_uri="http://localhost/cb",
                )

    @pytest.mark.asyncio
    async def test_refresh_token_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "ya29.refreshed",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "https://www.googleapis.com/auth/generative-language",
        }
        mock_response.raise_for_status = MagicMock()
        factory, _ = _mock_async_client(post_response=mock_response)

        with patch("helpers.oauth.httpx.AsyncClient", side_effect=factory):
            tokens = await self.provider.refresh_token(
                refresh_token="1//test-refresh",
                client_id="test-client-id",
                client_secret="test-secret",
            )
        assert tokens.access_token == "ya29.refreshed"
        assert tokens.refresh_token == "1//test-refresh"

    @pytest.mark.asyncio
    async def test_list_models_filters_chat_capable(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "models/gemini-2.5-pro", "displayName": "Gemini 2.5 Pro",
                 "supportedGenerationMethods": ["generateContent"],
                 "inputTokenLimit": 1048576, "outputTokenLimit": 65536},
                {"name": "models/text-embedding-004", "displayName": "Text Embedding 004",
                 "supportedGenerationMethods": ["embedContent"],
                 "inputTokenLimit": 2048},
            ],
        }
        mock_response.raise_for_status = MagicMock()
        factory, _ = _mock_async_client(get_response=mock_response)

        with patch("helpers.oauth.httpx.AsyncClient", side_effect=factory):
            models = await self.provider.list_models(access_token="ya29.test")
        assert len(models) == 1
        assert models[0].id == "gemini-2.5-pro"
        assert models[0].supports_vision is True


class TestOpenAIOAuth:
    def setup_method(self):
        self.provider = OpenAIOAuth()

    def test_provider_id(self):
        assert self.provider.provider_id == "openai"

    def test_authorization_url_params(self):
        url = self.provider.get_authorization_url(
            client_id="openai-cid", redirect_uri="http://localhost/cb", state="s1"
        )
        assert "client_id=openai-cid" in url
        assert "state=s1" in url
        assert "response_type=code" in url

    @pytest.mark.asyncio
    async def test_exchange_code_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "sk-oat-test",
            "refresh_token": "rt-test",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "model.read model.request",
        }
        mock_response.raise_for_status = MagicMock()
        factory, _ = _mock_async_client(post_response=mock_response)

        with patch("helpers.oauth.httpx.AsyncClient", side_effect=factory):
            tokens = await self.provider.exchange_code(
                code="oai-code", client_id="cid", client_secret="cs",
                redirect_uri="http://localhost/cb",
            )
        assert tokens.access_token == "sk-oat-test"

    @pytest.mark.asyncio
    async def test_list_models_filters_chat(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": "gpt-4o", "owned_by": "openai"},
                {"id": "o3-mini", "owned_by": "openai"},
                {"id": "text-embedding-3-large", "owned_by": "openai"},
                {"id": "dall-e-3", "owned_by": "openai"},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        factory, _ = _mock_async_client(get_response=mock_response)

        with patch("helpers.oauth.httpx.AsyncClient", side_effect=factory):
            models = await self.provider.list_models(access_token="sk-test")
        model_ids = [m.id for m in models]
        assert "gpt-4o" in model_ids
        assert "o3-mini" in model_ids
        assert "text-embedding-3-large" not in model_ids
        assert "dall-e-3" not in model_ids


class TestAnthropicOAuth:
    def setup_method(self):
        self.provider = AnthropicOAuth()

    def test_provider_id(self):
        assert self.provider.provider_id == "anthropic"

    def test_supports_pkce(self):
        assert self.provider.supports_pkce is True

    def test_authorization_url_has_pkce_challenge(self):
        verifier = secrets.token_urlsafe(43)
        url = self.provider.get_authorization_url(
            client_id="ant-cid", redirect_uri="http://localhost/cb",
            state="s2", code_verifier=verifier,
        )
        assert "code_challenge=" in url
        assert "code_challenge_method=S256" in url

    @pytest.mark.asyncio
    async def test_exchange_code_includes_verifier(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "ant-token",
            "refresh_token": "ant-refresh",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "user:inference",
        }
        mock_response.raise_for_status = MagicMock()
        factory, mock_client = _mock_async_client(post_response=mock_response)

        with patch("helpers.oauth.httpx.AsyncClient", side_effect=factory):
            await self.provider.exchange_code(
                code="ant-code", client_id="cid", client_secret="cs",
                redirect_uri="http://localhost/cb", code_verifier="test-verifier",
            )
            call_kwargs = mock_client.post.call_args
            assert call_kwargs.kwargs["data"]["code_verifier"] == "test-verifier"


def test_oauth_strategies_contains_all_providers():
    assert set(OAUTH_STRATEGIES.keys()) == {"google", "openai", "anthropic"}


def test_get_oauth_provider_returns_correct_type():
    provider = get_oauth_provider("openai")
    assert isinstance(provider, OpenAIOAuth)


def test_get_oauth_provider_returns_none_for_unknown():
    assert get_oauth_provider("unknown") is None
