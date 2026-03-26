import json
import os
import tempfile
import logging
from datetime import datetime, timezone
from typing import Optional

from python.helpers.oauth import OAuthTokens

logger = logging.getLogger(__name__)


class OAuthTokenStore:
    def __init__(self, file_path: str):
        self.file_path = file_path

    def _read_all(self) -> dict:
        if not os.path.exists(self.file_path):
            return {}
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("OAuth token file corrupted, treating as empty: %s", e)
            return {}

    def _write_all(self, data: dict):
        os.makedirs(os.path.dirname(self.file_path) or ".", exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=os.path.dirname(self.file_path) or ".",
            suffix=".tmp",
        )
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            os.replace(tmp, self.file_path)
            try:
                os.chmod(self.file_path, 0o600)
            except OSError:
                pass
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def save(self, provider_id: str, tokens: OAuthTokens):
        data = self._read_all()
        data[provider_id] = {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "expires_at": tokens.expires_at.isoformat(),
            "token_type": tokens.token_type,
            "scope": tokens.scope,
        }
        self._write_all(data)

    def load(self, provider_id: str) -> Optional[OAuthTokens]:
        data = self._read_all()
        entry = data.get(provider_id)
        if not entry:
            return None
        try:
            return OAuthTokens(
                access_token=entry["access_token"],
                refresh_token=entry.get("refresh_token"),
                expires_at=datetime.fromisoformat(entry["expires_at"]),
                token_type=entry.get("token_type", "Bearer"),
                scope=entry.get("scope", ""),
            )
        except (KeyError, ValueError) as e:
            logger.warning("Invalid token entry for %s: %s", provider_id, e)
            return None

    def delete(self, provider_id: str):
        data = self._read_all()
        data.pop(provider_id, None)
        self._write_all(data)

    def list_providers(self) -> list[str]:
        return list(self._read_all().keys())
