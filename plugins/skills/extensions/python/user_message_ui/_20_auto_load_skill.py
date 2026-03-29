import re
from helpers.extension import Extension
from plugins.skills.tools.skills_tool import DATA_NAME_LOADED_SKILLS, max_loaded_skills

_SKILL_PREFIX_RE = re.compile(
    r"^\[Load and use skill:\s*([^\]]+)\]\s*", re.IGNORECASE
)


class AutoLoadSkill(Extension):
    """Intercept '[Load and use skill: X] ...' messages from the UI slash command.

    Pre-populates agent.data["loaded_skills"] so that
    _65_include_loaded_skills.py injects the full SKILL.md content
    into the system prompt on the first monologue turn.
    The original message (with skill prefix) is preserved for chat history.
    """

    async def execute(self, data: dict | None = None, **kwargs):
        if not data:
            return

        message: str = data.get("message", "")
        m = _SKILL_PREFIX_RE.match(message)
        if not m:
            return

        skill_name = m.group(1).strip()

        loaded: list = self.agent.data.get(DATA_NAME_LOADED_SKILLS, [])
        if skill_name not in loaded:
            loaded.append(skill_name)
        self.agent.data[DATA_NAME_LOADED_SKILLS] = loaded[-max_loaded_skills():]
