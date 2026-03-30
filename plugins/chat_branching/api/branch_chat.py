from helpers.api import ApiHandler, Request, Response as FlaskResponse
from agent import AgentContext
from helpers import persist_chat


class BranchChat(ApiHandler):
    """Create a new chat by branching from an existing message."""

    async def process(self, input: dict, request: Request) -> dict | FlaskResponse:
        context_id = input.get("context_id", "")
        message_index = input.get("message_index")

        if not context_id:
            return FlaskResponse(status=400, response="Missing context_id")
        if message_index is None:
            return FlaskResponse(status=400, response="Missing message_index")

        ctx = AgentContext.use(context_id)
        if not ctx:
            return FlaskResponse(status=404, response="Context not found")

        try:
            from initialize import initialize_agent

            new_ctx = AgentContext(config=initialize_agent(), set_current=False)
            agent = ctx.agent0

            if agent and new_ctx.agent0:
                messages = agent.history.output()
                truncated = messages[: message_index + 1]
                new_agent = new_ctx.agent0
                new_agent.history.current.messages.clear()
                for msg in truncated:
                    new_agent.hist_add_message(msg.ai, content=msg.content)
                persist_chat.save_tmp_chat(new_ctx)
            else:
                truncated = []

            return {
                "ok": True,
                "new_context_id": new_ctx.id,
                "messages_copied": len(truncated),
            }
        except Exception as e:
            return FlaskResponse(status=500, response=str(e))
