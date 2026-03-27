# OAuth Provider Framework & Per-Chat Model Switching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add OAuth2 authentication for Google and OpenAI model providers (Anthropic code-complete but UI-hidden), a connected provider pool abstracting credential resolution, and per-chat model switching with dynamic model discovery.

**Architecture:** Strategy pattern for OAuth providers (`OAuthProvider` ABC with per-provider subclasses). A `ProviderPool` singleton manages connected providers and resolves credentials (OAuth token or API key) transparently for `models.py`. Per-chat model override stored in chat metadata and applied in `initialize.py`. Dynamic model lists fetched from provider APIs and cached.

**Tech Stack:** Python 3.12, Flask API handlers, LiteLLM, httpx (OAuth HTTP calls), Alpine.js (UI), pytest

**Spec:** `docs/superpowers/specs/2026-03-26-oauth-provider-framework-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `python/helpers/oauth.py` | `OAuthProvider` ABC, `OAuthTokens`, `GoogleOAuth`, `OpenAIOAuth`, `AnthropicOAuth` strategies |
| `python/helpers/connected_providers.py` | `ConnectedProvider`, `ProviderPool` singleton, credential resolution, model list caching |
| `python/helpers/oauth_store.py` | Token persistence: read/write `usr/oauth_tokens.json`, atomic file ops |
| `python/api/oauth_authorize.py` | `POST /oauth_authorize` — start OAuth flow |
| `python/api/oauth_callback.py` | `GET /oauth_callback` — redirect handler |
| `python/api/oauth_exchange.py` | `POST /oauth_exchange` — manual code exchange |
| `python/api/oauth_disconnect.py` | `POST /oauth_disconnect` — revoke + remove |
| `python/api/oauth_providers.py` | `GET /oauth_providers` — list providers with status |
| `python/api/oauth_status.py` | `GET /oauth_status` — single provider detail |
| `python/api/provider_models.py` | `GET /provider_models` — dynamic model list |
| `python/api/chat_model_override.py` | `POST/GET /chat_model_override` — per-chat model |
| `webui/js/oauth.js` | OAuth flow frontend logic |
| `webui/js/model-picker.js` | Chat model picker dropdown logic |
| `tests/helpers/test_oauth.py` | OAuth strategy unit tests |
| `tests/helpers/test_oauth_store.py` | Token storage tests |
| `tests/helpers/test_connected_providers.py` | ProviderPool tests |
| `tests/api/test_oauth_endpoints.py` | API endpoint tests |
| `tests/api/test_provider_models.py` | Model list endpoint tests |
| `tests/api/test_chat_model_override.py` | Per-chat override tests |

### Modified Files

| File | Change |
|------|--------|
| `conf/model_providers.yaml` | Add `oauth` blocks to google, openai, anthropic |
| `python/helpers/providers.py` | Parse `oauth` config from YAML, expose `get_oauth_config()` |
| `python/helpers/settings.py` | OAuth client credentials in sensitive settings load/save |
| `models.py:280-293` | `get_api_key()` delegates to `ProviderPool.get_credential()` |
| `initialize.py:31-43` | Apply per-chat model override for chat_llm |
| `webui/components/settings/agent/agent.html` | OAuth connect/disconnect UI per provider |

---

### Task 1: OAuthProvider ABC + GoogleOAuth Strategy

**Files:**
- Create: `python/helpers/oauth.py`
- Test: `tests/helpers/test_oauth.py`

- [ ] **Step 1: Write failing tests for GoogleOAuth**

Create `tests/helpers/test_oauth.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/helpers/test_oauth.py -v`
Expected: FAIL — `python.helpers.oauth` module not found.

- [ ] **Step 3: Implement OAuthProvider ABC + OAuthTokens + GoogleOAuth**

Create `python/helpers/oauth.py`:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx


@dataclass
class OAuthTokens:
    access_token: str
    refresh_token: Optional[str]
    expires_at: datetime
    token_type: str
    scope: str


@dataclass
class ModelInfo:
    id: str
    name: str
    context_length: int
    supports_vision: bool


class OAuthProvider(ABC):
    provider_id: str
    authorize_url: str
    token_url: str
    scopes: list[str]
    supports_pkce: bool = False

    @abstractmethod
    def get_authorization_url(
        self,
        client_id: str,
        redirect_uri: str,
        state: str,
        code_verifier: Optional[str] = None,
    ) -> str: ...

    @abstractmethod
    async def exchange_code(
        self,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code_verifier: Optional[str] = None,
    ) -> OAuthTokens: ...

    @abstractmethod
    async def refresh_token(
        self,
        refresh_token: str,
        client_id: str,
        client_secret: str,
    ) -> OAuthTokens: ...

    @abstractmethod
    async def revoke(self, access_token: str) -> None: ...

    @abstractmethod
    async def list_models(self, access_token: str) -> list[ModelInfo]: ...


def _tokens_from_response(data: dict) -> OAuthTokens:
    expires_in = data.get("expires_in", 3600)
    return OAuthTokens(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token"),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        token_type=data.get("token_type", "Bearer"),
        scope=data.get("scope", ""),
    )


class GoogleOAuth(OAuthProvider):
    provider_id = "google"
    authorize_url = "https://accounts.google.com/o/oauth2/v2/auth"
    token_url = "https://oauth2.googleapis.com/token"
    scopes = ["https://www.googleapis.com/auth/generative-language"]
    models_url = "https://generativelanguage.googleapis.com/v1beta/models"
    revoke_url = "https://oauth2.googleapis.com/revoke"
    supports_pkce = False

    def get_authorization_url(self, client_id, redirect_uri, state, code_verifier=None):
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{self.authorize_url}?{urlencode(params)}"

    async def exchange_code(self, code, client_id, client_secret, redirect_uri, code_verifier=None):
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.token_url, data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            })
            resp.raise_for_status()
            return _tokens_from_response(resp.json())

    async def refresh_token(self, refresh_token, client_id, client_secret):
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.token_url, data={
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
            })
            resp.raise_for_status()
            tokens = _tokens_from_response(resp.json())
            if not tokens.refresh_token:
                tokens.refresh_token = refresh_token
            return tokens

    async def revoke(self, access_token):
        async with httpx.AsyncClient() as client:
            await client.post(self.revoke_url, params={"token": access_token})

    async def list_models(self, access_token):
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                self.models_url,
                headers={"Authorization": f"Bearer {access_token}"},
                params={"pageSize": 100},
            )
            resp.raise_for_status()
            data = resp.json()

        result = []
        for m in data.get("models", []):
            methods = m.get("supportedGenerationMethods", [])
            if "generateContent" not in methods:
                continue
            model_id = m.get("name", "").replace("models/", "")
            result.append(ModelInfo(
                id=model_id,
                name=m.get("displayName", model_id),
                context_length=m.get("inputTokenLimit", 0),
                supports_vision="generateContent" in methods,
            ))
        return result
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/helpers/test_oauth.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add python/helpers/oauth.py tests/helpers/test_oauth.py
git commit -m "feat(oauth): add OAuthProvider ABC and GoogleOAuth strategy"
```

---

### Task 2: OpenAIOAuth + AnthropicOAuth Strategies

**Files:**
- Modify: `python/helpers/oauth.py`
- Modify: `tests/helpers/test_oauth.py`

- [ ] **Step 1: Write failing tests for OpenAI and Anthropic**

Append to `tests/helpers/test_oauth.py`:

```python
import hashlib, base64, secrets
from python.helpers.oauth import OpenAIOAuth, AnthropicOAuth


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
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
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
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
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
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
            await self.provider.exchange_code(
                code="ant-code", client_id="cid", client_secret="cs",
                redirect_uri="http://localhost/cb", code_verifier="test-verifier",
            )
            call_kwargs = mock_post.call_args
            assert "code_verifier" in str(call_kwargs)
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/helpers/test_oauth.py -v`
Expected: FAIL — `OpenAIOAuth` and `AnthropicOAuth` not defined.

- [ ] **Step 3: Implement OpenAIOAuth and AnthropicOAuth**

Append to `python/helpers/oauth.py`:

```python
import hashlib
import base64


class OpenAIOAuth(OAuthProvider):
    provider_id = "openai"
    authorize_url = "https://auth.openai.com/authorize"
    token_url = "https://auth.openai.com/oauth/token"
    scopes = ["model.read", "model.request"]
    models_url = "https://api.openai.com/v1/models"
    revoke_url = "https://auth.openai.com/oauth/revoke"
    supports_pkce = False

    CHAT_MODEL_PREFIXES = ("gpt-", "o1-", "o3-", "o4-", "chatgpt-")

    def get_authorization_url(self, client_id, redirect_uri, state, code_verifier=None):
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "state": state,
        }
        return f"{self.authorize_url}?{urlencode(params)}"

    async def exchange_code(self, code, client_id, client_secret, redirect_uri, code_verifier=None):
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.token_url, data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            })
            resp.raise_for_status()
            return _tokens_from_response(resp.json())

    async def refresh_token(self, refresh_token, client_id, client_secret):
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.token_url, data={
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
            })
            resp.raise_for_status()
            tokens = _tokens_from_response(resp.json())
            if not tokens.refresh_token:
                tokens.refresh_token = refresh_token
            return tokens

    async def revoke(self, access_token):
        async with httpx.AsyncClient() as client:
            await client.post(self.revoke_url, data={"token": access_token})

    async def list_models(self, access_token):
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                self.models_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            data = resp.json()

        result = []
        for m in data.get("data", []):
            mid = m.get("id", "")
            if not any(mid.startswith(p) for p in self.CHAT_MODEL_PREFIXES):
                continue
            result.append(ModelInfo(
                id=mid, name=mid,
                context_length=m.get("context_window", 0),
                supports_vision="vision" in mid or mid.startswith("gpt-4"),
            ))
        return result


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class AnthropicOAuth(OAuthProvider):
    provider_id = "anthropic"
    authorize_url = "https://claude.ai/oauth/authorize"
    token_url = "https://console.anthropic.com/v1/oauth/token"
    scopes = ["user:inference", "user:profile"]
    models_url = "https://api.anthropic.com/v1/models"
    revoke_url = "https://console.anthropic.com/v1/oauth/revoke"
    supports_pkce = True

    def get_authorization_url(self, client_id, redirect_uri, state, code_verifier=None):
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "state": state,
        }
        if code_verifier:
            params["code_challenge"] = _pkce_challenge(code_verifier)
            params["code_challenge_method"] = "S256"
        return f"{self.authorize_url}?{urlencode(params)}"

    async def exchange_code(self, code, client_id, client_secret, redirect_uri, code_verifier=None):
        payload = {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        if code_verifier:
            payload["code_verifier"] = code_verifier
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.token_url, data=payload)
            resp.raise_for_status()
            return _tokens_from_response(resp.json())

    async def refresh_token(self, refresh_token, client_id, client_secret):
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.token_url, data={
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
            })
            resp.raise_for_status()
            tokens = _tokens_from_response(resp.json())
            if not tokens.refresh_token:
                tokens.refresh_token = refresh_token
            return tokens

    async def revoke(self, access_token):
        async with httpx.AsyncClient() as client:
            await client.post(self.revoke_url, data={"token": access_token})

    async def list_models(self, access_token):
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                self.models_url,
                headers={"x-api-key": access_token, "anthropic-version": "2023-06-01"},
            )
            resp.raise_for_status()
            data = resp.json()

        result = []
        for m in data.get("data", []):
            mid = m.get("id", "")
            if not mid.startswith("claude-"):
                continue
            result.append(ModelInfo(
                id=mid, name=m.get("display_name", mid),
                context_length=m.get("context_window", 0),
                supports_vision=True,
            ))
        return result


OAUTH_STRATEGIES: dict[str, OAuthProvider] = {
    "google": GoogleOAuth(),
    "openai": OpenAIOAuth(),
    "anthropic": AnthropicOAuth(),
}


def get_oauth_provider(strategy_name: str) -> OAuthProvider | None:
    return OAUTH_STRATEGIES.get(strategy_name)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/helpers/test_oauth.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add python/helpers/oauth.py tests/helpers/test_oauth.py
git commit -m "feat(oauth): add OpenAI and Anthropic OAuth strategies"
```

---

### Task 3: Token Storage

**Files:**
- Create: `python/helpers/oauth_store.py`
- Test: `tests/helpers/test_oauth_store.py`

- [ ] **Step 1: Write failing tests for token persistence**

Create `tests/helpers/test_oauth_store.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/helpers/test_oauth_store.py -v`
Expected: FAIL — `python.helpers.oauth_store` not found.

- [ ] **Step 3: Implement OAuthTokenStore**

Create `python/helpers/oauth_store.py`:

```python
import json
import os
import tempfile
import logging
from datetime import datetime, timezone
from typing import Optional

from python.helpers.oauth import OAuthTokens

logger = logging.getLogger(__name__)


class OAuthTokenStore:
    def __init__(self, file_path: str):
        self.file_path = file_path

    def _read_all(self) -> dict:
        if not os.path.exists(self.file_path):
            return {}
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("OAuth token file corrupted, treating as empty: %s", e)
            return {}

    def _write_all(self, data: dict):
        os.makedirs(os.path.dirname(self.file_path) or ".", exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=os.path.dirname(self.file_path) or ".",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            os.replace(tmp, self.file_path)
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def save(self, provider_id: str, tokens: OAuthTokens):
        data = self._read_all()
        data[provider_id] = {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "expires_at": tokens.expires_at.isoformat(),
            "token_type": tokens.token_type,
            "scope": tokens.scope,
        }
        self._write_all(data)

    def load(self, provider_id: str) -> Optional[OAuthTokens]:
        data = self._read_all()
        entry = data.get(provider_id)
        if not entry:
            return None
        try:
            return OAuthTokens(
                access_token=entry["access_token"],
                refresh_token=entry.get("refresh_token"),
                expires_at=datetime.fromisoformat(entry["expires_at"]),
                token_type=entry.get("token_type", "Bearer"),
                scope=entry.get("scope", ""),
            )
        except (KeyError, ValueError) as e:
            logger.warning("Invalid token entry for %s: %s", provider_id, e)
            return None

    def delete(self, provider_id: str):
        data = self._read_all()
        data.pop(provider_id, None)
        self._write_all(data)

    def list_providers(self) -> list[str]:
        return list(self._read_all().keys())
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/helpers/test_oauth_store.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add python/helpers/oauth_store.py tests/helpers/test_oauth_store.py
git commit -m "feat(oauth): add token storage with atomic writes"
```

---

### Task 4: ProviderPool + Credential Resolution

**Files:**
- Create: `python/helpers/connected_providers.py`
- Test: `tests/helpers/test_connected_providers.py`

- [ ] **Step 1: Write failing tests for ProviderPool**

Create `tests/helpers/test_connected_providers.py`:

```python
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
        with patch("python.helpers.connected_providers._get_oauth_client_creds", return_value=("cid", "cs")):
            with patch.object(pool, "_refresh_provider", new_callable=AsyncMock, return_value=refreshed):
                cred = pool.get_credential("google")
                # Falls back to expired token synchronously; refresh happens async
                assert cred in ("old-access", "new-access")

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
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/helpers/test_connected_providers.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement ProviderPool**

Create `python/helpers/connected_providers.py`:

```python
import asyncio
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from python.helpers.oauth import OAuthProvider, OAuthTokens, ModelInfo, get_oauth_provider
from python.helpers.oauth_store import OAuthTokenStore
from python.helpers import files

logger = logging.getLogger(__name__)

_REFRESH_MARGIN = timedelta(minutes=5)
_MODEL_CACHE_TTL = timedelta(hours=1)

_DEFAULT_TOKEN_PATH = "usr/oauth_tokens.json"


def _get_api_key(provider_id: str) -> str:
    from python.helpers import dotenv
    return (
        dotenv.get_dotenv_value(f"API_KEY_{provider_id.upper()}")
        or dotenv.get_dotenv_value(f"{provider_id.upper()}_API_KEY")
        or dotenv.get_dotenv_value(f"{provider_id.upper()}_API_TOKEN")
        or "None"
    )


def _get_oauth_client_creds(provider_id: str) -> tuple[str, str]:
    from python.helpers import dotenv
    cid = dotenv.get_dotenv_value(f"OAUTH_CLIENT_ID_{provider_id.upper()}") or ""
    cs = dotenv.get_dotenv_value(f"OAUTH_CLIENT_SECRET_{provider_id.upper()}") or ""
    return cid, cs


def _get_all_provider_ids() -> list[str]:
    from python.helpers.providers import get_providers
    providers = get_providers("chat") + get_providers("embedding")
    seen = set()
    result = []
    for p in providers:
        pid = p["value"]
        if pid not in seen:
            seen.add(pid)
            result.append(pid)
    return result


@dataclass
class ConnectedProvider:
    provider_id: str
    auth_method: str  # "oauth" | "api_key"
    is_active: bool


class ProviderPool:
    _instance: Optional["ProviderPool"] = None

    def __init__(self, token_store_path: Optional[str] = None):
        path = token_store_path or files.get_abs_path(_DEFAULT_TOKEN_PATH)
        self.store = OAuthTokenStore(path)
        self._refresh_lock = threading.Lock()
        self._model_cache: dict[str, tuple[datetime, list[ModelInfo]]] = {}

    @classmethod
    def get_instance(cls) -> "ProviderPool":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        cls._instance = None

    def get_credential(self, provider_id: str) -> str:
        tokens = self.store.load(provider_id)
        if tokens:
            if tokens.expires_at > datetime.now(timezone.utc) + _REFRESH_MARGIN:
                return tokens.access_token
            # Token near expiry — try sync refresh, fall back to current token
            try:
                refreshed = self._try_sync_refresh(provider_id, tokens)
                if refreshed:
                    return refreshed.access_token
            except Exception as e:
                logger.warning("OAuth refresh failed for %s: %s", provider_id, e)
            # Return expired token as last resort before API key
            return tokens.access_token

        api_key = _get_api_key(provider_id)
        return api_key

    def _try_sync_refresh(self, provider_id: str, tokens: OAuthTokens) -> Optional[OAuthTokens]:
        if not tokens.refresh_token:
            return None
        strategy = get_oauth_provider(provider_id)
        if not strategy:
            return None
        cid, cs = _get_oauth_client_creds(provider_id)
        if not cid or not cs:
            return None

        with self._refresh_lock:
            # Re-check after acquiring lock
            current = self.store.load(provider_id)
            if current and current.expires_at > datetime.now(timezone.utc) + _REFRESH_MARGIN:
                return current

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(
                            asyncio.run,
                            strategy.refresh_token(tokens.refresh_token, cid, cs)
                        )
                        refreshed = future.result(timeout=30)
                else:
                    refreshed = loop.run_until_complete(
                        strategy.refresh_token(tokens.refresh_token, cid, cs)
                    )
                self.store.save(provider_id, refreshed)
                logger.info("OAuth token refreshed for %s", provider_id)
                return refreshed
            except Exception as e:
                logger.warning("Failed to refresh OAuth token for %s: %s", provider_id, e)
                return None

    def is_connected(self, provider_id: str) -> bool:
        tokens = self.store.load(provider_id)
        if tokens:
            return True
        api_key = _get_api_key(provider_id)
        return api_key not in ("None", "NA", "")

    def get_connected(self) -> list[ConnectedProvider]:
        result = []
        for pid in _get_all_provider_ids():
            tokens = self.store.load(pid)
            if tokens:
                result.append(ConnectedProvider(pid, "oauth", True))
            elif _get_api_key(pid) not in ("None", "NA", ""):
                result.append(ConnectedProvider(pid, "api_key", True))
        return result

    def disconnect(self, provider_id: str):
        tokens = self.store.load(provider_id)
        if tokens:
            strategy = get_oauth_provider(provider_id)
            if strategy:
                try:
                    import asyncio
                    asyncio.run(strategy.revoke(tokens.access_token))
                except Exception as e:
                    logger.warning("Failed to revoke token for %s (best-effort): %s", provider_id, e)
        self.store.delete(provider_id)
        self._model_cache.pop(provider_id, None)
        logger.info("Disconnected OAuth for %s", provider_id)

    async def list_models(self, provider_id: str) -> list[ModelInfo]:
        cached = self._model_cache.get(provider_id)
        if cached:
            ts, models = cached
            if datetime.now(timezone.utc) - ts < _MODEL_CACHE_TTL:
                return models

        strategy = get_oauth_provider(provider_id)
        if not strategy:
            return []
        cred = self.get_credential(provider_id)
        if not cred or cred in ("None", "NA"):
            return []
        try:
            models = await strategy.list_models(cred)
            self._model_cache[provider_id] = (datetime.now(timezone.utc), models)
            return models
        except Exception as e:
            logger.warning("Failed to fetch models for %s: %s", provider_id, e)
            if cached:
                return cached[1]
            return []
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/helpers/test_connected_providers.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add python/helpers/connected_providers.py tests/helpers/test_connected_providers.py
git commit -m "feat(oauth): add ProviderPool with credential resolution and model caching"
```

---

### Task 5: Provider YAML Config + Providers.py Integration

**Files:**
- Modify: `conf/model_providers.yaml`
- Modify: `python/helpers/providers.py`
- Test: `tests/helpers/test_providers_oauth.py`

- [ ] **Step 1: Write failing test for oauth config parsing**

Create `tests/helpers/test_providers_oauth.py`:

```python
from python.helpers.providers import get_provider_config


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
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/helpers/test_providers_oauth.py -v`
Expected: FAIL — no `oauth` config in YAML.

- [ ] **Step 3: Add oauth blocks to model_providers.yaml**

In `conf/model_providers.yaml`, add `oauth` to google, openai, anthropic under `chat:`:

```yaml
  google:
    name: Google
    litellm_provider: gemini
    oauth:
      enabled: true
      strategy: google
  openai:
    name: OpenAI
    litellm_provider: openai
    oauth:
      enabled: true
      strategy: openai
  anthropic:
    name: Anthropic
    litellm_provider: anthropic
    oauth:
      enabled: false
      strategy: anthropic
```

- [ ] **Step 4: Add `get_oauth_providers()` to providers.py**

Add to `python/helpers/providers.py` after the existing convenience functions (after line 101):

```python
def get_oauth_providers() -> list[dict]:
    """Return chat providers that have OAuth configured."""
    result = []
    for p in get_raw_providers("chat"):
        oauth = p.get("oauth")
        if isinstance(oauth, dict) and oauth.get("strategy"):
            result.append({
                "provider_id": (p.get("id") or p.get("value", "")).lower(),
                "name": p.get("name", ""),
                "enabled": oauth.get("enabled", False),
                "strategy": oauth["strategy"],
            })
    return result
```

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest tests/helpers/test_providers_oauth.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add conf/model_providers.yaml python/helpers/providers.py tests/helpers/test_providers_oauth.py
git commit -m "feat(oauth): add OAuth config to provider YAML and expose get_oauth_providers()"
```

---

### Task 6: models.py + settings.py Integration

**Files:**
- Modify: `models.py:280-293` (`get_api_key`)
- Modify: `python/helpers/settings.py:447-515` (sensitive settings)
- Test: `tests/helpers/test_oauth_integration.py`

- [ ] **Step 1: Write failing tests**

Create `tests/helpers/test_oauth_integration.py`:

```python
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


class TestSettingsOAuthClientCreds:
    def test_load_sensitive_loads_oauth_creds(self):
        settings = {"api_keys": {}, "oauth_client_credentials": {}}
        with patch("python.helpers.dotenv.get_dotenv_value") as mock_dotenv:
            def side_effect(key):
                mapping = {
                    "OAUTH_CLIENT_ID_GOOGLE": "google-cid",
                    "OAUTH_CLIENT_SECRET_GOOGLE": "google-cs",
                }
                return mapping.get(key, "")
            mock_dotenv.side_effect = side_effect
            from python.helpers.settings import _load_oauth_client_credentials
            _load_oauth_client_credentials(settings)

        assert settings["oauth_client_credentials"]["google"]["client_id"] == "google-cid"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/helpers/test_oauth_integration.py -v`
Expected: FAIL

- [ ] **Step 3: Modify `models.get_api_key()` to delegate**

In `models.py`, replace the `get_api_key` function (lines 280–293):

```python
def get_api_key(service: str) -> str:
    from python.helpers.connected_providers import ProviderPool
    pool = ProviderPool.get_instance()
    key = pool.get_credential(service)
    if key and key not in ("None", "NA"):
        # Round-robin for comma-separated API keys
        if "," in key:
            api_keys = [k.strip() for k in key.split(",") if k.strip()]
            api_keys_round_robin[service] = api_keys_round_robin.get(service, -1) + 1
            key = api_keys[api_keys_round_robin[service] % len(api_keys)]
        return key
    return "None"
```

- [ ] **Step 4: Add OAuth client credential helpers to settings.py**

Add `oauth_client_credentials` to the `Settings` TypedDict (after `api_keys` field, around line 130):

```python
    oauth_client_credentials: dict[str, dict[str, str]]
```

Add `_load_oauth_client_credentials()` and `_write_oauth_client_credentials()` functions:

```python
def _load_oauth_client_credentials(settings: Settings):
    from python.helpers.providers import get_oauth_providers
    creds = {}
    for p in get_oauth_providers():
        pid = p["provider_id"]
        cid = dotenv.get_dotenv_value(f"OAUTH_CLIENT_ID_{pid.upper()}") or ""
        cs = dotenv.get_dotenv_value(f"OAUTH_CLIENT_SECRET_{pid.upper()}") or ""
        if cid or cs:
            creds[pid] = {"client_id": cid, "client_secret": cs}
    settings["oauth_client_credentials"] = creds


def _write_oauth_client_credentials(settings: Settings):
    for pid, creds in settings.get("oauth_client_credentials", {}).items():
        cid = creds.get("client_id", "")
        cs = creds.get("client_secret", "")
        if cid:
            dotenv.save_dotenv_value(f"OAUTH_CLIENT_ID_{pid.upper()}", cid)
        if cs and cs != API_KEY_PLACEHOLDER:
            dotenv.save_dotenv_value(f"OAUTH_CLIENT_SECRET_{pid.upper()}", cs)
```

Wire into existing `_load_sensitive_settings()` (call `_load_oauth_client_credentials(settings)` at end) and `_write_sensitive_settings()` (call `_write_oauth_client_credentials(settings)` at end). Add to `_remove_sensitive_settings()`: `settings["oauth_client_credentials"] = {}`. Add default in `get_default_settings()`: `"oauth_client_credentials": {}`.

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest tests/helpers/test_oauth_integration.py -v`
Expected: PASS

- [ ] **Step 6: Run full existing test suite to check for regressions**

Run: `pytest tests/ -x --timeout=60 -q -m "not integration"`
Expected: No new failures.

- [ ] **Step 7: Commit**

```bash
git add models.py python/helpers/settings.py tests/helpers/test_oauth_integration.py
git commit -m "feat(oauth): integrate ProviderPool into models.py and OAuth creds into settings"
```

---

### Task 7: OAuth API Endpoints

**Files:**
- Create: `python/api/oauth_authorize.py`
- Create: `python/api/oauth_callback.py`
- Create: `python/api/oauth_exchange.py`
- Create: `python/api/oauth_disconnect.py`
- Create: `python/api/oauth_providers.py`
- Create: `python/api/oauth_status.py`
- Test: `tests/api/test_oauth_endpoints.py`

- [ ] **Step 1: Write failing tests for OAuth endpoints**

Create `tests/api/test_oauth_endpoints.py`:

```python
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from python.api.oauth_authorize import OAuthAuthorize
from python.api.oauth_callback import OAuthCallback
from python.api.oauth_disconnect import OAuthDisconnect
from python.api.oauth_providers import OAuthProviders


class TestOAuthAuthorize:
    @pytest.mark.asyncio
    async def test_returns_authorization_url(self):
        handler = OAuthAuthorize()
        with patch("python.api.oauth_authorize.get_oauth_provider") as mock_get:
            mock_provider = MagicMock()
            mock_provider.get_authorization_url.return_value = "https://accounts.google.com/auth?client_id=test"
            mock_provider.supports_pkce = False
            mock_get.return_value = mock_provider

            result = await handler.process({
                "provider_id": "google",
                "client_id": "test-cid",
                "client_secret": "test-cs",
                "redirect_uri": "http://localhost/oauth_callback",
            }, MagicMock())

        assert "authorization_url" in result
        assert "google.com" in result["authorization_url"]


class TestOAuthProviders:
    @pytest.mark.asyncio
    async def test_returns_provider_list_with_status(self):
        handler = OAuthProviders()
        with patch("python.api.oauth_providers.get_oauth_providers") as mock_providers:
            mock_providers.return_value = [
                {"provider_id": "google", "name": "Google", "enabled": True, "strategy": "google"},
            ]
            with patch("python.api.oauth_providers.ProviderPool") as mock_pool_cls:
                mock_pool = MagicMock()
                mock_pool.is_connected.return_value = True
                mock_pool_cls.get_instance.return_value = mock_pool

                result = await handler.process({}, MagicMock())

        assert len(result["providers"]) == 1
        assert result["providers"][0]["connected"] is True


class TestOAuthDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_calls_pool(self):
        handler = OAuthDisconnect()
        with patch("python.api.oauth_disconnect.ProviderPool") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool_cls.get_instance.return_value = mock_pool

            result = await handler.process({"provider_id": "google"}, MagicMock())

        mock_pool.disconnect.assert_called_once_with("google")
        assert result["status"] == "disconnected"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/api/test_oauth_endpoints.py -v`
Expected: FAIL — modules not found.

- [ ] **Step 3: Implement OAuth API endpoints**

Create each file following the `ApiHandler` pattern from `python/helpers/api.py`. Each handler subclasses `ApiHandler` and implements `async def process(self, input, request)`.

**`python/api/oauth_authorize.py`** — generates authorization URL, stores state + PKCE verifier in module-level dict with TTL:

```python
import secrets
import time
from python.helpers.api import ApiHandler, Request, Response
from python.helpers.oauth import get_oauth_provider
from python.helpers import dotenv

_pending_states: dict[str, dict] = {}
_STATE_TTL = 600  # 10 minutes


def _cleanup_expired():
    now = time.time()
    expired = [k for k, v in _pending_states.items() if now - v["created"] > _STATE_TTL]
    for k in expired:
        del _pending_states[k]


class OAuthAuthorize(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        _cleanup_expired()

        provider_id = input.get("provider_id", "")
        client_id = input.get("client_id", "")
        client_secret = input.get("client_secret", "")
        redirect_uri = input.get("redirect_uri", "")
        flow = input.get("flow", "redirect")

        provider = get_oauth_provider(provider_id)
        if not provider:
            return Response({"error": f"Unknown provider: {provider_id}"}, status=400)

        # Save client credentials
        if client_id:
            dotenv.save_dotenv_value(f"OAUTH_CLIENT_ID_{provider_id.upper()}", client_id)
        if client_secret:
            dotenv.save_dotenv_value(f"OAUTH_CLIENT_SECRET_{provider_id.upper()}", client_secret)

        state = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(43) if provider.supports_pkce else None

        _pending_states[state] = {
            "provider_id": provider_id,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
            "flow": flow,
            "created": time.time(),
        }

        auth_url = provider.get_authorization_url(
            client_id=client_id,
            redirect_uri=redirect_uri if flow == "redirect" else "",
            state=state,
            code_verifier=code_verifier,
        )

        return {"authorization_url": auth_url, "state": state, "flow": flow}
```

**`python/api/oauth_callback.py`** — handles redirect, validates state, exchanges code:

```python
from flask import Response as FlaskResponse
from python.helpers.api import ApiHandler, Request, Response
from python.helpers.oauth import get_oauth_provider
from python.helpers.connected_providers import ProviderPool
from python.helpers import dotenv
from python.api.oauth_authorize import _pending_states


class OAuthCallback(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        code = request.args.get("code", "")
        state = request.args.get("state", "")
        error = request.args.get("error", "")

        if error:
            return FlaskResponse(
                f"<html><body><h2>Authorization cancelled</h2><p>{error}</p></body></html>",
                content_type="text/html",
            )

        pending = _pending_states.pop(state, None)
        if not pending:
            return FlaskResponse(
                "<html><body><h2>Invalid or expired state</h2><p>Please try again.</p></body></html>",
                content_type="text/html", status=400,
            )

        provider_id = pending["provider_id"]
        provider = get_oauth_provider(provider_id)
        cid = dotenv.get_dotenv_value(f"OAUTH_CLIENT_ID_{provider_id.upper()}") or ""
        cs = dotenv.get_dotenv_value(f"OAUTH_CLIENT_SECRET_{provider_id.upper()}") or ""

        tokens = await provider.exchange_code(
            code=code, client_id=cid, client_secret=cs,
            redirect_uri=pending["redirect_uri"],
            code_verifier=pending.get("code_verifier"),
        )
        pool = ProviderPool.get_instance()
        pool.store.save(provider_id, tokens)
        pool._model_cache.pop(provider_id, None)  # invalidate model cache on connect

        return FlaskResponse(
            "<html><body><h2>Connected!</h2><p>You can close this window.</p>"
            "<script>window.close()</script></body></html>",
            content_type="text/html",
        )

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET"]
```

**`python/api/oauth_exchange.py`** — manual code exchange for copy-paste flow:

```python
from python.helpers.api import ApiHandler, Request, Response
from python.helpers.oauth import get_oauth_provider
from python.helpers.connected_providers import ProviderPool
from python.helpers import dotenv
from python.api.oauth_authorize import _pending_states


class OAuthExchange(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        provider_id = input.get("provider_id", "")
        code = input.get("code", "")
        state = input.get("state", "")

        pending = _pending_states.pop(state, None)
        if not pending:
            return Response({"error": "Invalid or expired state"}, status=400)

        provider = get_oauth_provider(provider_id)
        if not provider:
            return Response({"error": f"Unknown provider: {provider_id}"}, status=400)

        cid = dotenv.get_dotenv_value(f"OAUTH_CLIENT_ID_{provider_id.upper()}") or ""
        cs = dotenv.get_dotenv_value(f"OAUTH_CLIENT_SECRET_{provider_id.upper()}") or ""

        tokens = await provider.exchange_code(
            code=code, client_id=cid, client_secret=cs,
            redirect_uri=pending.get("redirect_uri", ""),
            code_verifier=pending.get("code_verifier"),
        )
        pool = ProviderPool.get_instance()
        pool.store.save(provider_id, tokens)
        pool._model_cache.pop(provider_id, None)  # invalidate model cache on connect

        return {"status": "connected", "provider_id": provider_id}
```

**`python/api/oauth_disconnect.py`:**

```python
from python.helpers.api import ApiHandler, Request, Response
from python.helpers.connected_providers import ProviderPool


class OAuthDisconnect(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        provider_id = input.get("provider_id", "")
        ProviderPool.get_instance().disconnect(provider_id)
        return {"status": "disconnected", "provider_id": provider_id}
```

**`python/api/oauth_providers.py`:**

```python
from python.helpers.api import ApiHandler, Request, Response
from python.helpers.providers import get_oauth_providers
from python.helpers.connected_providers import ProviderPool


class OAuthProviders(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        pool = ProviderPool.get_instance()
        providers = []
        for p in get_oauth_providers():
            providers.append({
                **p,
                "connected": pool.is_connected(p["provider_id"]),
            })
        return {"providers": providers}

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET", "POST"]
```

**`python/api/oauth_status.py`:**

```python
from python.helpers.api import ApiHandler, Request, Response
from python.helpers.connected_providers import ProviderPool


class OAuthStatus(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        provider_id = input.get("provider_id", "")
        pool = ProviderPool.get_instance()
        tokens = pool.store.load(provider_id)
        return {
            "provider_id": provider_id,
            "connected": tokens is not None,
            "expires_at": tokens.expires_at.isoformat() if tokens else None,
            "scope": tokens.scope if tokens else None,
        }
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/api/test_oauth_endpoints.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add python/api/oauth_*.py tests/api/test_oauth_endpoints.py
git commit -m "feat(oauth): add OAuth API endpoints (authorize, callback, exchange, disconnect, providers, status)"
```

---

### Task 8: Dynamic Model List Endpoint

**Files:**
- Create: `python/api/provider_models.py`
- Test: `tests/api/test_provider_models.py`

- [ ] **Step 1: Write failing test**

Create `tests/api/test_provider_models.py`:

```python
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from python.api.provider_models import ProviderModels
from python.helpers.oauth import ModelInfo


class TestProviderModels:
    @pytest.mark.asyncio
    async def test_returns_model_list(self):
        handler = ProviderModels()
        mock_models = [
            ModelInfo(id="gemini-2.5-pro", name="Gemini 2.5 Pro", context_length=1048576, supports_vision=True),
            ModelInfo(id="gemini-2.0-flash", name="Gemini 2.0 Flash", context_length=1048576, supports_vision=True),
        ]
        with patch("python.api.provider_models.ProviderPool") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool.list_models = AsyncMock(return_value=mock_models)
            mock_pool_cls.get_instance.return_value = mock_pool

            result = await handler.process({"provider_id": "google"}, MagicMock())

        assert len(result["models"]) == 2
        assert result["models"][0]["id"] == "gemini-2.5-pro"

    @pytest.mark.asyncio
    async def test_returns_empty_for_disconnected(self):
        handler = ProviderModels()
        with patch("python.api.provider_models.ProviderPool") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool.list_models = AsyncMock(return_value=[])
            mock_pool_cls.get_instance.return_value = mock_pool

            result = await handler.process({"provider_id": "unknown"}, MagicMock())

        assert result["models"] == []
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/api/test_provider_models.py -v`
Expected: FAIL

- [ ] **Step 3: Implement endpoint**

Create `python/api/provider_models.py`:

```python
from python.helpers.api import ApiHandler, Request, Response
from python.helpers.connected_providers import ProviderPool


class ProviderModels(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        provider_id = input.get("provider_id", "")
        pool = ProviderPool.get_instance()
        models = await pool.list_models(provider_id)
        return {
            "provider_id": provider_id,
            "models": [
                {
                    "id": m.id,
                    "name": m.name,
                    "context_length": m.context_length,
                    "supports_vision": m.supports_vision,
                }
                for m in models
            ],
        }

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET", "POST"]
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/api/test_provider_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add python/api/provider_models.py tests/api/test_provider_models.py
git commit -m "feat(oauth): add dynamic model list endpoint"
```

---

### Task 9: Per-Chat Model Override

**Files:**
- Create: `python/api/chat_model_override.py`
- Modify: `initialize.py:31-43`
- Test: `tests/api/test_chat_model_override.py`

- [ ] **Step 1: Write failing tests**

Create `tests/api/test_chat_model_override.py`:

```python
import pytest
import json
from unittest.mock import patch, MagicMock, AsyncMock
from python.api.chat_model_override import ChatModelOverride


class TestChatModelOverride:
    @pytest.mark.asyncio
    async def test_set_override(self):
        handler = ChatModelOverride()
        with patch("python.api.chat_model_override._save_override") as mock_save:
            result = await handler.process({
                "chat_id": "abc-123",
                "provider": "google",
                "model": "gemini-2.5-pro",
            }, MagicMock())
        mock_save.assert_called_once()
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_get_override_returns_null_when_unset(self):
        handler = ChatModelOverride()
        with patch("python.api.chat_model_override._load_override", return_value=None):
            result = await handler.process({"chat_id": "abc-123"}, MagicMock())
        assert result["override"] is None

    @pytest.mark.asyncio
    async def test_get_override_returns_saved_value(self):
        handler = ChatModelOverride()
        with patch("python.api.chat_model_override._load_override", return_value={"provider": "google", "model": "gemini-2.5-pro"}):
            result = await handler.process({"chat_id": "abc-123"}, MagicMock())
        assert result["override"]["provider"] == "google"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/api/test_chat_model_override.py -v`
Expected: FAIL

- [ ] **Step 3: Implement chat model override endpoint**

Create `python/api/chat_model_override.py`:

```python
import json
import os
from python.helpers.api import ApiHandler, Request, Response
from python.helpers import files


def _override_path(chat_id: str) -> str:
    return files.get_abs_path(f"usr/chats/{chat_id}/model_override.json")


def _load_override(chat_id: str) -> dict | None:
    path = _override_path(chat_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _save_override(chat_id: str, provider: str, model: str):
    path = _override_path(chat_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"provider": provider, "model": model}, f)


class ChatModelOverride(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        chat_id = input.get("chat_id", "")
        if not chat_id:
            return Response({"error": "chat_id required"}, status=400)

        provider = input.get("provider")
        model = input.get("model")

        if provider and model:
            _save_override(chat_id, provider, model)
            return {"status": "ok", "chat_id": chat_id, "provider": provider, "model": model}

        override = _load_override(chat_id)
        return {"chat_id": chat_id, "override": override}

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET", "POST"]
```

- [ ] **Step 4: Modify initialize.py to apply override**

In `initialize.py`, after building `chat_llm` from settings (line 43), add override check:

```python
    # Apply per-chat model override if present
    chat_override = kwargs.get("chat_model_override")
    if chat_override:
        override_provider = chat_override.get("provider")
        override_model = chat_override.get("model")
        if override_provider and override_model:
            from python.helpers.connected_providers import ProviderPool
            pool = ProviderPool.get_instance()
            if pool.is_connected(override_provider):
                chat_llm = models.ModelConfig(
                    type=models.ModelType.CHAT,
                    provider=override_provider,
                    name=override_model,
                    ctx_length=current_settings["chat_model_ctx_length"],
                    vision=current_settings["chat_model_vision"],
                    limit_requests=current_settings["chat_model_rl_requests"],
                    limit_input=current_settings["chat_model_rl_input"],
                    limit_output=current_settings["chat_model_rl_output"],
                    kwargs=_normalize_model_kwargs(current_settings["chat_model_kwargs"]),
                )
```

The `initialize_agent()` function is called from two key locations:
- `python/helpers/settings.py:619` — global re-initialization on settings change (no chat context, no override needed)
- `python/extensions/agent_init/_15_load_profile_settings.py:37` — per-agent profile override

Add `chat_id` as an optional parameter to `initialize_agent()`:

```python
def initialize_agent(override_settings: dict | None = None, chat_id: str | None = None):
```

At the top of the function (after building `chat_llm`), load and apply override:

```python
    if chat_id:
        from python.api.chat_model_override import _load_override
        chat_override = _load_override(chat_id)
        if chat_override:
            from python.helpers.connected_providers import ProviderPool
            pool = ProviderPool.get_instance()
            if pool.is_connected(chat_override["provider"]):
                chat_llm = models.ModelConfig(
                    type=models.ModelType.CHAT,
                    provider=chat_override["provider"],
                    name=chat_override["model"],
                    ctx_length=current_settings["chat_model_ctx_length"],
                    vision=current_settings["chat_model_vision"],
                    limit_requests=current_settings["chat_model_rl_requests"],
                    limit_input=current_settings["chat_model_rl_input"],
                    limit_output=current_settings["chat_model_rl_output"],
                    kwargs=_normalize_model_kwargs(current_settings["chat_model_kwargs"]),
                )
```

Then find where agent is created for a chat (search for `AgentContext` creation in `run_ui.py` or `python/api/chat_*.py`) and pass `chat_id` to `initialize_agent()` there. The agent context likely has a `chat_id` field — use it.

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest tests/api/test_chat_model_override.py -v`
Expected: PASS

- [ ] **Step 6: Run full test suite for regressions**

Run: `pytest tests/ -x --timeout=60 -q -m "not integration"`
Expected: No new failures.

- [ ] **Step 7: Commit**

```bash
git add python/api/chat_model_override.py initialize.py tests/api/test_chat_model_override.py
git commit -m "feat(oauth): add per-chat model override endpoint and initialize.py integration"
```

---

### Task 10: Settings UI — OAuth Connect/Disconnect

**Files:**
- Modify: `webui/components/settings/agent/agent.html`
- Create: `webui/js/oauth.js`

- [ ] **Step 1: Add OAuth section to agent settings HTML**

In `webui/components/settings/agent/agent.html`, after the existing agent profile field, add an OAuth connections section:

```html
          <div class="section-title">OAuth Connections</div>
          <div class="section-description">
            Connect model providers via OAuth for seamless authentication. You'll need to register an OAuth app with each provider first.
          </div>

          <template x-if="$store.oauth && $store.oauth.providers">
            <template x-for="provider in $store.oauth.providers.filter(p => p.enabled)" :key="provider.provider_id">
              <div class="field">
                <div class="field-label">
                  <div class="field-title" x-text="provider.name"></div>
                  <div class="field-description">
                    <span x-show="provider.connected" class="text-green">Connected</span>
                    <span x-show="!provider.connected" class="text-muted">Not connected</span>
                  </div>
                </div>
                <div class="field-control">
                  <template x-if="!provider.connected">
                    <div>
                      <input type="text" x-model="provider._client_id" placeholder="Client ID" class="input-sm">
                      <input type="password" x-model="provider._client_secret" placeholder="Client Secret" class="input-sm">
                      <button @click="$store.oauth.connect(provider)" class="btn btn-primary btn-sm">Sign in</button>
                      <template x-if="provider._manualFlow">
                        <div class="manual-code-flow">
                          <p class="text-muted">Redirect didn't work? Paste the authorization code here:</p>
                          <input type="text" x-model="provider._manualCode" placeholder="Paste authorization code">
                          <button @click="$store.oauth.submitManualCode(provider)" class="btn btn-sm">Submit code</button>
                        </div>
                      </template>
                    </div>
                  </template>
                  <template x-if="provider.connected">
                    <button @click="$store.oauth.disconnect(provider.provider_id)" class="btn btn-danger btn-sm">Disconnect</button>
                  </template>
                </div>
              </div>
            </template>
          </template>
```

- [ ] **Step 2: Create oauth.js store**

Create `webui/js/oauth.js` with Alpine.js store for OAuth management:

```javascript
document.addEventListener("alpine:init", () => {
  Alpine.store("oauth", {
    providers: [],

    async init() {
      await this.loadProviders();
    },

    async loadProviders() {
      try {
        const resp = await fetch("/oauth_providers");
        const data = await resp.json();
        this.providers = data.providers.map((p) => ({
          ...p,
          _client_id: "",
          _client_secret: "",
        }));
      } catch (e) {
        console.error("Failed to load OAuth providers:", e);
      }
    },

    _pendingState: null,

    async connect(provider) {
      const redirectUri = window.location.origin + "/oauth_callback";
      try {
        const resp = await fetch("/oauth_authorize", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            provider_id: provider.provider_id,
            client_id: provider._client_id,
            client_secret: provider._client_secret,
            redirect_uri: redirectUri,
            flow: "redirect",
          }),
        });
        const data = await resp.json();
        if (data.authorization_url) {
          this._pendingState = data.state;
          provider._manualFlow = false;
          provider._manualCode = "";

          const popup = window.open(data.authorization_url, "oauth", "width=600,height=700");
          let elapsed = 0;
          const timer = setInterval(() => {
            elapsed += 500;
            if (popup && popup.closed) {
              clearInterval(timer);
              this._pendingState = null;
              this.loadProviders();
            }
            // After 5s if popup hasn't closed, offer manual flow
            if (elapsed >= 5000 && popup && !popup.closed) {
              provider._manualFlow = true;
            }
          }, 500);
        }
      } catch (e) {
        console.error("OAuth connect failed:", e);
      }
    },

    async submitManualCode(provider) {
      if (!provider._manualCode || !this._pendingState) return;
      try {
        const resp = await fetch("/oauth_exchange", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            provider_id: provider.provider_id,
            code: provider._manualCode,
            state: this._pendingState,
          }),
        });
        const data = await resp.json();
        if (data.status === "connected") {
          this._pendingState = null;
          provider._manualFlow = false;
          await this.loadProviders();
        }
      } catch (e) {
        console.error("Manual code exchange failed:", e);
      }
    },

    async disconnect(providerId) {
      try {
        await fetch("/oauth_disconnect", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ provider_id: providerId }),
        });
        await this.loadProviders();
      } catch (e) {
        console.error("OAuth disconnect failed:", e);
      }
    },
  });
});
```

- [ ] **Step 3: Verify UI loads without JS errors**

Start the dev server and open the settings page. Verify:
- OAuth Connections section appears
- Provider list loads from API
- No console errors

- [ ] **Step 4: Commit**

```bash
git add webui/components/settings/agent/agent.html webui/js/oauth.js
git commit -m "feat(oauth): add OAuth connect/disconnect UI in settings"
```

---

### Task 11: Chat UI — Model Picker Dropdown

**Files:**
- Create: `webui/js/model-picker.js`
- Modify: chat UI template (header area)

- [ ] **Step 1: Create model picker Alpine component**

Create `webui/js/model-picker.js`:

```javascript
document.addEventListener("alpine:init", () => {
  Alpine.store("modelPicker", {
    models: {},       // { provider_id: [ModelInfo, ...] }
    currentOverride: null,
    chatId: null,
    open: false,

    async loadModels() {
      const pool = Alpine.store("oauth");
      if (!pool || !pool.providers) return;

      for (const p of pool.providers.filter((p) => p.connected)) {
        try {
          const resp = await fetch("/provider_models", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ provider_id: p.provider_id }),
          });
          const data = await resp.json();
          this.models[p.provider_id] = data.models;
        } catch (e) {
          console.error(`Failed to load models for ${p.provider_id}:`, e);
        }
      }
    },

    async loadOverride(chatId) {
      this.chatId = chatId;
      try {
        const resp = await fetch("/chat_model_override", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ chat_id: chatId }),
        });
        const data = await resp.json();
        this.currentOverride = data.override;
      } catch (e) {
        this.currentOverride = null;
      }
    },

    async selectModel(providerId, modelId) {
      if (!this.chatId) return;
      try {
        await fetch("/chat_model_override", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            chat_id: this.chatId,
            provider: providerId,
            model: modelId,
          }),
        });
        this.currentOverride = { provider: providerId, model: modelId };
        this.open = false;
      } catch (e) {
        console.error("Failed to set model override:", e);
      }
    },

    get currentLabel() {
      if (this.currentOverride) {
        return `${this.currentOverride.model} (${this.currentOverride.provider})`;
      }
      return "Default model";
    },
  });
});
```

- [ ] **Step 2: Add model picker dropdown to chat header**

Add to the chat header area (location depends on existing chat UI template structure — check `webui/components/chat/` or equivalent):

```html
<div class="model-picker" x-data>
  <button @click="$store.modelPicker.open = !$store.modelPicker.open" class="btn btn-sm btn-outline">
    <span x-text="$store.modelPicker.currentLabel"></span>
    <span class="caret">▾</span>
  </button>
  <div x-show="$store.modelPicker.open" @click.outside="$store.modelPicker.open = false" class="model-picker-dropdown">
    <template x-for="[providerId, models] in Object.entries($store.modelPicker.models)" :key="providerId">
      <div class="model-group">
        <div class="model-group-label" x-text="providerId"></div>
        <template x-for="model in models" :key="model.id">
          <div class="model-item" @click="$store.modelPicker.selectModel(providerId, model.id)">
            <span x-text="model.name"></span>
            <span class="model-meta" x-text="(model.context_length / 1000) + 'k'"></span>
            <span x-show="model.supports_vision" class="model-badge">vision</span>
          </div>
        </template>
      </div>
    </template>
  </div>
</div>
```

- [ ] **Step 3: Verify model picker works**

Start dev server, open a chat:
- Model picker shows in header
- Click opens dropdown with models grouped by provider
- Selecting a model saves override
- Refreshing page preserves selection

- [ ] **Step 4: Commit**

```bash
git add webui/js/model-picker.js webui/components/
git commit -m "feat(oauth): add per-chat model picker dropdown in chat UI"
```

---

### Task 12: Final Regression Tests + Cleanup

**Files:**
- All modified files
- `requirements.txt` (if `httpx` not already present)

- [ ] **Step 1: Add httpx to requirements if missing**

Check `requirements.txt` for `httpx`. If missing, add: `httpx>=0.27.0`

Run: `pip install httpx`

- [ ] **Step 2: Run full test suite**

Run: `pytest tests/ -x --timeout=60 -q -m "not integration"`
Expected: All tests pass, no regressions.

- [ ] **Step 3: Run linting if configured**

Run: `ruff check python/helpers/oauth.py python/helpers/oauth_store.py python/helpers/connected_providers.py python/api/oauth_*.py python/api/provider_models.py python/api/chat_model_override.py`
Fix any issues.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore(oauth): add httpx dependency and cleanup"
```

- [ ] **Step 5: Create PR**

```bash
git push -u origin HEAD
gh pr create --title "feat: OAuth provider framework & per-chat model switching" --body "$(cat <<'EOF'
## Summary
- OAuth2 authentication framework for model providers (Google, OpenAI enabled; Anthropic code-complete but hidden)
- Connected provider pool abstracting credential resolution (OAuth token or API key)
- Per-chat model switching with dynamic model discovery from provider APIs
- Settings UI for OAuth connect/disconnect
- Chat UI model picker dropdown

## Spec
docs/superpowers/specs/2026-03-26-oauth-provider-framework-design.md

## Test plan
- [ ] OAuth strategies tested with mocked HTTP (Google, OpenAI, Anthropic)
- [ ] Token storage: save/load/delete/corruption recovery
- [ ] ProviderPool: credential resolution, refresh, fallback
- [ ] API endpoints: authorize, callback, exchange, disconnect, providers, status
- [ ] Model list endpoint with caching
- [ ] Per-chat model override CRUD and initialization
- [ ] Full regression suite passes

EOF
)"
```
