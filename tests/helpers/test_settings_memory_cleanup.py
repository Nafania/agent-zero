"""Task 1: removed memory settings — schema, defaults, load/save/API shape."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import python.helpers.settings as settings_module

REMOVED_MEMORY_KEYS = frozenset(
    {
        "agent_memory_subdir",
        "agent_knowledge_subdir",
        "memory_recall_query_prep",
        "memory_recall_post_filter",
        "memory_recall_similarity_threshold",
        "memory_memorize_consolidation",
        "memory_memorize_replace_threshold",
    }
)


@pytest.fixture(autouse=True)
def _reset_settings_module_state():
    settings_module._settings = None
    settings_module._runtime_settings_snapshot = None
    yield
    settings_module._settings = None
    settings_module._runtime_settings_snapshot = None


def _minimal_settings():
    with (
        patch("python.helpers.settings.files") as mock_files,
        patch("python.helpers.settings.runtime") as mock_runtime,
        patch("python.helpers.settings.git") as mock_git,
        patch("python.helpers.settings.dotenv") as mock_dotenv,
    ):
        mock_files.read_file.return_value = "# gitignore"
        mock_files.get_abs_path.side_effect = lambda *p: "/a0/" + "/".join(p)
        mock_files.get_abs_path_dockerized.side_effect = lambda *p: "/a0/" + "/".join(p)
        mock_runtime.is_dockerized.return_value = False
        mock_git.get_version.return_value = "v0.9.0"
        mock_dotenv.get_dotenv_value.return_value = None
        return dict(settings_module.get_default_settings())


class TestRemovedKeysNotInDefaults:
    def test_default_settings_excludes_removed_keys(self):
        with (
            patch("python.helpers.settings.files") as mock_files,
            patch("python.helpers.settings.runtime") as mock_runtime,
            patch("python.helpers.settings.git") as mock_git,
            patch("python.helpers.settings.dotenv") as mock_dotenv,
        ):
            mock_files.read_file.return_value = "# gitignore"
            mock_files.get_abs_path.side_effect = lambda *p: "/a0/" + "/".join(p)
            mock_files.get_abs_path_dockerized.side_effect = lambda *p: "/a0/" + "/".join(p)
            mock_runtime.is_dockerized.return_value = False
            mock_git.get_version.return_value = "v0.9.0"
            mock_dotenv.get_dotenv_value.return_value = None
            defaults = settings_module.get_default_settings()
        for key in REMOVED_MEMORY_KEYS:
            assert key not in defaults


class TestLegacyPayloadNormalize:
    def test_normalize_strips_removed_keys_without_error(self):
        defs = _minimal_settings()
        legacy = dict(defs)
        for key in REMOVED_MEMORY_KEYS:
            legacy[key] = "legacy" if key in {"agent_memory_subdir", "agent_knowledge_subdir"} else (0.5 if "threshold" in key else True)

        with patch("python.helpers.settings.get_default_settings", return_value=defs):
            result = settings_module.normalize_settings(legacy)

        for key in REMOVED_MEMORY_KEYS:
            assert key not in result


class TestConvertOutDoesNotReEmitRemovedKeys:
    def test_strips_removed_keys_from_payload(self):
        s = _minimal_settings()
        for key in REMOVED_MEMORY_KEYS:
            s[key] = "x"

        with patch("python.helpers.settings.get_providers") as mock_prov:
            mock_prov.side_effect = lambda t: [{"value": "openrouter", "label": "OpenRouter"}] if t == "chat" else [{"value": "huggingface", "label": "HuggingFace"}]
        with patch("python.helpers.settings.files") as mock_files:
            mock_files.get_subdirectories.side_effect = lambda p, **kw: ["agent0"] if p == "agents" else ["custom"]
        with patch("python.helpers.settings.runtime") as mock_runtime:
            mock_runtime.is_dockerized.return_value = False
        with patch("python.helpers.settings.dotenv") as mock_dotenv:
            mock_dotenv.get_dotenv_value.return_value = ""
        with patch("python.helpers.settings.get_default_secrets_manager") as mock_sec:
            mock_sec.return_value.get_masked_secrets.return_value = ""
        with patch("python.helpers.settings.models") as mock_models:
            mock_models.get_api_key.return_value = ""

        out = settings_module.convert_out(s)
        for key in REMOVED_MEMORY_KEYS:
            assert key not in out["settings"]


class TestConvertInIgnoresRemovedKeys:
    def test_does_not_apply_removed_keys_to_current(self):
        base = _minimal_settings()
        with patch("python.helpers.settings.get_settings", return_value=base):
            incoming = {k: "should-not-apply" for k in REMOVED_MEMORY_KEYS}
            incoming["chat_model_provider"] = "custom-provider"
            result = settings_module.convert_in(incoming)

        for key in REMOVED_MEMORY_KEYS:
            assert key not in result
        assert result["chat_model_provider"] == "custom-provider"
