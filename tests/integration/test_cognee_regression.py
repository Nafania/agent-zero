"""
Regression tests for the cognee database initialization bug.

Production bug: sqlite3.OperationalError and DatabaseNotCreatedError occurred when
cognee database wasn't initialized before use. After refactoring, initialization
happens once at startup via init_cognee(), and get_cognee() raises RuntimeError
if called before initialization.
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


# --- Startup initialization gate ---


@pytest.mark.regression
def test_get_cognee_raises_before_init():
    """get_cognee() raises RuntimeError if init_cognee() hasn't been called."""
    from python.helpers.memory import _get_cognee

    with pytest.raises(RuntimeError, match="not initialized"):
        _get_cognee()


@pytest.mark.regression
@pytest.mark.asyncio
async def test_search_fails_without_init():
    """search_similarity_threshold raises RuntimeError when cognee not initialized."""
    from python.helpers.memory import Memory

    mem = Memory(dataset_name="default", memory_subdir="default")
    with pytest.raises(RuntimeError, match="not initialized"):
        await mem.search_similarity_threshold("test query", limit=5, threshold=0.5)


@pytest.mark.regression
@pytest.mark.asyncio
async def test_insert_fails_without_init():
    """insert_documents raises RuntimeError when cognee not initialized."""
    from python.helpers.memory import Memory
    from langchain_core.documents import Document

    mem = Memory(dataset_name="default", memory_subdir="default")
    with pytest.raises(RuntimeError, match="not initialized"):
        await mem.insert_documents([Document(page_content="test", metadata={})])


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

    with patch("python.api.memory_dashboard.Memory") as MockMem:
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
