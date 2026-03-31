from helpers.extension import Extension

DATA_NAME_COUNTER = "_plugin.error_retry.critical_exception_counter"


class ResetCriticalExceptionCounter(Extension):
    async def execute(self, data: dict = {}, **kwargs):
        if not self.agent:
            return

        self.agent.set_data(DATA_NAME_COUNTER, 0)
