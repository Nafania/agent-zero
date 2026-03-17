# Fork Upstream Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove all upstream (agent0ai) references from the agent-zero fork so it is fully independent.

**Architecture:** Targeted edits — replace image names, remove FUNDING, rewrite README, update docs. Remove unused Dockerfiles and nested copy.

**Tech Stack:** Docker, Markdown, YAML

---

## Task 1: Update docker-compose.yml

**Files:**
- Modify: `agent-zero/docker/run/docker-compose.yml`

**Step 1: Replace image**

Change line 4 from:
```yaml
    image: agent0ai/agent-zero:latest
```
to:
```yaml
    image: ghcr.io/nafania/agent-zero:latest
```

**Step 2: Commit**

```bash
git add agent-zero/docker/run/docker-compose.yml
git commit -m "chore: use fork Docker image in docker-compose"
```

---

## Task 2: Remove DockerfileLocal

**Files:**
- Delete: `agent-zero/DockerfileLocal`

**Step 1: Delete file**

Remove `agent-zero/DockerfileLocal` — it depends on agent0ai/agent-zero-base. Local builds use root `Dockerfile`.

**Step 2: Commit**

```bash
git rm agent-zero/DockerfileLocal
git commit -m "chore: remove DockerfileLocal (upstream base dependency)"
```

---

## Task 3: Remove docker/run/Dockerfile

**Files:**
- Delete: `agent-zero/docker/run/Dockerfile`

**Step 1: Delete file**

Remove `agent-zero/docker/run/Dockerfile` — it depends on agent0ai/agent-zero-base. Root Dockerfile is used for builds.

**Step 2: Commit**

```bash
git rm agent-zero/docker/run/Dockerfile
git commit -m "chore: remove docker/run/Dockerfile (upstream base dependency)"
```

---

## Task 4: Remove nested docker/run/agent-zero/

**Files:**
- Delete: `agent-zero/docker/run/agent-zero/` (entire directory)

**Step 1: Remove directory**

```bash
rm -rf agent-zero/docker/run/agent-zero
```

**Step 2: Commit**

```bash
git add -A agent-zero/docker/run/agent-zero
git status  # verify deletion
git commit -m "chore: remove nested docker/run/agent-zero copy"
```

---

## Task 5: Delete FUNDING.yml

**Files:**
- Delete: `agent-zero/.github/FUNDING.yml`

**Step 1: Delete file**

```bash
git rm agent-zero/.github/FUNDING.yml
git commit -m "chore: remove FUNDING.yml (upstream sponsors)"
```

---

## Task 6: Rewrite README.md

**Files:**
- Modify: `agent-zero/README.md`

**Step 1: Replace entire content**

Write concise fork README:

```markdown
# Agent Zero (Fork)

Custom fork of [agent0ai/agent-zero](https://github.com/agent0ai/agent-zero) — autonomous AI agent framework with Cognee-powered memory, MCP integration, and Home Assistant addon deployment.

See **[AGENTS.md](./AGENTS.md)** for architecture, versioning, testing, and deployment details.

## Quick Start

```bash
docker pull ghcr.io/nafania/agent-zero
docker run -p 50001:80 ghcr.io/nafania/agent-zero
```

Visit http://localhost:50001 to start.

## Source

- [Nafania/agent-zero](https://github.com/Nafania/agent-zero)
```

**Step 2: Commit**

```bash
git add agent-zero/README.md
git commit -m "docs: concise fork README, remove upstream branding"
```

---

## Task 7: Update docs/setup/installation.md

**Files:**
- Modify: `agent-zero/docs/setup/installation.md`

**Step 1: Replace agent0ai references**

Search and replace:
- `agent0ai/agent-zero` → `ghcr.io/nafania/agent-zero`
- Update Docker Desktop GUI instructions to mention `ghcr.io/nafania/agent-zero`
- Update terminal examples: `docker pull ghcr.io/nafania/agent-zero`, `docker run ... ghcr.io/nafania/agent-zero`

**Step 2: Commit**

```bash
git add agent-zero/docs/setup/installation.md
git commit -m "docs: use fork image in installation guide"
```

---

## Task 8: Scan and fix remaining docs

**Files:**
- Modify: `agent-zero/docs/**/*.md` (as needed)

**Step 1: Grep for upstream refs**

```bash
cd agent-zero
grep -r "agent0ai\|agent-zero\.ai\|trendshift\|deepwiki\|github\.com/sponsors\|Report Issues.*agent0ai" docs/ --include="*.md" -l
```

**Step 2: Edit each file**

For each file found, remove or replace:
- agent-zero.ai links → remove or link to Nafania/agent-zero
- agent0ai sponsors/Discord/YouTube → remove
- Report Issues github.com/agent0ai/agent-zero → github.com/Nafania/agent-zero/issues

**Step 3: Commit**

```bash
git add agent-zero/docs/
git commit -m "docs: remove upstream links from docs"
```

---

## Task 9: Check knowledge/

**Files:**
- Modify: `agent-zero/knowledge/main/about/*.md` (if needed)

**Step 1: Grep**

```bash
grep -r "agent0ai\|agent-zero\.ai" agent-zero/knowledge/ --include="*.md" -l
```

**Step 2: Update or remove**

If files reference upstream, update links to fork or remove upstream-only content.

**Step 3: Commit** (if changes)

```bash
git add agent-zero/knowledge/
git commit -m "docs: update knowledge references to fork"
```

---

## Task 10: Decide on docker/base/Dockerfile

**Files:**
- Optional delete: `agent-zero/docker/base/Dockerfile`

**Step 1: Verify usage**

Root `Dockerfile` does NOT use `docker/base/Dockerfile` — it copies `docker/base/fs/` and runs scripts directly. The `docker/base/Dockerfile` (Kali-based) appears to be legacy from upstream.

**Step 2: Delete or keep**

- If nothing references it: delete `agent-zero/docker/base/Dockerfile` and commit.
- If unsure: keep it (no upstream image reference; it uses kalilinux/kali-rolling which is public).

**Recommendation:** Keep — no agent0ai reference. Optional cleanup later.

---

## Task 11: Final verification

**Step 1: Grep entire repo**

```bash
cd agent-zero
grep -r "agent0ai" . --include="*.yml" --include="*.yaml" --include="*.md" --include="*.sh" --include="Dockerfile*" 2>/dev/null | grep -v ".git"
```

Expected: no matches.

**Step 2: Verify Docker flows**

- `docker-compose -f docker/run/docker-compose.yml up` — should pull ghcr.io/nafania/agent-zero
- `docker build .` — should build from root Dockerfile (no upstream base)

---

## Execution Handoff

Plan complete and saved to `docs/plans/2026-03-16-fork-upstream-cleanup-plan.md`.

**Two execution options:**

1. **Subagent-Driven (this session)** — Dispatch fresh subagent per task, review between tasks, fast iteration
2. **Parallel Session (separate)** — Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
