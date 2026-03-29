import pytest
import threading
from unittest.mock import patch, MagicMock
from api.chat_model_override import ChatModelOverride, _load_override, _save_override


def _make():
    return ChatModelOverride(MagicMock(), threading.Lock())


class TestChatModelOverrideEndpoint:
    @pytest.mark.asyncio
    async def test_set_override(self):
        handler = _make()
        with patch("api.chat_model_override._save_override") as mock_save:
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
        with patch("api.chat_model_override._load_override", return_value=None):
            result = await handler.process({"chat_id": "abc-123"}, MagicMock())
        assert result["override"] is None

    @pytest.mark.asyncio
    async def test_get_override_returns_saved_value(self):
        handler = _make()
        with patch("api.chat_model_override._load_override", return_value={"provider": "google", "model": "gemini-2.5-pro"}):
            result = await handler.process({"chat_id": "abc-123"}, MagicMock())
        assert result["override"]["provider"] == "google"

    @pytest.mark.asyncio
    async def test_missing_chat_id_returns_error(self):
        handler = _make()
        result = await handler.process({}, MagicMock())
        assert "error" in result


class TestOverrideHelpers:
    def test_save_and_load(self, tmp_path):
        with patch("api.chat_model_override.files.get_abs_path", side_effect=lambda p: str(tmp_path / p)):
            _save_override("chat-1", "openai", "gpt-4o")
            loaded = _load_override("chat-1")
        assert loaded == {"provider": "openai", "model": "gpt-4o"}

    def test_load_nonexistent_returns_none(self, tmp_path):
        with patch("api.chat_model_override.files.get_abs_path", side_effect=lambda p: str(tmp_path / p)):
            assert _load_override("nonexistent") is None

    def test_path_traversal_chat_id_rejected(self):
        assert _load_override("../../etc/passwd") is None

    def test_save_rejects_traversal(self):
        with pytest.raises(ValueError):
            _save_override("../evil", "openai", "gpt-4o")

    def test_save_rejects_slashes(self):
        with pytest.raises(ValueError):
            _save_override("foo/bar", "openai", "gpt-4o")

    def test_delete_override(self, tmp_path):
        from api.chat_model_override import _delete_override
        with patch("api.chat_model_override.files.get_abs_path", side_effect=lambda p: str(tmp_path / p)):
            _save_override("chat-del", "openai", "gpt-4o")
            assert _load_override("chat-del") is not None
            _delete_override("chat-del")
            assert _load_override("chat-del") is None


class TestChatModelOverrideReset:
    @pytest.mark.asyncio
    async def test_reset_override(self):
        handler = _make()
        with patch("api.chat_model_override._delete_override") as mock_del:
            result = await handler.process({
                "chat_id": "abc-123",
                "reset": True,
            }, MagicMock())
        mock_del.assert_called_once_with("abc-123")
        assert result["status"] == "ok"
        assert result["override"] is None

    @pytest.mark.asyncio
    async def test_invalid_chat_id_returns_error(self):
        handler = _make()
        result = await handler.process({"chat_id": "../../etc/passwd"}, MagicMock())
        assert "error" in result
