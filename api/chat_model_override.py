import json
import os
import re
from helpers.api import ApiHandler, Input, Output, Request
from helpers import files

_SAFE_CHAT_ID = re.compile(r"^[a-zA-Z0-9_\-]+$")


def _validate_chat_id(chat_id: str) -> str | None:
    if not chat_id or not _SAFE_CHAT_ID.match(chat_id):
        return None
    return chat_id


def _override_path(chat_id: str) -> str:
    return files.get_abs_path(f"usr/chats/{chat_id}/model_override.json")


def _load_override(chat_id: str) -> dict | None:
    safe = _validate_chat_id(chat_id)
    if not safe:
        return None
    path = _override_path(safe)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _save_override(chat_id: str, provider: str, model: str):
    safe = _validate_chat_id(chat_id)
    if not safe:
        raise ValueError(f"Invalid chat_id: {chat_id}")
    path = _override_path(safe)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"provider": provider, "model": model}, f)


def _delete_override(chat_id: str):
    safe = _validate_chat_id(chat_id)
    if not safe:
        return
    path = _override_path(safe)
    if os.path.exists(path):
        os.remove(path)


class ChatModelOverride(ApiHandler):
    async def process(self, input: Input, request: Request) -> Output:
        chat_id = input.get("chat_id", "")
        if not chat_id:
            return {"error": "chat_id required"}
        if not _validate_chat_id(chat_id):
            return {"error": "invalid chat_id"}

        if input.get("reset"):
            _delete_override(chat_id)
            return {"status": "ok", "chat_id": chat_id, "override": None}

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
