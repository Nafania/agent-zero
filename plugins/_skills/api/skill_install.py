from __future__ import annotations

from helpers.api import ApiHandler, Input, Output, Request, Response
from plugins._skills.helpers import skills_cli


class SkillInstall(ApiHandler):
    async def process(self, input: Input, request: Request) -> Output:
        source = (input.get("source") or "").strip()
        if not source:
            return {"ok": False, "error": "source is required"}

        try:
            output = await skills_cli.add(source)
            return {"ok": True, "output": output, "source": source}
        except skills_cli.SkillsCLIError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:
            return {"ok": False, "error": str(e)}
