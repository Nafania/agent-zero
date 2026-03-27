import { createStore } from "/js/AlpineStore.js";

const model = {
  providers: [],
  _pendingState: null,

  async init() {
    await this.loadProviders();
  },

  async loadProviders() {
    try {
      const resp = await fetch("/oauth_providers");
      const data = await resp.json();
      this.providers = data.providers.map((p) => ({
        ...p,
        _client_id: "",
        _client_secret: "",
        _manualFlow: false,
        _manualCode: "",
      }));
    } catch (e) {
      console.error("Failed to load OAuth providers:", e);
    }
  },

  async connect(provider) {
    const redirectUri = window.location.origin + "/oauth_callback";
    try {
      const resp = await fetch("/oauth_authorize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider_id: provider.provider_id,
          client_id: provider._client_id,
          client_secret: provider._client_secret,
          redirect_uri: redirectUri,
          flow: "redirect",
        }),
      });
      const data = await resp.json();
      if (data.authorization_url) {
        this._pendingState = data.state;
        provider._manualFlow = false;
        provider._manualCode = "";

        const popup = window.open(data.authorization_url, "oauth", "width=600,height=700");
        let elapsed = 0;
        const timer = setInterval(() => {
          elapsed += 500;
          if (popup && popup.closed) {
            clearInterval(timer);
            this._pendingState = null;
            this.loadProviders();
          }
          if (elapsed >= 5000 && popup && !popup.closed) {
            provider._manualFlow = true;
          }
        }, 500);
      }
    } catch (e) {
      console.error("OAuth connect failed:", e);
    }
  },

  async submitManualCode(provider) {
    if (!provider._manualCode || !this._pendingState) return;
    try {
      const resp = await fetch("/oauth_exchange", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider_id: provider.provider_id,
          code: provider._manualCode,
          state: this._pendingState,
        }),
      });
      const data = await resp.json();
      if (data.status === "connected") {
        this._pendingState = null;
        provider._manualFlow = false;
        await this.loadProviders();
      }
    } catch (e) {
      console.error("Manual code exchange failed:", e);
    }
  },

  async disconnect(providerId) {
    try {
      await fetch("/oauth_disconnect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider_id: providerId }),
      });
      await this.loadProviders();
    } catch (e) {
      console.error("OAuth disconnect failed:", e);
    }
  },
};

const store = createStore("oauth", model);

export { store };
