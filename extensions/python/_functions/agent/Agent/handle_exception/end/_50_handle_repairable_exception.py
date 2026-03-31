from helpers.extension import Extension
from helpers.errors import RepairableException
from helpers import errors, extension
from helpers.print_style import PrintStyle


# NOTE: Active when handle_exception is refactored to delegate to extensions
# instead of the current inline re-raise pattern in agent.py.
class HandleRepairableException(Extension):
    async def execute(self, data: dict | None = None, **kwargs):
        if data is None:
            data = {}
        if not self.agent:
            return

        if not data.get("exception"):
            return

        if isinstance(data["exception"], RepairableException):
            msg = {"message": errors.format_error(data["exception"])}
            await extension.call_extensions_async("error_format", agent=self.agent, msg=msg)
            wmsg = self.agent.hist_add_warning(msg["message"])
            PrintStyle(font_color="red", padding=True).print(msg["message"])
            self.agent.context.log.log(type="warning", content=msg["message"], id=wmsg.id)
            data["exception"] = None
