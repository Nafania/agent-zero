import sys
import threading
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from helpers.websocket import (
    WebSocketHandler,
    WebSocketResult,
    SingletonInstantiationError,
)


class _FakeSocketIO:
    async def emit(self, *_args, **_kwargs):
        return None
    async def disconnect(self, *_args, **_kwargs):
        return None


class _TestHandler(WebSocketHandler):
    async def process_event(self, event_type: str, data: dict, sid: str) -> None:
        return None


def _make_handler() -> _TestHandler:
    _TestHandler._reset_instance_for_testing()
    return _TestHandler.get_instance(_FakeSocketIO(), threading.RLock())


def test_websocket_result_ok_clones_payload():
    payload = {"value": 1}
    result = WebSocketResult.ok(payload)
    assert result.as_result(handler_id="handler", fallback_correlation_id="corr")["data"] == payload
    payload["value"] = 2
    assert result.as_result(handler_id="handler", fallback_correlation_id="corr")["data"] == {"value": 1}


def test_handler_direct_instantiation_disallowed():
    with pytest.raises(SingletonInstantiationError):
        _TestHandler(_FakeSocketIO(), threading.RLock())


def test_get_instance_returns_singleton():
    _TestHandler._reset_instance_for_testing()
    socketio = _FakeSocketIO()
    lock = threading.RLock()
    first = _TestHandler.get_instance(socketio, lock)
    second = _TestHandler.get_instance(None, None)
    assert first is second


@pytest.mark.asyncio
async def test_webui_handler_routes_state_request():
    from helpers.websocket_manager import WebSocketManager
    from websocket_handlers.webui_handler import WebuiHandler
    from helpers.state_monitor import _reset_state_monitor_for_testing

    _reset_state_monitor_for_testing()
    WebuiHandler._reset_instance_for_testing()

    socketio = _FakeSocketIO()
    lock = threading.RLock()
    manager = WebSocketManager(socketio, lock)
    handler = WebuiHandler.get_instance(socketio, lock)
    namespace = "/webui"
    manager.register_handlers({namespace: [handler]})
    await manager.handle_connect(namespace, "sid-1")

    response = await manager.route_event(
        namespace,
        "state_request",
        {
            "correlationId": "smoke-1",
            "ts": "2025-12-28T00:00:00.000Z",
            "data": {
                "context": None,
                "log_from": 0,
                "notifications_from": 0,
                "timezone": "UTC",
            },
        },
        "sid-1",
    )

    assert response["correlationId"] == "smoke-1"
    assert response["results"] and response["results"][0]["ok"] is True
    await manager.handle_disconnect(namespace, "sid-1")


@pytest.mark.asyncio
async def test_webui_handler_returns_error_for_invalid_state_request():
    from helpers.websocket_manager import WebSocketManager
    from websocket_handlers.webui_handler import WebuiHandler
    from helpers.state_monitor import _reset_state_monitor_for_testing

    _reset_state_monitor_for_testing()
    WebuiHandler._reset_instance_for_testing()

    socketio = _FakeSocketIO()
    lock = threading.RLock()
    manager = WebSocketManager(socketio, lock)
    handler = WebuiHandler.get_instance(socketio, lock)
    namespace = "/webui"
    manager.register_handlers({namespace: [handler]})
    await manager.handle_connect(namespace, "sid-1")

    response = await manager.route_event(
        namespace,
        "state_request",
        {
            "correlationId": "bad-1",
            "ts": "2025-12-28T00:00:00.000Z",
            "data": "not-a-dict",
        },
        "sid-1",
    )

    assert response["correlationId"] == "bad-1"
    result = response["results"][0]
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_REQUEST"
    await manager.handle_disconnect(namespace, "sid-1")
