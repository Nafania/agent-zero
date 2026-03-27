from flask import Response as FlaskResponse
from python.helpers.api import ApiHandler, Input, Output, Request
from python.helpers.oauth import get_oauth_provider
from python.helpers.connected_providers import ProviderPool
from python.helpers import dotenv
from python.api.oauth_authorize import _pending_states


class OAuthCallback(ApiHandler):
    async def process(self, input: Input, request: Request) -> Output:
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
                content_type="text/html",
                status=400,
            )

        provider_id = pending["provider_id"]
        provider = get_oauth_provider(provider_id)
        if not provider:
            return FlaskResponse(
                f"<html><body><h2>Unknown provider</h2><p>Provider '{provider_id}' is not supported.</p></body></html>",
                content_type="text/html",
                status=400,
            )
        cid = dotenv.get_dotenv_value(f"OAUTH_CLIENT_ID_{provider_id.upper()}") or ""
        cs = dotenv.get_dotenv_value(f"OAUTH_CLIENT_SECRET_{provider_id.upper()}") or ""

        tokens = await provider.exchange_code(
            code=code,
            client_id=cid,
            client_secret=cs,
            redirect_uri=pending["redirect_uri"],
            code_verifier=pending.get("code_verifier"),
        )
        pool = ProviderPool.get_instance()
        pool.store.save(provider_id, tokens)
        pool._model_cache.pop(provider_id, None)

        return FlaskResponse(
            "<html><body><h2>Connected!</h2><p>You can close this window.</p>"
            "<script>window.close()</script></body></html>",
            content_type="text/html",
        )

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET"]

    @classmethod
    def requires_csrf(cls) -> bool:
        return False
