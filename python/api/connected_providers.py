from python.helpers.api import ApiHandler, Input, Output, Request
from python.helpers.connected_providers import ProviderPool


class ConnectedProviders(ApiHandler):
    async def process(self, input: Input, request: Request) -> Output:
        pool = ProviderPool.get_instance()
        connected = pool.get_connected()
        return {
            "providers": [
                {
                    "provider_id": cp.provider_id,
                    "auth_method": cp.auth_method,
                    "is_active": cp.is_active,
                }
                for cp in connected
            ],
        }

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET", "POST"]
