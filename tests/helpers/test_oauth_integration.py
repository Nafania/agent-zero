import pytest
from unittest.mock import patch, MagicMock
from python.helpers.connected_providers import ProviderPool


class TestModelsGetApiKeyDelegation:
    def test_get_api_key_uses_provider_pool(self):
        with patch.object(ProviderPool, "get_instance") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool.get_credential.return_value = "oauth-token-123"
            mock_pool_cls.return_value = mock_pool

            import models
            key = models.get_api_key("google")
            mock_pool.get_credential.assert_called_with("google")
            assert key == "oauth-token-123"

    def test_get_api_key_round_robin_still_works(self):
        with patch.object(ProviderPool, "get_instance") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool.get_credential.return_value = "key1,key2,key3"
            mock_pool_cls.return_value = mock_pool

            import models
            models.api_keys_round_robin.pop("test_rr", None)
            k1 = models.get_api_key("test_rr")
            k2 = models.get_api_key("test_rr")
            k3 = models.get_api_key("test_rr")
            assert {k1, k2, k3} == {"key1", "key2", "key3"}

    def test_get_api_key_returns_none_when_no_cred(self):
        with patch.object(ProviderPool, "get_instance") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool.get_credential.return_value = "None"
            mock_pool_cls.return_value = mock_pool

            import models
            key = models.get_api_key("unknown")
            assert key == "None"
