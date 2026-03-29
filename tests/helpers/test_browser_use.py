"""Tests for python/helpers/browser_use.py."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TestBrowserUseModule:
    """Tests for the browser_use side-effect module."""

    def test_dotenv_save_called_on_import(self):
        """Importing browser_use calls dotenv.save_dotenv_value for telemetry."""
        if "helpers.browser_use" in sys.modules:
            del sys.modules["helpers.browser_use"]
        with patch.dict("sys.modules", {"browser_use": MagicMock(), "browser_use.utils": MagicMock()}):
            with patch("helpers.dotenv.save_dotenv_value") as mock_save:
                import helpers.browser_use  # noqa: F401

        mock_save.assert_called_with("ANONYMIZED_TELEMETRY", "false")

    def test_import_succeeds_with_mocked_browser_use(self):
        """Module imports without error when browser_use is mocked."""
        if "helpers.browser_use" in sys.modules:
            del sys.modules["helpers.browser_use"]
        with patch.dict("sys.modules", {"browser_use": MagicMock(), "browser_use.utils": MagicMock()}):
            with patch("helpers.dotenv.save_dotenv_value"):
                import helpers.browser_use as mod  # noqa: F401

        assert mod is not None
