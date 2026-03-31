from helpers.extension import Extension, extensible
from helpers import skills
from agent import Agent


class SkillsPrompt(Extension):

    async def execute(self, **kwargs):
        agent = self.agent
        system_prompt = kwargs.get("system_prompt", [])
        prompt = get_skills_prompt(agent)
        if prompt:
            system_prompt.append(prompt)


@extensible
def get_skills_prompt(agent: Agent) -> str:
    available = skills.list_skills(agent=agent)
    result = []
    for skill in available:
        name = skill.name.strip().replace("\n", " ")[:100]
        descr = skill.description.replace("\n", " ")[:500]
        result.append(f"**{name}** {descr}")

    if result:
        return agent.read_prompt("agent.system.skills.md", skills="\n".join(result))
    return ""
