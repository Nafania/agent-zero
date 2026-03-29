import json

from helpers.api import ApiHandler, Request, Response
from helpers import plugins, files


class Plugins(ApiHandler):
    """Plugin management API: list, toggle, get/save config, uninstall."""

    async def process(self, input: dict, request: Request) -> dict | Response:
        action = input.get("action", "list")

        if action == "list":
            custom = input.get("custom", True)
            builtin = input.get("builtin", True)
            items = plugins.get_enhanced_plugins_list(custom=custom, builtin=builtin)
            return {"ok": True, "plugins": [item.model_dump() for item in items]}

        if action == "get_config":
            plugin_name = input.get("plugin_name", "")
            project_name = input.get("project_name", "")
            agent_profile = input.get("agent_profile", "")
            if not plugin_name:
                return Response(status=400, response="Missing plugin_name")

            result = plugins.find_plugin_assets(
                plugins.CONFIG_FILE_NAME,
                plugin_name=plugin_name,
                project_name=project_name,
                agent_profile=agent_profile,
                only_first=True,
            )
            if result:
                entry = result[0]
                path = entry.get("path", "")
                settings = files.read_file_json(path) if path else {}
                loaded_project_name = entry.get("project_name", "")
                loaded_agent_profile = entry.get("agent_profile", "")
            else:
                settings = plugins.get_plugin_config(plugin_name, agent=None) or {}
                plugin_dir = plugins.find_plugin_dir(plugin_name)
                default_path = (
                    files.get_abs_path(plugin_dir, plugins.CONFIG_DEFAULT_FILE_NAME)
                    if plugin_dir
                    else ""
                )
                path = default_path if default_path and files.exists(default_path) else ""
                loaded_project_name = ""
                loaded_agent_profile = ""

            return {
                "ok": True,
                "loaded_path": path,
                "loaded_project_name": loaded_project_name,
                "loaded_agent_profile": loaded_agent_profile,
                "data": settings,
            }

        if action == "save_config":
            plugin_name = input.get("plugin_name", "")
            project_name = input.get("project_name", "")
            agent_profile = input.get("agent_profile", "")
            settings = input.get("settings", {})
            if not plugin_name:
                return Response(status=400, response="Missing plugin_name")
            plugins.save_plugin_config(plugin_name, project_name, agent_profile, settings)
            return {"ok": True}

        if action == "get_toggle_status":
            plugin_name = input.get("plugin_name", "")
            if not plugin_name:
                return Response(status=400, response="Missing plugin_name")
            meta = plugins.get_plugin_meta(plugin_name)
            if not meta:
                return Response(status=404, response="Plugin not found")
            state = plugins.get_toggle_state(plugin_name)
            return {"ok": True, "status": state}

        if action == "toggle":
            plugin_name = input.get("plugin_name", "")
            enabled = input.get("enabled", True)
            project_name = input.get("project_name", "")
            agent_profile = input.get("agent_profile", "")
            clear_overrides = input.get("clear_overrides", False)
            if not plugin_name:
                return Response(status=400, response="Missing plugin_name")
            plugins.toggle_plugin(
                plugin_name, enabled, project_name, agent_profile, clear_overrides
            )
            return {"ok": True}

        if action == "uninstall":
            plugin_name = input.get("plugin_name", "")
            if not plugin_name:
                return Response(status=400, response="Missing plugin_name")
            try:
                plugins.uninstall_plugin(plugin_name)
                return {"ok": True}
            except (FileNotFoundError, ValueError) as e:
                return Response(status=400, response=str(e))

        if action == "get_default_config":
            plugin_name = input.get("plugin_name", "")
            if not plugin_name:
                return Response(status=400, response="Missing plugin_name")
            config = plugins.get_default_plugin_config(plugin_name)
            return {"ok": True, "data": config}

        return Response(status=400, response=f"Unknown action: {action}")
