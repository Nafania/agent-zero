"""Task 6: chat util message path wires memory recall feedback UI + POST /memory_feedback."""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MESSAGES_JS = REPO_ROOT / "webui" / "js" / "messages.js"
FEEDBACK_JS = REPO_ROOT / "webui" / "js" / "memory-recall-feedback.js"


@pytest.fixture
def messages_js() -> str:
    assert MESSAGES_JS.is_file(), f"Expected {MESSAGES_JS}"
    return MESSAGES_JS.read_text(encoding="utf-8")


@pytest.fixture
def feedback_js() -> str:
    assert FEEDBACK_JS.is_file(), f"Expected {FEEDBACK_JS}"
    return FEEDBACK_JS.read_text(encoding="utf-8")


def test_messages_js_strips_feedback_items_from_kvps_table(messages_js: str) -> None:
    assert "memory_feedback_items" in messages_js
    assert "drawMessageUtil" in messages_js


def test_memory_recall_feedback_js_posts_contract(feedback_js: str) -> None:
    assert "/memory_feedback" in feedback_js
    assert "callJsonApi" in feedback_js
    assert "positive" in feedback_js
    assert "negative" in feedback_js
    assert "success" in feedback_js.lower() or "Thanks" in feedback_js
    assert "error" in feedback_js.lower() or "Failed" in feedback_js


def test_memory_settings_mentions_recall_feedback() -> None:
    p = REPO_ROOT / "webui" / "components" / "settings" / "agent" / "memory.html"
    text = p.read_text(encoding="utf-8")
    assert "feedback" in text.lower()
