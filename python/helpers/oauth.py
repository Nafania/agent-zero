import base64
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
from typing import Optional
from urllib.parse import urlencode

import httpx

_logger = logging.getLogger(__name__)


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
    def get_authorization_url(self, client_id: str, redirect_uri: str, state: str, code_verifier: Optional[str] = None) -> str: ...

    @abstractmethod
    async def exchange_code(self, code: str, client_id: str, client_secret: str, redirect_uri: str, code_verifier: Optional[str] = None) -> OAuthTokens: ...

    @abstractmethod
    async def refresh_token(self, refresh_token: str, client_id: str, client_secret: str) -> OAuthTokens: ...

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

    def get_authorization_url(
        self,
        client_id: str,
        redirect_uri: str,
        state: str,
        code_verifier: Optional[str] = None,
    ) -> str:
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

    async def exchange_code(
        self,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code_verifier: Optional[str] = None,
    ) -> OAuthTokens:
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.token_url, data={
                "code": code, "client_id": client_id, "client_secret": client_secret,
                "redirect_uri": redirect_uri, "grant_type": "authorization_code",
            })
            resp.raise_for_status()
            return _tokens_from_response(resp.json())

    async def refresh_token(
        self,
        refresh_token: str,
        client_id: str,
        client_secret: str,
    ) -> OAuthTokens:
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.token_url, data={
                "refresh_token": refresh_token, "client_id": client_id,
                "client_secret": client_secret, "grant_type": "refresh_token",
            })
            resp.raise_for_status()
            tokens = _tokens_from_response(resp.json())
            if not tokens.refresh_token:
                tokens.refresh_token = refresh_token
            return tokens

    async def revoke(self, access_token: str) -> None:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(self.revoke_url, params={"token": access_token})
            except httpx.RequestError as exc:
                _logger.warning("Google OAuth revoke request failed: %s", exc)
                return
            if resp.is_error:
                body_preview = (resp.text or "")[:200]
                _logger.warning(
                    "Google OAuth revoke returned HTTP %s: %s",
                    resp.status_code,
                    body_preview,
                )

    async def list_models(self, access_token: str) -> list[ModelInfo]:
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


class OpenAIOAuth(OAuthProvider):
    provider_id = "openai"
    authorize_url = "https://auth.openai.com/authorize"
    token_url = "https://auth.openai.com/oauth/token"
    scopes = ["model.read", "model.request"]
    models_url = "https://api.openai.com/v1/models"
    revoke_url = "https://auth.openai.com/oauth/revoke"
    supports_pkce = False

    CHAT_MODEL_PREFIXES = ("gpt-", "o1-", "o3-", "o4-", "chatgpt-")

    def get_authorization_url(
        self,
        client_id: str,
        redirect_uri: str,
        state: str,
        code_verifier: Optional[str] = None,
    ) -> str:
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "state": state,
        }
        return f"{self.authorize_url}?{urlencode(params)}"

    async def exchange_code(
        self,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code_verifier: Optional[str] = None,
    ) -> OAuthTokens:
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.token_url, data={
                "code": code, "client_id": client_id, "client_secret": client_secret,
                "redirect_uri": redirect_uri, "grant_type": "authorization_code",
            })
            resp.raise_for_status()
            return _tokens_from_response(resp.json())

    async def refresh_token(
        self,
        refresh_token: str,
        client_id: str,
        client_secret: str,
    ) -> OAuthTokens:
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.token_url, data={
                "refresh_token": refresh_token, "client_id": client_id,
                "client_secret": client_secret, "grant_type": "refresh_token",
            })
            resp.raise_for_status()
            tokens = _tokens_from_response(resp.json())
            if not tokens.refresh_token:
                tokens.refresh_token = refresh_token
            return tokens

    async def revoke(self, access_token: str) -> None:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(self.revoke_url, data={"token": access_token})
            except httpx.RequestError as exc:
                _logger.warning("OpenAI OAuth revoke request failed: %s", exc)
                return
            if resp.is_error:
                _logger.warning("OpenAI OAuth revoke returned HTTP %s: %s", resp.status_code, (resp.text or "")[:200])

    async def list_models(self, access_token: str) -> list[ModelInfo]:
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

    def get_authorization_url(
        self,
        client_id: str,
        redirect_uri: str,
        state: str,
        code_verifier: Optional[str] = None,
    ) -> str:
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

    async def exchange_code(
        self,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code_verifier: Optional[str] = None,
    ) -> OAuthTokens:
        payload = {
            "code": code, "client_id": client_id, "client_secret": client_secret,
            "redirect_uri": redirect_uri, "grant_type": "authorization_code",
        }
        if code_verifier:
            payload["code_verifier"] = code_verifier
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.token_url, data=payload)
            resp.raise_for_status()
            return _tokens_from_response(resp.json())

    async def refresh_token(
        self,
        refresh_token: str,
        client_id: str,
        client_secret: str,
    ) -> OAuthTokens:
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.token_url, data={
                "refresh_token": refresh_token, "client_id": client_id,
                "client_secret": client_secret, "grant_type": "refresh_token",
            })
            resp.raise_for_status()
            tokens = _tokens_from_response(resp.json())
            if not tokens.refresh_token:
                tokens.refresh_token = refresh_token
            return tokens

    async def revoke(self, access_token: str) -> None:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(self.revoke_url, data={"token": access_token})
            except httpx.RequestError as exc:
                _logger.warning("Anthropic OAuth revoke request failed: %s", exc)
                return
            if resp.is_error:
                _logger.warning("Anthropic OAuth revoke returned HTTP %s: %s", resp.status_code, (resp.text or "")[:200])

    async def list_models(self, access_token: str) -> list[ModelInfo]:
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
