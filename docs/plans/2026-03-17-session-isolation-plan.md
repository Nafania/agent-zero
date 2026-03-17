# Session Cache Isolation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Pass `session_id=context.id` to all `cognee.search()` calls so each chat gets an isolated session cache, preventing cross-dataset memory leakage.

**Architecture:** Two files need changes. `_50_recall_memories.py` adds `session_id` to its two `cognee.search` calls. `memory.py` adds an optional `session_id` parameter to `search_similarity_threshold` and forwards it.

**Tech Stack:** Python, Cognee 0.5.5, Agent Zero

---

### Task 1: Add session_id to recall_memories search calls

**Files:**
- Modify: `python/extensions/message_loop_prompts_after/_50_recall_memories.py:104-121`

**Step 1: Add session_id to both cognee.search calls**

In `search_memories()`, the two `cognee.search` calls at lines 107-120 need `session_id=self.agent.context.id`:

```python
        try:
            started = time.monotonic()
            mem_answers, sol_answers = await asyncio.gather(
                cognee.search(
                    query_text=query,
                    top_k=set["memory_recall_memories_max_search"],
                    datasets=datasets,
                    node_type=NodeSet,
                    node_name=mem_node_name,
                    session_id=self.agent.context.id,
                ),
                cognee.search(
                    query_text=query,
                    top_k=set["memory_recall_solutions_max_search"],
                    datasets=datasets,
                    node_type=NodeSet,
                    node_name=sol_node_name,
                    session_id=self.agent.context.id,
                ),
            )
```

**Step 2: Verify no syntax errors**

Run: `python -c "import ast; ast.parse(open('python/extensions/message_loop_prompts_after/_50_recall_memories.py').read()); print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add python/extensions/message_loop_prompts_after/_50_recall_memories.py
git commit -m "fix: pass session_id=context.id to cognee.search in recall_memories"
```

---

### Task 2: Add session_id parameter to memory.py search

**Files:**
- Modify: `python/helpers/memory.py:218-253`

**Step 1: Add session_id parameter to search_similarity_threshold**

```python
    async def search_similarity_threshold(
        self, query: str, limit: int, threshold: float, filter: str = "",
        include_default: bool = True, session_id: str | None = None,
    ) -> list[Document]:
```

And forward it to `cognee.search`:

```python
            results = await cognee.search(
                query_text=query,
                top_k=limit,
                datasets=datasets,
                node_type=NodeSet,
                node_name=node_names if node_names else None,
                session_id=session_id,
            )
```

**Step 2: Verify no syntax errors**

Run: `python -c "import ast; ast.parse(open('python/helpers/memory.py').read()); print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add python/helpers/memory.py
git commit -m "fix: add session_id parameter to search_similarity_threshold"
```

---

### Task 3: Build and verify in Docker

**Step 1: Rebuild Docker image**

```bash
cd docker/run && docker compose up -d --build
```

**Step 2: Verify fix**

1. Open Agent Zero UI
2. In a project chat, save unique info (e.g. "запомни что тестовое слово — бронтозавр")
3. Wait for cognify to process
4. Open a new non-project chat, ask "какое тестовое слово?"
5. Expected: agent should NOT know the answer (no leakage from project session cache)
