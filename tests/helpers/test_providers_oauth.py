import pytest

from python.helpers.providers import get_provider_config, get_oauth_providers, ProviderManager


@pytest.fixture(autouse=True)
def reset_provider_cache():
    ProviderManager._instance = None
    ProviderManager._raw = None
    ProviderManager._options = None


class TestProviderOAuthConfig:
    def test_google_has_oauth_config(self):
        cfg = get_provider_config("chat", "google")
        assert cfg is not None
        oauth = cfg.get("oauth")
        assert oauth is not None
        assert oauth["strategy"] == "google"
        assert oauth["enabled"] is True

    def test_openai_has_oauth_config(self):
        cfg = get_provider_config("chat", "openai")
        assert cfg is not None
        oauth = cfg.get("oauth")
        assert oauth is not None
        assert oauth["strategy"] == "openai"

    def test_anthropic_oauth_disabled(self):
        cfg = get_provider_config("chat", "anthropic")
        assert cfg is not None
        oauth = cfg.get("oauth")
        assert oauth is not None
        assert oauth["enabled"] is False

    def test_openrouter_no_oauth(self):
        cfg = get_provider_config("chat", "openrouter")
        assert cfg is not None
        assert cfg.get("oauth") is None


class TestGetOAuthProviders:
    def test_returns_oauth_capable_providers(self):
        providers = get_oauth_providers()
        ids = [p["provider_id"] for p in providers]
        assert "google" in ids
        assert "openai" in ids
        assert "anthropic" in ids

    def test_does_not_include_non_oauth_providers(self):
        providers = get_oauth_providers()
        ids = [p["provider_id"] for p in providers]
        assert "openrouter" not in ids
        assert "ollama" not in ids

    def test_anthropic_disabled(self):
        providers = get_oauth_providers()
        anthropic = [p for p in providers if p["provider_id"] == "anthropic"][0]
        assert anthropic["enabled"] is False
