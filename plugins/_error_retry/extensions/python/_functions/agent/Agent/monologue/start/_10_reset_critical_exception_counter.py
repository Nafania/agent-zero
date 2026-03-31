from helpers.extension import Extension
from plugins._error_retry.constants import DATA_NAME_COUNTER


class ResetCriticalExceptionCounter(Extension):
    async def execute(self, data: dict | None = None, **kwargs):
        if data is None:
            data = {}
        if not self.agent:
            return

        self.agent.set_data(DATA_NAME_COUNTER, 0)
