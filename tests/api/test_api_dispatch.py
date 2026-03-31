"""Tests for the lazy API dispatch system in helpers/api.py."""

import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from flask import Flask, Response

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from helpers.api import ApiHandler, register_api_route, CACHE_AREA
from helpers import cache

LOAD_CLASSES_PATCH = "helpers.modules.load_classes_from_file"


def _make_app():
    app = Flask("test_api_dispatch")
    app.secret_key = "test-secret"

    @app.get("/login")
    def login_handler():
        return Response("login", status=200)

    return app


class TestRegisterApiRoute:
    def test_registers_prefixed_route(self):
        app = _make_app()
        lock = threading.Lock()
        register_api_route(app, lock)
        rules = {rule.rule for rule in app.url_map.iter_rules()}
        assert "/api/<path:path>" in rules

    def test_registers_compat_route(self):
        app = _make_app()
        lock = threading.Lock()
        register_api_route(app, lock)
        rules = {rule.rule for rule in app.url_map.iter_rules()}
        assert "/<path:path>" in rules

    def test_canonical_route_accepts_all_methods(self):
        app = _make_app()
        lock = threading.Lock()
        register_api_route(app, lock)
        for rule in app.url_map.iter_rules():
            if rule.rule == "/api/<path:path>":
                for method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                    assert method in rule.methods

    def test_compat_catchall_excludes_get(self):
        app = _make_app()
        lock = threading.Lock()
        register_api_route(app, lock)
        for rule in app.url_map.iter_rules():
            if rule.rule == "/<path:path>" and rule.endpoint == "api_dispatch_compat":
                assert "GET" not in rule.methods
                for method in ("POST", "PUT", "PATCH", "DELETE"):
                    assert method in rule.methods


class TestDispatchResolution:
    @pytest.fixture(autouse=True)
    def clear_cache(self):
        cache.clear(CACHE_AREA)
        yield
        cache.clear(CACHE_AREA)

    def test_returns_404_for_unknown_path(self):
        app = _make_app()
        lock = threading.Lock()
        register_api_route(app, lock)
        client = app.test_client()

        with patch("helpers.api.files") as mock_files:
            mock_files.get_abs_path = MagicMock(
                side_effect=lambda *args: "/fake/" + "/".join(str(a) for a in args)
            )
            mock_files.is_in_dir = MagicMock(return_value=True)
            mock_files.exists = MagicMock(return_value=False)
            mock_files.PLUGINS_DIR = "plugins"
            mock_files.USER_DIR = "usr"

            resp = client.post("/api/nonexistent")
            assert resp.status_code == 404
            assert b"API endpoint not found" in resp.data

    def test_returns_404_for_compat_unknown_path(self):
        app = _make_app()
        lock = threading.Lock()
        register_api_route(app, lock)
        client = app.test_client()

        with patch("helpers.api.files") as mock_files:
            mock_files.get_abs_path = MagicMock(
                side_effect=lambda *args: "/fake/" + "/".join(str(a) for a in args)
            )
            mock_files.is_in_dir = MagicMock(return_value=True)
            mock_files.exists = MagicMock(return_value=False)
            mock_files.PLUGINS_DIR = "plugins"
            mock_files.USER_DIR = "usr"

            resp = client.post("/nonexistent")
            assert resp.status_code == 404

    def test_resolves_builtin_handler(self):
        app = _make_app()
        lock = threading.Lock()
        register_api_route(app, lock)
        client = app.test_client()

        class FakeHandler(ApiHandler):
            @classmethod
            def requires_auth(cls):
                return False

            @classmethod
            def requires_csrf(cls):
                return False

            @classmethod
            def get_methods(cls):
                return ["POST"]

            async def process(self, input, request):
                return {"status": "ok"}

        with patch("helpers.api.files") as mock_files, \
             patch(LOAD_CLASSES_PATCH, return_value=[FakeHandler]):
            mock_files.get_abs_path = MagicMock(
                side_effect=lambda *args: "/fake/" + "/".join(str(a) for a in args)
            )
            mock_files.is_in_dir = MagicMock(return_value=True)
            mock_files.exists = MagicMock(return_value=True)
            mock_files.PLUGINS_DIR = "plugins"
            mock_files.USER_DIR = "usr"

            resp = client.post("/api/test_handler")
            assert resp.status_code == 200
            assert resp.json == {"status": "ok"}

    def test_compat_route_resolves_same_handler(self):
        app = _make_app()
        lock = threading.Lock()
        register_api_route(app, lock)
        client = app.test_client()

        class FakeHandler(ApiHandler):
            @classmethod
            def requires_auth(cls):
                return False

            @classmethod
            def requires_csrf(cls):
                return False

            @classmethod
            def get_methods(cls):
                return ["POST"]

            async def process(self, input, request):
                return {"compat": True}

        with patch("helpers.api.files") as mock_files, \
             patch(LOAD_CLASSES_PATCH, return_value=[FakeHandler]):
            mock_files.get_abs_path = MagicMock(
                side_effect=lambda *args: "/fake/" + "/".join(str(a) for a in args)
            )
            mock_files.is_in_dir = MagicMock(return_value=True)
            mock_files.exists = MagicMock(return_value=True)
            mock_files.PLUGINS_DIR = "plugins"
            mock_files.USER_DIR = "usr"

            resp = client.post("/test_handler")
            assert resp.status_code == 200
            assert resp.json == {"compat": True}

    def test_returns_405_for_wrong_method(self):
        app = _make_app()
        lock = threading.Lock()
        register_api_route(app, lock)
        client = app.test_client()

        class PostOnlyHandler(ApiHandler):
            @classmethod
            def requires_auth(cls):
                return False

            @classmethod
            def requires_csrf(cls):
                return False

            @classmethod
            def get_methods(cls):
                return ["POST"]

            async def process(self, input, request):
                return {}

        with patch("helpers.api.files") as mock_files, \
             patch(LOAD_CLASSES_PATCH, return_value=[PostOnlyHandler]):
            mock_files.get_abs_path = MagicMock(
                side_effect=lambda *args: "/fake/" + "/".join(str(a) for a in args)
            )
            mock_files.is_in_dir = MagicMock(return_value=True)
            mock_files.exists = MagicMock(return_value=True)
            mock_files.PLUGINS_DIR = "plugins"
            mock_files.USER_DIR = "usr"

            resp = client.get("/api/post_only")
            assert resp.status_code == 405

    def test_caches_handler_on_second_call(self):
        app = _make_app()
        lock = threading.Lock()
        register_api_route(app, lock)
        client = app.test_client()

        class CachedHandler(ApiHandler):
            call_count = 0

            @classmethod
            def requires_auth(cls):
                return False

            @classmethod
            def requires_csrf(cls):
                return False

            @classmethod
            def get_methods(cls):
                return ["POST"]

            async def process(self, input, request):
                CachedHandler.call_count += 1
                return {"count": CachedHandler.call_count}

        with patch("helpers.api.files") as mock_files, \
             patch(LOAD_CLASSES_PATCH, return_value=[CachedHandler]) as mock_load:
            mock_files.get_abs_path = MagicMock(
                side_effect=lambda *args: "/fake/" + "/".join(str(a) for a in args)
            )
            mock_files.is_in_dir = MagicMock(return_value=True)
            mock_files.exists = MagicMock(return_value=True)
            mock_files.PLUGINS_DIR = "plugins"
            mock_files.USER_DIR = "usr"

            resp1 = client.post("/api/cached")
            assert resp1.status_code == 200

            resp2 = client.post("/api/cached")
            assert resp2.status_code == 200

            assert mock_load.call_count == 1

    def test_cached_handler_still_checks_method(self):
        app = _make_app()
        lock = threading.Lock()
        register_api_route(app, lock)
        client = app.test_client()

        class PostOnlyHandler(ApiHandler):
            @classmethod
            def requires_auth(cls):
                return False

            @classmethod
            def requires_csrf(cls):
                return False

            @classmethod
            def get_methods(cls):
                return ["POST"]

            async def process(self, input, request):
                return {"ok": True}

        with patch("helpers.api.files") as mock_files, \
             patch(LOAD_CLASSES_PATCH, return_value=[PostOnlyHandler]):
            mock_files.get_abs_path = MagicMock(
                side_effect=lambda *args: "/fake/" + "/".join(str(a) for a in args)
            )
            mock_files.is_in_dir = MagicMock(return_value=True)
            mock_files.exists = MagicMock(return_value=True)
            mock_files.PLUGINS_DIR = "plugins"
            mock_files.USER_DIR = "usr"

            resp = client.post("/api/method_cached")
            assert resp.status_code == 200

            resp = client.get("/api/method_cached")
            assert resp.status_code == 405

    def test_resolves_plugin_handler(self):
        app = _make_app()
        lock = threading.Lock()
        register_api_route(app, lock)
        client = app.test_client()

        class PluginHandler(ApiHandler):
            @classmethod
            def requires_auth(cls):
                return False

            @classmethod
            def requires_csrf(cls):
                return False

            @classmethod
            def get_methods(cls):
                return ["POST"]

            async def process(self, input, request):
                return {"plugin": "memory"}

        with patch("helpers.api.files") as mock_files, \
             patch("helpers.plugins.find_plugin_dir", return_value="/fake/plugins/memory"), \
             patch(LOAD_CLASSES_PATCH, return_value=[PluginHandler]):
            mock_files.get_abs_path = MagicMock(
                side_effect=lambda *args: "/fake/" + "/".join(str(a) for a in args)
            )
            mock_files.is_in_dir = MagicMock(return_value=True)
            mock_files.exists = MagicMock(return_value=False)
            mock_files.PLUGINS_DIR = "plugins"
            mock_files.USER_DIR = "usr"

            with patch.object(Path, "is_file", return_value=True):
                resp = client.post("/api/plugins/memory/dashboard")
                assert resp.status_code == 200
                assert resp.json == {"plugin": "memory"}

    def test_plugin_handler_via_compat_route(self):
        app = _make_app()
        lock = threading.Lock()
        register_api_route(app, lock)
        client = app.test_client()

        class PluginHandler(ApiHandler):
            @classmethod
            def requires_auth(cls):
                return False

            @classmethod
            def requires_csrf(cls):
                return False

            @classmethod
            def get_methods(cls):
                return ["POST"]

            async def process(self, input, request):
                return {"plugin_compat": True}

        with patch("helpers.api.files") as mock_files, \
             patch("helpers.plugins.find_plugin_dir", return_value="/fake/plugins/memory"), \
             patch(LOAD_CLASSES_PATCH, return_value=[PluginHandler]):
            mock_files.get_abs_path = MagicMock(
                side_effect=lambda *args: "/fake/" + "/".join(str(a) for a in args)
            )
            mock_files.is_in_dir = MagicMock(return_value=True)
            mock_files.exists = MagicMock(return_value=False)
            mock_files.PLUGINS_DIR = "plugins"
            mock_files.USER_DIR = "usr"

            with patch.object(Path, "is_file", return_value=True):
                resp = client.post("/plugins/memory/dashboard")
                assert resp.status_code == 200
                assert resp.json == {"plugin_compat": True}


class TestSecurityDecorators:
    @pytest.fixture(autouse=True)
    def clear_cache(self):
        cache.clear(CACHE_AREA)
        yield
        cache.clear(CACHE_AREA)

    def test_auth_required_handler_redirects_when_not_authenticated(self, monkeypatch):
        monkeypatch.setattr("helpers.login.get_credentials_hash", lambda: "hash123")
        app = _make_app()
        lock = threading.Lock()
        register_api_route(app, lock)
        client = app.test_client()

        class AuthHandler(ApiHandler):
            @classmethod
            def requires_auth(cls):
                return True

            @classmethod
            def requires_csrf(cls):
                return False

            @classmethod
            def get_methods(cls):
                return ["POST"]

            async def process(self, input, request):
                return {"authenticated": True}

        with patch("helpers.api.files") as mock_files, \
             patch(LOAD_CLASSES_PATCH, return_value=[AuthHandler]):
            mock_files.get_abs_path = MagicMock(
                side_effect=lambda *args: "/fake/" + "/".join(str(a) for a in args)
            )
            mock_files.is_in_dir = MagicMock(return_value=True)
            mock_files.exists = MagicMock(return_value=True)
            mock_files.PLUGINS_DIR = "plugins"
            mock_files.USER_DIR = "usr"

            resp = client.post("/api/auth_test")
            assert resp.status_code == 302

    def test_no_auth_handler_allows_unauthenticated(self, monkeypatch):
        monkeypatch.setattr("helpers.login.get_credentials_hash", lambda: "hash123")
        app = _make_app()
        lock = threading.Lock()
        register_api_route(app, lock)
        client = app.test_client()

        class NoAuthHandler(ApiHandler):
            @classmethod
            def requires_auth(cls):
                return False

            @classmethod
            def requires_csrf(cls):
                return False

            @classmethod
            def get_methods(cls):
                return ["POST"]

            async def process(self, input, request):
                return {"open": True}

        with patch("helpers.api.files") as mock_files, \
             patch(LOAD_CLASSES_PATCH, return_value=[NoAuthHandler]):
            mock_files.get_abs_path = MagicMock(
                side_effect=lambda *args: "/fake/" + "/".join(str(a) for a in args)
            )
            mock_files.is_in_dir = MagicMock(return_value=True)
            mock_files.exists = MagicMock(return_value=True)
            mock_files.PLUGINS_DIR = "plugins"
            mock_files.USER_DIR = "usr"

            resp = client.post("/api/noauth_test")
            assert resp.status_code == 200
            assert resp.json == {"open": True}


class TestWatchdogRegistration:
    def test_register_watchdogs_calls_add_watchdog(self):
        with patch("helpers.watchdog.add_watchdog") as mock_add_watchdog, \
             patch("helpers.api.files") as mock_files:
            mock_files.get_abs_path = MagicMock(
                side_effect=lambda *args: "/fake/" + "/".join(str(a) for a in args)
            )
            mock_files.exists = MagicMock(return_value=True)
            mock_files.PLUGINS_DIR = "plugins"
            mock_files.USER_DIR = "usr"

            from helpers.api import register_watchdogs
            register_watchdogs()

            mock_add_watchdog.assert_called_once()
            call_args = mock_add_watchdog.call_args
            assert call_args.kwargs.get("id", call_args.args[0] if call_args.args else None) == "api_handlers"
            assert call_args.kwargs.get("patterns") == ["*.py"]
