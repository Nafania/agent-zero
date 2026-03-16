# Fork Upstream Cleanup — Design

**Date:** 2026-03-16  
**Goal:** Make the agent-zero fork fully independent from upstream (agent0ai/agent-zero). Remove all references to upstream Docker images, branding, and community links.

## Context

- Fork: Nafania/agent-zero, originally from agent0ai/agent-zero v0.9.8
- CI already builds `ghcr.io/nafania/agent-zero` via root Dockerfile (self-contained)
- Hassio addon uses `ghcr.io/nafania/agent-zero:latest`
- Several files still reference agent0ai images, FUNDING, and upstream docs

## Requirements (from brainstorming)

1. **Docker:** All three scenarios work without upstream — CI, local dev (DockerfileLocal), docker-compose
2. **README:** Concise fork README, link to AGENTS.md, no changelog or upstream content
3. **Docs:** Replace agent0ai references with ghcr.io/nafania/agent-zero

## Design Summary

| Area | Action |
|------|--------|
| docker-compose.yml | `agent0ai/agent-zero:latest` → `ghcr.io/nafania/agent-zero:latest` |
| DockerfileLocal | `FROM agent0ai/agent-zero-base` → use root Dockerfile (or remove if unused) |
| docker/run/Dockerfile | Same — multistage from root or remove |
| docker/base/Dockerfile | Keep (Kali) or remove if unused |
| docker/run/agent-zero/ | Remove nested copy |
| FUNDING.yml | Delete |
| README.md | Concise fork README, link to AGENTS.md |
| docs/setup/installation.md | Replace agent0ai/agent-zero with ghcr.io/nafania/agent-zero |
| docs/ (others) | Remove/replace upstream links |
| knowledge/ | Check and update links |
| docker/fs/ins/*.sh | Verify no git clone to agent0ai (confirmed: none) |
| Final check | grep for remaining upstream refs |

## Docker Strategy

- **docker-compose:** One-line change — image name
- **DockerfileLocal / docker/run/Dockerfile:** Both depend on `agent0ai/agent-zero-base`. Options:
  - **Remove** if not used (docker-compose pulls pre-built image; CI uses root Dockerfile)
  - **Replace** with `FROM ghcr.io/nafania/agent-zero:latest` for dev — but that image is run image, not base
  - **Simplify:** DockerfileLocal → build from root: `docker build -f Dockerfile .` (no separate DockerfileLocal)
  - **docker/run/Dockerfile:** Used only if someone builds from docker/run/ context. Can remove and document that `docker build .` from repo root is the way.

**Recommendation:** Remove DockerfileLocal and docker/run/Dockerfile. Document in README: `docker build .` for local build, `docker pull ghcr.io/nafania/agent-zero` for pre-built. Root Dockerfile is self-contained.

## README Structure

- Title: Agent Zero (Fork)
- 1–2 paragraphs: what it is, link to AGENTS.md for full docs
- Quick Start: `docker pull ghcr.io/nafania/agent-zero` + `docker run -p 50001:80 ghcr.io/nafania/agent-zero`
- Link: https://github.com/Nafania/agent-zero
- No: changelog, trendshift, sponsors, Discord, YouTube, DeepWiki badges

## Approval

Design approved by user 2026-03-16.
