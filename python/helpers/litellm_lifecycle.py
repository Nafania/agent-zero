import asyncio
import atexit
import logging
from typing import Any

import httpx
import litellm


log = logging.getLogger("litellm_lifecycle")

_INIT_DONE = False
_SHUTDOWN_REGISTERED = False
_SHARED_ASYNC_CLIENT: httpx.AsyncClient | None = None
_SHARED_SYNC_CLIENT: httpx.Client | None = None
_FD_SAFE_LIMITS = httpx.Limits(
    max_connections=50,
    max_keepalive_connections=10,
    keepalive_expiry=30,
)
_CLIENT_TIMEOUT = httpx.Timeout(timeout=60.0, connect=10.0)


def _close_client(client: Any) -> None:
    if isinstance(client, httpx.Client):
        try:
            client.close()
        except Exception:
            pass
        return

    if isinstance(client, httpx.AsyncClient):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            try:
                asyncio.run(client.aclose())
            except Exception:
                pass
        else:
            try:
                loop.create_task(client.aclose())
            except Exception:
                pass


def _close_handler_value(value: Any) -> None:
    client = getattr(value, "client", value)
    _close_client(client)


def _patch_cache_eviction() -> None:
    cache = getattr(litellm, "in_memory_llm_clients_cache", None)
    if cache is None or getattr(cache, "_a0_fd_close_patch", False):
        return

    original_remove_key = cache._remove_key

    def _remove_key_with_close(key: str) -> None:
        value = cache.cache_dict.get(key)
        if value is not None:
            _close_handler_value(value)
        original_remove_key(key)

    cache._remove_key = _remove_key_with_close
    cache._a0_fd_close_patch = True


def _install_shared_clients() -> None:
    global _SHARED_ASYNC_CLIENT, _SHARED_SYNC_CLIENT
    async_client = httpx.AsyncClient(limits=_FD_SAFE_LIMITS, timeout=_CLIENT_TIMEOUT)
    sync_client = httpx.Client(limits=_FD_SAFE_LIMITS, timeout=_CLIENT_TIMEOUT)

    old_async = getattr(litellm, "aclient_session", None)
    old_sync = getattr(litellm, "client_session", None)
    _close_client(old_async)
    _close_client(old_sync)

    litellm.aclient_session = async_client
    litellm.client_session = sync_client

    for handler_name, client in (
        ("module_level_aclient", async_client),
        ("module_level_client", sync_client),
    ):
        handler = getattr(litellm, handler_name, None)
        if handler is not None and hasattr(handler, "client"):
            old = getattr(handler, "client", None)
            _close_client(old)
            handler.client = client

    _SHARED_ASYNC_CLIENT = async_client
    _SHARED_SYNC_CLIENT = sync_client


def shutdown() -> None:
    global _SHARED_ASYNC_CLIENT, _SHARED_SYNC_CLIENT
    if _SHARED_ASYNC_CLIENT is not None:
        _close_client(_SHARED_ASYNC_CLIENT)
        _SHARED_ASYNC_CLIENT = None
    if _SHARED_SYNC_CLIENT is not None:
        _close_client(_SHARED_SYNC_CLIENT)
        _SHARED_SYNC_CLIENT = None


def initialize() -> None:
    global _INIT_DONE, _SHUTDOWN_REGISTERED
    if _INIT_DONE:
        return

    _install_shared_clients()
    _patch_cache_eviction()
    if not _SHUTDOWN_REGISTERED:
        atexit.register(shutdown)
        _SHUTDOWN_REGISTERED = True
    _INIT_DONE = True
    log.info("LiteLLM client lifecycle initialized with shared httpx clients")
