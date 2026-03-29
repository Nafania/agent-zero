from helpers.extension import Extension
from helpers import skills
from agent import LoopData


class SkillsCatalogPrompt(Extension):
    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        extras = loop_data.extras_persistent

        all_skills = skills.list_skills(agent=self.agent, include_content=False)
        if not all_skills:
            return

        lines = []
        for s in sorted(all_skills, key=lambda x: x.name.lower()):
            desc = (s.description or "").strip()
            if len(desc) > 200:
                desc = desc[:200].rstrip() + "\u2026"
            lines.append(f"- **{s.name}**: {desc}")

        catalog_text = "\n".join(lines)

        extras["available_skills"] = self.agent.read_prompt(
            "agent.system.skills.catalog.md",
            skills=catalog_text,
        )
