from helpers.api import ApiHandler, Input, Output, Request
from helpers.oauth import get_oauth_provider
from helpers.connected_providers import ProviderPool
from helpers import dotenv
from api.oauth_authorize import _pending_states


class OAuthExchange(ApiHandler):
    async def process(self, input: Input, request: Request) -> Output:
        provider_id = input.get("provider_id", "")
        code = input.get("code", "")
        state = input.get("state", "")

        pending = _pending_states.pop(state, None)
        if not pending:
            return {"error": "Invalid or expired state"}

        provider = get_oauth_provider(provider_id)
        if not provider:
            return {"error": f"Unknown provider: {provider_id}"}

        cid = dotenv.get_dotenv_value(f"OAUTH_CLIENT_ID_{provider_id.upper()}") or ""
        cs = dotenv.get_dotenv_value(f"OAUTH_CLIENT_SECRET_{provider_id.upper()}") or ""

        tokens = await provider.exchange_code(
            code=code,
            client_id=cid,
            client_secret=cs,
            redirect_uri=pending.get("redirect_uri", ""),
            code_verifier=pending.get("code_verifier"),
        )
        pool = ProviderPool.get_instance()
        pool.store.save(provider_id, tokens)
        pool._model_cache.pop(provider_id, None)

        return {"status": "connected", "provider_id": provider_id}
