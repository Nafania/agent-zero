from python.helpers.api import ApiHandler, Input, Output, Request
from python.helpers.providers import get_oauth_providers
from python.helpers.connected_providers import ProviderPool


class OAuthProviders(ApiHandler):
    async def process(self, input: Input, request: Request) -> Output:
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
