# Agent Zero: Aggressive Dependency Bump

**Date:** 2026-03-23
**Scope:** All packages in `requirements.txt` and `requirements2.txt`
**Strategy:** Layered (grouped by risk), 4 groups, one commit per group

---

## Current State

- **requirements.txt** — 54 packages (main deps), installed first
- **requirements2.txt** — 3 packages (overrides: `litellm`, `openai`, `cognee`), installed after
- Installation via `uv pip install` inside Docker
- ~2400 unit tests, 76% coverage
- Duplicate `crontab==1.0.1` entry to be removed

## Group 1 — Utilities & Low Risk

One commit. Minor/patch bumps, no API changes expected.

| Package | Current | Target |
|---------|---------|--------|
| `a2wsgi` | ==1.10.8 | ==1.10.10 |
| `ansio` | ==0.0.1 | ==0.0.2 |
| `bubus` | >=1.4.7,<2.0.0 | >=1.6.0,<2.0.0 |
| `crontab` | ==1.0.1 (duplicate) | ==1.0.5 (remove duplicate) |
| `GitPython` | ==3.1.43 | ==3.1.46 |
| `lxml_html_clean` | ==0.3.1 | ==0.4.4 |
| `markdown` | ==3.7 | ==3.10.2 |
| `pytz` | ==2024.2 | ==2026.1.post1 |
| `pywinpty` | ==3.0.2 | ==3.0.3 |
| `simpleeval` | ==1.0.3 | ==1.0.7 |
| `webcolors` | ==24.6.0 | ==25.10.0 |

**Verification:** `pytest tests/ -m "not integration"` — expect all green, no code changes.

## Group 2 — Infrastructure & Document Processing

> **Note:** `litellm` and `openai` live in `requirements2.txt` (override file installed after `requirements.txt`). All other packages are in `requirements.txt`.

One commit. Mix of minor bumps and several major bumps. Some require code investigation.

### Minor/Patch Bumps (no code changes expected)

| Package | Current | Target |
|---------|---------|--------|
| `flask[async]` | ==3.0.3 | ==3.1.3 |
| `uvicorn` | >=0.38.0 | >=0.42.0 |
| `pydantic` | >=2.11.7 | >=2.12.5 |
| `python-dotenv` | >=1.1.0 | >=1.2.2 |
| `python-socketio` | >=5.14.2 | >=5.16.1 |
| `wsproto` | >=1.2.0 | >=1.3.2 |
| `boto3` | >=1.35.0 | >=1.42.74 |
| `exchangelib` | >=5.4.3 | >=5.6.0 |
| `imapclient` | >=3.0.1 | >=3.1.0 |
| `html2text` | >=2024.2.26 | >=2025.4.15 |
| `beautifulsoup4` | >=4.12.3 | >=4.14.3 |
| `psutil` | >=7.0.0 | >=7.2.2 |
| `tiktoken` | >=0.8.0 | >=0.12.0 |
| `pymupdf` | ==1.25.3 | ==1.27.2.2 |
| `unstructured[all-docs]` | ==0.18.18 | ==0.18.32 |
| `unstructured-client` | ==0.31.0 | ==0.42.10 |
| `fasta2a` | ==0.5.0 | ==0.6.0 |

### Major Bumps in This Group

#### `paramiko` 3.5.0 → 4.0.0 — LOW RISK

- **What breaks:** DSA/DSSKey algorithm support removed entirely.
- **Codebase impact:** No `paramiko` imports or API usage anywhere in project code. Only listed as a dependency.
- **Action:** Bump version, no code changes.

#### `pathspec` >=0.12.1 → >=1.0.4 — LOW RISK

- **What breaks:** `GitIgnorePattern` removed (deprecated since v0.4). Python 3.8 dropped.
- **Codebase impact:** No `pathspec` imports or API usage anywhere. Transitive dependency only.
- **Action:** Bump version, no code changes.

#### `ipython` >=8.0.0 → >=9.11.0 — LOW RISK

- **What breaks:** Deprecated shim modules removed, color system rewrite.
- **Codebase impact:** Only used as CLI: `ipython -c <code>` in `code_execution_tool.py`. No Python API calls.
- **Action:** Bump version, no code changes.

#### `duckduckgo-search` 6.1.12 → 8.1.1 — MEDIUM RISK

- **What breaks in v8:**
  - `AsyncDDGS` removed — NOT USED in codebase ✓
  - `answers()`, `maps()`, `suggestions()`, `translate()` removed — NOT USED ✓
  - Multithreading removed from `text()` — performance change only
  - Package potentially renamed to `ddgs` on PyPI
- **Codebase impact:** `helpers/duckduckgo_search.py` uses `from duckduckgo_search import DDGS` and `DDGS().text(query, region=..., safesearch=..., timelimit=..., max_results=...)`.
- **Action:**
  1. Verify `from duckduckgo_search import DDGS` still works in 8.x (or if import path changed to `ddgs`)
  2. Verify `text()` method signature unchanged
  3. Update import if needed
  4. Update pip package name in requirements.txt if renamed

#### `fastmcp` 2.13.1 → 3.1.1 — HIGH RISK

- **What breaks in v3:**
  - Constructor params removed: `host`, `port`, `log_level`, `debug`, `sse_path`, etc.
  - `get_tools/get_resources/get_prompts` → `list_tools/list_resources/list_prompts`
  - `ctx.set_state/get_state` now async
  - `PromptMessage` → `fastmcp.prompts.Message`
- **Codebase impact** (`helpers/mcp_server.py`, 489 lines, tracked in git):
  - `FastMCP(name=..., instructions=...)` — safe, only uses non-removed params ✓
  - `@mcp_server.tool(name=..., description=..., tags=..., annotations=...)` — decorator, should work ✓
  - `from fastmcp.server.http import create_sse_app, create_base_app, build_resource_metadata_url` — **RISK: internal imports may have moved**
  - `fastmcp.settings.message_path/sse_path/streamable_http_path/debug` — **RISK: settings module API**
  - `mcp_server._mcp_server` — **RISK: private attribute**
  - `mcp_server.auth` — **RISK: auth API**
  - `mcp_server._get_additional_http_routes()` — **RISK: private method**
- **Action:**
  1. Read fastmcp 3.x source/docs for `fastmcp.server.http` module — verify `create_sse_app`, `create_base_app`, `build_resource_metadata_url` still exist
  2. Verify `fastmcp.settings` module API
  3. Verify `._mcp_server`, `.auth`, `._get_additional_http_routes()` on `FastMCP` object
  4. Refactor `DynamicMcpProxy` if any of these changed
  5. Run MCP-related tests: `tests/helpers/test_mcp_server.py`, `tests/helpers/test_mcp_handler.py`, `tests/api/test_mcp_server_get_detail.py`, `tests/api/test_mcp_server_get_log.py`, `tests/api/test_mcp_servers_apply.py`, `tests/api/test_mcp_servers_status.py`

**Verification:** `pytest tests/ -m "not integration"` after all changes in this group.

## Group 3 — Memory & Embeddings

One commit.

#### `sentence-transformers` 3.0.1 → 5.3.0 — LOW RISK

- **What breaks:** Nothing — v5 is fully backwards compatible per migration guide.
- **Codebase impact** (`models.py`):
  - `SentenceTransformer(model, **kwargs)` — constructor, unchanged
  - `.encode(texts, convert_to_tensor=False)` — two call sites, unchanged
- **Action:** Bump version, no code changes.

#### `faiss-cpu` >=1.9.0 → >=1.13.2 — LOW RISK

- **Action:** Bump lower bound. Minor version bumps.

**Verification:** `pytest tests/ -m "not integration"` — focus on `tests/test_models.py` embedding tests.

## Group 4 — LLM Core

One commit. Most critical group — the LLM pipeline.

> **Note:** `litellm` and `openai` pins live in `requirements2.txt`, not `requirements.txt`.

#### `litellm` 1.79.3 → 1.82.6 — MEDIUM RISK

- **Codebase impact:** Core of all LLM calls in `models.py`. Uses `completion`, `acompletion`, `embedding`, `token_counter`, `get_model_info`.
- **Action:** Bump version. Minor version, should be backwards compatible. Verify via tests.

#### `openai` >=1.99.5 → >=2.29.0 — MEDIUM RISK

- **Codebase impact** (`models.py`):
  - `import openai`
  - `getattr(openai, "APITimeoutError", Exception)` and 5 other error classes for retry logic
  - No direct API calls — all go through litellm
- **What breaks:** Error classes should persist in 2.x. The `getattr` with `Exception` fallback makes this safe even if classes move.
- **Action:** Bump version. Verify error class names still exist in `openai` module.

#### `langchain-core` 0.3.81 → 1.2.21 — HIGH RISK

- **What breaks in 1.0:**
  - Legacy `langchain.*` import paths moved to `langchain-classic`
  - `langchain_core.*` paths should be stable
- **Codebase impact:**
  - `models.py`: `from langchain.embeddings.base import Embeddings` — **BREAKS** (legacy path)
  - `document_query.py`: `from langchain.schema import SystemMessage, HumanMessage` — **BREAKS** (legacy path)
  - `document_query.py`: `from langchain.text_splitter import RecursiveCharacterTextSplitter` — **BREAKS** (legacy path)
  - `models.py`: `from langchain_core.language_models.chat_models import SimpleChatModel` — should be fine
  - `models.py`: `from langchain_core.messages import ...` — should be fine
  - `document_query.py`: `from langchain_core.documents import Document` — should be fine
- **Action — required code changes:**
  1. `models.py`: `from langchain.embeddings.base import Embeddings` → `from langchain_core.embeddings import Embeddings`
  2. `document_query.py`: `from langchain.schema import SystemMessage, HumanMessage` → `from langchain_core.messages import SystemMessage, HumanMessage`
  3. `document_query.py`: `from langchain.text_splitter import RecursiveCharacterTextSplitter` → `from langchain_text_splitters import RecursiveCharacterTextSplitter`. Confirm whether `langchain-text-splitters` must be added to `requirements.txt` or is already pulled in transitively by `langchain-core` or `langchain-community`.
  4. Verify `SimpleChatModel` still in `langchain_core.language_models.chat_models`
  5. Verify `ChatGenerationChunk` still in `langchain_core.outputs.chat_generation`
  6. Verify callback managers still in `langchain_core.callbacks.manager`

#### `langchain-community` 0.3.19 → 0.4.1 — MEDIUM RISK

- **Codebase impact** (`document_query.py`):
  - `AsyncHtmlLoader`, `PyMuPDFLoader`, `TextLoader` (unused import)
  - `MarkdownifyTransformer`, `TesseractBlobParser`
- **Action:** Bump version. Verify loader/transformer APIs unchanged. Remove unused `TextLoader` import.

#### `langchain-unstructured` 0.1.6 → 1.0.1 — HIGH RISK

- **Codebase impact** (`document_query.py`):
  - `from langchain_unstructured import UnstructuredLoader`
  - Used for URL-mode and temp-file-mode document loading
- **Action:** Verify `UnstructuredLoader` constructor and `.load()` method unchanged in 1.0.

**Verification:** `pytest tests/ -m "not integration"` — focus on `tests/test_models.py`, `tests/helpers/test_document_query.py`.

## Packages Already at Latest (No Changes)

| Package | Version |
|---------|---------|
| `browser-use` | 0.12.2 |
| `docker` | 7.1.0 |
| `flask-basicauth` | 0.2.0 |
| `flaredantic` | 0.1.5 |
| `inputimeout` | 1.0.4 |
| `mcp` | 1.26.0 |
| `newspaper3k` | 0.2.8 |
| `openai-whisper` | 20250625 |
| `nest-asyncio` | 1.6.0 |
| `markdownify` | 1.2.2 |
| `pytesseract` | 0.3.13 |
| `pdf2image` | 1.17.0 |
| `soundfile` | 0.13.1 |
| `cognee` | >=0.5.5 (latest is 0.5.5) |

## Packages Within Range (Bump Lower Bound Only)

| Package | Current | Target | Notes |
|---------|---------|--------|-------|
| `kokoro` | >=0.9.2 | >=0.9.4 | Group 1, TTS engine, minor bump |
| `pypdf` | >=6.6.2,<7.0.0 | >=6.9.2,<7.0.0 | Group 2, document processing, within range |

## Cleanup

- Remove the duplicate `crontab` line from requirements.txt

## Verification Strategy

For each group:
1. Update versions in `requirements.txt` / `requirements2.txt`
2. Apply any required code changes (import path fixes, API adjustments)
3. Run `pytest tests/ -m "not integration"` (~2400 tests)
4. If tests fail — isolate which package caused it, fix or rollback that package
5. Commit the group

Final verification after all groups:
- Docker build to verify all deps resolve together
- Integration tests if possible
