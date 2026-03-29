# Agent Zero: OAuth Provider Framework & Per-Chat Model Switching

**Date:** 2026-03-26  
**Scope:** OAuth authentication framework, connected provider pool, per-chat model switching  
**Goal:** Allow users to authenticate with model providers via OAuth2 (alongside existing API keys), maintain a pool of connected providers, and switch chat models on-the-fly within a conversation.

---

## Final Product Decisions

1. **OAuth as alternative to API key** — each provider shows "Sign in" button alongside the API key field. Either method works; OAuth takes priority when both are present.
2. **Three providers at launch:** Google (enabled), OpenAI (enabled), Anthropic (code-complete but hidden in UI — blocked by Anthropic's third-party restriction, enable when they open access).
3. **User provides OAuth app credentials** — user registers their own OAuth app with each provider, enters `client_id` + `client_secret` in Agent Zero settings. Stored persistently in `usr/.env`.
4. **Dynamic redirect with manual code fallback** — OAuth callback URL derived from browser's `window.location.origin`. When redirect is unreachable (remote access, NAT), user can copy-paste the authorization code manually.
5. **Per-chat model switching** — only the chat model can be overridden per conversation. Utility, browser, and embedding models remain global.
6. **Dynamic model lists** — provider APIs queried for available models (cached 1 hour).

---

## Current-State Problems

- All providers authenticate via API keys only (`API_KEY_<PROVIDER>` in `usr/.env`). No OAuth support exists.
- Users with Google/OpenAI accounts cannot use their existing subscriptions without manually creating and managing API keys.
- Model selection is global — changing the chat model affects all conversations. No per-chat override exists.
- The model name is typed manually — no discovery of available models from the provider.

---

## Target Architecture

### A. OAuth Provider Framework

New module `helpers/oauth.py` with strategy pattern:

**Base class:**
- `OAuthProvider` ABC with `provider_id`, `authorize_url`, `token_url`, `scopes`, `supports_pkce`
- Methods: `get_authorization_url()`, `exchange_code()`, `refresh_token()`, `revoke()`, `list_models()`

**Concrete strategies:**
- `GoogleOAuth` — standard OAuth2 Authorization Code flow. Token URL: `https://oauth2.googleapis.com/token`. Models endpoint: `https://generativelanguage.googleapis.com/v1beta/models`. Scopes: `https://www.googleapis.com/auth/generative-language`.
- `OpenAIOAuth` — standard OAuth2 Authorization Code flow. Token URL: `https://auth.openai.com/oauth/token`. Models endpoint: `https://api.openai.com/v1/models`. Scopes: provider-defined (request at authorization time).
- `AnthropicOAuth` — OAuth2 with PKCE (S256). Authorization: `https://claude.ai/oauth/authorize`. Token: `https://console.anthropic.com/v1/oauth/token`. Models: `https://api.anthropic.com/v1/models`. Scopes: `user:inference user:profile`.

**Data types:**

```
OAuthTokens:
    access_token: str
    refresh_token: str | None
    expires_at: datetime
    token_type: str
    scope: str

ModelInfo:
    id: str               # "gpt-4o", "gemini-2.5-pro"
    name: str             # human-readable
    context_length: int
    supports_vision: bool
```

**Provider YAML extension.** `conf/model_providers.yaml` gains optional `oauth` block per provider:

```yaml
google:
  name: Google
  litellm_provider: gemini
  oauth:
    enabled: true
    strategy: google
openai:
  name: OpenAI
  litellm_provider: openai
  oauth:
    enabled: true
    strategy: openai
anthropic:
  name: Anthropic
  litellm_provider: anthropic
  oauth:
    enabled: false    # hidden in UI, code ready
    strategy: anthropic
```

Providers without an `oauth` block behave as before — API key only.

### B. Connected Provider Pool

New module `helpers/connected_providers.py`:

**`ConnectedProvider`** — represents a provider with either (or both) API key and OAuth credentials:
- `provider_id`, `auth_method` (api_key | oauth), `is_active`, `oauth_tokens`, `api_key`

**`ProviderPool`** — singleton managing all connected providers:
- `get_connected()` — list of providers with at least one valid credential
- `get_credential(provider_id)` — returns access_token or api_key (caller is agnostic to auth method)
- `is_connected(provider_id)` — boolean
- `disconnect(provider_id)` — revoke + remove tokens
- `list_models(provider_id)` — delegates to strategy or API key-based model list endpoint

**Credential resolution in `get_credential()`:**
1. If OAuth tokens exist and are valid → return access_token
2. If OAuth tokens exist but expired → attempt refresh → return new access_token
3. If refresh fails → mark disconnected, log warning → fall back to API key
4. If no OAuth → return API key (current behavior)

**Integration point:** `models.py` `get_api_key()` delegates to `ProviderPool.get_credential()`. All existing LiteLLM wiring continues unchanged — only the credential source is abstracted.

### C. Token Storage & Lifecycle

**Storage:** OAuth tokens persisted in `usr/oauth_tokens.json` — separate from `usr/.env` (API keys) and `usr/settings.json` (non-secret prefs). File protected by same filesystem permissions as `.env`.

**Client credentials** (`client_id`, `client_secret`) stored in `usr/.env` as:
- `OAUTH_CLIENT_ID_GOOGLE`, `OAUTH_CLIENT_SECRET_GOOGLE`
- `OAUTH_CLIENT_ID_OPENAI`, `OAUTH_CLIENT_SECRET_OPENAI`
- `OAUTH_CLIENT_ID_ANTHROPIC`, `OAUTH_CLIENT_SECRET_ANTHROPIC`

**Auto-refresh:** On each `get_credential()` call, if `expires_at` is within 5 minutes, trigger background refresh. If refresh fails — deactivate provider, log structured warning. If API key exists for same provider — transparent fallback.

**Token revocation on disconnect:** Call provider's revoke endpoint, then delete tokens from `oauth_tokens.json`.

### D. Per-Chat Model Switching

**Override structure:**

```
ChatModelOverride:
    chat_provider: str | None   # None = global default
    chat_model: str | None
```

Stored in chat metadata (existing `context.json`). Only the chat model is overridable — utility, browser, and embedding remain global settings.

**Application:** `initialize.py` checks for per-chat override before building `ModelConfig`. If override exists and the provider is connected, use it. If provider has disconnected since override was set — fallback to global default, notify user.

**Dynamic model list:** `ProviderPool.list_models(provider_id)` queries the provider's models API endpoint. Results cached in memory for 1 hour. Cache invalidated on connect/disconnect. Works for both OAuth and API-key providers. Model lists are filtered to chat-capable models only — each strategy defines a filter predicate (e.g., Google: `generateContent` method supported; OpenAI: model ID starts with `gpt-`, `o1-`, `o3-`, `chatgpt-`; Anthropic: model ID starts with `claude-`).

**UI: Model Picker dropdown in chat header:**
- Shows current model: "GPT-4o (OpenAI)"
- Groups available models by connected provider
- Only `is_connected == true` providers appear
- Displays context_length and vision support per model
- Selection saves override, next message uses new model

---

## API Endpoints

New file `api/oauth.py`:

### OAuth Flow
| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/oauth/providers` | List providers with OAuth support and connection status |
| `POST` | `/api/oauth/authorize` | Accept `{provider_id, client_id, client_secret, redirect_uri}` or `{..., flow: "manual"}`. Save client creds, generate state + PKCE, return `{authorization_url}`. State and PKCE verifier stored server-side in an in-memory dict keyed by state value (TTL 10 min). |
| `GET` | `/api/oauth/callback` | Redirect endpoint. Validate state, exchange code, persist tokens, return HTML success page |
| `POST` | `/api/oauth/exchange-code` | Manual code exchange for copy-paste fallback: `{provider_id, code}` |
| `POST` | `/api/oauth/disconnect` | Revoke + remove tokens for `{provider_id}` |
| `GET` | `/api/oauth/status/{provider_id}` | Detailed status: connected, expiry, scopes |

### Model List
| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/models/{provider_id}` | Dynamic model list from provider API (cached 1h) |

### Per-Chat Override
| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/chat/{chat_id}/model` | Set override: `{provider, model}` |
| `GET` | `/api/chat/{chat_id}/model` | Get current override or null |

CSRF/auth: same model as existing API handlers. State parameter validation on callback prevents CSRF on OAuth flow.

---

## Redirect Strategy

**Primary: dynamic redirect.** Frontend sends `window.location.origin + "/api/oauth/callback"` as `redirect_uri` in the authorize request. Works when user accesses Agent Zero UI directly (same host resolves for both browser and server).

**Fallback: manual code exchange.** When redirect fails (NAT, tunnel, provider rejects dynamic URI):
1. Frontend calls authorize with `{flow: "manual"}`
2. Backend returns authorization URL without redirect
3. User opens URL, authorizes, receives code on provider's page
4. User pastes code into Agent Zero UI
5. Frontend calls `/api/oauth/exchange-code` with the code

UI auto-detects which flow to use based on whether the callback was received within a timeout.

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| User denies consent | Callback receives `error=access_denied`. UI shows "Authorization cancelled". Provider stays disconnected. |
| Token refresh fails | Provider marked disconnected, warning logged. Fallback to API key if present. UI notification "Provider X disconnected, please re-authorize". |
| Provider API down during exchange | Retry 3x with backoff. All fail → error to user with "try again" option. |
| Invalid/expired state | Callback rejects request (CSRF). User must restart flow. |
| Disconnected provider in chat override | Fallback to global default. Notification shown in chat. |
| Model removed from provider | Model picker refreshes list. Override reset if model gone. |

---

## Component-by-Component Changes

### New Files

| File | Purpose |
|------|---------|
| `helpers/oauth.py` | `OAuthProvider` ABC + `GoogleOAuth`, `OpenAIOAuth`, `AnthropicOAuth` strategies |
| `helpers/connected_providers.py` | `ProviderPool` singleton, `ConnectedProvider`, credential resolution |
| `api/oauth.py` | REST endpoints for OAuth flow, model list, chat override |
| `webui/js/oauth.js` | Frontend OAuth flow logic, model picker |

### Modified Files

| File | Change |
|------|--------|
| `models.py` | `get_api_key()` delegates to `ProviderPool.get_credential()` |
| `initialize.py` | Apply per-chat model override from chat metadata |
| `helpers/settings.py` | OAuth client credentials as sensitive settings (load/save to `.env`) |
| `helpers/providers.py` | Parse `oauth` block from `model_providers.yaml` |
| `conf/model_providers.yaml` | Add `oauth` sections to google, openai, anthropic |
| `webui/components/settings/agent/agent.html` | OAuth connect/disconnect buttons per provider |
| Chat UI (header/sidebar) | Model picker dropdown |

### Runtime Files

| File | Purpose |
|------|---------|
| `usr/oauth_tokens.json` | Persisted OAuth tokens (access, refresh, expiry) |
| `usr/.env` | OAuth client credentials (`OAUTH_CLIENT_ID_*`, `OAUTH_CLIENT_SECRET_*`) |

---

## Test Plan

### 1. OAuth Provider Strategies (`tests/helpers/test_oauth.py`)
- URL generation with correct params (scopes, PKCE, state)
- Code exchange with mocked HTTP (success + error cases)
- Token refresh (success, expired refresh token, network error)
- Revocation
- Model list parsing from mocked API responses

### 2. Provider Pool (`tests/helpers/test_connected_providers.py`)
- Credential resolution: OAuth token → API key fallback
- Auto-refresh trigger when token near expiry
- Disconnect clears tokens and updates status
- `list_models` caching and invalidation
- Concurrent `get_credential()` calls don't race on refresh

### 3. API Endpoints (`tests/api/test_oauth.py`)
- `/authorize` generates valid URL and persists state
- `/callback` validates state, exchanges code, saves tokens
- `/callback` rejects invalid state (CSRF)
- `/exchange-code` works for manual flow
- `/disconnect` revokes and cleans up
- `/providers` returns correct status
- `/models/{provider}` returns cached list
- Auth/CSRF enforced on all endpoints

### 4. Per-Chat Override (`tests/api/test_chat_model_override.py`)
- Set and get override
- Override applied during agent initialization
- Fallback to global when provider disconnected
- Null override uses global default

### 5. Integration (`tests/integration/test_oauth_flow.py`, marker: `integration`)
- Full redirect flow with test provider sandbox (if available)
- Full copy-paste flow
- End-to-end: connect → list models → switch model in chat → send message

### 6. Settings Compatibility
- Existing settings without OAuth fields still load
- OAuth client credentials round-trip through settings API
- Credentials masked in API output

---

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Anthropic blocks third-party OAuth tokens | Code-complete but UI-hidden (`oauth.enabled: false`). Enable when restriction lifts. |
| Provider OAuth endpoints change | Adapter per provider — isolated blast radius. Structured error logging surfaces issues fast. |
| Dynamic redirect URI rejected by provider | Automatic fallback to manual copy-paste flow. UI detects and switches seamlessly. |
| Token file corruption | Atomic writes (write temp + rename). On parse error — treat as empty (all providers disconnected), log warning. |
| Concurrent refresh race | Lock per provider in `ProviderPool` — only one refresh in flight at a time. |
| Old chats reference disconnected provider | Fallback to global default with user notification. |

---

## Acceptance Criteria

- Google and OpenAI OAuth flows work end-to-end (redirect and copy-paste).
- Anthropic OAuth code exists, is tested with mocks, but hidden in UI.
- Connected providers show in model picker with dynamically fetched model lists.
- Per-chat model override works — switching model mid-conversation uses the new model for subsequent messages.
- `get_credential()` transparently returns OAuth token or API key — existing LiteLLM integration unchanged.
- All tokens and credentials persist across container restarts (`usr/` volume).
- Tests cover strategies, pool, API endpoints, overrides, and error paths.
