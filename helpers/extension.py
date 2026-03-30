import os
import inspect
from abc import abstractmethod
from typing import Any, Awaitable, Type, cast
from functools import wraps
from typing import TYPE_CHECKING

from helpers import modules, files
from helpers import cache
from helpers.print_style import PrintStyle

if TYPE_CHECKING:
    from agent import Agent


_EXTENSIONS_CACHE_AREA = "extension_folder_classes(extensions)"
_CLASSES_CACHE_AREA = "extension_classes(extensions)"


class _Unset:
    pass


_UNSET = _Unset()


_EXTENSIONS_LOG_COUNTS: dict[str, int] = {}

def _log_extension_call(name: str):
    try:
        every = int(os.getenv("EXTENSIONS_LOG", "0"))
    except ValueError:
        return
    if every <= 0:
        return
    _EXTENSIONS_LOG_COUNTS[name] = _EXTENSIONS_LOG_COUNTS.get(name, 0) + 1
    _EXTENSIONS_LOG_COUNTS["_total"] = _EXTENSIONS_LOG_COUNTS.get("_total", 0) + 1
    if _EXTENSIONS_LOG_COUNTS["_total"] % every == 0:
        for key, count in _EXTENSIONS_LOG_COUNTS.items():
            print(f"{str(count):<6} {key}")


def extensible(func):
    """Make a function emit two implicit extension points around its execution.

    Derives path-based ``_functions/{module}/{qualname}/start`` and ``end``
    extension points. Extensions may mutate ``data["args"]``,
    ``data["kwargs"]``, ``data["result"]``, or ``data["exception"]``.
    """

    def _get_agent(args, kwargs):
        from agent import Agent
        candidate = kwargs.get("agent")
        if isinstance(candidate, Agent) and bool(getattr(candidate, "__dict__", None)):
            return candidate
        for a in args:
            if isinstance(a, Agent) and bool(getattr(a, "__dict__", None)):
                return a
        return None

    def _prepare_inputs(args, kwargs):
        module_name = getattr(func, "__module__", "")
        qual_name = getattr(func, "__qualname__", "")
        if not module_name or not qual_name:
            return None

        module_parts = [part for part in module_name.split(".") if part]
        qual_parts = [part for part in qual_name.split(".") if part and part != "<locals>"]
        if not module_parts or not qual_parts:
            return None

        base_path = os.path.join("_functions", *module_parts, *qual_parts)
        start_point = os.path.join(base_path, "start")
        end_point = os.path.join(base_path, "end")
        agent = _get_agent(args, kwargs)

        data = {
            "args": args,
            "kwargs": kwargs,
            "result": _UNSET,
            "exception": None,
        }

        return start_point, end_point, agent, data

    def _process_result(data):
        exc = data.get("exception")
        if isinstance(exc, BaseException):
            raise exc

        return data.get("result")

    def _call_original(data):
        call_args = data.get("args")
        call_kwargs = data.get("kwargs")

        if not isinstance(call_args, tuple):
            call_args = (call_args,)
        if not isinstance(call_kwargs, dict):
            call_kwargs = {}

        try:
            data["result"] = func(*call_args, **call_kwargs)
        except Exception as e:
            data["exception"] = e
            return _UNSET

    async def _run_async(*args, **kwargs):
        prepared = _prepare_inputs(args, kwargs)
        if prepared is None:
            return await func(*args, **kwargs)

        start_point, end_point, agent, data = prepared

        await call_extensions_async(start_point, agent=agent, data=data)

        if (result := _process_result(data)) is _UNSET:
            _call_original(data)
            try:
                data["result"] = await data["result"]
            except Exception as e:
                data["exception"] = e

        await call_extensions_async(end_point, agent=agent, data=data)

        result = _process_result(data)
        return None if result is _UNSET else result

    def _run_sync(*args, **kwargs):
        prepared = _prepare_inputs(args, kwargs)
        if prepared is None:
            return func(*args, **kwargs)

        start_point, end_point, agent, data = prepared

        call_extensions_sync(start_point, agent=agent, data=data)

        if (result := _process_result(data)) is _UNSET:
            _call_original(data)

        call_extensions_sync(end_point, agent=agent, data=data)

        result = _process_result(data)
        return None if result is _UNSET else result

    if inspect.iscoroutinefunction(func):
        return wraps(func)(_run_async)

    return wraps(func)(_run_sync)


class Extension:

    def __init__(self, agent: "Agent|None", **kwargs):
        self.agent: "Agent|None" = agent
        self.kwargs = kwargs

    @abstractmethod
    def execute(self, **kwargs) -> None | Awaitable[None]:
        pass


async def call_extensions(
    extension_point: str, agent: "Agent|None" = None, **kwargs
) -> Any:
    """Legacy async-only entry point kept for backward compatibility."""
    await call_extensions_async(extension_point, agent=agent, **kwargs)


async def call_extensions_async(
    extension_point: str, agent: "Agent|None" = None, **kwargs
):
    _log_extension_call(extension_point)
    classes = _get_extension_classes(extension_point, agent=agent, **kwargs)

    for cls in classes:
        result = cls(agent=agent).execute(**kwargs)
        if isinstance(result, Awaitable):
            await result


def call_extensions_sync(extension_point: str, agent: "Agent|None" = None, **kwargs):
    _log_extension_call(extension_point)
    classes = _get_extension_classes(extension_point, agent=agent, **kwargs)

    for cls in classes:
        result = cls(agent=agent).execute(**kwargs)
        if isinstance(result, Awaitable):
            raise ValueError(
                f"Extension {cls.__name__} returned awaitable in sync mode"
            )


def get_webui_extensions(
    agent: "Agent | None", extension_point: str, filters: list[str] | None = None
) -> list[str]:
    from helpers import subagents

    entries: list[str] = []
    effective_filters = filters or ["*"]

    folders = subagents.get_paths(
        agent,
        "extensions/webui",
        extension_point,
    )

    extensions: list[str] = []

    for folder in folders:
        for f in effective_filters:
            pattern = files.get_abs_path(folder, f)
            extensions.extend(files.find_existing_paths_by_pattern(pattern))

    for ext in extensions:
        rel_path = files.deabsolute_path(ext)
        entries.append(rel_path)

    return entries


def _get_extension_classes(
    extension_point: str, agent: "Agent|None" = None, **kwargs
) -> list[Type[Extension]]:
    from helpers import subagents

    cache_key = f"{id(agent)}:{extension_point}"
    cached = cache.get(_CLASSES_CACHE_AREA, cache_key)
    if cached is not None:
        return cached

    paths = subagents.get_paths(agent, "extensions/python", extension_point)

    all_exts = [cls for path in paths for cls in _get_extensions(path)]

    unique: dict[str, Type[Extension]] = {}
    for cls in all_exts:
        file = _get_file_from_module(cls.__module__)
        if file not in unique:
            unique[file] = cls
    classes = sorted(
        unique.values(), key=lambda cls: _get_file_from_module(cls.__module__)
    )
    cache.add(_CLASSES_CACHE_AREA, cache_key, classes)
    return classes


def _get_file_from_module(module_name: str) -> str:
    return module_name.split(".")[-1]


def _get_extensions(folder: str) -> list[Type[Extension]]:
    folder = files.get_abs_path(folder)
    cached = cache.get(_EXTENSIONS_CACHE_AREA, folder)
    if cached is not None:
        return cached

    if not files.exists(folder):
        return []

    classes = modules.load_classes_from_folder(folder, "*", Extension)
    cache.add(_EXTENSIONS_CACHE_AREA, folder, classes)
    return classes


def register_extensions_watchdogs():
    from helpers import watchdog, projects

    def extensions_changed(items: list[watchdog.WatchItem]):
        cache.clear(_EXTENSIONS_CACHE_AREA)
        cache.clear(_CLASSES_CACHE_AREA)
        PrintStyle.debug("Extensions watchdog triggered:", items)

    watchdog.add_watchdog(
        id="extensions_base",
        roots=[
            files.get_abs_path(files.EXTENSIONS_DIR),
            files.get_abs_path(files.USER_DIR, files.EXTENSIONS_DIR),
        ],
        handler=extensions_changed,
    )

    watchdog.add_watchdog(
        id="extensions_projects",
        roots=[files.get_abs_path(projects.PROJECTS_PARENT_DIR)],
        patterns=[f"*/{projects.PROJECT_META_DIR}/**/{files.EXTENSIONS_DIR}/**/*"],
        handler=extensions_changed,
    )

    watchdog.add_watchdog(
        id="extensions_agents",
        roots=[
            files.get_abs_path(files.AGENTS_DIR),
            files.get_abs_path(files.USER_DIR, files.AGENTS_DIR),
        ],
        patterns=[f"*/{files.EXTENSIONS_DIR}/**/*"],
        handler=extensions_changed,
    )
