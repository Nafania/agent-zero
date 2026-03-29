from helpers.api import ApiHandler, Input, Output, Request
from helpers.connected_providers import ProviderPool


class ProviderModels(ApiHandler):
    async def process(self, input: Input, request: Request) -> Output:
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
