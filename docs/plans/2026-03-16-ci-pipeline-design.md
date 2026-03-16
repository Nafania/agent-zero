# CI Pipeline Design: Tests + Auto-Build + Release

**Date:** 2026-03-16
**Status:** Approved

## Problem

1. `actions/checkout@v4` and `actions/setup-python@v5` run on Node.js 20, deprecated June 2, 2026.
2. Docker build and release process is entirely manual (build → tag → push → update hassio).
3. No automated versioning after merge to main.

## Solution

Single unified workflow file (`ci.yml`) replacing `tests.yml` with four chained jobs.

## Node.js 20 Fix

Add workflow-level environment variable:

```yaml
env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true
```

Action versions remain `@v4`/`@v5` (latest major). Remove env var once actions ship native Node.js 24 support.

## Job Chain

```
unit-tests → integration-tests → build-and-release → notify-hassio
```

### Triggers

- `push` to `main`, `develop` — with paths filter
- `pull_request` — with paths filter

### unit-tests

Runs on all triggers. No changes from current.

### integration-tests

Only on `push` to `main`, `needs: unit-tests`. No changes from current.

### build-and-release

Only on `push` to `main`, `needs: integration-tests`.

Steps:
1. Checkout with `fetch-depth: 0` (all tags)
2. Determine next version: parse latest `v0.9.8.*` tag, increment patch
3. Docker login to GHCR via `docker/login-action@v3`
4. Build + push via `docker/build-push-action@v6`:
   - Tag: `ghcr.io/nafania/agent-zero:v0.9.8.(N+1)`
   - Build args: `A0_VERSION=v0.9.8.(N+1)`, `BRANCH=main`
5. Create and push git tag `v0.9.8.(N+1)`

Permissions: `contents: write` (tags), `packages: write` (GHCR).

Outputs: `version` (semver without `v` prefix, e.g. `0.9.8.19`).

### notify-hassio

Only on `push` to `main`, `needs: build-and-release`.

Uses `peter-evans/repository-dispatch@v3` to trigger `new-release` event in `Nafania/agent-zero-hassio` with payload `{"version": "0.9.8.N"}`.

Requires `HASSIO_DISPATCH_TOKEN` secret (PAT with `repo` scope on `Nafania/agent-zero-hassio`).

## Versioning

- Auto-increment: latest tag `v0.9.8.N` → `v0.9.8.(N+1)`
- Tags created automatically on successful build
- Docker image tagged with version only (no `:latest`)

## Secrets Required

| Secret | Purpose | How to create |
|--------|---------|---------------|
| `HASSIO_DISPATCH_TOKEN` | Trigger workflow in hassio repo | GitHub PAT with `repo` scope |
| `GITHUB_TOKEN` | GHCR push, tag creation | Auto-provided by GitHub Actions |

## Out of Scope

- Hassio-side workflow to receive `repository_dispatch` and update `config.yaml` (separate task)
- Multi-platform Docker builds (amd64 only for now)
- `:latest` Docker tag (version tag only)
