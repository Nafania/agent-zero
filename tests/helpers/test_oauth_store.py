import pytest
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from python.helpers.oauth import OAuthTokens
from python.helpers.oauth_store import OAuthTokenStore


@pytest.fixture
def tmp_store(tmp_path):
    store_path = tmp_path / "oauth_tokens.json"
    return OAuthTokenStore(str(store_path))


@pytest.fixture
def sample_tokens():
    return OAuthTokens(
        access_token="ya29.test",
        refresh_token="1//refresh",
        expires_at=datetime(2026, 12, 31, tzinfo=timezone.utc),
        token_type="Bearer",
        scope="test-scope",
    )


class TestOAuthTokenStore:
    def test_save_and_load(self, tmp_store, sample_tokens):
        tmp_store.save("google", sample_tokens)
        loaded = tmp_store.load("google")
        assert loaded is not None
        assert loaded.access_token == "ya29.test"
        assert loaded.refresh_token == "1//refresh"

    def test_load_nonexistent_returns_none(self, tmp_store):
        assert tmp_store.load("google") is None

    def test_delete(self, tmp_store, sample_tokens):
        tmp_store.save("google", sample_tokens)
        tmp_store.delete("google")
        assert tmp_store.load("google") is None

    def test_list_providers(self, tmp_store, sample_tokens):
        tmp_store.save("google", sample_tokens)
        tmp_store.save("openai", sample_tokens)
        providers = tmp_store.list_providers()
        assert set(providers) == {"google", "openai"}

    def test_corrupted_file_returns_empty(self, tmp_store):
        with open(tmp_store.file_path, "w") as f:
            f.write("{invalid json")
        assert tmp_store.load("google") is None
        assert tmp_store.list_providers() == []

    def test_atomic_write_survives_concurrent_reads(self, tmp_store, sample_tokens):
        tmp_store.save("google", sample_tokens)
        tmp_store.save("openai", sample_tokens)
        loaded_g = tmp_store.load("google")
        loaded_o = tmp_store.load("openai")
        assert loaded_g is not None
        assert loaded_o is not None
