# A5: WebSocket Handler Extension-Based Architecture

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace monolithic `StateSyncHandler` with a thin extension-driven `WebuiHandler`, and simplify handler registration by removing per-event-type indexing.

**Architecture:** Upstream replaced `state_sync_handler.py` (which hardcoded state-sync logic) with `webui_handler.py` that delegates all lifecycle events (connect, disconnect, process_event) to the extension system via `call_extensions_async`. The state-sync logic moves into three extension files. Handler registration no longer indexes by event type — all events are dispatched to the namespace's handlers via the catch-all `*` event. `WebSocketHandler.get_event_types()` is removed as an abstract method.

**Tech Stack:** Python, Socket.IO, Agent Zero extension system (`call_extensions_async`)

**Worktree:** `.worktrees/upstream-a5-ws-extensions` (branch `upstream/a5-ws-extensions`)

---

## Scope Notes

The phase-3 spec lists four A5 work items. Items 2-4 are **not implemented in upstream** and are deferred:

| Spec item | Status | Rationale |
|-----------|--------|-----------|
| 1. Add `webui_handler.py`, reconcile with `state_sync` | **This plan** | Core upstream change |
| 2. Plugin WS handler discovery | **Deferred** | Upstream doesn't scan plugin `websocket_handlers/` either |
| 3. `@extensible` on WS registration | **Deferred** | Upstream has no `@extensible` on WS functions |
| 4. Watchdog for WS handler cache | **Deferred** | Not present in upstream |

---

## File Map

### Modified files
- `helpers/websocket.py` — Remove `get_event_types()` abstract method, replace `validate_event_types()` with `validate_event_type()`
- `helpers/websocket_manager.py` — Flatten handler indexing (remove per-event dict), add shared manager singleton, add `send_data()` method
- `run_ui.py` — Add `set_shared_websocket_manager()`, remove per-event registration loop
- `websocket_handlers/_default.py` — Remove `get_event_types()` override
- `websocket_handlers/hello_handler.py` — Remove `get_event_types()` override
- `websocket_handlers/dev_websocket_test_handler.py` — Remove `get_event_types()` override
- `webui/components/sync/sync-store.js` — Rename namespace `/state_sync` → `/webui`
- `webui/components/settings/developer/websocket-test-store.js` — Rename namespace `/state_sync` → `/webui`

### Created files
- `websocket_handlers/webui_handler.py` — Thin handler using `call_extensions_async`
- `extensions/python/webui_ws_connect/_10_state_sync.py` — State monitor bind/register on WS connect
- `extensions/python/webui_ws_disconnect/_10_state_sync.py` — State monitor unregister on WS disconnect
- `extensions/python/webui_ws_event/_10_state_sync.py` — State request processing logic
- `extensions/webui/webui_ws_push/clear_cache.js` — Frontend cache-clear via WS push

### Deleted files
- `websocket_handlers/state_sync_handler.py` — Replaced by `webui_handler.py` + extensions

### Test files to modify
- `tests/helpers/test_websocket.py` — Update for removed `get_event_types`/`validate_event_types`, add `validate_event_type` tests
- `tests/helpers/test_websocket_manager.py` — Update for flat handler indexing, add `send_data`/shared manager tests
- `tests/helpers/test_websocket_handlers.py` — Remove `get_event_types` references
- `tests/helpers/test_websocket_namespace_discovery.py` — Remove `get_event_types` references
- `tests/helpers/test_websocket_namespace_security.py` — Remove `get_event_types` references
- `tests/helpers/test_websocket_namespaces.py` — Remove `get_event_types` references, update `/state_sync` → `/webui`
- `tests/helpers/test_websocket_root_namespace.py` — Remove `get_event_types` references
- `tests/helpers/test_websocket_namespaces_integration.py` — Remove `get_event_types` references
- `tests/helpers/test_state_sync_handler.py` — Update imports to `WebuiHandler`, update namespace to `/webui`
- `tests/helpers/test_state_sync_welcome_screen.py` — Update imports to `WebuiHandler`, update namespace to `/webui`
- `tests/helpers/test_state_monitor.py` — Update namespace `/state_sync` → `/webui`
- `tests/test_websocket_handlers.py` — Create (from upstream), tests for `WebuiHandler` + state_request routing

---

## Task 1: Update `helpers/websocket.py` — Remove event-type declaration interface

**Files:**
- Modify: `helpers/websocket.py`
- Test: `tests/helpers/test_websocket.py`

- [ ] **Step 1: Update `WebSocketHandler` class in `helpers/websocket.py`**

Remove the `get_event_types()` abstract method and replace `validate_event_types()` with `validate_event_type()`:

```python
# REMOVE these methods from WebSocketHandler:
#   @classmethod
#   @abstractmethod
#   def get_event_types(cls) -> list[str]: ...
#
#   @classmethod
#   def validate_event_types(cls, event_types: Iterable[str]) -> list[str]: ...

# REPLACE with:
    @classmethod
    def validate_event_type(cls, event_type: str) -> str:
        """Validate a runtime event name before dispatch."""

        if not isinstance(event_type, str):
            raise TypeError("Event type must be a string")
        if not _EVENT_NAME_PATTERN.fullmatch(event_type):
            raise ValueError(
                f"Invalid event type '{event_type}' – must match lowercase_snake_case"
            )
        if event_type in _RESERVED_EVENT_NAMES:
            raise ValueError(
                f"Event type '{event_type}' is reserved by Socket.IO and cannot be used"
            )
        return event_type
```

Also update the class docstring:
```python
    """Base class for WebSocket event handlers.

    The interface mirrors :class:`helpers.api.ApiHandler` with declarative
    security configuration and lifecycle hooks. Handlers are namespace-wide:
    every inbound event for the bound namespace is dispatched to
    :meth:`process_event`, which decides whether and how to respond.
    """
```

Remove `Iterable` from imports if no longer needed.

- [ ] **Step 2: Update tests in `tests/helpers/test_websocket.py`**

Tests that call `get_event_types()` or `validate_event_types()` must be updated:
- Remove test classes/methods for `validate_event_types()` (batch validation, duplicates, reserved names, empty list)
- Add tests for `validate_event_type()`:
  - Valid snake_case event name returns the name
  - Non-string raises `TypeError`
  - Invalid format raises `ValueError`
  - Reserved Socket.IO name raises `ValueError`
- Remove `get_event_types()` overrides from test handler classes — `process_event` is the only required abstract method now
- Any test `_TestHandler` that defines `get_event_types` can keep it as a regular method, but it's no longer abstract

- [ ] **Step 3: Run tests to verify**

Run: `pytest tests/helpers/test_websocket.py -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add helpers/websocket.py tests/helpers/test_websocket.py
git commit -m "refactor: remove get_event_types, replace validate_event_types with validate_event_type"
```

---

## Task 2: Update `helpers/websocket_manager.py` — Flatten handler indexing

**Files:**
- Modify: `helpers/websocket_manager.py`
- Test: `tests/helpers/test_websocket_manager.py`

- [ ] **Step 1: Add shared manager singleton at module level**

Add at module level after `BUFFER_TTL`:

```python
_shared_websocket_manager: WebSocketManager | None = None


async def send_data(
    event_name: str,
    data: dict[str, Any],
    endpoint_name: str = "/webui",
    connection_id: str | None = None,
) -> None:
    manager = get_shared_websocket_manager()
    print(f"Sending data to {endpoint_name}/{event_name} with data {data}")
    await manager.send_data(endpoint_name, event_name, data, connection_id)


def set_shared_websocket_manager(manager: "WebSocketManager") -> None:
    global _shared_websocket_manager
    _shared_websocket_manager = manager


def get_shared_websocket_manager() -> "WebSocketManager":
    manager = _shared_websocket_manager
    if manager is None:
        raise RuntimeError("Shared WebSocketManager has not been initialized")
    return manager
```

- [ ] **Step 2: Change `self.handlers` type from nested dict to flat dict**

```python
# OLD:
self.handlers: defaultdict[str, defaultdict[str, List[WebSocketHandler]]] = defaultdict(
    lambda: defaultdict(list)
)

# NEW:
self.handlers: defaultdict[str, List[WebSocketHandler]] = defaultdict(list)
```

- [ ] **Step 3: Update `register_handlers()` — remove per-event registration**

Remove `get_event_types()`, `validate_event_types()` calls, per-event indexing. Replace with simple list append:

```python
def register_handlers(self, handlers_by_namespace):
    for namespace, handlers in handlers_by_namespace.items():
        for handler in handlers:
            handler.bind_manager(self, namespace=namespace)
            if _ws_debug_enabled():
                PrintStyle.info(
                    "Registered WebSocket handler %s namespace=%s"
                    % (handler.identifier, namespace)
                )
            existing = self.handlers.get(namespace, [])
            if handler in existing:
                PrintStyle.warning(
                    f"Duplicate handler registration for namespace '{namespace}'"
                )
            self.handlers[namespace].append(handler)
            self._debug(
                f"Registered handler {handler.identifier} namespace={namespace}"
            )
```

- [ ] **Step 4: Update `iter_event_types()` to return empty list**

```python
def iter_event_types(self, namespace: str) -> Iterable[str]:
    return []
```

- [ ] **Step 5: Update `_select_handlers()` — remove `event_type` parameter**

```python
def _select_handlers(
    self,
    namespace: str,
    *,
    include: Set[str] | None,
    exclude: Set[str] | None,
) -> tuple[list[WebSocketHandler], Set[str]]:
    registered = self.handlers.get(namespace, [])
    # ... rest stays the same
```

- [ ] **Step 6: Update `route_event()` — validate event type at runtime, lookup by namespace only**

Add runtime validation before handler lookup:

```python
try:
    WebSocketHandler.validate_event_type(event_type)
except (TypeError, ValueError) as exc:
    error = self._build_error_result(
        handler_id=handler_id or self._identifier,
        code="INVALID_EVENT",
        message=str(exc),
        correlation_id=correlation_id,
    )
    if ack:
        ack({"correlationId": correlation_id, "results": [error]})
    return {"correlationId": correlation_id, "results": [error]}

registered = self.handlers.get(namespace, [])
```

Update the `_select_handlers` call to not pass `event_type`:
```python
selected_handlers, _ = self._select_handlers(
    namespace, include=include, exclude=exclude
)
```

Update the "no handlers" error message:
```python
message=f"No handler for namespace '{namespace}'",
```

- [ ] **Step 7: Update `_run_lifecycle()` — iterate flat handler list**

```python
async def _run_lifecycle(
    self, namespace: str, fn: Callable[[WebSocketHandler], Any]
) -> None:
    seen: Set[WebSocketHandler] = set()
    coros: list[Any] = []
    for handler in self.handlers.get(namespace, []):
        if handler in seen:
            continue
        seen.add(handler)
        coros.append(self._get_handler_worker().execute_inside(fn, handler))
    if coros:
        await asyncio.gather(*coros, return_exceptions=True)
```

- [ ] **Step 8: Add `send_data()` method to `WebSocketManager`**

```python
async def send_data(
    self,
    endpoint_name: str,
    event_name: str,
    data: dict[str, Any],
    connection_id: str | None = None,
) -> None:
    if connection_id is not None:
        await self.emit_to(endpoint_name, connection_id, event_name, data)
        return
    await self.broadcast(endpoint_name, event_name, data)
```

- [ ] **Step 9: Update tests in `tests/helpers/test_websocket_manager.py`**

- Remove all references to `get_event_types()` from test handler classes
- Update handler registration assertions (no per-event validation)
- Update `_select_handlers` calls to not pass `event_type`
- Add tests for `set_shared_websocket_manager()` / `get_shared_websocket_manager()`
- Add test for `send_data()` method
- Update route_event tests that expect per-event handler matching

- [ ] **Step 10: Run tests**

Run: `pytest tests/helpers/test_websocket_manager.py -v`
Expected: All tests pass

- [ ] **Step 11: Commit**

```bash
git add helpers/websocket_manager.py tests/helpers/test_websocket_manager.py
git commit -m "refactor: flatten handler indexing, add shared manager singleton"
```

---

## Task 3: Create `webui_handler.py` and state-sync extensions

**Files:**
- Create: `websocket_handlers/webui_handler.py`
- Create: `extensions/python/webui_ws_connect/_10_state_sync.py`
- Create: `extensions/python/webui_ws_disconnect/_10_state_sync.py`
- Create: `extensions/python/webui_ws_event/_10_state_sync.py`
- Create: `extensions/webui/webui_ws_push/clear_cache.js`
- Delete: `websocket_handlers/state_sync_handler.py`

- [ ] **Step 1: Create `websocket_handlers/webui_handler.py`**

```python
from helpers.websocket import WebSocketHandler, WebSocketResult
from helpers import extension


class WebuiHandler(WebSocketHandler):
    async def on_connect(self, sid: str) -> None:
        await extension.call_extensions_async(
            "webui_ws_connect", agent=None, instance=self, sid=sid
        )

    async def on_disconnect(self, sid: str) -> None:
        await extension.call_extensions_async(
            "webui_ws_disconnect", agent=None, instance=self, sid=sid
        )

    async def process_event(
        self, event_type: str, data: dict, sid: str
    ) -> dict | WebSocketResult | None:
        response_data: dict = {}

        await extension.call_extensions_async(
            "webui_ws_event",
            agent=None,
            instance=self,
            sid=sid,
            event_type=event_type,
            data=data,
            response_data=response_data,
        )

        return self.result_ok(
            response_data,
            correlation_id=data.get("correlationId"),
        )
```

- [ ] **Step 2: Create `extensions/python/webui_ws_connect/_10_state_sync.py`**

```python
from helpers.extension import Extension
from helpers.print_style import PrintStyle
from helpers.state_monitor import get_state_monitor, _ws_debug_enabled


class StateSync(Extension):
    async def execute(self, instance=None, sid: str = "", **kwargs):
        if instance is None:
            return

        monitor = get_state_monitor()
        monitor.bind_manager(instance.manager, handler_id=instance.identifier)
        monitor.register_sid(instance.namespace, sid)
        if _ws_debug_enabled():
            PrintStyle.debug(f"[WebuiHandler] connect sid={sid}")
```

- [ ] **Step 3: Create `extensions/python/webui_ws_disconnect/_10_state_sync.py`**

```python
from helpers.extension import Extension
from helpers.print_style import PrintStyle
from helpers.state_monitor import get_state_monitor, _ws_debug_enabled


class StateSync(Extension):
    async def execute(self, instance=None, sid: str = "", **kwargs):
        if instance is None:
            return

        get_state_monitor().unregister_sid(instance.namespace, sid)
        if _ws_debug_enabled():
            PrintStyle.debug(f"[WebuiHandler] disconnect sid={sid}")
```

- [ ] **Step 4: Create `extensions/python/webui_ws_event/_10_state_sync.py`**

```python
from helpers import runtime
from helpers.extension import Extension
from helpers.print_style import PrintStyle
from helpers.state_monitor import get_state_monitor, _ws_debug_enabled
from helpers.state_snapshot import (
    StateRequestValidationError,
    parse_state_request_payload,
)


class StateSync(Extension):
    async def execute(
        self,
        instance=None,
        sid: str = "",
        event_type: str = "",
        data: dict | None = None,
        response_data: dict | None = None,
        **kwargs,
    ):
        if instance is None or data is None:
            return

        if event_type != "state_request":
            return

        correlation_id = data.get("correlationId")
        try:
            request = parse_state_request_payload(data)
        except StateRequestValidationError as exc:
            PrintStyle.warning(
                f"[WebuiHandler] INVALID_REQUEST sid={sid} reason={exc.reason} details={exc.details!r}"
            )
            if response_data is not None:
                response_data["code"] = "INVALID_REQUEST"
                response_data["message"] = str(exc)
            return

        if _ws_debug_enabled():
            PrintStyle.debug(
                f"[WebuiHandler] state_request sid={sid} context={request.context!r} "
                f"log_from={request.log_from} notifications_from={request.notifications_from} timezone={request.timezone!r} "
                f"correlation_id={correlation_id}"
            )

        seq_base = 1
        monitor = get_state_monitor()
        monitor.update_projection(
            instance.namespace,
            sid,
            request=request,
            seq_base=seq_base,
        )
        monitor.mark_dirty(
            instance.namespace,
            sid,
            reason="webui_ws_event.StateSync.state_request",
        )
        if _ws_debug_enabled():
            PrintStyle.debug(
                f"[WebuiHandler] state_request accepted sid={sid} seq_base={seq_base}"
            )

        if response_data is not None:
            response_data["runtime_epoch"] = runtime.get_runtime_id()
            response_data["seq_base"] = seq_base
```

- [ ] **Step 5: Create `extensions/webui/webui_ws_push/clear_cache.js`**

```javascript
import { clear, clear_all } from "/js/cache.js";

export default async function clearCache(eventType, envelope) {
  try {
    if (eventType == "clear_cache") {
      const areas = envelope?.data?.areas || [];
      console.log("Clearing caches", areas);
      if (areas.length > 0) {
        for (const area of areas) {
          clear(area);
        }
      } else {
        clear_all();
      }
    }
  } catch (e) {
    console.error(e);
  }
}
```

- [ ] **Step 6: Delete `websocket_handlers/state_sync_handler.py`**

- [ ] **Step 7: Commit**

```bash
git add websocket_handlers/webui_handler.py \
  extensions/python/webui_ws_connect/_10_state_sync.py \
  extensions/python/webui_ws_disconnect/_10_state_sync.py \
  extensions/python/webui_ws_event/_10_state_sync.py \
  extensions/webui/webui_ws_push/clear_cache.js
git rm websocket_handlers/state_sync_handler.py
git commit -m "feat: replace StateSyncHandler with WebuiHandler + extensions"
```

---

## Task 4: Update remaining handlers — remove `get_event_types()`

**Files:**
- Modify: `websocket_handlers/_default.py`
- Modify: `websocket_handlers/hello_handler.py`
- Modify: `websocket_handlers/dev_websocket_test_handler.py`

- [ ] **Step 1: Remove `get_event_types()` from `_default.py`**

Remove the method. The handler's `process_event()` already handles all events for the `/` namespace.

- [ ] **Step 2: Remove `get_event_types()` from `hello_handler.py`**

Remove the method override.

- [ ] **Step 3: Remove `get_event_types()` from `dev_websocket_test_handler.py`**

Remove the method override.

- [ ] **Step 4: Commit**

```bash
git add websocket_handlers/_default.py websocket_handlers/hello_handler.py websocket_handlers/dev_websocket_test_handler.py
git commit -m "refactor: remove get_event_types from all handlers"
```

---

## Task 5: Update `run_ui.py` — shared manager + simplified WS registration

**Files:**
- Modify: `run_ui.py`

- [ ] **Step 1: Update import to include `set_shared_websocket_manager`**

```python
from helpers.websocket_manager import WebSocketManager, set_shared_websocket_manager
```

- [ ] **Step 2: Call `set_shared_websocket_manager()` after creating `websocket_manager`**

Add after `websocket_manager = WebSocketManager(socketio_server, lock)`:
```python
set_shared_websocket_manager(websocket_manager)
```

- [ ] **Step 3: Remove per-event registration in `configure_websocket_namespaces()`**

Remove the loop:
```python
# REMOVE:
for _event_type in websocket_manager.iter_event_types(namespace):
    _register_socketio_event(_event_type)
```

And remove the `_register_socketio_event` helper function entirely. Only the `@socketio_server.on("*", ...)` catch-all remains.

- [ ] **Step 4: Commit**

```bash
git add run_ui.py
git commit -m "refactor: use shared WS manager, remove per-event registration"
```

---

## Task 5b: Update frontend JS — namespace `/state_sync` → `/webui`

**Files:**
- Modify: `webui/components/sync/sync-store.js`
- Modify: `webui/components/settings/developer/websocket-test-store.js`

- [ ] **Step 1: Update `sync-store.js`**

```javascript
// OLD:
const stateSocket = getNamespacedClient("/state_sync");
// NEW:
const stateSocket = getNamespacedClient("/webui");
```

- [ ] **Step 2: Update `websocket-test-store.js`**

```javascript
// OLD:
const stateSocket = getNamespacedClient("/state_sync");
// NEW:
const stateSocket = getNamespacedClient("/webui");
```

- [ ] **Step 3: Commit**

```bash
git add webui/components/sync/sync-store.js webui/components/settings/developer/websocket-test-store.js
git commit -m "fix: rename WS namespace /state_sync to /webui"
```

---

## Task 6: Update remaining test files

**Files:**
- Modify: `tests/helpers/test_websocket_handlers.py`
- Modify: `tests/helpers/test_websocket_namespace_discovery.py`
- Modify: `tests/helpers/test_websocket_namespace_security.py`
- Modify: `tests/helpers/test_websocket_namespaces.py`
- Modify: `tests/helpers/test_websocket_root_namespace.py`
- Modify: `tests/helpers/test_websocket_namespaces_integration.py`
- Modify: `tests/helpers/test_state_sync_handler.py`
- Modify: `tests/helpers/test_state_sync_welcome_screen.py`
- Create: `tests/test_websocket_handlers.py`

- [ ] **Step 1: Update `test_websocket_handlers.py`**

Remove `get_event_types()` overrides from test handler stubs.

- [ ] **Step 2: Update `test_websocket_namespace_discovery.py`**

Remove `get_event_types()` overrides and assertions about event type validation during discovery.

- [ ] **Step 3: Update `test_websocket_namespace_security.py`**

Remove `get_event_types()` from mock handler classes.

- [ ] **Step 4: Update `test_websocket_namespaces.py`**

Remove `get_event_types()` from mock handler classes, update assertions that reference event types.

- [ ] **Step 5: Update `test_websocket_root_namespace.py`**

Remove `get_event_types()` from mock handler classes.

- [ ] **Step 6: Update `test_websocket_namespaces_integration.py`**

Remove `get_event_types()` references.

- [ ] **Step 7: Update `test_state_sync_handler.py`**

Change imports from `websocket_handlers.state_sync_handler.StateSyncHandler` to `websocket_handlers.webui_handler.WebuiHandler`. Update namespace from `/state_sync` to `/webui`.

- [ ] **Step 8: Update `test_state_sync_welcome_screen.py`**

Change imports from `websocket_handlers.state_sync_handler.StateSyncHandler` to `websocket_handlers.webui_handler.WebuiHandler`. Update namespace to `/webui`.

- [ ] **Step 8b: Update `test_state_monitor.py`**

Change namespace from `/state_sync` to `/webui`.

- [ ] **Step 9: Create `tests/test_websocket_handlers.py`**

Port from upstream — smoke test that `WebuiHandler` processes a `state_request` event via extensions:

```python
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


def test_websocket_result_error_contains_metadata():
    result = WebSocketResult.error(
        code="E_TEST", message="failure", details="additional",
        correlation_id="corr", duration_ms=12.5,
    )
    as_payload = result.as_result(handler_id="handler", fallback_correlation_id=None)
    assert as_payload["ok"] is False
    assert as_payload["error"] == {"code": "E_TEST", "error": "failure", "details": "additional"}
    assert as_payload["correlationId"] == "corr"
    assert as_payload["durationMs"] == pytest.approx(12.5, rel=1e-3)


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
```

- [ ] **Step 10: Run full WS test suite**

Run: `pytest tests/helpers/test_websocket*.py tests/helpers/test_state_sync*.py tests/helpers/test_state_monitor.py tests/test_websocket_handlers.py -v`
Expected: All tests pass

- [ ] **Step 11: Commit**

```bash
git add tests/
git commit -m "test: update all WS tests for extension-based handler architecture"
```

---

## Task 7: Full test suite + Docker verification

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -x -q`
Expected: All tests pass (2624+ tests)

- [ ] **Step 2: Docker verification** (per `.cursor/rules/docker-verification.mdc`)

1. Build Docker image from worktree
2. Run container with `usr/` data synced in
3. Verify UI loads at `http://localhost:50081/`
4. Verify WebSocket connection works (chat loads, state sync operates)
5. Check Docker logs for errors

- [ ] **Step 3: Final commit and push**

```bash
git push -u origin upstream/a5-ws-extensions
```

- [ ] **Step 4: Create PR**

```bash
gh pr create --title "A5: WebSocket Handler Extension-Based Architecture" --body "..."
```
