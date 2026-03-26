from datetime import datetime
from typing import Any, List, Optional
from python.helpers import guids

import os
import json
import asyncio
import hashlib


from python.helpers.print_style import PrintStyle
from python.helpers import files
from langchain_core.documents import Document
from python.helpers import knowledge_import
from python.helpers.log import Log, LogItem
from enum import Enum
from agent import Agent, AgentContext
import models
import logging
from python.helpers.cognee_init import get_cognee_setting


def _get_cognee():
    from python.helpers.cognee_init import get_cognee
    return get_cognee()


def stable_memory_id_fallback(content: str, dataset_name: str = "") -> str:
    """Deterministic id when Cognee/chunk metadata has no id (feedback correlation)."""
    h = hashlib.sha256()
    h.update(str(dataset_name).encode("utf-8", errors="replace"))
    h.update(b"\0")
    h.update(content[:8000].encode("utf-8", errors="replace"))
    return "syn_" + h.hexdigest()[:32]


class Memory:

    class Area(Enum):
        MAIN = "main"
        FRAGMENTS = "fragments"
        SOLUTIONS = "solutions"

    _initialized: bool = False
    _datasets_cache: dict[str, str] = {}
    _existing_datasets_cache: set[str] | None = None
    _existing_datasets_ts: float = 0
    _DATASETS_CACHE_TTL = 30
    SEARCH_TIMEOUT = 15

    @staticmethod
    async def get(agent: Agent) -> "Memory":
        memory_subdir = get_agent_memory_subdir(agent)
        dataset_name = _subdir_to_dataset(memory_subdir)
        mem = Memory(dataset_name=dataset_name, memory_subdir=memory_subdir)
        if not Memory._initialized:
            Memory._initialized = True
            knowledge_subdirs = get_knowledge_subdirs_by_memory_subdir(
                memory_subdir, agent.config.knowledge_subdirs or []
            )
            if knowledge_subdirs:
                log_item = agent.context.log.log(
                    type="util",
                    heading=f"Initializing Cognee memory in '{memory_subdir}'",
                )
                await mem.preload_knowledge(log_item, knowledge_subdirs, memory_subdir)
        return mem

    @staticmethod
    async def get_by_subdir(
        memory_subdir: str,
        log_item: LogItem | None = None,
        preload_knowledge: bool = True,
    ) -> "Memory":
        dataset_name = _subdir_to_dataset(memory_subdir)
        mem = Memory(dataset_name=dataset_name, memory_subdir=memory_subdir)
        if preload_knowledge:
            import initialize
            agent_config = initialize.initialize_agent()
            knowledge_subdirs = get_knowledge_subdirs_by_memory_subdir(
                memory_subdir, agent_config.knowledge_subdirs or []
            )
            if knowledge_subdirs:
                await mem.preload_knowledge(log_item, knowledge_subdirs, memory_subdir)
        return mem

    @staticmethod
    async def reload(agent: Agent) -> "Memory":
        Memory._initialized = False
        Memory._datasets_cache.clear()
        return await Memory.get(agent)

    def __init__(self, dataset_name: str, memory_subdir: str):
        self.dataset_name = dataset_name
        self.memory_subdir = memory_subdir

    def get_search_datasets(self) -> list[str]:
        """Always search in 'default' + current project dataset (if any)."""
        ds = ["default"]
        if self.dataset_name != "default" and self.dataset_name not in ds:
            ds.append(self.dataset_name)
        return ds

    @staticmethod
    async def _get_existing_dataset_names() -> set[str]:
        import time as _t
        now = _t.monotonic()
        if (Memory._existing_datasets_cache is not None
                and now - Memory._existing_datasets_ts < Memory._DATASETS_CACHE_TTL):
            return Memory._existing_datasets_cache
        try:
            cognee, _ = _get_cognee()
            all_ds = await cognee.datasets.list_datasets()
            Memory._existing_datasets_cache = {ds.name for ds in all_ds}
            Memory._existing_datasets_ts = now
        except Exception:
            if Memory._existing_datasets_cache is not None:
                return Memory._existing_datasets_cache
            return set()
        return Memory._existing_datasets_cache

    @staticmethod
    def _invalidate_datasets_cache():
        Memory._existing_datasets_cache = None

    async def preload_knowledge(
        self, log_item: LogItem | None, kn_dirs: list[str], memory_subdir: str
    ):
        cognee, _ = _get_cognee()

        if log_item:
            log_item.update(heading="Preloading knowledge...")

        state_dir = _state_dir(memory_subdir)
        os.makedirs(state_dir, exist_ok=True)
        index_path = os.path.join(state_dir, "knowledge_import.json")

        index: dict[str, knowledge_import.KnowledgeImport] = {}
        if os.path.exists(index_path):
            with open(index_path, "r") as f:
                index = json.load(f)

        if index:
            try:
                datasets = await cognee.datasets.list_datasets()
                if not datasets:
                    PrintStyle.warning("Cognee DB is empty but index exists — forcing full re-import")
                    if log_item:
                        log_item.stream(progress="\nCognee DB empty, re-importing all knowledge...")
                    index = {}
            except Exception:
                PrintStyle.warning("Cannot check cognee datasets — forcing full re-import")
                index = {}

        index = self._preload_knowledge_folders(log_item, kn_dirs, index)

        for file_key in index:
            entry = index[file_key]
            if entry["state"] in ["changed", "removed"] and entry.get("ids", []):
                for data_id in entry["ids"]:
                    try:
                        await _delete_data_by_id(self.dataset_name, data_id)
                    except Exception:
                        pass
            if entry["state"] == "changed" and entry.get("documents"):
                new_ids = []
                area = entry.get("metadata", {}).get("area", "main")
                for doc in entry["documents"]:
                    content = doc.page_content if hasattr(doc, "page_content") else str(doc)
                    try:
                        await cognee.add(
                            content,
                            dataset_name=self.dataset_name,
                            node_set=[area],
                        )
                        new_ids.append(guids.generate_id(10))
                    except Exception as e:
                        PrintStyle.error(f"Failed to import knowledge: {e}")
                entry["ids"] = new_ids

        index = {k: v for k, v in index.items() if v["state"] != "removed"}

        for file_key in index:
            if "documents" in index[file_key]:
                del index[file_key]["documents"]
            if "state" in index[file_key]:
                del index[file_key]["state"]
        with open(index_path, "w") as f:
            json.dump(index, f)

    def _preload_knowledge_folders(
        self,
        log_item: LogItem | None,
        kn_dirs: list[str],
        index: dict[str, knowledge_import.KnowledgeImport],
    ):
        for kn_dir in kn_dirs:
            index = knowledge_import.load_knowledge(
                log_item,
                abs_knowledge_dir(kn_dir),
                index,
                {"area": Memory.Area.MAIN.value},
                filename_pattern="*",
                recursive=False,
            )
            for area in Memory.Area:
                index = knowledge_import.load_knowledge(
                    log_item,
                    abs_knowledge_dir(kn_dir, area.value),
                    index,
                    {"area": area.value},
                    recursive=True,
                )
        return index

    def get_document_by_id(self, id: str) -> Document | None:
        return None

    async def search_similarity_threshold(
        self, query: str, limit: int, threshold: float, filter: str = "",
        include_default: bool = True, session_id: str | None = None,
    ) -> list[Document]:
        cognee, SearchType = _get_cognee()
        from cognee.modules.engine.models.node_set import NodeSet

        node_names = _parse_filter_to_node_names(filter)
        datasets = self.get_search_datasets() if include_default else [self.dataset_name]

        try:
            results = await cognee.search(
                query_text=query,
                top_k=limit,
                datasets=datasets,
                node_type=NodeSet,
                node_name=node_names if node_names else None,
                session_id=session_id,
            )
        except Exception as e:
            PrintStyle.error(f"cognee.search failed: {e}")
            return []

        return _results_to_documents(results or [], limit)

    async def delete_documents_by_query(
        self, query: str, threshold: float, filter: str = ""
    ) -> list[Document]:
        docs = await self.search_similarity_threshold(
            query=query, limit=100, threshold=threshold, filter=filter,
            include_default=False,
        )
        if docs:
            ids = [doc.metadata.get("id", "") for doc in docs if doc.metadata.get("id")]
            for doc_id in ids:
                try:
                    await _delete_data_by_id(self.dataset_name, doc_id)
                except Exception:
                    pass
            _invalidate_dashboard_cache()
        return docs

    async def delete_documents_by_ids(self, ids: list[str]) -> list[Document]:
        if not ids:
            return []

        cognee, _ = _get_cognee()
        removed = []
        id_set = set(ids)

        try:
            datasets_list = await cognee.datasets.list_datasets()
            target = None
            for ds in datasets_list:
                if ds.name == self.dataset_name:
                    target = ds
                    break
            if target:
                data_items = await cognee.datasets.list_data(target.id)
                for item in data_items:
                    item_text = getattr(item, "raw_data_location", "") or getattr(item, "name", "") or ""
                    item_str = str(item_text)
                    for doc_id in list(id_set):
                        if doc_id in item_str:
                            await cognee.datasets.delete_data(
                                dataset_id=target.id,
                                data_id=item.id,
                            )
                            removed.append(Document(page_content="", metadata={"id": doc_id}))
                            id_set.discard(doc_id)
                            break
        except Exception as e:
            PrintStyle.error(f"Failed to delete from {self.dataset_name}: {e}")

        if removed:
            _invalidate_dashboard_cache()
        return removed

    async def insert_text(self, text: str, metadata: dict = {}) -> str:
        doc = Document(text, metadata=metadata)
        ids = await self.insert_documents([doc])
        return ids[0]

    async def insert_documents(self, docs: list[Document]) -> list[str]:
        cognee, _ = _get_cognee()
        ids = []
        timestamp = self.get_timestamp()
        from python.helpers.cognee_background import CogneeBackgroundWorker

        for doc in docs:
            doc_id = guids.generate_id(10)
            doc.metadata["id"] = doc_id
            doc.metadata["timestamp"] = timestamp
            area = doc.metadata.get("area", Memory.Area.MAIN.value)
            if not area:
                area = Memory.Area.MAIN.value
                doc.metadata["area"] = area

            meta_header = json.dumps(doc.metadata, default=str)
            enriched_text = f"[META:{meta_header}]\n{doc.page_content}"

            try:
                await cognee.add(
                    enriched_text,
                    dataset_name=self.dataset_name,
                    node_set=[area],
                )
                ids.append(doc_id)
                CogneeBackgroundWorker.get_instance().mark_dirty(self.dataset_name)
            except Exception as e:
                PrintStyle.error(f"Cognee insert failed for {doc_id}: {e}")

        _invalidate_dashboard_cache()
        return ids

    async def update_documents(self, docs: list[Document]) -> list:
        ids = [doc.metadata["id"] for doc in docs]
        await self.delete_documents_by_ids(ids)
        result = await self.insert_documents(docs)
        return result

    @staticmethod
    def format_docs_plain(docs: list[Document]) -> list[str]:
        result = []
        for doc in docs:
            text = ""
            for k, v in doc.metadata.items():
                text += f"{k}: {v}\n"
            text += f"Content: {doc.page_content}"
            result.append(text)
        return result

    @staticmethod
    def get_timestamp():
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _subdir_to_dataset(memory_subdir: str) -> str:
    return memory_subdir.replace("/", "_").replace(" ", "_").lower()


def _state_dir(memory_subdir: str) -> str:
    if memory_subdir.startswith("projects/"):
        from python.helpers.projects import get_project_meta_folder
        return files.get_abs_path(get_project_meta_folder(memory_subdir[9:]), "cognee_state")
    return files.get_abs_path("usr/cognee_state", memory_subdir)


def _parse_filter_to_node_names(filter_str: str) -> list[str]:
    if not filter_str:
        return []
    node_names = []
    for area in Memory.Area:
        if area.value in filter_str:
            node_names.append(area.value)
    return node_names


def recall_text_and_feedback_items(
    answers: Any,
    limit: int,
    *,
    context_id: str,
    fallback_dataset: str,
    kind: str,
) -> tuple[list[str], list[dict[str, Any]]]:
    """
    Plain recall lines for prompts plus rows the UI can POST to /memory_feedback.
    Each row: text, memory_id, dataset, context_id, kind ('memory' | 'solution').
    """
    docs = _results_to_documents(answers or [], limit)
    texts: list[str] = []
    items: list[dict[str, Any]] = []
    for doc in docs:
        content = (doc.page_content or "").strip()
        if not content:
            continue
        ds = str(doc.metadata.get("dataset") or fallback_dataset or "default")
        mid = str(doc.metadata.get("id") or stable_memory_id_fallback(content, ds))
        texts.append(content)
        items.append(
            {
                "text": content,
                "memory_id": mid,
                "dataset": ds,
                "context_id": str(context_id or ""),
                "kind": kind,
            }
        )
    return texts, items


def _results_to_documents(results: Any, limit: int) -> list[Document]:
    docs = []
    if not results:
        return docs

    for result in results:
        if len(docs) >= limit:
            break

        content = ""
        metadata: dict[str, Any] = {}

        raw = result
        if hasattr(result, "search_result"):
            raw = result.search_result

        if isinstance(raw, str):
            content, metadata = _extract_metadata_from_text(raw)
        elif hasattr(raw, "text"):
            content, metadata = _extract_metadata_from_text(str(raw.text))
        elif hasattr(raw, "page_content"):
            content = raw.page_content
            metadata = getattr(raw, "metadata", {})
        elif isinstance(raw, dict):
            content = raw.get("text", raw.get("content", str(raw)))
            content, metadata = _extract_metadata_from_text(content)
        else:
            content, metadata = _extract_metadata_from_text(str(raw))

        if hasattr(result, "dataset_name") and result.dataset_name:
            metadata.setdefault("dataset", result.dataset_name)

        if not metadata.get("id"):
            ds = str(metadata.get("dataset") or "")
            metadata["id"] = stable_memory_id_fallback(content, ds)
        if not metadata.get("area"):
            metadata["area"] = Memory.Area.MAIN.value
        if not metadata.get("timestamp"):
            metadata["timestamp"] = Memory.get_timestamp()

        docs.append(Document(page_content=content, metadata=metadata))

    return docs


def _deduplicate_documents(docs: list[Document]) -> list[Document]:
    seen: set[str] = set()
    unique: list[Document] = []
    for doc in docs:
        key = doc.metadata.get("id", "")
        if not key:
            key = doc.page_content[:200]
        if key not in seen:
            seen.add(key)
            unique.append(doc)
    return unique


def _extract_metadata_from_text(text: str) -> tuple[str, dict]:
    if text.startswith("[META:"):
        try:
            meta_end = text.index("]\n")
            meta_json = text[6:meta_end]
            metadata = json.loads(meta_json)
            content = text[meta_end + 2:]
            return content, metadata
        except (ValueError, json.JSONDecodeError):
            pass
    return text, {"area": Memory.Area.MAIN.value}


async def _delete_data_by_id(dataset_name: str, data_id: str):
    cognee, _ = _get_cognee()
    try:
        datasets = await cognee.datasets.list_datasets()
        target = None
        for ds in datasets:
            if ds.name == dataset_name:
                target = ds
                break
        if not target:
            return False
        data_items = await cognee.datasets.list_data(target.id)
        for item in data_items:
            item_text = getattr(item, "raw_data_location", "") or getattr(item, "name", "") or ""
            if data_id in str(item_text):
                await cognee.datasets.delete_data(
                    dataset_id=target.id,
                    data_id=item.id,
                )
                return True
    except Exception as e:
        PrintStyle.error(f"Failed to delete data {data_id} from {dataset_name}: {e}")
    return False


def _invalidate_dashboard_cache():
    try:
        from python.api.memory_dashboard import invalidate_dashboard_cache
        invalidate_dashboard_cache()
    except Exception:
        pass


def get_custom_knowledge_subdir_abs(agent: Agent) -> str:
    for dir in agent.config.knowledge_subdirs:
        if dir != "default":
            if dir == "custom":
                return files.get_abs_path("usr/knowledge")
            return files.get_abs_path("usr/knowledge", dir)
    raise Exception("No custom knowledge subdir set")


def reload():
    import python.helpers.cognee_init as ci
    ci._configured = False
    ci._cognee_module = None
    ci._search_type_class = None
    Memory._initialized = False
    Memory._datasets_cache.clear()
    Memory._invalidate_datasets_cache()
    ci.configure_cognee()


def abs_db_dir(memory_subdir: str) -> str:
    return _state_dir(memory_subdir)


def abs_knowledge_dir(knowledge_subdir: str, *sub_dirs: str) -> str:
    if knowledge_subdir.startswith("projects/"):
        from python.helpers.projects import get_project_meta_folder
        return files.get_abs_path(
            get_project_meta_folder(knowledge_subdir[9:]), "knowledge", *sub_dirs
        )
    if knowledge_subdir == "default":
        return files.get_abs_path("knowledge", *sub_dirs)
    if knowledge_subdir == "custom":
        return files.get_abs_path("usr/knowledge", *sub_dirs)
    return files.get_abs_path("usr/knowledge", knowledge_subdir, *sub_dirs)


def get_memory_subdir_abs(agent: Agent) -> str:
    subdir = get_agent_memory_subdir(agent)
    return _state_dir(subdir)


def get_agent_memory_subdir(agent: Agent) -> str:
    return get_context_memory_subdir(agent.context)


def get_context_memory_subdir(context: AgentContext) -> str:
    from python.helpers.projects import (
        get_context_memory_subdir as get_project_memory_subdir,
    )
    memory_subdir = get_project_memory_subdir(context)
    if memory_subdir:
        return memory_subdir
    return context.config.memory_subdir or "default"


def get_existing_memory_subdirs() -> list[str]:
    try:
        subdirs: set[str] = set()

        from python.helpers.projects import get_projects_parent_folder
        project_parent = get_projects_parent_folder()
        if os.path.exists(project_parent):
            for name in files.get_subdirectories(project_parent):
                subdirs.add(f"projects/{name}")

        result = sorted(subdirs)
        result.insert(0, "default")
        return result
    except Exception as e:
        PrintStyle.error(f"Failed to get memory subdirectories: {str(e)}")
        return ["default"]


def get_knowledge_subdirs_by_memory_subdir(
    memory_subdir: str, default: list[str]
) -> list[str]:
    result = list(default)
    if memory_subdir.startswith("projects/"):
        from python.helpers.projects import get_project_meta_folder
        result.append(get_project_meta_folder(memory_subdir[9:], "knowledge"))
    return result
