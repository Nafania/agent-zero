import asyncio
import uuid

from helpers.extension import Extension
from helpers.errors import RepairableException
from helpers import errors, plugins
from helpers.print_style import PrintStyle
from agent import HandledException

from plugins.error_retry.constants import DATA_NAME_COUNTER


# NOTE: This extension becomes active when handle_exception is refactored to be the
# central exception handler, replacing the inline handle_critical_exception /
# retry_critical_exception code path in agent.py monologue(). Until then, the fork's
# handle_exception() simply re-raises, so this code path is not reached in production.
class RetryCriticalException(Extension):
    async def execute(self, data: dict | None = None, **kwargs):
        if data is None:
            data = {}
        if not self.agent:
            return

        exception = data.get("exception")
        if not exception:
            self.agent.set_data(DATA_NAME_COUNTER, 0)
            return

        if isinstance(exception, (HandledException, RepairableException)):
            self.agent.set_data(DATA_NAME_COUNTER, 0)
            return

        config = plugins.get_plugin_config("error_retry", agent=self.agent) or {}

        if not config.get("retry_on_critical", True):
            return

        max_retries = config.get("max_retries", 3)
        delay = config.get("retry_delay", 3)

        counter = self.agent.get_data(DATA_NAME_COUNTER) or 0
        if counter >= max_retries:
            return

        self.agent.set_data(DATA_NAME_COUNTER, counter + 1)

        error_message = errors.format_error(exception)
        msg_id = str(uuid.uuid4())
        self.agent.context.log.log(
            type="warning",
            heading="Critical error occurred, retrying...",
            content=error_message,
            id=msg_id,
        )
        PrintStyle(font_color="orange", padding=True).print(
            "Critical error occurred, retrying..."
        )
        await asyncio.sleep(delay)
        await self.agent.handle_intervention()
        agent_facing_error = self.agent.read_prompt(
            "fw.msg_critical_error.md", error_message=error_message
        )
        self.agent.hist_add_warning(message=agent_facing_error, id=msg_id)
        PrintStyle(font_color="orange", padding=True).print(agent_facing_error)

        data["exception"] = None
