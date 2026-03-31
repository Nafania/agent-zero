from helpers.extension import Extension
from agent import InterventionException


# NOTE: Active when handle_exception is refactored to delegate to extensions
# instead of the current inline re-raise pattern in agent.py.
class HandleInterventionException(Extension):
    async def execute(self, data: dict = {}, **kwargs):
        if not self.agent:
            return

        if not data.get("exception"):
            return

        if isinstance(data["exception"], InterventionException):
            data["exception"] = None
