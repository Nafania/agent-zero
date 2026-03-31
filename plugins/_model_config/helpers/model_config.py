import os
import models
from helpers import plugins, files
from helpers import yaml as yaml_helper
from helpers.providers import get_providers

PRESETS_FILE = "presets.yaml"
DEFAULT_PRESETS_FILE = "default_presets.yaml"
LOCAL_PROVIDERS = {"ollama", "lm_studio"}
LOCAL_EMBEDDING = {"huggingface"}


def _get_presets_path() -> str:
    return files.get_abs_path(files.USER_DIR, files.PLUGINS_DIR, "_model_config", PRESETS_FILE)


def _get_default_presets_path() -> str:
    plugin_dir = plugins.find_plugin_dir("_model_config")
    return files.get_abs_path(plugin_dir, DEFAULT_PRESETS_FILE) if plugin_dir else ""


def get_config(agent=None, project_name=None, agent_profile=None) -> dict:
    return plugins.get_plugin_config(
        "_model_config",
        agent=agent,
        project_name=project_name,
        agent_profile=agent_profile,
    ) or {}


def get_presets() -> list:
    path = _get_presets_path()
    if files.exists(path):
        data = yaml_helper.loads(files.read_file(path))
        if isinstance(data, list):
            return data
    default_path = _get_default_presets_path()
    if default_path and files.exists(default_path):
        data = yaml_helper.loads(files.read_file(default_path))
        if isinstance(data, list):
            return data
    return []


def save_presets(presets: list) -> None:
    path = _get_presets_path()
    files.write_file(path, yaml_helper.dumps(presets))


def reset_presets() -> list:
    path = _get_presets_path()
    if os.path.exists(path):
        os.remove(path)
    return get_presets()


def get_preset_by_name(name: str) -> dict | None:
    for p in get_presets():
        if p.get("name") == name:
            return p
    return None


def _resolve_override(agent) -> dict | None:
    if not agent:
        return None
    if not is_chat_override_allowed(agent):
        return None
    override = agent.context.get_data("chat_model_override")
    if not override:
        return None
    if "preset_name" in override:
        preset = get_preset_by_name(override["preset_name"])
        if not preset:
            return None
        return preset
    return override


def get_chat_model_config(agent=None) -> dict:
    override = _resolve_override(agent)
    if override:
        chat_cfg = override.get("chat", override)
        if chat_cfg.get("provider") or chat_cfg.get("name"):
            return chat_cfg
    cfg = get_config(agent)
    return cfg.get("chat_model", {})


def get_utility_model_config(agent=None) -> dict:
    override = _resolve_override(agent)
    if override:
        util_cfg = override.get("utility", {})
        if util_cfg.get("provider") or util_cfg.get("name"):
            return util_cfg
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


def is_chat_override_allowed(agent=None) -> bool:
    cfg = get_config(agent)
    return bool(cfg.get("allow_chat_override", False))


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
        limit_concurrent=int(cfg.get("rl_concurrent", 0)),
        kwargs=_normalize_kwargs(cfg.get("kwargs", {}) if isinstance(cfg.get("kwargs"), dict) else {}),
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


def get_chat_providers():
    return get_providers("chat")


def get_embedding_providers():
    return get_providers("embedding")


def has_provider_api_key(provider: str, configured_api_key: str = "") -> bool:
    configured_value = (configured_api_key or "").strip()
    if configured_value and configured_value != "None":
        return True
    api_key = models.get_api_key(provider.lower())
    return bool(api_key and api_key.strip() and api_key != "None")


def get_missing_api_key_providers(agent=None) -> list[dict]:
    cfg = get_config(agent)
    missing = []
    checks = [
        ("Chat Model", cfg.get("chat_model", {})),
        ("Utility Model", cfg.get("utility_model", {})),
        ("Embedding Model", cfg.get("embedding_model", {})),
    ]
    for label, model_cfg in checks:
        provider = model_cfg.get("provider", "")
        if not provider:
            continue
        provider_lower = provider.lower()
        if provider_lower in LOCAL_PROVIDERS:
            continue
        if label == "Embedding Model" and provider_lower in LOCAL_EMBEDDING:
            continue
        if not has_provider_api_key(provider_lower, model_cfg.get("api_key", "")):
            missing.append({"model_type": label, "provider": provider})
    return missing
