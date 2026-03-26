"""Static checks: obsolete memory settings controls stay out of the WebUI template."""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MEMORY_SETTINGS_HTML = REPO_ROOT / "webui" / "components" / "settings" / "agent" / "memory.html"

# Removed from UI per memory/Cognee cleanup; template must not expose these.
REMOVED_FIELD_TITLES = (
    "Memory Subdirectory",
    "Auto-recall AI query preparation",
    "Auto-recall AI post-filtering",
    "Memory auto-recall similarity threshold",
    "Auto-memorize AI consolidation",
    "Auto-memorize replacement threshold",
)

REMOVED_SETTING_BINDINGS = (
    "agent_memory_subdir",
    "memory_recall_query_prep",
    "memory_recall_post_filter",
    "memory_recall_similarity_threshold",
    "memory_memorize_consolidation",
    "memory_memorize_replace_threshold",
)


@pytest.fixture
def memory_settings_html() -> str:
    assert MEMORY_SETTINGS_HTML.is_file(), f"Expected {MEMORY_SETTINGS_HTML}"
    return MEMORY_SETTINGS_HTML.read_text(encoding="utf-8")


def test_memory_settings_template_excludes_removed_field_titles(memory_settings_html: str) -> None:
    for title in REMOVED_FIELD_TITLES:
        assert title not in memory_settings_html, f"Removed title still present: {title!r}"


def test_memory_settings_template_excludes_removed_x_model_bindings(memory_settings_html: str) -> None:
    for binding in REMOVED_SETTING_BINDINGS:
        needle = f"$store.settings.settings.{binding}"
        assert needle not in memory_settings_html, f"Removed setting binding still present: {needle!r}"
