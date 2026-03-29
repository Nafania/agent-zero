from __future__ import annotations

from helpers.api import ApiHandler, Input, Output, Request, Response
from helpers import skills_cli


class SkillsCatalog(ApiHandler):
    async def process(self, input: Input, request: Request) -> Output:
        query = (input.get("query") or "").strip()
        if not query:
            return {"ok": False, "error": "query is required"}

        try:
            results = await skills_cli.find(query, enrich=True)
            return {"ok": True, "results": results}
        except Exception as e:
            return {"ok": False, "error": str(e)}
