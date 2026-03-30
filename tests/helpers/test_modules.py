"""Tests for helpers/modules.py — import_module, load_classes, purge_namespace."""

import os
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import helpers.modules as _mod


class TestImportModule:
    def test_import_module(self, tmp_path):
        py = tmp_path / "greet.py"
        py.write_text("HELLO = 'world'\n")
        with patch.object(_mod, "get_abs_path", return_value=str(py)):
            module = _mod.import_module(str(py))
        assert hasattr(module, "HELLO")
        assert module.HELLO == "world"

    def test_import_module_raises_for_missing_file(self, tmp_path):
        bad = str(tmp_path / "no_such_file.py")
        with patch.object(_mod, "get_abs_path", return_value=bad):
            with pytest.raises((ImportError, FileNotFoundError)):
                _mod.import_module(bad)


class TestLoadClassesFromFolder:
    def _make_plugin_files(self, folder: Path, base_cls_name: str = "Base"):
        init = folder / "__init__.py"
        init.write_text("")

        base = folder / "base.py"
        base.write_text(textwrap.dedent(f"""\
            class {base_cls_name}:
                pass
        """))

        alpha = folder / "alpha.py"
        alpha.write_text(textwrap.dedent(f"""\
            from base import {base_cls_name}
            class Alpha({base_cls_name}):
                pass
        """))

        beta = folder / "beta.py"
        beta.write_text(textwrap.dedent(f"""\
            from base import {base_cls_name}
            class Beta({base_cls_name}):
                pass
        """))
        return base, alpha, beta

    def test_load_classes_from_folder(self, tmp_path):
        folder = tmp_path / "plugins"
        folder.mkdir()
        self._make_plugin_files(folder)

        sys.path.insert(0, str(folder))
        try:
            base_mod = _mod.import_module.__wrapped__ if hasattr(_mod.import_module, "__wrapped__") else None

            from base import Base

            def fake_abs(p):
                if os.path.isabs(p):
                    return p
                return str(folder / p)

            with patch.object(_mod, "get_abs_path", side_effect=fake_abs):
                classes = _mod.load_classes_from_folder(
                    str(folder), "*.py", Base, one_per_file=True
                )

            names = {c.__name__ for c in classes}
            assert "Alpha" in names
            assert "Beta" in names
            assert "Base" not in names
        finally:
            sys.path.remove(str(folder))


class TestLoadClassesFromFile:
    def test_load_classes_from_file(self, tmp_path):
        """Use a stdlib base class (Exception) so re-import doesn't create
        a different class object for the base."""
        py = tmp_path / "things.py"
        py.write_text(textwrap.dedent("""\
            class DogError(Exception):
                pass
            class CatError(Exception):
                pass
        """))

        with patch.object(_mod, "get_abs_path", return_value=str(py)):
            classes = _mod.load_classes_from_file(str(py), Exception, one_per_file=False)

        names = {c.__name__ for c in classes}
        assert "DogError" in names
        assert "CatError" in names

    def test_load_classes_from_file_one_per_file(self, tmp_path):
        py = tmp_path / "multi.py"
        py.write_text(textwrap.dedent("""\
            class FirstError(Exception):
                pass
            class SecondError(Exception):
                pass
        """))

        with patch.object(_mod, "get_abs_path", return_value=str(py)):
            classes = _mod.load_classes_from_file(str(py), Exception, one_per_file=True)

        assert len(classes) == 1
        assert classes[0].__name__ in ("FirstError", "SecondError")


class TestPurgeNamespace:
    def test_purge_namespace(self):
        ns = "_test_purge_ns_12345"
        child = f"{ns}.child"
        sys.modules[ns] = type(sys)("fake_ns")
        sys.modules[child] = type(sys)("fake_child")

        deleted = _mod.purge_namespace(ns)

        assert ns not in sys.modules
        assert child not in sys.modules
        assert ns in deleted
        assert child in deleted

    def test_purge_namespace_ignores_unrelated(self):
        sentinel = "_test_purge_sentinel_99999"
        sys.modules[sentinel] = type(sys)("sentinel")

        _mod.purge_namespace("_test_purge_other")

        assert sentinel in sys.modules
        del sys.modules[sentinel]
