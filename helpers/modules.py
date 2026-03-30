import os, importlib, importlib.util, inspect, sys
from types import ModuleType
from typing import Any, TypeVar
from helpers.files import get_abs_path
from fnmatch import fnmatch


T = TypeVar("T")  # Define a generic type variable


def import_module(file_path: str) -> ModuleType:
    # Does not register the module in sys.modules, so repeated calls re-execute
    # the file — intentional for extension loading (isolated fresh namespace).
    abs_path = get_abs_path(file_path)
    module_name = os.path.basename(abs_path).replace(".py", "")
    spec = importlib.util.spec_from_file_location(module_name, abs_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {abs_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_classes_from_folder(
    folder: str, name_pattern: str, base_class: type[T], one_per_file: bool = True
) -> list[type[T]]:
    classes = []
    abs_folder = get_abs_path(folder)
    py_files = sorted(
        [
            file_name
            for file_name in os.listdir(abs_folder)
            if fnmatch(file_name, name_pattern) and file_name.endswith(".py")
        ]
    )
    for file_name in py_files:
        file_path = os.path.join(abs_folder, file_name)
        module = import_module(file_path)
        class_list = inspect.getmembers(module, inspect.isclass)
        for cls in reversed(class_list):
            if cls[1] is not base_class and issubclass(cls[1], base_class):
                classes.append(cls[1])
                if one_per_file:
                    break
    return classes


def load_classes_from_file(
    file: str, base_class: type[T], one_per_file: bool = True
) -> list[type[T]]:
    classes = []
    module = import_module(file)
    class_list = inspect.getmembers(module, inspect.isclass)
    for cls in reversed(class_list):
        if cls[1] is not base_class and issubclass(cls[1], base_class):
            classes.append(cls[1])
            if one_per_file:
                break
    return classes


def purge_namespace(namespace: str):
    to_delete = [
        name
        for name in sys.modules
        if name == namespace or name.startswith(namespace + ".")
    ]
    to_delete.sort(key=lambda n: n.count("."), reverse=True)
    for name in to_delete:
        del sys.modules[name]
    importlib.invalidate_caches()
    return to_delete
