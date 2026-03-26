"""Static checks: removed agent settings controls stay out of the WebUI template."""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
AGENT_SETTINGS_HTML = REPO_ROOT / "webui" / "components" / "settings" / "agent" / "agent.html"


@pytest.fixture
def agent_settings_html() -> str:
    assert AGENT_SETTINGS_HTML.is_file(), f"Expected {AGENT_SETTINGS_HTML}"
    return AGENT_SETTINGS_HTML.read_text(encoding="utf-8")


def test_agent_settings_template_excludes_knowledge_subdirectory_title(agent_settings_html: str) -> None:
    assert "Knowledge subdirectory" not in agent_settings_html


def test_agent_settings_template_excludes_removed_agent_knowledge_binding(agent_settings_html: str) -> None:
    assert "$store.settings.settings.agent_knowledge_subdir" not in agent_settings_html
