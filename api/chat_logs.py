from helpers.api import ApiHandler, Input, Output, Request, Response
from agent import AgentContext


class ChatLogs(ApiHandler):
    async def process(self, input: Input, request: Request) -> Output:
        context_id = input.get("context_id", "")
        if not context_id:
            raise Exception("No context_id provided")

        before = int(input.get("before", 0))
        limit = int(input.get("limit", 50))

        context = AgentContext.get(context_id)
        if not context:
            return {"logs": [], "has_more": False}

        return context.log.get_items_before(before, limit)
