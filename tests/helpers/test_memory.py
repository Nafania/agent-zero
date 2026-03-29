"""Tests for helpers/memory.py — Cognee memory layer."""

import sys
import json
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Reset module-level state before each test."""
    import helpers.memory as mem
    import helpers.cognee_init as ci
    ci._cognee_module = None
    ci._search_type_class = None
    ci._configured = False
    mem.Memory._initialized_subdirs.clear()
    mem.Memory._datasets_cache.clear()
    yield
    ci._cognee_module = None
    ci._search_type_class = None
    ci._configured = False
    mem.Memory._initialized_subdirs.clear()
    mem.Memory._datasets_cache.clear()


# --- _subdir_to_dataset ---

class TestSubdirToDataset:
    def test_simple_name(self):
        from helpers.memory import _subdir_to_dataset
        assert _subdir_to_dataset("default") == "default"

    def test_slash_replaced(self):
        from helpers.memory import _subdir_to_dataset
        assert _subdir_to_dataset("projects/personal") == "projects_personal"

    def test_spaces_replaced(self):
        from helpers.memory import _subdir_to_dataset
        assert _subdir_to_dataset("my project") == "my_project"

    def test_mixed(self):
        from helpers.memory import _subdir_to_dataset
        assert _subdir_to_dataset("projects/my project") == "projects_my_project"

    def test_lowercased(self):
        from helpers.memory import _subdir_to_dataset
        assert _subdir_to_dataset("Projects/MyApp") == "projects_myapp"


# --- _extract_metadata_from_text ---

class TestExtractMetadataFromText:
    def test_text_with_meta_header(self):
        from helpers.memory import _extract_metadata_from_text
        meta = {"id": "abc123", "area": "main", "timestamp": "2026-01-01"}
        text = f'[META:{json.dumps(meta)}]\nHello world content'
        content, extracted = _extract_metadata_from_text(text)
        assert content == "Hello world content"
        assert extracted["id"] == "abc123"
        assert extracted["area"] == "main"

    def test_text_without_meta_header(self):
        from helpers.memory import _extract_metadata_from_text
        content, meta = _extract_metadata_from_text("Just plain text")
        assert content == "Just plain text"
        assert meta["area"] == "main"

    def test_malformed_meta_returns_full_text(self):
        from helpers.memory import _extract_metadata_from_text
        text = "[META:not valid json]\nContent here"
        content, meta = _extract_metadata_from_text(text)
        assert content == text
        assert meta["area"] == "main"

    def test_meta_without_closing_bracket(self):
        from helpers.memory import _extract_metadata_from_text
        text = '[META:{"id": "test"} some more text'
        content, meta = _extract_metadata_from_text(text)
        assert content == text


# --- _deduplicate_documents ---

class TestDeduplicateDocuments:
    def test_removes_duplicates_by_id(self):
        from helpers.memory import _deduplicate_documents
        from langchain_core.documents import Document

        docs = [
            Document(page_content="First", metadata={"id": "a"}),
            Document(page_content="Second", metadata={"id": "b"}),
            Document(page_content="Duplicate", metadata={"id": "a"}),
        ]
        result = _deduplicate_documents(docs)
        assert len(result) == 2
        assert result[0].page_content == "First"
        assert result[1].page_content == "Second"

    def test_deduplicates_by_content_when_no_id(self):
        from helpers.memory import _deduplicate_documents
        from langchain_core.documents import Document

        docs = [
            Document(page_content="Same content", metadata={}),
            Document(page_content="Same content", metadata={}),
            Document(page_content="Different", metadata={}),
        ]
        result = _deduplicate_documents(docs)
        assert len(result) == 2

    def test_preserves_order(self):
        from helpers.memory import _deduplicate_documents
        from langchain_core.documents import Document

        docs = [
            Document(page_content="C", metadata={"id": "3"}),
            Document(page_content="A", metadata={"id": "1"}),
            Document(page_content="B", metadata={"id": "2"}),
        ]
        result = _deduplicate_documents(docs)
        assert [d.page_content for d in result] == ["C", "A", "B"]


# --- _parse_filter_to_node_names ---

class TestParseFilterToNodeNames:
    def test_empty_filter(self):
        from helpers.memory import _parse_filter_to_node_names
        assert _parse_filter_to_node_names("") == []

    def test_main_filter(self):
        from helpers.memory import _parse_filter_to_node_names
        result = _parse_filter_to_node_names("area == 'main'")
        assert "main" in result

    def test_solutions_filter(self):
        from helpers.memory import _parse_filter_to_node_names
        result = _parse_filter_to_node_names("area == 'solutions'")
        assert "solutions" in result

    def test_combined_filter(self):
        from helpers.memory import _parse_filter_to_node_names
        result = _parse_filter_to_node_names("area == 'main' or area == 'fragments'")
        assert "main" in result
        assert "fragments" in result


# --- _results_to_documents ---

class TestResultsToDocuments:
    def test_empty_results(self):
        from helpers.memory import _results_to_documents
        assert _results_to_documents(None, 10) == []
        assert _results_to_documents([], 10) == []

    def test_string_results(self):
        from helpers.memory import _results_to_documents
        results = ["Hello world", "Test content"]
        docs = _results_to_documents(results, 10)
        assert len(docs) == 2
        assert docs[0].page_content == "Hello world"

    def test_result_with_search_result_attr(self):
        from helpers.memory import _results_to_documents
        mock_result = MagicMock()
        mock_result.search_result = "inner content"
        mock_result.dataset_name = "test_ds"
        docs = _results_to_documents([mock_result], 10)
        assert len(docs) == 1
        assert docs[0].page_content == "inner content"
        assert docs[0].metadata["dataset"] == "test_ds"

    def test_respects_limit(self):
        from helpers.memory import _results_to_documents
        results = [f"item_{i}" for i in range(20)]
        docs = _results_to_documents(results, 5)
        assert len(docs) == 5

    def test_meta_header_extraction(self):
        from helpers.memory import _results_to_documents
        meta = {"id": "test_id", "area": "solutions"}
        text = f'[META:{json.dumps(meta)}]\nActual content'
        docs = _results_to_documents([text], 10)
        assert docs[0].page_content == "Actual content"
        assert docs[0].metadata["id"] == "test_id"
        assert docs[0].metadata["area"] == "solutions"

    def test_dict_results(self):
        from helpers.memory import _results_to_documents
        results = [{"text": "from dict", "other": "data"}]
        docs = _results_to_documents(results, 10)
        assert docs[0].page_content == "from dict"

    def test_cognee_05_dict_format(self):
        from helpers.memory import _results_to_documents
        result = {"dataset_name": "test_ds", "search_result": ["actual content"]}
        docs = _results_to_documents([result], 10)
        assert len(docs) == 1
        assert docs[0].page_content == "actual content"
        assert docs[0].metadata["dataset"] == "test_ds"

    def test_cognee_05_multi_element_list(self):
        from helpers.memory import _results_to_documents
        result = {"search_result": ["line1", "line2"]}
        docs = _results_to_documents([result], 10)
        assert docs[0].page_content == "line1\nline2"

    def test_cognee_05_empty_search_result(self):
        from helpers.memory import _results_to_documents
        result = {"search_result": []}
        docs = _results_to_documents([result], 10)
        assert len(docs) == 0

    def test_skips_empty_content(self):
        from helpers.memory import _results_to_documents
        docs = _results_to_documents(["", "  ", "valid content"], 10)
        assert len(docs) == 1
        assert docs[0].page_content == "valid content"


# --- get_knowledge_subdirs_by_memory_subdir ---

class TestGetKnowledgeSubdirsByMemorySubdir:
    def test_does_not_mutate_input_list(self):
        from helpers.memory import get_knowledge_subdirs_by_memory_subdir
        original = ["default", "custom"]
        original_copy = list(original)
        with patch("helpers.memory.get_project_meta_folder",
                    create=True, return_value="usr/projects/test/.a0proj"):
            with patch.dict("sys.modules", {"helpers.projects": MagicMock(
                get_project_meta_folder=MagicMock(return_value="usr/projects/test/.a0proj/knowledge")
            )}):
                result = get_knowledge_subdirs_by_memory_subdir("projects/test", original)
        assert original == original_copy
        assert len(result) > len(original)

    def test_non_project_returns_copy(self):
        from helpers.memory import get_knowledge_subdirs_by_memory_subdir
        original = ["default"]
        result = get_knowledge_subdirs_by_memory_subdir("default", original)
        assert result == original
        assert result is not original


# --- _get_cognee delegates to cognee_init.get_cognee ---

class TestGetCognee:
    def test_returns_same_instance(self):
        from helpers.memory import _get_cognee
        import helpers.cognee_init as ci
        mock_cognee = MagicMock()
        mock_search_type = MagicMock()
        ci._cognee_module = mock_cognee
        ci._search_type_class = mock_search_type
        c1, st1 = _get_cognee()
        c2, st2 = _get_cognee()
        assert c1 is c2
        assert c1 is mock_cognee
        assert st1 is mock_search_type

    def test_raises_when_not_initialized(self):
        from helpers.memory import _get_cognee
        with pytest.raises(RuntimeError, match="not initialized"):
            _get_cognee()


# --- reload resets _configured ---

class TestReload:
    def test_reload_reconfigures_cognee(self):
        import helpers.memory as mem
        import helpers.cognee_init as ci
        ci._configured = True
        ci._cognee_module = MagicMock()
        ci._search_type_class = MagicMock()
        mem.Memory._initialized_subdirs.add("default")
        mem.reload()
        assert ci._configured is True
        assert ci._cognee_module is not None
        assert ci._search_type_class is not None
        assert len(mem.Memory._initialized_subdirs) == 0
        assert len(mem.Memory._datasets_cache) == 0


# --- _delete_data_by_id improved matching ---

@pytest.mark.asyncio
async def test_delete_data_by_id_uses_raw_data_location():
    from helpers.memory import _delete_data_by_id
    import helpers.cognee_init as ci

    mock_cognee = MagicMock()
    mock_ds = MagicMock()
    mock_ds.name = "test_main"
    mock_ds.id = "ds_id_1"

    mock_item = MagicMock()
    mock_item.raw_data_location = "file:///data/doc_abc123.txt"
    mock_item.name = "doc_abc123.txt"
    mock_item.id = "item_id_1"

    mock_cognee.datasets.list_datasets = AsyncMock(return_value=[mock_ds])
    mock_cognee.datasets.list_data = AsyncMock(return_value=[mock_item])
    mock_cognee.datasets.delete_data = AsyncMock()

    ci._cognee_module = mock_cognee
    ci._search_type_class = MagicMock()

    result = await _delete_data_by_id("test_main", "abc123")
    assert result is True
    mock_cognee.datasets.delete_data.assert_called_once_with(
        dataset_id="ds_id_1", data_id="item_id_1"
    )


@pytest.mark.asyncio
async def test_delete_data_by_id_returns_false_when_not_found():
    from helpers.memory import _delete_data_by_id
    import helpers.cognee_init as ci

    mock_cognee = MagicMock()
    mock_ds = MagicMock()
    mock_ds.name = "test_main"
    mock_ds.id = "ds_id_1"
    mock_cognee.datasets.list_datasets = AsyncMock(return_value=[mock_ds])
    mock_cognee.datasets.list_data = AsyncMock(return_value=[])

    ci._cognee_module = mock_cognee
    ci._search_type_class = MagicMock()

    result = await _delete_data_by_id("test_main", "nonexistent_id")
    assert result is False


@pytest.mark.asyncio
async def test_delete_data_by_id_returns_false_for_missing_dataset():
    from helpers.memory import _delete_data_by_id
    import helpers.cognee_init as ci

    mock_cognee = MagicMock()
    mock_cognee.datasets.list_datasets = AsyncMock(return_value=[])

    ci._cognee_module = mock_cognee
    ci._search_type_class = MagicMock()

    result = await _delete_data_by_id("nonexistent_dataset", "some_id")
    assert result is False


# --- configure_cognee integration ---

class TestMemoryCallsConfigureCognee:
    """Verify Memory operations use cognee_init.get_cognee() for module access."""

    @pytest.mark.asyncio
    async def test_insert_documents_uses_initialized_cognee(self):
        from helpers.memory import Memory
        from langchain_core.documents import Document
        import helpers.cognee_init as ci

        mock_cognee = MagicMock()
        mock_cognee.add = AsyncMock()
        ci._cognee_module = mock_cognee
        ci._search_type_class = MagicMock()

        memory = await Memory.get_by_subdir("default", preload_knowledge=False)
        doc = Document(page_content="test", metadata={"area": "main"})
        with patch("helpers.cognee_background.CogneeBackgroundWorker") as MockBg:
            MockBg.get_instance.return_value = MagicMock()
            await memory.insert_documents([doc])

        mock_cognee.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_returns_valid_memory(self):
        from helpers.memory import Memory

        mock_agent = MagicMock()
        mock_agent.context = MagicMock()
        mock_agent.context.config = MagicMock()
        mock_agent.context.config.knowledge_subdirs = []
        mock_agent.context.config.memory_subdir = "default"

        with patch("helpers.memory.get_agent_memory_subdir", return_value="default"), \
             patch("helpers.memory.get_knowledge_subdirs_by_memory_subdir", return_value=[]):
            mem = await Memory.get(mock_agent)

        assert mem.dataset_name == "default"

    @pytest.mark.asyncio
    async def test_insert_documents_works_after_init(self):
        from helpers.memory import Memory
        import helpers.cognee_init as ci

        mock_cognee = MagicMock()
        mock_cognee.add = AsyncMock()
        ci._cognee_module = mock_cognee
        ci._search_type_class = MagicMock()

        from langchain_core.documents import Document
        doc = Document(page_content="test content", metadata={"area": "main"})

        with patch("helpers.cognee_background.CogneeBackgroundWorker") as MockBg:
            MockBg.get_instance.return_value = MagicMock()
            memory = await Memory.get_by_subdir("default", preload_knowledge=False)
            ids = await memory.insert_documents([doc])

        mock_cognee.add.assert_called_once()
        assert len(ids) == 1

    @pytest.mark.asyncio
    async def test_insert_documents_does_not_return_id_on_failure(self):
        from helpers.memory import Memory
        import helpers.cognee_init as ci

        mock_cognee = MagicMock()
        mock_cognee.add = AsyncMock(side_effect=Exception("add failed"))
        ci._cognee_module = mock_cognee
        ci._search_type_class = MagicMock()

        from langchain_core.documents import Document
        doc = Document(page_content="test content", metadata={"area": "main"})

        with patch("helpers.cognee_background.CogneeBackgroundWorker") as MockBg:
            MockBg.get_instance.return_value = MagicMock()
            memory = await Memory.get_by_subdir("default", preload_knowledge=False)
            ids = await memory.insert_documents([doc])

        assert len(ids) == 0

    @pytest.mark.asyncio
    async def test_search_similarity_threshold_handles_cognee_failure(self):
        """If cognee.search() fails, search_similarity_threshold should return []."""
        from helpers.memory import Memory
        import helpers.cognee_init as ci

        mock_cognee = MagicMock()
        mock_cognee.search = AsyncMock(side_effect=Exception("search failed"))
        mock_search_type = MagicMock()
        mock_search_type.CHUNKS = MagicMock(name="CHUNKS")
        ci._cognee_module = mock_cognee
        ci._search_type_class = mock_search_type

        mock_node_set = MagicMock()
        with patch.dict("sys.modules", {"cognee": MagicMock(), "cognee.modules": MagicMock(),
                                         "cognee.modules.engine": MagicMock(),
                                         "cognee.modules.engine.models": MagicMock(),
                                         "cognee.modules.engine.models.node_set": MagicMock(NodeSet=mock_node_set)}):
            memory = await Memory.get_by_subdir("default", preload_knowledge=False)
            results = await memory.search_similarity_threshold(
                query="test", limit=10, threshold=0.5
            )

        assert results == []


# --- Memory.Area enum ---

class TestMemoryAreaEnum:
    def test_area_values(self):
        from helpers.memory import Memory
        assert Memory.Area.MAIN.value == "main"
        assert Memory.Area.FRAGMENTS.value == "fragments"
        assert Memory.Area.SOLUTIONS.value == "solutions"

    def test_area_iteration(self):
        from helpers.memory import Memory
        areas = list(Memory.Area)
        assert len(areas) == 3
        assert Memory.Area.MAIN in areas


# --- Memory.insert_text ---

class TestMemoryInsertText:
    @pytest.mark.asyncio
    async def test_insert_text_returns_id(self):
        from helpers.memory import Memory
        import helpers.cognee_init as ci

        mock_cognee = MagicMock()
        mock_cognee.add = AsyncMock()
        ci._cognee_module = mock_cognee
        ci._search_type_class = MagicMock()

        with patch("helpers.cognee_background.CogneeBackgroundWorker") as MockBg:
            MockBg.get_instance.return_value = MagicMock()
            memory = Memory(dataset_name="default", memory_subdir="default")
            doc_id = await memory.insert_text("hello world", {"area": "main"})

        assert isinstance(doc_id, str)
        assert len(doc_id) > 0
        mock_cognee.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_insert_text_with_metadata(self):
        from helpers.memory import Memory
        import helpers.cognee_init as ci

        mock_cognee = MagicMock()
        mock_cognee.add = AsyncMock()
        ci._cognee_module = mock_cognee
        ci._search_type_class = MagicMock()

        with patch("helpers.cognee_background.CogneeBackgroundWorker") as MockBg:
            MockBg.get_instance.return_value = MagicMock()
            memory = Memory(dataset_name="default", memory_subdir="default")
            doc_id = await memory.insert_text("test", {"area": "solutions", "custom": "value"})

        assert doc_id
        call_args = mock_cognee.add.call_args
        assert "[META:" in call_args[0][0]
        assert "solutions" in call_args[0][0]


# --- Memory.delete_documents_by_query ---

class TestMemoryDeleteDocumentsByQuery:
    @pytest.mark.asyncio
    async def test_delete_documents_by_query_returns_docs(self):
        """search_similarity_threshold is called then results deleted."""
        from helpers.memory import Memory
        from langchain_core.documents import Document

        memory = Memory(dataset_name="default", memory_subdir="default")
        mock_docs = [Document(page_content="match", metadata={"id": "id1"})]

        with patch.object(memory, "search_similarity_threshold", new_callable=AsyncMock,
                          return_value=mock_docs), \
             patch("helpers.memory._delete_data_by_id", new_callable=AsyncMock,
                   return_value=True), \
             patch("helpers.memory._invalidate_dashboard_cache"):
            removed = await memory.delete_documents_by_query("test query", threshold=0.5)

        assert len(removed) == 1
        assert removed[0].metadata["id"] == "id1"


# --- Memory.delete_documents_by_ids ---

class TestMemoryDeleteDocumentsByIds:
    @pytest.mark.asyncio
    async def test_delete_documents_by_ids(self):
        from helpers.memory import Memory
        import helpers.cognee_init as ci

        mock_cognee = MagicMock()
        mock_ds = MagicMock()
        mock_ds.name = "default"
        mock_ds.id = "ds1"
        mock_item = MagicMock()
        mock_item.raw_data_location = "abc123"
        mock_item.id = "item1"
        mock_cognee.datasets.list_datasets = AsyncMock(return_value=[mock_ds])
        mock_cognee.datasets.list_data = AsyncMock(return_value=[mock_item])
        mock_cognee.datasets.delete_data = AsyncMock()
        ci._cognee_module = mock_cognee
        ci._search_type_class = MagicMock()

        memory = Memory(dataset_name="default", memory_subdir="default")
        with patch("helpers.memory._invalidate_dashboard_cache"):
            removed = await memory.delete_documents_by_ids(["abc123"])

        assert len(removed) >= 1


# --- Memory.format_docs_plain ---

class TestMemoryFormatDocsPlain:
    def test_format_docs_plain(self):
        from helpers.memory import Memory
        from langchain_core.documents import Document

        docs = [
            Document(page_content="content1", metadata={"id": "1", "area": "main"}),
            Document(page_content="content2", metadata={"id": "2"}),
        ]
        result = Memory.format_docs_plain(docs)
        assert len(result) == 2
        assert "id: 1" in result[0]
        assert "Content: content1" in result[0]
        assert "Content: content2" in result[1]


# --- Memory.get_timestamp ---

class TestMemoryGetTimestamp:
    def test_get_timestamp_format(self):
        from helpers.memory import Memory
        ts = Memory.get_timestamp()
        assert "202" in ts or "203" in ts
        assert "-" in ts
        assert ":" in ts


# --- Memory.get_document_by_id ---

class TestMemoryGetDocumentById:
    def test_get_document_by_id_returns_none(self):
        from helpers.memory import Memory
        memory = Memory(dataset_name="default", memory_subdir="default")
        result = memory.get_document_by_id("nonexistent")
        assert result is None


# --- Memory.update_documents ---

class TestMemoryUpdateDocuments:
    @pytest.mark.asyncio
    async def test_update_documents_deletes_and_inserts(self):
        from helpers.memory import Memory
        from langchain_core.documents import Document
        import helpers.cognee_init as ci

        mock_cognee = MagicMock()
        mock_cognee.add = AsyncMock()
        mock_ds = MagicMock()
        mock_ds.name = "default_main"
        mock_ds.id = "ds1"
        mock_cognee.datasets.list_datasets = AsyncMock(return_value=[mock_ds])
        mock_cognee.datasets.list_data = AsyncMock(return_value=[])
        ci._cognee_module = mock_cognee
        ci._search_type_class = MagicMock()

        doc = Document(page_content="updated", metadata={"id": "old_id", "area": "main"})
        with patch("helpers.cognee_background.CogneeBackgroundWorker") as MockBg:
            MockBg.get_instance.return_value = MagicMock()
            memory = Memory(dataset_name="default", memory_subdir="default")
            ids = await memory.update_documents([doc])

        assert len(ids) == 1
        mock_cognee.add.assert_called_once()


# --- abs_knowledge_dir ---

class TestAbsKnowledgeDir:
    def test_default_subdir(self):
        from helpers.memory import abs_knowledge_dir
        with patch("helpers.memory.files") as mock_files:
            mock_files.get_abs_path.side_effect = lambda *a: "/".join(str(x) for x in a)
            result = abs_knowledge_dir("default")
        assert "knowledge" in result

    def test_custom_subdir(self):
        from helpers.memory import abs_knowledge_dir
        with patch("helpers.memory.files") as mock_files:
            mock_files.get_abs_path.side_effect = lambda *a: "/".join(str(x) for x in a)
            result = abs_knowledge_dir("custom")
        assert "usr" in result
        assert "knowledge" in result

    def test_named_subdir(self):
        from helpers.memory import abs_knowledge_dir
        with patch("helpers.memory.files") as mock_files:
            mock_files.get_abs_path.side_effect = lambda *a: "/".join(str(x) for x in a)
            result = abs_knowledge_dir("my_knowledge", "sub")
        assert "my_knowledge" in result
        assert "sub" in result


# --- get_existing_memory_subdirs ---

class TestGetExistingMemorySubdirs:
    def test_returns_default_when_exception(self):
        from helpers.memory import get_existing_memory_subdirs
        with patch("helpers.projects.get_projects_parent_folder") as mock_get:
            mock_get.side_effect = Exception("no projects")
            result = get_existing_memory_subdirs()
        assert result == ["default"]

    def test_includes_projects(self):
        from helpers.memory import get_existing_memory_subdirs
        with patch("helpers.projects.get_projects_parent_folder", return_value="/tmp/projects"), \
             patch("os.path.exists", return_value=True), \
             patch("helpers.memory.files") as mock_files:
            mock_files.get_subdirectories.return_value = ["proj1", "proj2"]
            result = get_existing_memory_subdirs()
        assert "default" in result
        assert "projects/proj1" in result
        assert "projects/proj2" in result


# --- abs_db_dir ---

class TestAbsDbDir:
    def test_abs_db_dir_delegates_to_state_dir(self):
        from helpers.memory import abs_db_dir
        with patch("helpers.memory._state_dir") as mock_state:
            mock_state.return_value = "/tmp/state"
            result = abs_db_dir("default")
        assert result == "/tmp/state"


# --- get_custom_knowledge_subdir_abs ---

class TestGetCustomKnowledgeSubdirAbs:
    def test_returns_custom_path(self):
        from helpers.memory import get_custom_knowledge_subdir_abs
        with patch("helpers.memory.files") as mock_files:
            mock_files.get_abs_path.return_value = "/usr/knowledge"
            mock_agent = MagicMock()
            mock_agent.config.knowledge_subdirs = ["custom"]
            result = get_custom_knowledge_subdir_abs(mock_agent)
        assert result == "/usr/knowledge"

    def test_raises_when_no_custom(self):
        from helpers.memory import get_custom_knowledge_subdir_abs
        mock_agent = MagicMock()
        mock_agent.config.knowledge_subdirs = ["default"]
        with pytest.raises(Exception, match="No custom knowledge subdir"):
            get_custom_knowledge_subdir_abs(mock_agent)


# --- Default search types: GRAPH_COMPLETION only ---

class TestDefaultSearchTypesGraphOnly:
    def test_default_search_types_is_graph_completion(self):
        from helpers.cognee_init import _COGNEE_DEFAULTS
        val = _COGNEE_DEFAULTS["cognee_search_types"]
        assert val == "GRAPH_COMPLETION", f"Expected 'GRAPH_COMPLETION', got '{val}'"


# --- Reload invalidates datasets cache ---

class TestReloadInvalidatesDatasetsCache:
    def test_reload_invalidates_datasets_cache(self):
        from helpers.memory import Memory, reload
        import helpers.cognee_init as ci

        Memory._existing_datasets_cache = {"old_ds"}
        Memory._existing_datasets_ts = 999.0

        with patch.object(ci, "configure_cognee"):
            reload()

        assert Memory._existing_datasets_cache is None


# --- Bulk delete optimization ---

class TestDeleteOptimization:
    def _setup_cognee(self, ci, items_list):
        """Wire mock cognee with a single dataset containing items."""
        mock_cognee = MagicMock()

        mock_ds = MagicMock()
        mock_ds.name = "default"
        mock_ds.id = "ds_default"

        mock_cognee.datasets.list_datasets = AsyncMock(return_value=[mock_ds])
        mock_cognee.datasets.list_data = AsyncMock(return_value=items_list)
        mock_cognee.datasets.delete_data = AsyncMock()

        ci._cognee_module = mock_cognee
        ci._search_type_class = MagicMock()
        return mock_cognee

    @staticmethod
    def _make_item(raw_loc: str, item_id: str):
        item = MagicMock()
        item.raw_data_location = raw_loc
        item.name = raw_loc
        item.id = item_id
        return item

    @pytest.mark.asyncio
    async def test_bulk_delete_single_scan(self):
        from helpers.memory import Memory
        import helpers.cognee_init as ci

        items = [
            self._make_item("doc_id1_file.txt", "item1"),
            self._make_item("doc_id2_file.txt", "item2"),
            self._make_item("doc_id3_file.txt", "item3"),
        ]
        mock_cognee = self._setup_cognee(ci, items)

        memory = Memory(dataset_name="default", memory_subdir="default")
        with patch("helpers.memory._invalidate_dashboard_cache"):
            removed = await memory.delete_documents_by_ids(["id1", "id2", "id3"])

        assert len(removed) == 3
        assert mock_cognee.datasets.delete_data.call_count == 3

    @pytest.mark.asyncio
    async def test_bulk_delete_finds_matching_items(self):
        from helpers.memory import Memory
        import helpers.cognee_init as ci

        items = [
            self._make_item("alpha_file.txt", "item_a"),
            self._make_item("beta_file.txt", "item_b"),
            self._make_item("gamma_file.txt", "item_c"),
        ]
        mock_cognee = self._setup_cognee(ci, items)

        memory = Memory(dataset_name="default", memory_subdir="default")
        with patch("helpers.memory._invalidate_dashboard_cache"):
            removed = await memory.delete_documents_by_ids(["alpha", "beta", "gamma"])

        deleted_ids = {doc.metadata["id"] for doc in removed}
        assert deleted_ids == {"alpha", "beta", "gamma"}
        assert mock_cognee.datasets.delete_data.call_count == 3

    @pytest.mark.asyncio
    async def test_bulk_delete_missing_ids_returns_partial(self):
        from helpers.memory import Memory
        import helpers.cognee_init as ci

        items = [self._make_item("found_one.txt", "item_f")]
        mock_cognee = self._setup_cognee(ci, items)

        memory = Memory(dataset_name="default", memory_subdir="default")
        with patch("helpers.memory._invalidate_dashboard_cache"):
            removed = await memory.delete_documents_by_ids(["found_one", "missing_two"])

        assert len(removed) == 1
        assert removed[0].metadata["id"] == "found_one"

    @pytest.mark.asyncio
    async def test_bulk_delete_empty_ids_returns_empty(self):
        from helpers.memory import Memory
        import helpers.cognee_init as ci

        mock_cognee = self._setup_cognee(ci, [])

        memory = Memory(dataset_name="default", memory_subdir="default")
        removed = await memory.delete_documents_by_ids([])

        assert removed == []
        mock_cognee.datasets.list_datasets.assert_not_called()


# --- read_data_item_content ---

class TestReadDataItemContent:
    def test_valid_file_returns_content(self, tmp_path):
        from helpers.memory import read_data_item_content

        f = tmp_path / "mem.txt"
        f.write_text("hello world", encoding="utf-8")

        item = MagicMock()
        item.raw_data_location = str(f)
        item.name = "mem.txt"

        assert read_data_item_content(item) == "hello world"

    def test_file_uri_scheme(self, tmp_path):
        from helpers.memory import read_data_item_content
        from urllib.parse import quote

        f = tmp_path / "doc.txt"
        f.write_text("uri content", encoding="utf-8")

        item = MagicMock()
        item.raw_data_location = f"file://{quote(str(f))}"
        item.name = "doc.txt"

        assert read_data_item_content(item) == "uri content"

    def test_missing_file_falls_back_to_raw_location(self):
        from helpers.memory import read_data_item_content

        item = MagicMock()
        item.raw_data_location = "/nonexistent/path/abc123.txt"
        item.name = "abc123.txt"

        assert read_data_item_content(item) == "/nonexistent/path/abc123.txt"

    def test_none_raw_location_falls_back_to_name(self):
        from helpers.memory import read_data_item_content

        item = MagicMock()
        item.raw_data_location = None
        item.name = "fallback_name"

        assert read_data_item_content(item) == "fallback_name"

    def test_unreadable_file_falls_back_gracefully(self, tmp_path):
        from helpers.memory import read_data_item_content

        f = tmp_path / "locked.txt"
        f.write_text("secret", encoding="utf-8")
        f.chmod(0o000)

        item = MagicMock()
        item.raw_data_location = str(f)
        item.name = "locked.txt"

        result = read_data_item_content(item)
        f.chmod(0o644)
        assert result == str(f)
