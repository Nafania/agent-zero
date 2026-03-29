from helpers.api import ApiHandler, Input, Output, Request
from helpers.connected_providers import ProviderPool


class OAuthDisconnect(ApiHandler):
    async def process(self, input: Input, request: Request) -> Output:
        provider_id = input.get("provider_id", "")
        ProviderPool.get_instance().disconnect(provider_id)
        return {"status": "disconnected", "provider_id": provider_id}
