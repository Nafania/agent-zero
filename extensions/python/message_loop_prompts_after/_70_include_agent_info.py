from helpers.extension import Extension
from agent import Agent, LoopData


class IncludeAgentInfo(Extension):
    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):

        from plugins._model_config.helpers.model_config import get_chat_model_config
        chat_cfg = get_chat_model_config(self.agent)
        max_depth = getattr(self.agent.config, "max_agent_depth", 5) or 5
        remaining = max(0, max_depth - self.agent.number - 1)
        is_sub = self.agent.get_data(Agent.DATA_NAME_SUPERIOR) is not None
        agent_info_prompt = self.agent.read_prompt(
            "agent.extras.agent_info.md",
            number=self.agent.number,
            profile=self.agent.config.profile or "Default",
            llm=chat_cfg.get("provider", "") + "/" + chat_cfg.get("name", ""),
            max_depth=max_depth,
            remaining_depth=remaining,
            is_subordinate=is_sub,
        )

        loop_data.extras_temporary["agent_info"] = agent_info_prompt
