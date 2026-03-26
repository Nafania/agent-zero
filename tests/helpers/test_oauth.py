import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from python.helpers.oauth import GoogleOAuth, OAuthTokens


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

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
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

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
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

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
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

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            models = await self.provider.list_models(access_token="ya29.test")
        assert len(models) == 1
        assert models[0].id == "gemini-2.5-pro"
        assert models[0].supports_vision is True
