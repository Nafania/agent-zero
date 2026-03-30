import re, os
from typing import Any, TypeVar
from .dirty_json import DirtyJson
from .files import get_abs_path
import regex

from helpers import modules as _modules

def json_parse_dirty(json:str) -> dict[str,Any] | None:
    if not json or not isinstance(json, str):
        return None

    ext_json = extract_json_object_string(json.strip())
    if ext_json:
        try:
            data = DirtyJson.parse_string(ext_json)
            if isinstance(data,dict): return data
        except Exception:
            return None
    return None

def extract_json_object_string(content):
    start = content.find('{')
    if start == -1:
        return ""

    end = content.rfind('}')
    if end == -1:
        return content[start:]
    else:
        return content[start:end+1]

def extract_json_string(content):
    pattern = r'\{(?:[^{}]|(?R))*\}|\[(?:[^\[\]]|(?R))*\]|"(?:\\.|[^"\\])*"|true|false|null|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?'

    match = regex.search(pattern, content)

    if match:
        return match.group(0)
    else:
        return ""

def fix_json_string(json_string):
    def replace_unescaped_newlines(match):
        return match.group(0).replace('\n', '\\n')

    fixed_string = re.sub(r'(?<=: ")(.*?)(?=")', replace_unescaped_newlines, json_string, flags=re.DOTALL)
    return fixed_string


T = TypeVar('T')

import_module = _modules.import_module
load_classes_from_folder = _modules.load_classes_from_folder
load_classes_from_file = _modules.load_classes_from_file
