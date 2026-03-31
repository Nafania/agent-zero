"""Tests for helpers/cognee_feedback.py — Cognee feedback adapter and durable queue."""

import json
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from helpers import cognee_feedback as cf
from plugins._memory.helpers.memory import stable_memory_id_fallback


def _abs_path_mock(root: Path):
    return lambda *parts: str(root.joinpath(*parts))


def _tmp_usr_queue(tmp_path: Path) -> Path:
    q = tmp_path / "usr" / "cognee_feedback_queue" / "pending"
    q.mkdir(parents=True, exist_ok=True)
    return q


@pytest.fixture
def feedback_payload():
    return {
        "context_id": "ctx-1",
        "dataset": "default",
        "memory_id": "qa-99",
        "feedback": "positive",
        "reason": "helpful",
    }


class TestDiscoverFeedbackSurface:
    def test_returns_callable_when_session_add_feedback_exists(self):
        cognee = MagicMock()
        cognee.session.add_feedback = AsyncMock()
        fn = cf.discover_cognee_feedback_callable(cognee)
        assert fn is cognee.session.add_feedback

    def test_returns_none_without_session(self):
        cognee = MagicMock(spec=[])  # no session
        assert cf.discover_cognee_feedback_callable(cognee) is None

    def test_falls_back_to_module_add_feedback_when_session_lacks_it(self):
        cognee = MagicMock()
        cognee.session = MagicMock(spec=["get_session"])
        cognee.add_feedback = MagicMock()
        fn = cf.discover_cognee_feedback_callable(cognee)
        assert fn is cognee.add_feedback

    def test_returns_none_when_no_add_feedback_on_session_or_module(self):
        cognee = MagicMock(spec=["session"])
        cognee.session = MagicMock(spec=["get_session"])
        assert cf.discover_cognee_feedback_callable(cognee) is None


class TestSubmitMemoryFeedback:
    @pytest.mark.asyncio
    async def test_queue_only_when_callable_missing(self, feedback_payload, tmp_path, caplog):
        pending = _tmp_usr_queue(tmp_path)
        with patch("plugins._memory.helpers.cognee_feedback.files.get_abs_path", side_effect=_abs_path_mock(tmp_path)), \
             patch("plugins._memory.helpers.cognee_feedback.get_settings", return_value={"cognee_feedback_enabled": True}):
            caplog.set_level("WARNING")
            result = await cf.submit_memory_feedback(feedback_payload, cognee_module=None)
        assert result["status"] == "queued"
        files = list(pending.glob("*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text())
        assert data["context_id"] == "ctx-1"
        assert data["feedback"] == "positive"
        assert "Cognee feedback API unavailable" in caplog.text

    @pytest.mark.asyncio
    async def test_forwarded_when_cognee_accepts(self, feedback_payload, tmp_path):
        cognee = MagicMock()
        cognee.session.add_feedback = AsyncMock(return_value=True)
        with patch("plugins._memory.helpers.cognee_feedback.files.get_abs_path", side_effect=_abs_path_mock(tmp_path)), \
             patch("plugins._memory.helpers.cognee_feedback.get_settings", return_value={"cognee_feedback_enabled": True}):
            result = await cf.submit_memory_feedback(feedback_payload, cognee_module=cognee)
        assert result["status"] == "forwarded"
        cognee.session.add_feedback.assert_awaited_once()
        call_kw = cognee.session.add_feedback.await_args.kwargs
        assert call_kw["session_id"] == "ctx-1"
        assert call_kw["qa_id"] == "qa-99"
        assert call_kw["feedback_score"] == 5

    @pytest.mark.asyncio
    async def test_forwarded_when_cognee_returns_none(self, feedback_payload, tmp_path):
        cognee = MagicMock()
        cognee.session.add_feedback = AsyncMock(return_value=None)
        with patch("plugins._memory.helpers.cognee_feedback.files.get_abs_path", side_effect=_abs_path_mock(tmp_path)), \
             patch("plugins._memory.helpers.cognee_feedback.get_settings", return_value={"cognee_feedback_enabled": True}):
            result = await cf.submit_memory_feedback(feedback_payload, cognee_module=cognee)
        assert result["status"] == "forwarded"

    @pytest.mark.asyncio
    async def test_forwarded_via_module_add_feedback_when_session_has_none(self, feedback_payload, tmp_path):
        cognee = MagicMock()
        cognee.session = MagicMock(spec=["get_session"])
        cognee.add_feedback = AsyncMock(return_value=None)
        with patch("plugins._memory.helpers.cognee_feedback.files.get_abs_path", side_effect=_abs_path_mock(tmp_path)), \
             patch("plugins._memory.helpers.cognee_feedback.get_settings", return_value={"cognee_feedback_enabled": True}):
            result = await cf.submit_memory_feedback(feedback_payload, cognee_module=cognee)
        assert result["status"] == "forwarded"
        cognee.add_feedback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_negative_maps_to_low_score(self, feedback_payload, tmp_path):
        feedback_payload["feedback"] = "negative"
        cognee = MagicMock()
        cognee.session.add_feedback = AsyncMock(return_value=True)
        with patch("plugins._memory.helpers.cognee_feedback.files.get_abs_path", side_effect=_abs_path_mock(tmp_path)), \
             patch("plugins._memory.helpers.cognee_feedback.get_settings", return_value={"cognee_feedback_enabled": True}):
            result = await cf.submit_memory_feedback(feedback_payload, cognee_module=cognee)
        assert result["status"] == "forwarded"
        assert cognee.session.add_feedback.await_args.kwargs["feedback_score"] == 1

    @pytest.mark.asyncio
    async def test_queued_when_cognee_returns_false(self, feedback_payload, tmp_path):
        cognee = MagicMock()
        cognee.session.add_feedback = AsyncMock(return_value=False)
        pending = _tmp_usr_queue(tmp_path)
        with patch("plugins._memory.helpers.cognee_feedback.files.get_abs_path", side_effect=_abs_path_mock(tmp_path)), \
             patch("plugins._memory.helpers.cognee_feedback.get_settings", return_value={"cognee_feedback_enabled": True}):
            result = await cf.submit_memory_feedback(feedback_payload, cognee_module=cognee)
        assert result["status"] == "queued"
        assert list(pending.glob("*.json"))

    @pytest.mark.asyncio
    async def test_queued_when_cognee_returns_empty_string(self, feedback_payload, tmp_path):
        cognee = MagicMock()
        cognee.session.add_feedback = AsyncMock(return_value="")
        pending = _tmp_usr_queue(tmp_path)
        with patch("plugins._memory.helpers.cognee_feedback.files.get_abs_path", side_effect=_abs_path_mock(tmp_path)), \
             patch("plugins._memory.helpers.cognee_feedback.get_settings", return_value={"cognee_feedback_enabled": True}):
            result = await cf.submit_memory_feedback(feedback_payload, cognee_module=cognee)
        assert result["status"] == "queued"
        assert list(pending.glob("*.json"))

    @pytest.mark.asyncio
    async def test_queued_when_feedback_disabled(self, feedback_payload, tmp_path):
        _tmp_usr_queue(tmp_path)
        cognee = MagicMock()
        cognee.session.add_feedback = AsyncMock(return_value=True)
        with patch("plugins._memory.helpers.cognee_feedback.files.get_abs_path", side_effect=_abs_path_mock(tmp_path)), \
             patch("plugins._memory.helpers.cognee_feedback.get_settings", return_value={"cognee_feedback_enabled": False}):
            result = await cf.submit_memory_feedback(feedback_payload, cognee_module=cognee)
        assert result["status"] == "queued"
        cognee.session.add_feedback.assert_not_called()

    @pytest.mark.asyncio
    async def test_failed_when_enqueue_raises(self, feedback_payload, tmp_path):
        cognee = MagicMock()
        cognee.session.add_feedback = AsyncMock(return_value=False)

        def bad_abs(*_a, **_k):
            raise OSError("disk full")

        with patch("plugins._memory.helpers.cognee_feedback.drain_feedback_queue", new=AsyncMock()), \
             patch("plugins._memory.helpers.cognee_feedback.files.get_abs_path", side_effect=bad_abs), \
             patch("plugins._memory.helpers.cognee_feedback.get_settings", return_value={"cognee_feedback_enabled": True}):
            result = await cf.submit_memory_feedback(feedback_payload, cognee_module=cognee)
        assert result["status"] == "failed"


class TestDrainFeedbackQueue:
    @pytest.mark.asyncio
    async def test_drain_removes_on_success(self, feedback_payload, tmp_path):
        pending = _tmp_usr_queue(tmp_path)
        fid = uuid.uuid4().hex
        (pending / f"{fid}.json").write_text(json.dumps(feedback_payload))
        cognee = MagicMock()
        cognee.session.add_feedback = AsyncMock(return_value=True)
        with patch("plugins._memory.helpers.cognee_feedback.files.get_abs_path", side_effect=_abs_path_mock(tmp_path)):
            n = await cf.drain_feedback_queue(cognee_module=cognee, limit=10)
        assert n == 1
        assert not list(pending.glob("*.json"))

    @pytest.mark.asyncio
    async def test_drain_keeps_file_on_failure(self, feedback_payload, tmp_path):
        pending = _tmp_usr_queue(tmp_path)
        (pending / "x.json").write_text(json.dumps(feedback_payload))
        cognee = MagicMock()
        cognee.session.add_feedback = AsyncMock(return_value=False)
        with patch("plugins._memory.helpers.cognee_feedback.files.get_abs_path", side_effect=_abs_path_mock(tmp_path)):
            n = await cf.drain_feedback_queue(cognee_module=cognee, limit=10)
        assert n == 0
        assert list(pending.glob("*.json"))

    @pytest.mark.asyncio
    async def test_drain_quarantines_invalid_json(self, tmp_path):
        pending = _tmp_usr_queue(tmp_path)
        (pending / "bad.json").write_text("not json {{{")
        failed = tmp_path / "usr" / "cognee_feedback_queue" / "failed"
        with patch("plugins._memory.helpers.cognee_feedback.files.get_abs_path", side_effect=_abs_path_mock(tmp_path)):
            n = await cf.drain_feedback_queue(cognee_module=None, limit=10)
        assert n == 0
        assert not list(pending.glob("*.json"))
        assert list(failed.glob("*.json"))

    @pytest.mark.asyncio
    async def test_drain_quarantines_invalid_payload(self, feedback_payload, tmp_path):
        pending = _tmp_usr_queue(tmp_path)
        bad = dict(feedback_payload)
        bad["feedback"] = "nope"
        (pending / "bad.json").write_text(json.dumps(bad))
        failed = tmp_path / "usr" / "cognee_feedback_queue" / "failed"
        with patch("plugins._memory.helpers.cognee_feedback.files.get_abs_path", side_effect=_abs_path_mock(tmp_path)):
            n = await cf.drain_feedback_queue(cognee_module=None, limit=10)
        assert n == 0
        assert not list(pending.glob("*.json"))
        assert list(failed.glob("*.json"))

    @pytest.mark.asyncio
    async def test_drain_counts_none_return_as_success(self, feedback_payload, tmp_path):
        pending = _tmp_usr_queue(tmp_path)
        (pending / "ok.json").write_text(json.dumps(feedback_payload))
        cognee = MagicMock()
        cognee.session.add_feedback = AsyncMock(return_value=None)
        with patch("plugins._memory.helpers.cognee_feedback.files.get_abs_path", side_effect=_abs_path_mock(tmp_path)):
            n = await cf.drain_feedback_queue(cognee_module=cognee, limit=10)
        assert n == 1
        assert not list(pending.glob("*.json"))

    @pytest.mark.asyncio
    async def test_drain_increments_attempts_on_rejection(self, feedback_payload, tmp_path):
        pending = _tmp_usr_queue(tmp_path)
        (pending / "retry.json").write_text(json.dumps(feedback_payload))
        cognee = MagicMock()
        cognee.session.add_feedback = AsyncMock(return_value=False)
        with patch("plugins._memory.helpers.cognee_feedback.files.get_abs_path", side_effect=_abs_path_mock(tmp_path)):
            n = await cf.drain_feedback_queue(cognee_module=cognee, limit=10)
        assert n == 0
        record = json.loads((pending / "retry.json").read_text())
        assert record["attempts"] == 1

    @pytest.mark.asyncio
    async def test_drain_quarantines_after_max_rejections(self, feedback_payload, tmp_path):
        pending = _tmp_usr_queue(tmp_path)
        stale = dict(feedback_payload)
        stale["attempts"] = cf.MAX_RETRY_ATTEMPTS - 1
        (pending / "stale.json").write_text(json.dumps(stale))
        failed = tmp_path / "usr" / "cognee_feedback_queue" / "failed"
        cognee = MagicMock()
        cognee.session.add_feedback = AsyncMock(return_value=False)
        with patch("plugins._memory.helpers.cognee_feedback.files.get_abs_path", side_effect=_abs_path_mock(tmp_path)):
            n = await cf.drain_feedback_queue(cognee_module=cognee, limit=10)
        assert n == 0
        assert not list(pending.glob("*.json"))
        assert list(failed.glob("*.json"))


class TestValidatePayload:
    def test_accepts_minimal(self):
        cf.validate_feedback_payload({
            "context_id": "c",
            "dataset": "d",
            "memory_id": "m",
            "feedback": "positive",
        })

    def test_rejects_bad_feedback(self):
        with pytest.raises(cf.FeedbackPayloadError):
            cf.validate_feedback_payload({
                "context_id": "c",
                "dataset": "d",
                "memory_id": "m",
                "feedback": "meh",
            })

    def test_rejects_empty_memory_id(self):
        with pytest.raises(cf.FeedbackPayloadError):
            cf.validate_feedback_payload({
                "context_id": "c",
                "dataset": "d",
                "memory_id": "",
                "feedback": "positive",
            })


class TestStableMemoryIdFallback:
    def test_deterministic(self):
        a = stable_memory_id_fallback("hello world", "default")
        b = stable_memory_id_fallback("hello world", "default")
        assert a == b
        assert a.startswith("syn_")

    def test_differs_by_dataset(self):
        a = stable_memory_id_fallback("hello world", "default")
        b = stable_memory_id_fallback("hello world", "projects_x")
        assert a != b

    def test_differs_by_content(self):
        a = stable_memory_id_fallback("a", "default")
        b = stable_memory_id_fallback("b", "default")
        assert a != b
