from helpers.extension import Extension, extensible
from agent import Agent


class SecretsPrompt(Extension):

    async def execute(self, **kwargs):
        agent = self.agent
        system_prompt = kwargs.get("system_prompt", [])
        prompt = get_secrets_prompt(agent)
        if prompt:
            system_prompt.append(prompt)


@extensible
def get_secrets_prompt(agent: Agent) -> str:
    try:
        from helpers.secrets import get_secrets_manager
        from helpers.settings import get_settings

        secrets_manager = get_secrets_manager(agent.context)
        secrets = secrets_manager.get_secrets_for_prompt()
        vars = get_settings()["variables"]
        return agent.read_prompt("agent.system.secrets.md", secrets=secrets, vars=vars)
    except Exception:
        return ""
