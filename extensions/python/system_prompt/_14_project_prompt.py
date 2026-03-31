from helpers.extension import Extension, extensible
from helpers import projects
from agent import Agent


class ProjectPrompt(Extension):

    async def execute(self, **kwargs):
        agent = self.agent
        system_prompt = kwargs.get("system_prompt", [])
        prompt = get_project_prompt(agent)
        if prompt:
            system_prompt.append(prompt)


@extensible
def get_project_prompt(agent: Agent) -> str:
    result = agent.read_prompt("agent.system.projects.main.md")
    project_name = agent.context.get_data(projects.CONTEXT_DATA_KEY_PROJECT)
    if project_name:
        project_vars = projects.build_system_prompt_vars(project_name)
        result += "\n\n" + agent.read_prompt(
            "agent.system.projects.active.md", **project_vars
        )
    else:
        result += "\n\n" + agent.read_prompt("agent.system.projects.inactive.md")
    return result
