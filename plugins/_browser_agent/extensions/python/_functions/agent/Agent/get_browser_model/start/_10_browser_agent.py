from helpers.extension import Extension

# TODO: Upstream uses build_browser_model_for_agent() from browser_llm helper
# to wrap the chat model with BrowserCompatibleChatWrapper. In this fork,
# model_config plugin already handles get_browser_model via its own extension,
# and browser compatibility patches are applied separately in browser_use.py.
# This extension is a placeholder for future alignment with upstream.


class BrowserModelProvider(Extension):
    def execute(self, data: dict | None = None, **kwargs):
        pass
