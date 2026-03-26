import pytest
import threading
from unittest.mock import patch, MagicMock
from python.api.chat_model_override import ChatModelOverride, _load_override, _save_override


def _make():
    return ChatModelOverride(MagicMock(), threading.Lock())


class TestChatModelOverrideEndpoint:
    @pytest.mark.asyncio
    async def test_set_override(self):
        handler = _make()
        with patch("python.api.chat_model_override._save_override") as mock_save:
            result = await handler.process({
                "chat_id": "abc-123",
                "provider": "google",
                "model": "gemini-2.5-pro",
            }, MagicMock())
        mock_save.assert_called_once_with("abc-123", "google", "gemini-2.5-pro")
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_get_override_returns_null_when_unset(self):
        handler = _make()
        with patch("python.api.chat_model_override._load_override", return_value=None):
            result = await handler.process({"chat_id": "abc-123"}, MagicMock())
        assert result["override"] is None

    @pytest.mark.asyncio
    async def test_get_override_returns_saved_value(self):
        handler = _make()
        with patch("python.api.chat_model_override._load_override", return_value={"provider": "google", "model": "gemini-2.5-pro"}):
            result = await handler.process({"chat_id": "abc-123"}, MagicMock())
        assert result["override"]["provider"] == "google"

    @pytest.mark.asyncio
    async def test_missing_chat_id_returns_error(self):
        handler = _make()
        result = await handler.process({}, MagicMock())
        assert "error" in result


class TestOverrideHelpers:
    def test_save_and_load(self, tmp_path):
        with patch("python.api.chat_model_override.files.get_abs_path", side_effect=lambda p: str(tmp_path / p)):
            _save_override("chat-1", "openai", "gpt-4o")
            loaded = _load_override("chat-1")
        assert loaded == {"provider": "openai", "model": "gpt-4o"}

    def test_load_nonexistent_returns_none(self, tmp_path):
        with patch("python.api.chat_model_override.files.get_abs_path", side_effect=lambda p: str(tmp_path / p)):
            assert _load_override("nonexistent") is None
