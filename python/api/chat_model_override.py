import json
import os
from python.helpers.api import ApiHandler, Input, Output, Request
from python.helpers import files


def _override_path(chat_id: str) -> str:
    return files.get_abs_path(f"usr/chats/{chat_id}/model_override.json")


def _load_override(chat_id: str) -> dict | None:
    path = _override_path(chat_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _save_override(chat_id: str, provider: str, model: str):
    path = _override_path(chat_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"provider": provider, "model": model}, f)


class ChatModelOverride(ApiHandler):
    async def process(self, input: Input, request: Request) -> Output:
        chat_id = input.get("chat_id", "")
        if not chat_id:
            return {"error": "chat_id required"}

        provider = input.get("provider")
        model = input.get("model")

        if provider and model:
            _save_override(chat_id, provider, model)
            return {"status": "ok", "chat_id": chat_id, "provider": provider, "model": model}

        override = _load_override(chat_id)
        return {"chat_id": chat_id, "override": override}

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET", "POST"]
