from python.helpers.api import ApiHandler, Input, Output, Request
from python.helpers.connected_providers import ProviderPool


class OAuthStatus(ApiHandler):
    async def process(self, input: Input, request: Request) -> Output:
        provider_id = input.get("provider_id", "")
        pool = ProviderPool.get_instance()
        tokens = pool.store.load(provider_id)
        return {
            "provider_id": provider_id,
            "connected": tokens is not None,
            "expires_at": tokens.expires_at.isoformat() if tokens else None,
            "scope": tokens.scope if tokens else None,
        }
