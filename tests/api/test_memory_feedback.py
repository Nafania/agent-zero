"""Tests for python/api/memory_feedback.py — Memory feedback API handler."""

import json
import sys
import threading
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class _TestJsonResponse:
    """Minimal HTTP response (pytest env may mock flask/werkzeug imports)."""

    def __init__(self, response: str, status: int, mimetype: str):
        self._text = response
        self.status_code = status
        self.mimetype = mimetype

    def get_data(self, as_text: bool = False):
        if as_text:
            return self._text
        return self._text.encode("utf-8")


def _patch_memory_feedback_response():
    import python.api.memory_feedback as mf

    mf.Response = _TestJsonResponse


def _memory_feedback_class():
    _patch_memory_feedback_response()
    from python.api.memory_feedback import MemoryFeedback

    return MemoryFeedback


def _make_handler():
    return _memory_feedback_class()(app=MagicMock(), thread_lock=threading.Lock())


def _out_json(out):
    if isinstance(out, dict):
        return out
    return json.loads(out.get_data(as_text=True))


class TestMemoryFeedbackHandler:
    def test_requires_auth_and_csrf_default(self):
        MF = _memory_feedback_class()
        assert MF.requires_auth() is True
        assert MF.requires_csrf() is True

    @pytest.mark.asyncio
    async def test_invalid_feedback_returns_400(self):
        handler = _make_handler()
        inp = {
            "context_id": "c1",
            "dataset": "default",
            "memory_id": "m1",
            "feedback": "maybe",
        }
        out = await handler.process(inp, MagicMock())
        assert out.status_code == 400
        body = _out_json(out)
        assert body["status"] == "failed"

    @pytest.mark.asyncio
    async def test_missing_field_returns_400(self):
        handler = _make_handler()
        inp = {"context_id": "c1", "dataset": "default", "feedback": "positive"}
        out = await handler.process(inp, MagicMock())
        assert out.status_code == 400

    @pytest.mark.asyncio
    async def test_success_returns_forwarded(self):
        handler = _make_handler()
        inp = {
            "context_id": "c1",
            "dataset": "default",
            "memory_id": "m1",
            "feedback": "positive",
            "reason": "ok",
        }
        with patch(
            "python.api.memory_feedback.cf.submit_memory_feedback",
            new=AsyncMock(return_value={"status": "forwarded"}),
        ):
            out = await handler.process(inp, MagicMock())
        body = _out_json(out)
        assert body["success"] is True
        assert body["status"] == "forwarded"

    @pytest.mark.asyncio
    async def test_queued_status_200(self):
        handler = _make_handler()
        inp = {
            "context_id": "c1",
            "dataset": "default",
            "memory_id": "m1",
            "feedback": "negative",
        }
        with patch(
            "python.api.memory_feedback.cf.submit_memory_feedback",
            new=AsyncMock(return_value={"status": "queued"}),
        ):
            out = await handler.process(inp, MagicMock())
        assert _out_json(out)["status"] == "queued"

    @pytest.mark.asyncio
    async def test_failed_status_503(self):
        handler = _make_handler()
        inp = {
            "context_id": "c1",
            "dataset": "default",
            "memory_id": "m1",
            "feedback": "positive",
        }
        with patch(
            "python.api.memory_feedback.cf.submit_memory_feedback",
            new=AsyncMock(return_value={"status": "failed", "error": "enqueue failed"}),
        ):
            out = await handler.process(inp, MagicMock())
        assert out.status_code == 503
        body = _out_json(out)
        assert body["status"] == "failed"


def test_memory_feedback_discovered_like_run_ui():
    """Same discovery mechanism as run_ui (load_classes_from_folder on python/api)."""
    from python.helpers.api import ApiHandler
    from python.helpers.extract_tools import load_classes_from_file
    from python.helpers.files import get_abs_path

    path = get_abs_path("python", "api", "memory_feedback.py")
    classes = load_classes_from_file(path, ApiHandler)
    names = {c.__name__ for c in classes}
    assert "MemoryFeedback" in names
