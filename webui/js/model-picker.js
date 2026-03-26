import { createStore } from "/js/AlpineStore.js";
import { store as oauthStore } from "/js/oauth.js";

const model = {
  models: {},
  currentOverride: null,
  chatId: null,
  open: false,

  async loadModels() {
    if (!oauthStore || !oauthStore.providers) return;

    for (const p of oauthStore.providers.filter((p) => p.connected)) {
      try {
        const resp = await fetch("/provider_models", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ provider_id: p.provider_id }),
        });
        const data = await resp.json();
        this.models[p.provider_id] = data.models;
      } catch (e) {
        console.error(`Failed to load models for ${p.provider_id}:`, e);
      }
    }
  },

  async loadOverride(chatId) {
    this.chatId = chatId;
    try {
      const resp = await fetch("/chat_model_override", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_id: chatId }),
      });
      const data = await resp.json();
      this.currentOverride = data.override;
    } catch (e) {
      this.currentOverride = null;
    }
  },

  async selectModel(providerId, modelId) {
    if (!this.chatId) return;
    try {
      await fetch("/chat_model_override", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          chat_id: this.chatId,
          provider: providerId,
          model: modelId,
        }),
      });
      this.currentOverride = { provider: providerId, model: modelId };
      this.open = false;
    } catch (e) {
      console.error("Failed to set model override:", e);
    }
  },

  get currentLabel() {
    if (this.currentOverride) {
      return `${this.currentOverride.model} (${this.currentOverride.provider})`;
    }
    return "Default model";
  },
};

const store = createStore("modelPicker", model);

export { store };
