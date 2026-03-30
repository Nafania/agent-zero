from helpers.extension import Extension


class ChatModelOverrideHook(Extension):
    """Apply per-chat model override if one is saved for the current context."""

    def execute(self, data: dict = {}, **kwargs):
        if not self.agent or not self.agent.context:
            return

        chat_id = getattr(self.agent.context, "id", None)
        if not chat_id:
            return

        from api.chat_model_override import _load_override
        override = _load_override(chat_id)
        if not override:
            return

        provider = override.get("provider", "")
        model_name = override.get("model", "")
        if not provider or not model_name:
            return

        from helpers.connected_providers import ProviderPool
        pool = ProviderPool.get_instance()
        if not pool.is_connected(provider):
            return

        import models
        from plugins.model_config.helpers.model_config import get_chat_model_config
        cfg = get_chat_model_config(self.agent)

        from helpers.providers import get_provider_config
        provider_cfg = get_provider_config("chat", provider) or {}
        api_base = (provider_cfg.get("kwargs") or {}).get("api_base", "") or ""

        mc = models.ModelConfig(
            type=models.ModelType.CHAT,
            provider=provider,
            name=model_name,
            api_base=api_base,
            ctx_length=int(cfg.get("ctx_length", 128000)),
            vision=bool(cfg.get("vision", True)),
            limit_requests=int(cfg.get("rl_requests", 0)),
            limit_input=int(cfg.get("rl_input", 0)),
            limit_output=int(cfg.get("rl_output", 0)),
            kwargs=cfg.get("kwargs", {}),
        )
        data["result"] = models.get_chat_model(
            mc.provider, mc.name, model_config=mc, **mc.build_kwargs()
        )
