import os
from helpers.tool import Tool, Response
from helpers import files


class TextEditor(Tool):
    """Read, write, and patch text files in an LLM-friendly way."""

    async def execute(self, **kwargs):
        action = self.args.get("action", "read")
        path = self.args.get("path", "")
        content = self.args.get("content", "")

        if not path:
            return Response(message="Error: path is required", break_loop=False)

        abs_path = files.get_abs_path(path) if not os.path.isabs(path) else path

        if action == "read":
            return await self._read(abs_path)
        elif action == "write":
            return await self._write(abs_path, content)
        elif action == "patch":
            old_text = self.args.get("old_text", "")
            new_text = self.args.get("new_text", "")
            return await self._patch(abs_path, old_text, new_text)
        else:
            return Response(message=f"Unknown action: {action}", break_loop=False)

    async def _read(self, path: str) -> Response:
        try:
            if not os.path.exists(path):
                return Response(message=f"File not found: {path}", break_loop=False)
            if files.is_probably_binary_file(path):
                return Response(message=f"Binary file, cannot read: {path}", break_loop=False)
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            lines = content.split("\n")
            numbered = "\n".join(f"{i+1:6}|{line}" for i, line in enumerate(lines))
            return Response(message=numbered, break_loop=False)
        except Exception as e:
            return Response(message=f"Error reading {path}: {e}", break_loop=False)

    async def _write(self, path: str, content: str) -> Response:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return Response(message=f"Written {len(content)} bytes to {path}", break_loop=False)
        except Exception as e:
            return Response(message=f"Error writing {path}: {e}", break_loop=False)

    async def _patch(self, path: str, old_text: str, new_text: str) -> Response:
        try:
            if not os.path.exists(path):
                return Response(message=f"File not found: {path}", break_loop=False)
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            if old_text not in content:
                return Response(
                    message=f"old_text not found in {path}. No changes made.",
                    break_loop=False,
                )
            new_content = content.replace(old_text, new_text, 1)
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)
            return Response(message=f"Patched {path} successfully", break_loop=False)
        except Exception as e:
            return Response(message=f"Error patching {path}: {e}", break_loop=False)
