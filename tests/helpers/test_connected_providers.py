import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from python.helpers.oauth import OAuthTokens
from python.helpers.connected_providers import ProviderPool, ConnectedProvider


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
