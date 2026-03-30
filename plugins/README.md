# Agent Zero Plugins

Built-in plugins that extend Agent Zero's functionality. Each plugin is a self-contained directory with a `plugin.yaml` manifest.

## Directory Structure

```
plugins/<name>/
  plugin.yaml              # manifest (required)
  default_config.yaml      # default configuration
  hooks.py                 # lifecycle hooks (uninstall, config, etc.)
  tools/                   # tool .py files
  extensions/python/<hook>/ # python extension hooks
  extensions/webui/<hook>/  # webui extension hooks (HTML/JS)
  helpers/                 # plugin-specific helper modules
  api/                     # API handlers
  prompts/                 # prompt templates
  webui/                   # UI components (main.html, config.html)
  agents/                  # agent profiles
```

## Custom Plugins

User-installed plugins go to `usr/plugins/`. They take priority over built-in plugins with the same name.
