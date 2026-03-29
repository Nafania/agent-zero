"""Tests for helpers/document_query.py — import verification and core logic."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TestLangchainImports:
    """Verify updated langchain import paths resolve correctly."""

    def test_langchain_core_messages_import(self):
        from langchain_core.messages import SystemMessage, HumanMessage

        assert SystemMessage is not None
        assert HumanMessage is not None

    def test_langchain_text_splitters_import(self):
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        assert RecursiveCharacterTextSplitter is not None

    def test_langchain_core_documents_import(self):
        from langchain_core.documents import Document

        assert Document is not None

    def test_langchain_community_loaders_import(self):
        from langchain_community.document_loaders import AsyncHtmlLoader

        assert AsyncHtmlLoader is not None

    def test_langchain_community_pdf_loader_import(self):
        from langchain_community.document_loaders.pdf import PyMuPDFLoader

        assert PyMuPDFLoader is not None

    def test_langchain_community_transformers_import(self):
        from langchain_community.document_transformers import MarkdownifyTransformer

        assert MarkdownifyTransformer is not None

    def test_langchain_community_tesseract_parser_import(self):
        from langchain_community.document_loaders.parsers.images import TesseractBlobParser

        assert TesseractBlobParser is not None

    def test_langchain_unstructured_import(self):
        from langchain_unstructured import UnstructuredLoader

        assert UnstructuredLoader is not None

    def test_no_legacy_langchain_schema_import(self):
        """Ensure document_query.py does not use the legacy langchain.schema path."""
        import inspect
        from helpers import document_query

        source = inspect.getsource(document_query)
        assert "from langchain.schema" not in source

    def test_no_legacy_langchain_text_splitter_import(self):
        """Ensure document_query.py does not use the legacy langchain.text_splitter path."""
        import inspect
        from helpers import document_query

        source = inspect.getsource(document_query)
        assert "from langchain.text_splitter" not in source

    def test_no_textloader_import(self):
        """Ensure the unused TextLoader import was removed."""
        import inspect
        from helpers import document_query

        source = inspect.getsource(document_query)
        assert "from langchain_community.document_loaders.text import TextLoader" not in source


class TestDocumentQueryStoreNormalizeUri:
    def test_normalize_file_uri(self):
        from helpers.document_query import DocumentQueryStore

        result = DocumentQueryStore.normalize_uri("file:///tmp/test.txt")
        assert result.startswith("file://")
        assert "test.txt" in result

    def test_normalize_http_to_https(self):
        from helpers.document_query import DocumentQueryStore

        result = DocumentQueryStore.normalize_uri("http://example.com/doc.pdf")
        assert result.startswith("https://")

    def test_normalize_strips_whitespace(self):
        from helpers.document_query import DocumentQueryStore

        result = DocumentQueryStore.normalize_uri("  https://example.com/doc  ")
        assert not result.startswith(" ")
        assert not result.endswith(" ")


class TestDocumentQueryStoreInit:
    def test_store_get_requires_agent(self):
        from helpers.document_query import DocumentQueryStore

        with pytest.raises(ValueError, match="Agent and agent config"):
            DocumentQueryStore.get(None)

    def test_store_initializes_with_agent(self):
        from helpers.document_query import DocumentQueryStore

        agent = MagicMock()
        agent.config = MagicMock()
        store = DocumentQueryStore.get(agent)
        assert store.agent is agent
        assert store.vector_db is None
