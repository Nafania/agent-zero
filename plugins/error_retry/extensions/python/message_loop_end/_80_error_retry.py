from helpers.extension import Extension
from helpers.print_style import PrintStyle


class ErrorRetry(Extension):
    """Retry the message loop if a critical exception occurred."""

    def execute(self, **kwargs):
        agent = self.agent
        if agent is None:
            return

        from helpers import plugins
        config = plugins.get_plugin_config("error_retry", agent=agent) or {}
        max_retries = config.get("max_retries", 3)
        retry_on_critical = config.get("retry_on_critical", True)

        if not retry_on_critical:
            return

        last_exception = kwargs.get("exception")
        if last_exception is None:
            return

        retry_count = getattr(agent, "_error_retry_count", 0)
        if retry_count >= max_retries:
            PrintStyle.warning(f"Error retry limit ({max_retries}) reached, not retrying")
            return

        agent._error_retry_count = retry_count + 1
        PrintStyle.warning(
            f"Critical exception detected, retrying ({agent._error_retry_count}/{max_retries})"
        )
