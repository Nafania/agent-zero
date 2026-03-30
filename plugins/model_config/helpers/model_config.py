import models
from helpers import plugins, files
from helpers import yaml as yaml_helper


def get_config(agent=None, project_name=None, agent_profile=None) -> dict:
    return plugins.get_plugin_config(
        "model_config",
        agent=agent,
        project_name=project_name,
        agent_profile=agent_profile,
    ) or {}


def get_chat_model_config(agent=None) -> dict:
    cfg = get_config(agent)
    return cfg.get("chat_model", {})


def get_utility_model_config(agent=None) -> dict:
    cfg = get_config(agent)
    return cfg.get("utility_model", {})


def get_embedding_model_config(agent=None) -> dict:
    cfg = get_config(agent)
    return cfg.get("embedding_model", {})


def get_browser_model_config(agent=None) -> dict:
    cfg = get_config(agent)
    return cfg.get("browser_model", {})


def get_ctx_history(agent=None) -> float:
    cfg = get_chat_model_config(agent)
    return float(cfg.get("ctx_history", 0.7))


def get_ctx_input(agent=None) -> float:
    cfg = get_utility_model_config(agent)
    return float(cfg.get("ctx_input", 0.7))


def _normalize_kwargs(kwargs: dict) -> dict:
    result = {}
    for key, value in kwargs.items():
        if isinstance(value, str):
            try:
                result[key] = int(value)
            except ValueError:
                try:
                    result[key] = float(value)
                except ValueError:
                    result[key] = value
        else:
            result[key] = value
    return result


def build_model_config(cfg: dict, model_type: models.ModelType) -> models.ModelConfig:
    return models.ModelConfig(
        type=model_type,
        provider=cfg.get("provider", ""),
        name=cfg.get("name", ""),
        api_base=cfg.get("api_base", ""),
        ctx_length=int(cfg.get("ctx_length", 0)),
        vision=bool(cfg.get("vision", False)),
        limit_requests=int(cfg.get("rl_requests", 0)),
        limit_input=int(cfg.get("rl_input", 0)),
        limit_output=int(cfg.get("rl_output", 0)),
        kwargs=_normalize_kwargs(cfg.get("kwargs", {})),
    )


def build_chat_model(agent=None):
    cfg = get_chat_model_config(agent)
    mc = build_model_config(cfg, models.ModelType.CHAT)
    return models.get_chat_model(
        mc.provider, mc.name, model_config=mc, **mc.build_kwargs()
    )


def build_utility_model(agent=None):
    cfg = get_utility_model_config(agent)
    mc = build_model_config(cfg, models.ModelType.CHAT)
    return models.get_chat_model(
        mc.provider, mc.name, model_config=mc, **mc.build_kwargs()
    )


def build_embedding_model(agent=None):
    cfg = get_embedding_model_config(agent)
    mc = build_model_config(cfg, models.ModelType.EMBEDDING)
    return models.get_embedding_model(
        mc.provider, mc.name, model_config=mc, **mc.build_kwargs()
    )


def build_browser_model(agent=None):
    cfg = get_browser_model_config(agent)
    mc = build_model_config(cfg, models.ModelType.CHAT)
    return models.get_browser_model(
        mc.provider, mc.name, model_config=mc, **mc.build_kwargs()
    )


def get_embedding_model_config_object(agent=None) -> models.ModelConfig:
    cfg = get_embedding_model_config(agent)
    return build_model_config(cfg, models.ModelType.EMBEDDING)
