import { createStore } from "/js/AlpineStore.js";

const model = {
  models: {},
  currentOverride: null,
  chatId: null,
  open: false,
  loading: false,

  init() {
    this.loadModels();
  },

  async toggle() {
    this.open = !this.open;
    if (this.open) {
      const chats = globalThis.Alpine?.store("chats");
      const chatId = chats?.selected;
      if (chatId && chatId !== this.chatId) {
        await this.loadOverride(chatId);
      }
    }
  },

  async loadModels() {
    this.loading = true;
    try {
      const resp = await fetch("/connected_providers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = await resp.json();
      const providers = (data.providers || []).filter((p) => p.is_active);

      const modelPromises = providers.map(async (p) => {
        try {
          const mResp = await fetch("/provider_models", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ provider_id: p.provider_id }),
          });
          const mData = await mResp.json();
          return { providerId: p.provider_id, models: mData.models || [] };
        } catch (e) {
          console.error(`Failed to load models for ${p.provider_id}:`, e);
          return { providerId: p.provider_id, models: [] };
        }
      });

      const results = await Promise.all(modelPromises);
      const newModels = {};
      for (const r of results) {
        if (r.models.length > 0) {
          newModels[r.providerId] = r.models;
        }
      }
      this.models = newModels;
    } catch (e) {
      console.error("Failed to load connected providers:", e);
    } finally {
      this.loading = false;
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

  async resetToDefault() {
    if (!this.chatId) return;
    try {
      await fetch("/chat_model_override", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_id: this.chatId, reset: true }),
      });
      this.currentOverride = null;
      this.open = false;
    } catch (e) {
      console.error("Failed to reset model override:", e);
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
