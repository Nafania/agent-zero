from python.helpers.api import ApiHandler, Input, Output, Request, Response
from agent import AgentContext


class ChatLogs(ApiHandler):
    async def process(self, input: Input, request: Request) -> Output:
        context_id = input.get("context_id", "")
        if not context_id:
            raise Exception("No context_id provided")

        before = int(input.get("before", 0))
        limit = int(input.get("limit", 50))
        limit = max(1, min(limit, 200))

        context = AgentContext.get(context_id)
        if not context:
            return {"logs": [], "has_more": False}

        log = context.log
        with log._lock:
            all_logs = list(log.logs)

        if before <= 0:
            before = len(all_logs)

        start_idx = max(0, before - limit)
        items = all_logs[start_idx:before]
        has_more = start_idx > 0

        return {
            "logs": [item.output() for item in items],
            "has_more": has_more,
        }
