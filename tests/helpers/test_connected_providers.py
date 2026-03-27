import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
from python.helpers.oauth import OAuthTokens, ModelInfo
from python.helpers.connected_providers import (
    ProviderPool,
    ConnectedProvider,
    _list_models_via_api,
    _resolve_api_base,
)


@pytest.fixture
def valid_tokens():
    return OAuthTokens(
        access_token="test-access",
        refresh_token="test-refresh",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        token_type="Bearer",
        scope="test",
    )


@pytest.fixture
def expired_tokens():
    return OAuthTokens(
        access_token="old-access",
        refresh_token="old-refresh",
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        token_type="Bearer",
        scope="test",
    )


@pytest.fixture
def pool(tmp_path):
    store_path = str(tmp_path / "tokens.json")
    return ProviderPool(token_store_path=store_path)


class TestProviderPool:
    def test_get_credential_returns_api_key_when_no_oauth(self, pool):
        with patch("python.helpers.connected_providers._get_api_key", return_value="sk-test"):
            cred = pool.get_credential("openrouter")
        assert cred == "sk-test"

    def test_get_credential_prefers_oauth_over_api_key(self, pool, valid_tokens):
        pool.store.save("google", valid_tokens)
        with patch("python.helpers.connected_providers._get_api_key", return_value="api-key"):
            cred = pool.get_credential("google")
        assert cred == "test-access"

    @pytest.mark.asyncio
    async def test_get_credential_refreshes_expired_token(self, pool, expired_tokens):
        pool.store.save("google", expired_tokens)
        refreshed = OAuthTokens(
            access_token="new-access", refresh_token="new-refresh",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            token_type="Bearer", scope="test",
        )
        with patch.object(pool, "_try_sync_refresh", return_value=refreshed):
            cred = pool.get_credential("google")
            assert cred == "new-access"

    def test_get_credential_falls_back_to_api_key_on_missing_oauth(self, pool):
        with patch("python.helpers.connected_providers._get_api_key", return_value="fallback-key"):
            cred = pool.get_credential("google")
        assert cred == "fallback-key"

    def test_is_connected_true_with_oauth(self, pool, valid_tokens):
        pool.store.save("google", valid_tokens)
        assert pool.is_connected("google") is True

    def test_is_connected_true_with_api_key(self, pool):
        with patch("python.helpers.connected_providers._get_api_key", return_value="sk-test"):
            assert pool.is_connected("openrouter") is True

    def test_is_connected_false_when_nothing(self, pool):
        with patch("python.helpers.connected_providers._get_api_key", return_value="None"):
            assert pool.is_connected("google") is False

    def test_get_connected_lists_all(self, pool, valid_tokens):
        pool.store.save("google", valid_tokens)
        with patch("python.helpers.connected_providers._get_api_key", side_effect=lambda p: "sk-test" if p == "openai" else "None"):
            with patch("python.helpers.connected_providers._get_all_provider_ids", return_value=["google", "openai", "anthropic"]):
                connected = pool.get_connected()
        ids = [c.provider_id for c in connected]
        assert "google" in ids
        assert "openai" in ids
        assert "anthropic" not in ids

    def test_disconnect_removes_tokens(self, pool, valid_tokens):
        pool.store.save("google", valid_tokens)
        pool.disconnect("google")
        assert pool.store.load("google") is None

    def test_run_async_from_sync_context(self, pool):
        import asyncio
        async def _coro():
            return 42
        result = pool._run_async(_coro())
        assert result == 42

    def test_disconnect_revokes_via_run_async(self, pool, valid_tokens):
        pool.store.save("google", valid_tokens)
        with patch("python.helpers.connected_providers.get_oauth_provider") as mock_get:
            mock_strategy = MagicMock()
            mock_strategy.revoke = AsyncMock(return_value=None)
            mock_get.return_value = mock_strategy
            pool.disconnect("google")
        mock_strategy.revoke.assert_called_once_with("test-access")
        assert pool.store.load("google") is None


# --- list_models API-key fallback (I3) ---

class TestListModelsApiKeyFallback:
    @pytest.mark.asyncio
    async def test_list_models_returns_empty_for_no_credential(self, pool):
        with patch("python.helpers.connected_providers._get_api_key", return_value="None"):
            with patch("python.helpers.connected_providers.get_oauth_provider", return_value=None):
                result = await pool.list_models("openrouter")
        assert result == []

    @pytest.mark.asyncio
    async def test_list_models_uses_api_key_when_no_oauth_strategy(self, pool):
        mock_models = [ModelInfo(id="gpt-4o", name="GPT-4o", context_length=128000, supports_vision=True)]
        with patch("python.helpers.connected_providers._get_api_key", return_value="sk-test"):
            with patch("python.helpers.connected_providers.get_oauth_provider", return_value=None):
                with patch("python.helpers.connected_providers._list_models_via_api", new_callable=AsyncMock, return_value=mock_models):
                    result = await pool.list_models("openai")
        assert len(result) == 1
        assert result[0].id == "gpt-4o"

    @pytest.mark.asyncio
    async def test_list_models_caches_api_key_result(self, pool):
        mock_models = [ModelInfo(id="m1", name="Model 1", context_length=4096, supports_vision=False)]
        with patch("python.helpers.connected_providers._get_api_key", return_value="sk-test"):
            with patch("python.helpers.connected_providers.get_oauth_provider", return_value=None):
                with patch("python.helpers.connected_providers._list_models_via_api", new_callable=AsyncMock, return_value=mock_models) as mock_api:
                    await pool.list_models("openai")
                    result2 = await pool.list_models("openai")
        mock_api.assert_called_once()
        assert len(result2) == 1

    @pytest.mark.asyncio
    async def test_list_models_returns_stale_cache_on_api_failure(self, pool):
        pool._model_cache["openai"] = (
            datetime.now(timezone.utc) - timedelta(hours=2),
            [ModelInfo(id="old", name="Old", context_length=0, supports_vision=False)],
        )
        with patch("python.helpers.connected_providers._get_api_key", return_value="sk-test"):
            with patch("python.helpers.connected_providers.get_oauth_provider", return_value=None):
                with patch("python.helpers.connected_providers._list_models_via_api", new_callable=AsyncMock, return_value=[]):
                    result = await pool.list_models("openai")
        assert len(result) == 1
        assert result[0].id == "old"


# --- _list_models_via_api (I2) ---

class TestListModelsViaApi:
    @pytest.mark.asyncio
    async def test_success_parses_models(self):
        response_data = {
            "data": [
                {"id": "gpt-4o", "name": "GPT-4o", "context_length": 128000},
                {"id": "gpt-4o-mini", "context_length": 16384},
                {"id": "", "name": "Empty ID"},
            ]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = response_data

        with patch("python.helpers.connected_providers._resolve_api_base", return_value="https://api.openai.com/v1"):
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.get.return_value = mock_resp
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client_cls.return_value = mock_client

                result = await _list_models_via_api("openai", "sk-test")

        assert len(result) == 2
        ids = [m.id for m in result]
        assert "gpt-4o" in ids
        assert "gpt-4o-mini" in ids
        gpt4o = next(m for m in result if m.id == "gpt-4o")
        assert gpt4o.name == "GPT-4o"
        assert gpt4o.context_length == 128000

    @pytest.mark.asyncio
    async def test_non_200_returns_empty(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 401

        with patch("python.helpers.connected_providers._resolve_api_base", return_value="https://api.openai.com/v1"):
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.get.return_value = mock_resp
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client_cls.return_value = mock_client

                result = await _list_models_via_api("openai", "sk-bad")

        assert result == []

    @pytest.mark.asyncio
    async def test_network_error_returns_empty(self):
        with patch("python.helpers.connected_providers._resolve_api_base", return_value="https://api.openai.com/v1"):
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.get.side_effect = httpx.ConnectError("connection refused")
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client_cls.return_value = mock_client

                result = await _list_models_via_api("openai", "sk-test")

        assert result == []

    @pytest.mark.asyncio
    async def test_empty_data_returns_empty(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": []}

        with patch("python.helpers.connected_providers._resolve_api_base", return_value="https://api.openai.com/v1"):
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.get.return_value = mock_resp
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client_cls.return_value = mock_client

                result = await _list_models_via_api("openai", "sk-test")

        assert result == []

    @pytest.mark.asyncio
    async def test_no_api_base_returns_empty(self):
        with patch("python.helpers.connected_providers._resolve_api_base", return_value=""):
            result = await _list_models_via_api("unknown", "sk-test")
        assert result == []

    @pytest.mark.asyncio
    async def test_openrouter_vision_detection(self):
        response_data = {
            "data": [
                {
                    "id": "openai/gpt-4o",
                    "name": "GPT-4o",
                    "context_length": 128000,
                    "architecture": {"modality": "text+image->text"},
                },
                {
                    "id": "anthropic/claude-3.5-sonnet",
                    "name": "Claude 3.5 Sonnet",
                    "context_length": 200000,
                    "architecture": {"modality": "text->text"},
                },
            ]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = response_data

        with patch("python.helpers.connected_providers._resolve_api_base", return_value="https://openrouter.ai/api/v1"):
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.get.return_value = mock_resp
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client_cls.return_value = mock_client

                result = await _list_models_via_api("openrouter", "sk-test")

        gpt4o = next(m for m in result if m.id == "openai/gpt-4o")
        claude = next(m for m in result if m.id == "anthropic/claude-3.5-sonnet")
        assert gpt4o.supports_vision is True
        assert claude.supports_vision is False
