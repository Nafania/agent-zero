from helpers.extension import Extension, extensible
from agent import Agent


class MainPrompt(Extension):

    async def execute(self, **kwargs):
        agent = self.agent
        system_prompt = kwargs.get("system_prompt", [])
        prompt = get_main_prompt(agent)
        system_prompt.append(prompt)


@extensible
def get_main_prompt(agent: Agent) -> str:
    return agent.read_prompt("agent.system.main.md")
