import asyncio
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from python.helpers.oauth import OAuthProvider, OAuthTokens, ModelInfo, get_oauth_provider
from python.helpers.oauth_store import OAuthTokenStore

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
        if token_store_path:
            path = token_store_path
        else:
            from python.helpers import files
            path = files.get_abs_path(_DEFAULT_TOKEN_PATH)
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
            try:
                refreshed = self._try_sync_refresh(provider_id, tokens)
                if refreshed:
                    return refreshed.access_token
            except Exception as e:
                logger.warning("OAuth refresh failed for %s: %s", provider_id, e)
            return tokens.access_token

        api_key = _get_api_key(provider_id)
        return api_key

    def _try_sync_refresh(
        self,
        provider_id: str,
        tokens: OAuthTokens,
    ) -> Optional[OAuthTokens]:
        if not tokens.refresh_token:
            return None
        strategy = get_oauth_provider(provider_id)
        if not strategy:
            return None
        cid, cs = _get_oauth_client_creds(provider_id)
        if not cid or not cs:
            return None

        with self._refresh_lock:
            current = self.store.load(provider_id)
            if current and current.expires_at > datetime.now(timezone.utc) + _REFRESH_MARGIN:
                return current

            try:
                refreshed = self._run_async(
                    strategy.refresh_token(tokens.refresh_token, cid, cs)
                )
                self.store.save(provider_id, refreshed)
                logger.info("OAuth token refreshed for %s", provider_id)
                return refreshed
            except Exception as e:
                logger.warning("Failed to refresh OAuth token for %s: %s", provider_id, e)
                return None

    @staticmethod
    def _run_async(coro):
        """Run an async coroutine from sync code, safe when called inside a running event loop."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result(timeout=30)

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
                    self._run_async(strategy.revoke(tokens.access_token))
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

        cred = self.get_credential(provider_id)
        if not cred or cred in ("None", "NA"):
            return []

        strategy = get_oauth_provider(provider_id)
        if strategy:
            try:
                models = await strategy.list_models(cred)
                self._model_cache[provider_id] = (datetime.now(timezone.utc), models)
                return models
            except Exception as e:
                logger.warning("Failed to fetch models for %s via OAuth: %s", provider_id, e)
                if cached:
                    return cached[1]
                return []

        models = await _list_models_via_api(provider_id, cred)
        if models:
            self._model_cache[provider_id] = (datetime.now(timezone.utc), models)
        elif cached:
            return cached[1]
        return models


_KNOWN_API_BASES: dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "mistral": "https://api.mistral.ai/v1",
    "xai": "https://api.x.ai/v1",
}


def _resolve_api_base(provider_id: str) -> str:
    """Derive API base URL from providers.yaml config, falling back to known defaults."""
    from python.helpers.providers import get_provider_config

    config = get_provider_config("chat", provider_id)
    if not config:
        return _KNOWN_API_BASES.get(provider_id, "")

    kwargs = config.get("kwargs", {}) or {}
    api_base = kwargs.get("api_base", "")
    if api_base:
        return api_base

    litellm_provider = config.get("litellm_provider", "")
    return _KNOWN_API_BASES.get(litellm_provider) or _KNOWN_API_BASES.get(provider_id, "")


async def _list_models_via_api(provider_id: str, api_key: str) -> list[ModelInfo]:
    """List models from a provider using its OpenAI-compatible /models endpoint."""
    import httpx

    api_base = _resolve_api_base(provider_id)
    if not api_base:
        return []

    models_url = f"{api_base.rstrip('/')}/models"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(models_url, headers={"Authorization": f"Bearer {api_key}"})
            if resp.status_code != 200:
                logger.warning("Models API returned %d for %s", resp.status_code, provider_id)
                return []
            data = resp.json()
    except Exception as e:
        logger.warning("Failed to list models via API for %s: %s", provider_id, e)
        return []

    result: list[ModelInfo] = []
    items = data.get("data", []) if isinstance(data, dict) else []
    for m in items:
        mid = m.get("id", "")
        if not mid:
            continue
        name = m.get("name") or mid
        ctx = m.get("context_length") or m.get("context_window") or 0
        # Vision detection relies on OpenRouter's architecture.modality field.
        # Other providers (OpenAI, Groq, Mistral, etc.) don't expose this,
        # so supports_vision will be False for them.
        vision = False
        arch = m.get("architecture", {})
        if isinstance(arch, dict):
            modality = arch.get("modality", "")
            if "image" in modality:
                vision = True
        result.append(ModelInfo(id=mid, name=name, context_length=ctx, supports_vision=vision))

    result.sort(key=lambda x: x.name)
    return result
