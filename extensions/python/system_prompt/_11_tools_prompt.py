from helpers.extension import Extension, extensible
from agent import Agent


class ToolsPrompt(Extension):

    async def execute(self, **kwargs):
        agent = self.agent
        system_prompt = kwargs.get("system_prompt", [])
        prompt = get_tools_prompt(agent)
        system_prompt.append(prompt)


@extensible
def get_tools_prompt(agent: Agent) -> str:
    prompt = agent.read_prompt("agent.system.tools.md")
    from plugins.model_config.helpers.model_config import get_chat_model_config

    if get_chat_model_config(agent).get("vision", False):
        prompt += "\n\n" + agent.read_prompt("agent.system.tools_vision.md")
    return prompt
