from abc import abstractmethod
import inspect
import json
import socket
import struct
import threading
from functools import wraps
from pathlib import Path
from typing import Union, TypedDict, Dict, Any
from flask import (
    Request,
    Response,
    Flask,
    jsonify,
    session,
    request,
    send_file,
    redirect,
    url_for,
)
from werkzeug.wrappers.response import Response as BaseResponse
from agent import AgentContext
from initialize import initialize_agent
from helpers.print_style import PrintStyle
from helpers.errors import format_error
from helpers import files, cache

ThreadLockType = Union[threading.Lock, threading.RLock]

CACHE_AREA = "api_handlers(api)"

Input = dict
Output = Union[Dict[str, Any], Response, TypedDict]  # type: ignore


class ApiHandler:
    def __init__(self, app: Flask, thread_lock: ThreadLockType):
        self.app = app
        self.thread_lock = thread_lock

    @classmethod
    def requires_loopback(cls) -> bool:
        return False

    @classmethod
    def requires_api_key(cls) -> bool:
        return False

    @classmethod
    def requires_auth(cls) -> bool:
        return True

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["POST"]

    @classmethod
    def requires_csrf(cls) -> bool:
        return cls.requires_auth()

    @abstractmethod
    async def process(self, input: Input, request: Request) -> Output:
        pass

    async def handle_request(self, request: Request) -> Response:
        try:
            input_data: Input = {}
            if request.is_json:
                try:
                    if request.data:
                        input_data = request.get_json()
                except Exception as e:
                    PrintStyle().print(f"Error parsing JSON: {str(e)}")
                    input_data = {}
            else:
                input_data = {}

            output = await self.process(input_data, request)

            if isinstance(output, Response):
                return output
            else:
                response_json = json.dumps(output)
                return Response(
                    response=response_json, status=200, mimetype="application/json"
                )

        except Exception as e:
            error = format_error(e)
            PrintStyle.error(f"API error: {error}")
            return Response(response=error, status=500, mimetype="text/plain")

    def handle_request_sync(self, request: Request) -> Response:
        """
        Run async API handlers through an explicit event loop per request.
        This avoids relying on Flask's implicit async bridge under WSGI,
        which can retain event-loop descriptors under heavy traffic.
        """
        import asyncio

        return asyncio.run(self.handle_request(request))

    def use_context(self, ctxid: str, create_if_not_exists: bool = True):
        with self.thread_lock:
            if not ctxid:
                first = AgentContext.first()
                if first:
                    AgentContext.use(first.id)
                    return first
                context = AgentContext(config=initialize_agent(), set_current=True)
                return context
            got = AgentContext.use(ctxid)
            if got:
                return got
            if create_if_not_exists:
                context = AgentContext(
                    config=initialize_agent(), id=ctxid, set_current=True
                )
                return context
            else:
                raise Exception(f"Context {ctxid} not found")


# ---------------------------------------------------------------------------
# Security helpers & decorators
# ---------------------------------------------------------------------------

def is_loopback_address(address: str) -> bool:
    loopback_checker = {
        socket.AF_INET: lambda x: (
            struct.unpack("!I", socket.inet_aton(x))[0] >> (32 - 8)
        )
        == 127,
        socket.AF_INET6: lambda x: x == "::1",
    }
    address_type = "hostname"
    try:
        socket.inet_pton(socket.AF_INET6, address)
        address_type = "ipv6"
    except socket.error:
        try:
            socket.inet_pton(socket.AF_INET, address)
            address_type = "ipv4"
        except socket.error:
            address_type = "hostname"

    if address_type == "ipv4":
        return loopback_checker[socket.AF_INET](address)
    elif address_type == "ipv6":
        return loopback_checker[socket.AF_INET6](address)
    else:
        for family in (socket.AF_INET, socket.AF_INET6):
            try:
                r = socket.getaddrinfo(address, None, family, socket.SOCK_STREAM)
            except socket.gaierror:
                return False
            for family, _, _, _, sockaddr in r:
                if not loopback_checker[family](sockaddr[0]):
                    return False
        return True


def requires_api_key(f):
    if inspect.iscoroutinefunction(f):
        @wraps(f)
        async def decorated_async(*args, **kwargs):
            from helpers.settings import get_settings

            valid_api_key = get_settings()["mcp_server_token"]

            if api_key := request.headers.get("X-API-KEY"):
                if api_key != valid_api_key:
                    return Response("Invalid API key", 401)
            elif request.json and request.json.get("api_key"):
                api_key = request.json.get("api_key")
                if api_key != valid_api_key:
                    return Response("Invalid API key", 401)
            else:
                return Response("API key required", 401)
            return await f(*args, **kwargs)

        return decorated_async

    @wraps(f)
    def decorated_sync(*args, **kwargs):
        from helpers.settings import get_settings

        valid_api_key = get_settings()["mcp_server_token"]

        if api_key := request.headers.get("X-API-KEY"):
            if api_key != valid_api_key:
                return Response("Invalid API key", 401)
        elif request.json and request.json.get("api_key"):
            api_key = request.json.get("api_key")
            if api_key != valid_api_key:
                return Response("Invalid API key", 401)
        else:
            return Response("API key required", 401)
        return f(*args, **kwargs)

    return decorated_sync


def requires_loopback(f):
    if inspect.iscoroutinefunction(f):
        @wraps(f)
        async def decorated_async(*args, **kwargs):
            if not is_loopback_address(request.remote_addr):
                return Response("Access denied.", 403, {})
            return await f(*args, **kwargs)

        return decorated_async

    @wraps(f)
    def decorated_sync(*args, **kwargs):
        if not is_loopback_address(request.remote_addr):
            return Response("Access denied.", 403, {})
        return f(*args, **kwargs)

    return decorated_sync


def requires_auth(f):
    if inspect.iscoroutinefunction(f):
        @wraps(f)
        async def decorated_async(*args, **kwargs):
            from helpers import login

            user_pass_hash = login.get_credentials_hash()
            if not user_pass_hash:
                return await f(*args, **kwargs)
            if session.get("authentication") != user_pass_hash:
                return redirect(url_for("login_handler"))
            return await f(*args, **kwargs)

        return decorated_async

    @wraps(f)
    def decorated_sync(*args, **kwargs):
        from helpers import login

        user_pass_hash = login.get_credentials_hash()
        if not user_pass_hash:
            return f(*args, **kwargs)
        if session.get("authentication") != user_pass_hash:
            return redirect(url_for("login_handler"))
        return f(*args, **kwargs)

    return decorated_sync


def csrf_protect(f):
    if inspect.iscoroutinefunction(f):
        @wraps(f)
        async def decorated_async(*args, **kwargs):
            from helpers import runtime

            token = session.get("csrf_token")
            header = request.headers.get("X-CSRF-Token")
            cookie = request.cookies.get(
                "csrf_token_" + runtime.get_persistent_id()[:16]
            )
            sent = header or cookie
            if not token or not sent or token != sent:
                return Response("CSRF token missing or invalid", 403)
            return await f(*args, **kwargs)

        return decorated_async

    @wraps(f)
    def decorated_sync(*args, **kwargs):
        from helpers import runtime

        token = session.get("csrf_token")
        header = request.headers.get("X-CSRF-Token")
        cookie = request.cookies.get(
            "csrf_token_" + runtime.get_persistent_id()[:16]
        )
        sent = header or cookie
        if not token or not sent or token != sent:
            return Response("CSRF token missing or invalid", 403)
        return f(*args, **kwargs)

    return decorated_sync


# ---------------------------------------------------------------------------
# Lazy API dispatch
# ---------------------------------------------------------------------------

def register_api_route(app: Flask, lock: ThreadLockType) -> None:

    async def _dispatch(path: str) -> BaseResponse:
        from helpers.modules import load_classes_from_file
        from helpers import plugins

        cached = cache.get(CACHE_AREA, path)
        if cached is not None:
            handler_fn, allowed_methods = cached
            if request.method not in allowed_methods:
                return Response(
                    f"Method {request.method} not allowed for: {path}", 405
                )
            return await handler_fn()

        handler_cls: type[ApiHandler] | None = None

        builtin_file = files.get_abs_path(f"api/{path}.py")
        if files.is_in_dir(builtin_file, files.get_abs_path("api")) and files.exists(
            builtin_file
        ):
            classes = load_classes_from_file(builtin_file, ApiHandler)
            if classes:
                handler_cls = classes[0]

        if handler_cls is None and path.startswith("plugins/"):
            parts = path.split("/", 2)
            if len(parts) == 3:
                _, plugin_name, handler_name = parts
                plugin_dir = plugins.find_plugin_dir(plugin_name)
                if plugin_dir:
                    api_dir = Path(plugin_dir) / "api"
                    plugin_file = api_dir / f"{handler_name}.py"
                    if plugin_file.resolve().is_relative_to(api_dir.resolve()) and plugin_file.is_file():
                        classes = load_classes_from_file(
                            str(plugin_file), ApiHandler
                        )
                        if classes:
                            handler_cls = classes[0]

        if handler_cls is None:
            return Response(f"API endpoint not found: {path}", 404)

        if request.method not in handler_cls.get_methods():
            return Response(
                f"Method {request.method} not allowed for: {path}", 405
            )

        async def call_handler() -> BaseResponse:
            instance = handler_cls(app, lock)  # type: ignore[misc]
            return await instance.handle_request(request=request)

        handler_fn = call_handler
        if handler_cls.requires_csrf():
            handler_fn = csrf_protect(handler_fn)
        if handler_cls.requires_api_key():
            handler_fn = requires_api_key(handler_fn)
        if handler_cls.requires_auth():
            handler_fn = requires_auth(handler_fn)
        if handler_cls.requires_loopback():
            handler_fn = requires_loopback(handler_fn)

        cache.add(CACHE_AREA, path, (handler_fn, handler_cls.get_methods()))
        return await handler_fn()

    app.add_url_rule(
        "/api/<path:path>",
        "api_dispatch",
        _dispatch,
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    )


def register_watchdogs() -> None:
    from helpers import watchdog

    def on_api_change(items: list[watchdog.WatchItem]) -> None:
        PrintStyle.debug("API endpoint watchdog triggered:", items)
        cache.clear(CACHE_AREA)

    roots = [files.get_abs_path("api")]
    plugins_dir = files.get_abs_path(files.PLUGINS_DIR)
    if files.exists(plugins_dir):
        roots.append(plugins_dir)
    user_plugins_dir = files.get_abs_path(files.USER_DIR, files.PLUGINS_DIR)
    if files.exists(user_plugins_dir):
        roots.append(user_plugins_dir)

    watchdog.add_watchdog(
        "api_handlers",
        roots=roots,
        patterns=["*.py"],
        handler=on_api_change,
    )
