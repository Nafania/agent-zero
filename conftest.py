"""Root conftest — mock heavy optional dependencies not installed locally.

Only mocks modules that fail to import. In CI (all deps installed),
nothing gets mocked. Locally (partial deps), only missing packages
are replaced with stubs.
"""

import importlib
import sys
from unittest.mock import MagicMock


class _MockModule(MagicMock):
    """MagicMock that acts as both a module and its submodules."""
    __path__ = []
    __all__ = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__path__ = []


_OPTIONAL_MODULES = [
    "browser_use", "browser_use.llm", "browser_use.utils",
    "cognee", "cognee.api", "cognee.api.v1", "cognee.api.v1.search",
    "cognee.api.v1.search.search_types", "cognee.datasets",
    "cognee.infrastructure", "cognee.infrastructure.databases",
    "cognee.infrastructure.databases.relational",
    "langchain", "langchain.embeddings", "langchain.embeddings.base",
    "langchain.prompts", "langchain.schema", "langchain.text_splitter",
    "langchain_text_splitters",
    "langchain_community", "langchain_community.document_loaders",
    "langchain_community.document_loaders.parsers",
    "langchain_community.document_loaders.parsers.images",
    "langchain_community.document_loaders.pdf",
    "langchain_community.document_loaders.text",
    "langchain_community.document_transformers",
    "langchain_unstructured",
    "litellm", "litellm.types", "litellm.types.utils",
    "openai",
    "sentence_transformers",
    "whisper",
    "nest_asyncio2",
    "tiktoken",
    "docker",
    "aiohttp",
    "flask", "werkzeug", "werkzeug.datastructures", "werkzeug.serving", "werkzeug.utils",
    "socketio",
    "paramiko",
    "psutil",
    "kokoro",
    "soundfile",
    "crontab",
    "simpleeval",
    "ddgs",
    "html2text",
    "bs4",
    "httpx",
    "requests",
    "pdf2image",
    "pytesseract",
    "PIL",
    "webcolors",
    "regex",
    "pytz",
    "flaredantic",
    "fastmcp", "fastmcp.server", "fastmcp.server.http",
    "fasta2a", "fasta2a.broker", "fasta2a.client", "fasta2a.schema", "fasta2a.storage",
    "mcp", "mcp.client", "mcp.client.sse", "mcp.client.stdio",
    "mcp.client.streamable_http", "mcp.server", "mcp.server.auth",
    "mcp.server.auth.middleware", "mcp.server.auth.middleware.bearer_auth",
    "mcp.server.streamable_http_manager", "mcp.shared", "mcp.shared.message", "mcp.types",
    "starlette", "starlette.exceptions", "starlette.middleware",
    "starlette.middleware.base", "starlette.requests", "starlette.routing", "starlette.types",
    "cryptography", "cryptography.hazmat", "cryptography.hazmat.primitives",
    "cryptography.hazmat.primitives.asymmetric",
    "imapclient", "exchangelib",
    "git", "pathspec", "pathspec.patterns", "pathspec.patterns.gitwildmatch",
    "inputimeout",
    "winpty",
    "attr",
    "dirty_json",
    "log_format",
    "dotenv", "dotenv.parser",
    "yaml",
]

_checked_top_level: dict[str, bool] = {}

for mod_name in _OPTIONAL_MODULES:
    if mod_name not in sys.modules:
        top_level = mod_name.split(".")[0]
        if top_level not in _checked_top_level:
            try:
                _checked_top_level[top_level] = importlib.util.find_spec(top_level) is not None
            except (ValueError, ModuleNotFoundError):
                _checked_top_level[top_level] = False
        if not _checked_top_level[top_level]:
            sys.modules[mod_name] = _MockModule(name=mod_name)
