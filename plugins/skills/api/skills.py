import json
import os
import shutil

from helpers.api import ApiHandler, Input, Output, Request, Response
from helpers import runtime, projects, files
from plugins.skills.helpers import skills, skills_cli


class Skills(ApiHandler):
    async def process(self, input: Input, request: Request) -> Output:
        action = input.get("action", "")

        try:
            if action == "list":
                data = self.list_skills(input)
            elif action == "delete":
                data = self.delete_skill(input)
            elif action == "check_updates":
                data = await self.check_updates_action()
            elif action == "update":
                data = await self.update_action()
            elif action == "move":
                data = self.move_skill(input)
            else:
                raise Exception("Invalid action")

            return {
                "ok": True,
                "data": data,
            }
        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
            }

    def list_skills(self, input: Input):
        skill_list = skills.list_skills()

        # filter by project
        if project_name := (input.get("project_name") or "").strip() or None:
            project_folder = projects.get_project_folder(project_name)
            if runtime.is_development():
                project_folder = files.normalize_a0_path(project_folder)
            skill_list = [
                s for s in skill_list if files.is_in_dir(str(s.path), project_folder)
            ]

        # filter by agent profile
        if agent_profile := (input.get("agent_profile") or "").strip() or None:
            roots: list[str] = [
                files.get_abs_path("agents", agent_profile, "skills"),
                files.get_abs_path("usr", "agents", agent_profile, "skills"),
            ]
            if project_name:
                roots.append(
                    projects.get_project_meta_folder(project_name, "agents", agent_profile, "skills")
                )

            skill_list = [
                s
                for s in skill_list
                if any(files.is_in_dir(str(s.path), r) for r in roots)
            ]

        lock = self._read_skill_lock()

        result = []
        for skill in skill_list:
            entry = {
                "name": skill.name,
                "description": skill.description,
                "path": str(skill.path),
            }
            if skill.name in lock:
                src = lock[skill.name].get("source", "")
                if src:
                    entry["source"] = f"{src}@{skill.name}"
            result.append(entry)
        result.sort(key=lambda x: (x["name"], x["path"]))
        return result

    @staticmethod
    def _read_skill_lock() -> dict:
        lock_path = os.path.expanduser("~/.agents/.skill-lock.json")
        try:
            with open(lock_path, "r") as f:
                data = json.load(f)
            return data.get("skills", {})
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def delete_skill(self, input: Input):
        skill_path = str(input.get("skill_path") or "").strip()
        if not skill_path:
            raise Exception("skill_path is required")

        skills.delete_skill(skill_path)
        return {"ok": True, "skill_path": skill_path}

    async def check_updates_action(self):
        output = await skills_cli.check_updates()
        return {"output": output}

    async def update_action(self):
        output = await skills_cli.update()
        return {"output": output}

    def move_skill(self, input: Input):
        skill_path = str(input.get("skill_path") or "").strip()
        target_project = str(input.get("target_project") or "").strip() or None

        if not skill_path:
            raise Exception("skill_path is required")

        if not os.path.isdir(skill_path):
            raise Exception(f"Skill directory not found: {skill_path}")

        skill_name = os.path.basename(skill_path)

        if target_project:
            dest_base = projects.get_project_meta_folder(target_project, "skills")
        else:
            dest_base = files.get_abs_path("usr", "skills")

        dest = os.path.join(dest_base, skill_name)
        os.makedirs(dest_base, exist_ok=True)

        if os.path.exists(dest):
            raise Exception(f"Skill already exists at destination: {dest}")

        shutil.move(skill_path, dest)
        return {"skill_path": dest, "moved_to": "global" if not target_project else target_project}
