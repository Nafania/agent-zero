from __future__ import annotations

import types
from typing import Any, Mapping, TypedDict, Union, get_args, get_origin, get_type_hints

from dataclasses import dataclass

import pytz  # type: ignore[import-untyped]

from agent import AgentContext, AgentContextType

from python.helpers.dotenv import get_dotenv_value
from python.helpers.localization import Localization
from python.helpers.task_scheduler import TaskScheduler

import time as _time
import threading as _threading

_chat_list_lock = _threading.Lock()
_chat_list_updated_at: float = _time.time()


def touch_chat_list() -> None:
    """Call when the chat list changes (create, remove, rename, running status)."""
    global _chat_list_updated_at
    with _chat_list_lock:
        _chat_list_updated_at = _time.time()


def get_chat_list_updated_at() -> float:
    with _chat_list_lock:
        return _chat_list_updated_at


class SnapshotV1(TypedDict):
    deselect_chat: bool
    context: str
    contexts: list[dict[str, Any]] | None
    tasks: list[dict[str, Any]] | None
    chat_list_updated_at: float
    logs: list[dict[str, Any]]
    log_guid: str
    log_version: int
    log_progress: str | int
    log_progress_active: bool
    has_earlier_logs: bool
    paused: bool
    notifications: list[dict[str, Any]]
    notifications_guid: str
    notifications_version: int

@dataclass(frozen=True)
class StateRequestV1:
    context: str | None
    log_from: int
    notifications_from: int
    timezone: str
    chat_list_since: float = 0.0


class StateRequestValidationError(ValueError):
    def __init__(
        self,
        *,
        reason: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.details = details or {}


def _annotation_to_isinstance_types(annotation: Any) -> tuple[type, ...]:
    """Convert type annotation to tuple suitable for isinstance()."""
    origin = get_origin(annotation)

    # Handle Union (typing.Union or types.UnionType from X | Y)
    _union_type = getattr(types, "UnionType", None)
    if origin is Union or origin is _union_type:
        result: list[type] = []
        for arg in get_args(annotation):
            result.extend(_annotation_to_isinstance_types(arg))
        return tuple(result)

    # Generic aliases: list[X] -> list, dict[K,V] -> dict
    if origin is not None:
        return (origin,)

    if isinstance(annotation, type):
        return (annotation,)

    return ()


def _build_schema_from_typeddict(td: type) -> dict[str, tuple[type, ...]]:
    """Extract field names and isinstance-compatible types from TypedDict."""
    return {k: _annotation_to_isinstance_types(v) for k, v in get_type_hints(td).items()}


_SNAPSHOT_V1_SCHEMA = _build_schema_from_typeddict(SnapshotV1)
SNAPSHOT_SCHEMA_V1_KEYS: tuple[str, ...] = tuple(_SNAPSHOT_V1_SCHEMA.keys())


def validate_snapshot_schema_v1(snapshot: Mapping[str, Any]) -> None:
    if not isinstance(snapshot, dict):
        raise TypeError("snapshot must be a dict")
    expected = set(SNAPSHOT_SCHEMA_V1_KEYS)
    actual = set(snapshot.keys())
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        message = "snapshot schema mismatch"
        if missing:
            message += f"; missing={missing}"
        if extra:
            message += f"; unexpected={extra}"
        raise ValueError(message)

    for key, expected_types in _SNAPSHOT_V1_SCHEMA.items():
        if expected_types and not isinstance(snapshot.get(key), expected_types):
            type_desc = " | ".join(t.__name__ for t in expected_types)
            raise TypeError(f"snapshot.{key} must be {type_desc}")


def _coerce_non_negative_int(value: Any, default: int = 0) -> int:
    try:
        as_int = int(value)
    except (TypeError, ValueError):
        return default
    return as_int if as_int >= 0 else default


def parse_state_request_payload(payload: Mapping[str, Any]) -> StateRequestV1:
    context = payload.get("context")
    log_from = payload.get("log_from")
    notifications_from = payload.get("notifications_from")
    timezone = payload.get("timezone")

    if context is not None and not isinstance(context, str):
        raise StateRequestValidationError(
            reason="context_type",
            message="context must be a string or null",
            details={"context_type": type(context).__name__},
        )
    if not isinstance(log_from, int) or log_from < 0:
        raise StateRequestValidationError(
            reason="log_from",
            message="log_from must be an integer >= 0",
            details={"log_from": log_from},
        )
    if not isinstance(notifications_from, int) or notifications_from < 0:
        raise StateRequestValidationError(
            reason="notifications_from",
            message="notifications_from must be an integer >= 0",
            details={"notifications_from": notifications_from},
        )
    if not isinstance(timezone, str) or not timezone.strip():
        raise StateRequestValidationError(
            reason="timezone_empty",
            message="timezone must be a non-empty string",
            details={"timezone": timezone},
        )

    tz = timezone.strip()
    try:
        pytz.timezone(tz)
    except pytz.exceptions.UnknownTimeZoneError as exc:
        raise StateRequestValidationError(
            reason="timezone_invalid",
            message="timezone must be a valid IANA timezone name",
            details={"timezone": tz},
        ) from exc

    chat_list_since = payload.get("chat_list_since", 0.0)
    if not isinstance(chat_list_since, (int, float)):
        chat_list_since = 0.0
    chat_list_since = max(0.0, float(chat_list_since))

    ctxid: str | None = context.strip() if isinstance(context, str) else None
    if ctxid == "":
        ctxid = None
    return StateRequestV1(
        context=ctxid,
        log_from=log_from,
        notifications_from=notifications_from,
        timezone=tz,
        chat_list_since=chat_list_since,
    )


def _coerce_state_request_inputs(
    *,
    context: Any,
    log_from: Any,
    notifications_from: Any,
    timezone: Any,
    chat_list_since: float = 0.0,
) -> StateRequestV1:
    tz = timezone if isinstance(timezone, str) and timezone else None
    tz = tz or get_dotenv_value("DEFAULT_USER_TIMEZONE", "UTC")

    ctxid: str | None = context.strip() if isinstance(context, str) else None
    if ctxid == "":
        ctxid = None

    return StateRequestV1(
        context=ctxid,
        log_from=_coerce_non_negative_int(log_from, default=0),
        notifications_from=_coerce_non_negative_int(notifications_from, default=0),
        timezone=tz,
        chat_list_since=chat_list_since,
    )


def advance_state_request_after_snapshot(
    request: StateRequestV1,
    snapshot: Mapping[str, Any],
) -> StateRequestV1:
    log_from = request.log_from
    notifications_from = request.notifications_from

    try:
        log_from = int(snapshot.get("log_version", log_from))
    except (TypeError, ValueError):
        pass

    try:
        notifications_from = int(snapshot.get("notifications_version", notifications_from))
    except (TypeError, ValueError):
        pass

    chat_list_since = request.chat_list_since
    try:
        chat_list_since = float(snapshot.get("chat_list_updated_at", chat_list_since))
    except (TypeError, ValueError):
        pass

    return StateRequestV1(
        context=request.context,
        log_from=log_from,
        notifications_from=notifications_from,
        timezone=request.timezone,
        chat_list_since=chat_list_since,
    )


INITIAL_LOG_TAIL = 50


async def build_snapshot_from_request(*, request: StateRequestV1) -> SnapshotV1:
    """Build a poll-shaped snapshot for both /poll and state_push."""

    Localization.get().set_timezone(request.timezone)

    ctxid = request.context if isinstance(request.context, str) else ""
    ctxid = ctxid.strip()

    from_no = _coerce_non_negative_int(request.log_from, default=0)
    notifications_from_no = _coerce_non_negative_int(request.notifications_from, default=0)

    active_context = AgentContext.get(ctxid) if ctxid else None

    has_earlier_logs = False
    if active_context:
        if from_no == 0:
            logs, has_earlier_logs = active_context.log.output(start=from_no, tail=INITIAL_LOG_TAIL)
        else:
            logs = active_context.log.output(start=from_no)
    else:
        logs = []

    notification_manager = AgentContext.get_notification_manager()
    notifications = notification_manager.output(start=notifications_from_no)

    current_chat_list_ts = get_chat_list_updated_at()
    chat_list_stale = request.chat_list_since < current_chat_list_ts

    ctxs: list[dict[str, Any]] | None = None
    tasks: list[dict[str, Any]] | None = None

    if chat_list_stale:
        scheduler = TaskScheduler.get()
        ctxs_list: list[dict[str, Any]] = []
        tasks_list: list[dict[str, Any]] = []
        processed_contexts: set[str] = set()

        all_ctxs = AgentContext.all()
        for ctx in all_ctxs:
            if ctx.id in processed_contexts:
                continue

            if ctx.type == AgentContextType.BACKGROUND:
                processed_contexts.add(ctx.id)
                continue

            context_data = ctx.output()

            context_task = scheduler.get_task_by_uuid(ctx.id)
            is_task_context = context_task is not None and context_task.context_id == ctx.id

            if not is_task_context:
                ctxs_list.append(context_data)
            else:
                task_details = scheduler.serialize_task(ctx.id)
                if task_details:
                    context_data.update(
                        {
                            "task_name": task_details.get("name"),
                            "uuid": task_details.get("uuid"),
                            "state": task_details.get("state"),
                            "type": task_details.get("type"),
                            "system_prompt": task_details.get("system_prompt"),
                            "prompt": task_details.get("prompt"),
                            "last_run": task_details.get("last_run"),
                            "last_result": task_details.get("last_result"),
                            "attachments": task_details.get("attachments", []),
                            "context_id": task_details.get("context_id"),
                        }
                    )

                    if task_details.get("type") == "scheduled":
                        context_data["schedule"] = task_details.get("schedule")
                    elif task_details.get("type") == "planned":
                        context_data["plan"] = task_details.get("plan")
                    else:
                        context_data["token"] = task_details.get("token")

                tasks_list.append(context_data)

            processed_contexts.add(ctx.id)

        ctxs_list.sort(key=lambda x: x["created_at"], reverse=True)
        tasks_list.sort(key=lambda x: x["created_at"], reverse=True)
        ctxs = ctxs_list
        tasks = tasks_list

    snapshot: SnapshotV1 = {
        "deselect_chat": bool(ctxid) and active_context is None,
        "context": active_context.id if active_context else "",
        "contexts": ctxs,
        "tasks": tasks,
        "chat_list_updated_at": current_chat_list_ts,
        "logs": logs,
        "log_guid": active_context.log.guid if active_context else "",
        "log_version": len(active_context.log.updates) if active_context else 0,
        "has_earlier_logs": has_earlier_logs,
        "log_progress": active_context.log.progress if active_context else 0,
        "log_progress_active": bool(active_context.log.progress_active) if active_context else False,
        "paused": active_context.paused if active_context else False,
        "notifications": notifications,
        "notifications_guid": notification_manager.guid,
        "notifications_version": len(notification_manager.updates),
    }

    validate_snapshot_schema_v1(snapshot)
    return snapshot


async def build_snapshot(
    *,
    context: str | None,
    log_from: int,
    notifications_from: int,
    timezone: str | None,
    chat_list_since: float = 0.0,
) -> SnapshotV1:
    request = _coerce_state_request_inputs(
        context=context,
        log_from=log_from,
        notifications_from=notifications_from,
        timezone=timezone,
        chat_list_since=chat_list_since,
    )
    return await build_snapshot_from_request(request=request)
