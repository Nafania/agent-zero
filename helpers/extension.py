from abc import abstractmethod
from typing import Any, Awaitable, Type, cast
from helpers import extract_tools, files
from helpers import cache, subagents
from typing import TYPE_CHECKING
from functools import wraps
import inspect

if TYPE_CHECKING:
    from agent import Agent


_CACHE_AREA = "extension_folder_classes(extensions)(plugins)"
cache.toggle_area(_CACHE_AREA, False)


class _Unset:
    pass


_UNSET = _Unset()


def extensible(func):
    """Make a function emit two implicit extension points around its execution.

    Derives ``{module}_{qualname}_start`` and ``{module}_{qualname}_end``
    extension points. Extensions may mutate ``data["args"]``,
    ``data["kwargs"]``, ``data["result"]``, or ``data["exception"]``.
    """

    def _get_agent(args, kwargs):
        try:
            from agent import Agent
        except (ImportError, TypeError):
            return None

        def _check(obj):
            try:
                return (
                    isinstance(obj, Agent)
                    and bool(getattr(obj, "__dict__", None))
                    and hasattr(obj, "config")
                )
            except TypeError:
                return False

        candidate = kwargs.get("agent")
        if _check(candidate):
            return candidate

        for a in args:
            if _check(a):
                return a

        return None

    def _prepare_inputs(args, kwargs):
        module_name = getattr(func, "__module__", "").replace(".", "_")
        qual_name = getattr(func, "__qualname__", "").replace(".", "_")
        if not module_name or not qual_name:
            return None

        start_point = f"{module_name}_{qual_name}_start"
        end_point = f"{module_name}_{qual_name}_end"
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
    classes = _get_extension_classes(extension_point, agent=agent, **kwargs)

    for cls in classes:
        result = cls(agent=agent).execute(**kwargs)
        if isinstance(result, Awaitable):
            await result


def call_extensions_sync(extension_point: str, agent: "Agent|None" = None, **kwargs):
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
    return classes


def _get_file_from_module(module_name: str) -> str:
    return module_name.split(".")[-1]


def _get_extensions(folder: str) -> list[Type[Extension]]:
    folder = files.get_abs_path(folder)
    cached = cache.get(_CACHE_AREA, folder)
    if cached is not None:
        return cached

    if not files.exists(folder):
        return []

    classes = extract_tools.load_classes_from_folder(folder, "*", Extension)
    cache.add(_CACHE_AREA, folder, classes)
    return classes
