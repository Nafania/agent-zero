"""
Regression tests for the cognee database initialization bug.

Production bug: prepare.py and the web server run as separate Python processes.
init_cognee() in prepare.py set _cognee_module, but that died with the process.
The server process called configure_cognee() but never set _cognee_module.

Fix: configure_cognee() now sets _cognee_module and _search_type_class,
so any process calling it gets a working cognee module.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Reset module-level state before each test."""
    import python.helpers.cognee_init as ci
    old = ci._configured, ci._cognee_module, ci._search_type_class
    ci._configured = False
    ci._cognee_module = None
    ci._search_type_class = None
    yield
    ci._configured, ci._cognee_module, ci._search_type_class = old


def _setup_cognee_mock():
    """Simulate initialized cognee by setting cognee_init globals to mocks."""
    import python.helpers.cognee_init as ci

    mock_cognee = MagicMock()
    mock_cognee.search = AsyncMock(return_value=[])
    mock_cognee.add = AsyncMock(return_value=None)
    mock_cognee.datasets = MagicMock()
    mock_cognee.datasets.list_datasets = AsyncMock(return_value=[])
    mock_cognee.datasets.list_data = AsyncMock(return_value=[])
    mock_cognee.datasets.delete_data = AsyncMock()

    mock_search_type = MagicMock()
    mock_search_type.CHUNKS = MagicMock(name="CHUNKS")
    mock_search_type.GRAPH_COMPLETION = MagicMock(name="GRAPH_COMPLETION")
    mock_search_type.CHUNKS_LEXICAL = MagicMock(name="CHUNKS_LEXICAL")

    ci._cognee_module = mock_cognee
    ci._search_type_class = mock_search_type
    ci._configured = True
    return mock_cognee, mock_search_type


# --- Startup initialization: must succeed or crash ---


@pytest.mark.regression
def test_get_cognee_raises_before_configure():
    """get_cognee() raises RuntimeError if configure_cognee() hasn't been called."""
    from python.helpers.memory import _get_cognee
    with pytest.raises(RuntimeError, match="not initialized"):
        _get_cognee()


@pytest.mark.regression
def test_configure_cognee_alone_makes_get_cognee_work():
    """THE FIX: configure_cognee() sets _cognee_module so get_cognee() works.
    Server process calls configure_cognee() but NOT init_cognee(). Before the fix,
    _cognee_module was only set in init_cognee(), leaving the server broken."""
    import python.helpers.cognee_init as ci

    mock_cognee = MagicMock()
    mock_search_type = MagicMock()
    mock_cognee.SearchType = mock_search_type

    with patch("python.helpers.cognee_init.dotenv") as mock_dotenv, \
         patch("python.helpers.cognee_init.get_settings", return_value={
             "util_model_provider": "openai",
             "util_model_name": "gpt-4o-mini",
             "util_model_api_base": "",
             "embed_model_provider": "huggingface",
             "embed_model_name": "BAAI/bge-small-en-v1.5",
             "embed_model_api_base": "",
             "api_keys": {"openai": "sk-test", "huggingface": "hf-test"},
         }), \
         patch("python.helpers.cognee_init.files") as mock_files, \
         patch.dict("sys.modules", {"cognee": mock_cognee}):
        mock_files.get_abs_path.return_value = "/tmp/test_cognee"
        mock_dotenv.load_dotenv.return_value = None
        mock_dotenv.get_dotenv_value.return_value = None
        ci.configure_cognee()

    cognee_mod, search_type = ci.get_cognee()
    assert cognee_mod is mock_cognee
    assert search_type is mock_search_type


@pytest.mark.regression
def test_configure_cognee_retryable_after_failure():
    """configure_cognee() can be retried after failure because _configured
    is only set to True after successful completion."""
    import python.helpers.cognee_init as ci

    with patch("python.helpers.cognee_init.dotenv") as mock_dotenv, \
         patch("python.helpers.cognee_init.get_settings",
               side_effect=Exception("settings not ready")), \
         patch("python.helpers.cognee_init.files") as mock_files:
        mock_dotenv.load_dotenv.return_value = None
        mock_dotenv.get_dotenv_value.return_value = None
        mock_files.get_abs_path.return_value = "/tmp/test_cognee"
        try:
            ci.configure_cognee()
        except Exception:
            pass

    assert ci._configured is False, \
        "_configured must stay False after failure so prepare.py can retry"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_init_cognee_succeeds_on_retry_after_failure():
    """init_cognee() fails first (bad settings), reload() resets state,
    second call succeeds — this is what prepare.py's retry loop does."""
    import python.helpers.cognee_init as ci
    from python.helpers.memory import reload

    mock_cognee = MagicMock()
    mock_search_type = MagicMock()
    mock_cognee.SearchType = mock_search_type
    mock_create_tables = AsyncMock()

    with patch("python.helpers.cognee_init.dotenv") as mock_dotenv, \
         patch("python.helpers.cognee_init.files") as mock_files, \
         patch.dict("sys.modules", {
             "cognee": mock_cognee,
             "cognee.infrastructure.databases.relational": MagicMock(
                 create_db_and_tables=mock_create_tables
             ),
         }):
        mock_dotenv.load_dotenv.return_value = None
        mock_dotenv.get_dotenv_value.return_value = None
        mock_files.get_abs_path.return_value = "/tmp/test_cognee"

        with patch("python.helpers.cognee_init.get_settings",
                   side_effect=Exception("settings not ready")):
            with pytest.raises(Exception, match="settings not ready"):
                await ci.init_cognee()

        assert ci._cognee_module is None

        reload()

        with patch("python.helpers.cognee_init.get_settings", return_value={
            "util_model_provider": "openai",
            "util_model_name": "gpt-4o-mini",
            "util_model_api_base": "",
            "embed_model_provider": "huggingface",
            "embed_model_name": "BAAI/bge-small-en-v1.5",
            "embed_model_api_base": "",
            "api_keys": {"openai": "sk-test", "huggingface": "hf-test"},
        }):
            await ci.init_cognee()

    assert ci._cognee_module is mock_cognee
    cognee_mod, search_type = ci.get_cognee()
    assert cognee_mod is mock_cognee


# --- Database not created: proper error handling ---


@pytest.mark.regression
@pytest.mark.asyncio
async def test_search_handles_sqlite_operational_error():
    """When cognee database doesn't exist, search_similarity_threshold returns [] instead of crashing."""
    import sqlite3
    from python.helpers.memory import Memory

    mock_cognee, _ = _setup_cognee_mock()
    mock_cognee.search = AsyncMock(
        side_effect=sqlite3.OperationalError("no such table: datasets")
    )

    mem = Memory(dataset_name="default", memory_subdir="default")
    result = await mem.search_similarity_threshold("query", limit=5, threshold=0.5)

    assert result == []
    assert isinstance(result, list)


@pytest.mark.regression
@pytest.mark.asyncio
async def test_search_handles_database_not_created_error():
    """When cognee raises DatabaseNotCreatedError, search returns [] instead of unhandled crash."""

    class DatabaseNotCreatedError(Exception):
        pass

    from python.helpers.memory import Memory

    mock_cognee, _ = _setup_cognee_mock()
    mock_cognee.search = AsyncMock(
        side_effect=DatabaseNotCreatedError("DB not created")
    )

    mem = Memory(dataset_name="default", memory_subdir="default")
    result = await mem.search_similarity_threshold("query", limit=5, threshold=0.5)

    assert result == []


@pytest.mark.regression
@pytest.mark.asyncio
async def test_delete_data_by_id_handles_database_not_created():
    """_delete_data_by_id handles DatabaseNotCreatedError and returns False, no crash."""

    class DatabaseNotCreatedError(Exception):
        pass

    from python.helpers.memory import _delete_data_by_id

    mock_cognee, _ = _setup_cognee_mock()
    mock_cognee.datasets.list_datasets = AsyncMock(
        side_effect=DatabaseNotCreatedError("DB not created")
    )

    result = await _delete_data_by_id("default_main", "some_id")
    assert result is False


@pytest.mark.regression
@pytest.mark.asyncio
async def test_memory_dashboard_handles_db_error_gracefully():
    """MemoryDashboard returns success with empty memories when cognee DB operations fail."""

    class DatabaseNotCreatedError(Exception):
        pass

    from python.api.memory_dashboard import MemoryDashboard

    _setup_cognee_mock()

    mock_cognee = MagicMock()
    mock_cognee.datasets.list_datasets = AsyncMock(
        side_effect=DatabaseNotCreatedError("db not created")
    )

    with patch("python.api.memory_dashboard.Memory") as MockMem, \
         patch.dict("sys.modules", {"cognee": mock_cognee}):
        mock_mem_instance = MagicMock()
        mock_mem_instance._area_dataset.side_effect = lambda a: f"default_{a}"
        MockMem.get_by_subdir = AsyncMock(return_value=mock_mem_instance)
        MockMem.Area = MagicMock()
        MockMem.Area.__iter__ = MagicMock(return_value=iter([MagicMock(value="main")]))
        MockMem.Area.MAIN = MagicMock(value="main")

        dashboard = MemoryDashboard(app=MagicMock(), thread_lock=MagicMock())
        result = await dashboard._search_memories({"memory_subdir": "default"})

    assert result["success"] is True
    assert result["memories"] == []


# --- init_cognee failure ---


@pytest.mark.regression
@pytest.mark.asyncio
async def test_init_cognee_propagates_configure_failure():
    """When configure_cognee() raises during init_cognee(), the error propagates."""
    from python.helpers.cognee_init import init_cognee

    with patch(
        "python.helpers.cognee_init.configure_cognee",
        side_effect=ValueError("bad config"),
    ):
        with pytest.raises(ValueError, match="bad config"):
            await init_cognee()


@pytest.mark.regression
def test_get_cognee_returns_modules_after_setup():
    """After initialization, get_cognee() returns the cognee module and SearchType."""
    from python.helpers.cognee_init import get_cognee

    mock_cognee, mock_search_type = _setup_cognee_mock()

    cognee_mod, search_type = get_cognee()
    assert cognee_mod is mock_cognee
    assert search_type is mock_search_type
