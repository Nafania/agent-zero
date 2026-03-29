# Agent Zero: Aggressive Dependency Bump — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bump all dependencies in agent-zero to latest versions and verify everything works.

**Architecture:** Layered update in 4 groups (utilities → infrastructure → memory → LLM core), one commit per group. Each group gets its versions bumped, code fixed if needed, and tests run before committing.

**Tech Stack:** Python, pip/uv, pytest, Docker

**Spec:** `docs/superpowers/specs/2026-03-23-dependency-bump-design.md`

---

### Task 1: Group 1 — Utilities & Low Risk

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Update utility package versions in requirements.txt**

Apply these changes to `requirements.txt`:

```
a2wsgi==1.10.8        →  a2wsgi==1.10.10
ansio==0.0.1          →  ansio==0.0.2
bubus>=1.4.7,<2.0.0   →  bubus>=1.6.0,<2.0.0
crontab==1.0.1        →  crontab==1.0.5       (also remove the duplicate crontab==1.0.1 line)
GitPython==3.1.43     →  GitPython==3.1.46
kokoro>=0.9.2         →  kokoro>=0.9.4
lxml_html_clean==0.3.1 →  lxml_html_clean==0.4.4
markdown==3.7         →  markdown==3.10.2
pytz==2024.2          →  pytz==2026.1.post1
pywinpty==3.0.2       →  pywinpty==3.0.3       (keep the ; sys_platform == "win32" marker)
simpleeval==1.0.3     →  simpleeval==1.0.7
webcolors==24.6.0     →  webcolors==25.10.0
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/ -m "not integration" -x -q`
Expected: All pass, no failures

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: bump Group 1 utilities (a2wsgi, ansio, bubus, crontab, GitPython, kokoro, lxml, markdown, pytz, pywinpty, simpleeval, webcolors)"
```

---

### Task 2: Group 2 — Infrastructure & Document Processing (minor bumps)

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Update minor/patch infrastructure versions in requirements.txt**

Apply these changes to `requirements.txt`:

```
flask[async]==3.0.3           →  flask[async]==3.1.3
uvicorn>=0.38.0               →  uvicorn>=0.42.0
pydantic>=2.11.7              →  pydantic>=2.12.5
python-dotenv>=1.1.0          →  python-dotenv>=1.2.2
python-socketio>=5.14.2       →  python-socketio>=5.16.1
wsproto>=1.2.0                →  wsproto>=1.3.2
boto3>=1.35.0                 →  boto3>=1.42.74
exchangelib>=5.4.3            →  exchangelib>=5.6.0
imapclient>=3.0.1             →  imapclient>=3.1.0
html2text>=2024.2.26          →  html2text>=2025.4.15
beautifulsoup4>=4.12.3        →  beautifulsoup4>=4.14.3
psutil>=7.0.0                 →  psutil>=7.2.2
tiktoken>=0.8.0               →  tiktoken>=0.12.0
pymupdf==1.25.3               →  pymupdf==1.27.2.2
unstructured[all-docs]==0.18.18  →  unstructured[all-docs]==0.18.32
unstructured-client==0.31.0   →  unstructured-client==0.42.10
fasta2a==0.5.0                →  fasta2a==0.6.0
pypdf>=6.6.2,<7.0.0           →  pypdf>=6.9.2,<7.0.0
```

- [ ] **Step 2: Update low-risk major bumps in requirements.txt**

```
paramiko==3.5.0      →  paramiko==4.0.0
pathspec>=0.12.1     →  pathspec>=1.0.4
ipython>=8.0.0       →  ipython>=9.11.0
```

No code changes needed — paramiko has no API usage (only a dep), pathspec has no API usage, ipython is CLI-only (`ipython -c`).

- [ ] **Step 3: Run tests**

Run: `pytest tests/ -m "not integration" -x -q`
Expected: All pass, no failures

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore: bump Group 2 infrastructure (flask, uvicorn, pydantic, paramiko 4.0, ipython 9.x, unstructured, pymupdf, and 15 more)"
```

---

### Task 3: Group 2 — duckduckgo-search 6 → 8 (medium risk)

**Files:**
- Modify: `requirements.txt`
- Modify: `helpers/duckduckgo_search.py`
- Verify: `tests/helpers/test_duckduckgo_search.py`

- [ ] **Step 1: Check if `duckduckgo-search` 8.x still uses `from duckduckgo_search import DDGS`**

The pip package `duckduckgo-search` 8.1.1 still provides `from duckduckgo_search import DDGS` but emits a RuntimeWarning recommending migration to the `ddgs` package. The new package `ddgs` uses `from ddgs import DDGS`.

Decision: Switch to `ddgs` package to avoid deprecation warnings.

- [ ] **Step 2: Update requirements.txt**

```
duckduckgo-search==6.1.12  →  ddgs==8.1.1
```

- [ ] **Step 3: Update import in helpers/duckduckgo_search.py**

Change:
```python
from duckduckgo_search import DDGS
```
To:
```python
from ddgs import DDGS
```

- [ ] **Step 4: Update mock path in tests/helpers/test_duckduckgo_search.py**

Find all `patch("helpers.duckduckgo_search.DDGS")` calls — these should still work because the mock target is the name as imported in the helper module, not the source package. Verify this.

- [ ] **Step 5: Update conftest.py optional module stub**

In `conftest.py` (repo root), find `"duckduckgo_search"` in `_OPTIONAL_MODULES` and change to `"ddgs"`.

- [ ] **Step 6: Run tests**

Run: `pytest tests/helpers/test_duckduckgo_search.py -v`
Expected: All pass

Run: `pytest tests/ -m "not integration" -x -q`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add requirements.txt helpers/duckduckgo_search.py tests/helpers/test_duckduckgo_search.py conftest.py
git commit -m "chore: migrate duckduckgo-search to ddgs 8.1.1"
```

---

### Task 4: Group 2 — fastmcp 2 → 3 (high risk)

**Files:**
- Modify: `requirements.txt`
- Possibly modify: `helpers/mcp_server.py` (tracked in git, not in workspace — use `git show HEAD:helpers/mcp_server.py` to read). Key class to watch: `DynamicMcpProxy` which uses fastmcp internal APIs.
- Verify: `tests/helpers/test_mcp_server.py`, `tests/helpers/test_mcp_handler.py`, `tests/api/test_mcp_server_get_detail.py`, `tests/api/test_mcp_server_get_log.py`, `tests/api/test_mcp_servers_apply.py`, `tests/api/test_mcp_servers_status.py`

- [ ] **Step 1: Read fastmcp 3.x source to verify internal APIs**

Before bumping, verify these imports/APIs still exist in fastmcp 3.x. Use `pip3 download fastmcp==3.1.1 --no-deps -d /tmp/fastmcp3` then inspect, or check docs:

1. `from fastmcp.server.http import create_sse_app, create_base_app, build_resource_metadata_url` — do these functions still exist?
2. `fastmcp.settings` module — does it still have `message_path`, `sse_path`, `streamable_http_path`, `debug`?
3. `FastMCP._mcp_server` — does this private attribute still exist?
4. `FastMCP.auth` — does this property still exist?
5. `FastMCP._get_additional_http_routes()` — does this method still exist?

If any of these have moved or been removed, document the exact replacement before proceeding.

- [ ] **Step 2: Update requirements.txt**

```
fastmcp==2.13.1  →  fastmcp==3.1.1
```

- [ ] **Step 3: Fix code in helpers/mcp_server.py (if needed)**

Based on fastmcp 3.0 breaking changes that affect this file:

**Known safe:** `FastMCP(name=..., instructions=...)` constructor — only uses `name` and `instructions`, both still supported.

**Known safe:** `@mcp_server.tool(name=..., description=..., tags=..., annotations=...)` decorator — still works, but now returns the original function instead of a component object. Since `send_message` and `finish_chat` are only used as tool handlers (not accessed for `.name`/`.description`), this is fine.

**Potentially breaking:**
- `from fastmcp.server.http import create_sse_app, create_base_app, build_resource_metadata_url` — if moved, update import path
- `fastmcp.settings.message_path` etc. — if settings API changed, update access pattern
- `mcp_server._mcp_server` — if internal structure changed, find new equivalent
- `mcp_server.auth` — if auth API changed, update
- `mcp_server._get_additional_http_routes()` — if removed, find new equivalent

Apply fixes based on Step 1 findings.

- [ ] **Step 4: Run MCP-related tests**

Run: `pytest tests/helpers/test_mcp_server.py tests/helpers/test_mcp_handler.py tests/api/test_mcp_server_get_detail.py tests/api/test_mcp_server_get_log.py tests/api/test_mcp_servers_apply.py tests/api/test_mcp_servers_status.py -v`
Expected: All pass

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -m "not integration" -x -q`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add requirements.txt helpers/mcp_server.py
git commit -m "chore: bump fastmcp 2.13.1 → 3.1.1"
```

---

### Task 5: Group 3 — Memory & Embeddings

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Update versions in requirements.txt**

```
sentence-transformers==3.0.1  →  sentence-transformers==5.3.0
faiss-cpu>=1.9.0              →  faiss-cpu>=1.13.2
```

No code changes needed — sentence-transformers v5 is fully backwards compatible. The codebase uses `SentenceTransformer(model)` constructor and `.encode(texts, convert_to_tensor=False)` which are unchanged.

- [ ] **Step 2: Run embedding-related tests**

Run: `pytest tests/test_models.py -v -k "embedding or Embedding or SentenceTransformer"`
Expected: All pass

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -m "not integration" -x -q`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore: bump Group 3 memory/embeddings (sentence-transformers 5.3.0, faiss-cpu)"
```

---

### Task 6: Group 4 — LLM Core (litellm + openai)

**Files:**
- Modify: `requirements2.txt`

- [ ] **Step 1: Update versions in requirements2.txt**

```
litellm==1.79.3    →  litellm==1.82.6
openai>=1.99.5     →  openai>=2.29.0
```

No code changes expected:
- `litellm` is a minor bump (1.79→1.82), API should be stable
- `openai` is used only for error class names via `getattr(openai, "APITimeoutError", Exception)` with `Exception` fallback — safe even if classes move

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_models.py -v`
Expected: All pass

Run: `pytest tests/ -m "not integration" -x -q`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
git add requirements2.txt
git commit -m "chore: bump Group 4 LLM core (litellm 1.82.6, openai 2.29.0)"
```

---

### Task 7: Group 4 — langchain ecosystem (high risk)

**Files:**
- Modify: `requirements.txt`
- Modify: `models.py`
- Modify: `helpers/document_query.py`
- Verify: `tests/test_models.py`, `tests/helpers/test_document_query.py`

- [ ] **Step 1: Update langchain versions in requirements.txt**

```
langchain-core==0.3.81                    →  langchain-core==1.2.21
langchain-community==0.3.19              →  langchain-community==0.4.1
langchain-unstructured[all-docs]==0.1.6  →  langchain-unstructured[all-docs]==1.0.1
```

Also add `langchain-text-splitters` (required for the import path change below — it's a separate package since langchain 1.0):

```
langchain-text-splitters==1.1.1
```

- [ ] **Step 2: Fix legacy import in models.py**

In `models.py`, find:
```python
from langchain.embeddings.base import Embeddings
```
Replace with:
```python
from langchain_core.embeddings import Embeddings
```

- [ ] **Step 3: Fix legacy imports in helpers/document_query.py**

Find:
```python
from langchain.schema import SystemMessage, HumanMessage
```
Replace with:
```python
from langchain_core.messages import SystemMessage, HumanMessage
```

Find:
```python
from langchain.text_splitter import RecursiveCharacterTextSplitter
```
Replace with:
```python
from langchain_text_splitters import RecursiveCharacterTextSplitter
```

- [ ] **Step 4: Remove unused TextLoader import in document_query.py**

Find and remove:
```python
from langchain_community.document_loaders.text import TextLoader
```

(It's imported but never used in the file.)

- [ ] **Step 5: Verify remaining langchain_core imports are stable**

These imports in `models.py` should still work with langchain-core 1.2.21 (they use `langchain_core.*` paths, not legacy `langchain.*`):
- `from langchain_core.language_models.chat_models import SimpleChatModel`
- `from langchain_core.outputs.chat_generation import ChatGenerationChunk`
- `from langchain_core.callbacks.manager import CallbackManagerForLLMRun, AsyncCallbackManagerForLLMRun`
- `from langchain_core.messages import BaseMessage, AIMessageChunk, HumanMessage, SystemMessage`

These imports in `document_query.py` should still work with langchain-community 0.4.1:
- `from langchain_community.document_loaders import AsyncHtmlLoader`
- `from langchain_community.document_loaders.pdf import PyMuPDFLoader`
- `from langchain_community.document_transformers import MarkdownifyTransformer`
- `from langchain_community.document_loaders.parsers.images import TesseractBlobParser`

This import should still work with langchain-unstructured 1.0.1:
- `from langchain_unstructured import UnstructuredLoader`

If any fail at import time, look up the new import path in langchain 1.0 docs.

- [ ] **Step 6: Run document query and model tests**

Run: `pytest tests/test_models.py tests/helpers/test_document_query.py -v`
Expected: All pass

- [ ] **Step 7: Run full test suite**

Run: `pytest tests/ -m "not integration" -x -q`
Expected: All pass

- [ ] **Step 8: Commit**

```bash
git add requirements.txt models.py helpers/document_query.py
git commit -m "chore: bump Group 4 langchain ecosystem (langchain-core 1.2.21, langchain-community 0.4.1, langchain-unstructured 1.0.1)"
```

---

### Task 8: Final Verification

- [ ] **Step 1: Run the full test suite one final time**

Run: `pytest tests/ -m "not integration" -q`
Expected: All ~2400 tests pass

- [ ] **Step 2: Verify Docker build (if Docker is available)**

From the `agent-zero` repo root, run: `docker build -t agent-zero-test .`
Expected: Build succeeds, all deps resolve together

- [ ] **Step 3: Review all changes**

Run: `git log --oneline -10` to see the commit history.
Run: `git diff main...HEAD --stat` to see all changed files.

- [ ] **Step 4: Run integration tests (optional, if API keys/services available)**

Run: `pytest tests/ -m "integration" -q`
Expected: All pass (if services/keys are configured)

Verify:
- `requirements.txt` — all version bumps applied, duplicate crontab removed
- `requirements2.txt` — litellm and openai bumped
- `models.py` — one import path fixed
- `helpers/document_query.py` — three import paths fixed, one unused import removed
- `helpers/duckduckgo_search.py` — import changed from duckduckgo_search to ddgs
- `helpers/mcp_server.py` — any fastmcp 3.0 adjustments
- `conftest.py` — optional module name updated
