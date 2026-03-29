import secrets
import time
from helpers.api import ApiHandler, Input, Output, Request
from helpers.oauth import get_oauth_provider
from helpers import dotenv

_pending_states: dict[str, dict] = {}
_STATE_TTL = 600


def _cleanup_expired():
    now = time.time()
    expired = [k for k, v in _pending_states.items() if now - v["created"] > _STATE_TTL]
    for k in expired:
        del _pending_states[k]


class OAuthAuthorize(ApiHandler):
    async def process(self, input: Input, request: Request) -> Output:
        _cleanup_expired()

        provider_id = input.get("provider_id", "")
        client_id = input.get("client_id", "")
        client_secret = input.get("client_secret", "")
        redirect_uri = input.get("redirect_uri", "")
        flow = input.get("flow", "redirect")

        provider = get_oauth_provider(provider_id)
        if not provider:
            return {"error": f"Unknown provider: {provider_id}"}

        if client_id:
            dotenv.save_dotenv_value(f"OAUTH_CLIENT_ID_{provider_id.upper()}", client_id)
        if client_secret:
            dotenv.save_dotenv_value(f"OAUTH_CLIENT_SECRET_{provider_id.upper()}", client_secret)

        state = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(43) if provider.supports_pkce else None

        _pending_states[state] = {
            "provider_id": provider_id,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
            "flow": flow,
            "created": time.time(),
        }

        auth_url = provider.get_authorization_url(
            client_id=client_id,
            redirect_uri=redirect_uri if flow == "redirect" else "",
            state=state,
            code_verifier=code_verifier,
        )

        return {"authorization_url": auth_url, "state": state, "flow": flow}
