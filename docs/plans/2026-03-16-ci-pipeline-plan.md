# CI Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace manual release process with automated CI pipeline: tests → Docker build → tag → notify hassio.

**Architecture:** Single unified GitHub Actions workflow (`ci.yml`) with four chained jobs. Version auto-incremented from latest git tag. Docker image pushed to GHCR. Hassio repo notified via repository_dispatch.

**Tech Stack:** GitHub Actions, Docker (build-push-action), GHCR, peter-evans/repository-dispatch

---

### Task 1: Fix Node.js 20 deprecation and rename workflow

**Files:**
- Delete: `.github/workflows/tests.yml`
- Create: `.github/workflows/ci.yml`

**Step 1: Create new workflow file with Node.js 24 fix**

Copy current `tests.yml` to `ci.yml`, add `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24` env, rename workflow:

```yaml
name: CI

on:
  push:
    branches: [main, develop]
    paths: ['python/**', 'tests/**', 'requirements*.txt', 'agent.py', 'initialize.py', 'models.py']
  pull_request:
    paths: ['python/**', 'tests/**']

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: pip
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements2.txt
          pip install -r requirements.dev.txt
      - name: Run unit tests
        run: python -m pytest tests/ -m "not integration" --tb=short -q --timeout=30
        env:
          PYTHONPATH: .

  integration-tests:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    needs: unit-tests
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: pip
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements2.txt
          pip install -r requirements.dev.txt
      - name: Run integration tests
        run: python -m pytest tests/integration/ --tb=short -q --timeout=60
        env:
          PYTHONPATH: .
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
```

**Step 2: Delete old tests.yml**

```bash
git rm .github/workflows/tests.yml
```

**Step 3: Verify YAML is valid**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`
Expected: No errors

**Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: rename tests.yml to ci.yml, fix Node.js 20 deprecation"
```

---

### Task 2: Add build-and-release job

**Files:**
- Modify: `.github/workflows/ci.yml`

**Step 1: Add paths filter for Docker/workflow files**

In the `on.push.paths` array, add entries so the workflow also triggers on Dockerfile and workflow changes:

```yaml
paths: ['python/**', 'tests/**', 'requirements*.txt', 'agent.py', 'initialize.py', 'models.py', 'Dockerfile', 'docker/**', '.github/workflows/**']
```

**Step 2: Add build-and-release job**

Append after `integration-tests` job:

```yaml
  build-and-release:
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    needs: integration-tests
    permissions:
      contents: write
      packages: write
    outputs:
      version: ${{ steps.version.outputs.semver }}
      tag: ${{ steps.version.outputs.tag }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Determine next version
        id: version
        run: |
          LATEST=$(git tag --sort=-v:refname | grep '^v0\.9\.8\.' | head -1)
          if [ -z "$LATEST" ]; then
            LATEST="v0.9.8.0"
          fi
          PATCH=$(echo "$LATEST" | sed 's/v0\.9\.8\.//')
          NEXT=$((PATCH + 1))
          echo "tag=v0.9.8.$NEXT" >> "$GITHUB_OUTPUT"
          echo "semver=0.9.8.$NEXT" >> "$GITHUB_OUTPUT"
          echo "Next version: v0.9.8.$NEXT (previous: $LATEST)"

      - uses: docker/setup-buildx-action@v3

      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ghcr.io/nafania/agent-zero:${{ steps.version.outputs.tag }}
          build-args: |
            A0_VERSION=${{ steps.version.outputs.tag }}
            BRANCH=main

      - name: Create and push tag
        run: |
          git tag ${{ steps.version.outputs.tag }}
          git push origin ${{ steps.version.outputs.tag }}
```

**Step 3: Verify YAML is valid**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`
Expected: No errors

**Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add build-and-release job with auto-versioning"
```

---

### Task 3: Add notify-hassio job

**Files:**
- Modify: `.github/workflows/ci.yml`

**Step 1: Add notify-hassio job**

Append after `build-and-release` job:

```yaml
  notify-hassio:
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    needs: build-and-release
    steps:
      - name: Trigger hassio addon update
        uses: peter-evans/repository-dispatch@v3
        with:
          token: ${{ secrets.HASSIO_DISPATCH_TOKEN }}
          repository: Nafania/agent-zero-hassio
          event-type: new-release
          client-payload: '{"version": "${{ needs.build-and-release.outputs.version }}"}'
```

**Step 2: Verify YAML is valid**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`
Expected: No errors

**Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add notify-hassio job with repository_dispatch"
```

---

### Task 4: Update AGENTS.md release flow

**Files:**
- Modify: `AGENTS.md`

**Step 1: Update the Versioning & Release section**

Replace the manual release flow in `AGENTS.md` with the automated one:

```markdown
## Versioning & Release

- Current: **v0.9.8.N** (auto-incremented)
- Tags follow: `v0.9.8.N` increments
- The hassio addon version MUST match the fork tag

Automated release flow (on merge to `main`):
1. CI runs unit tests → integration tests
2. Auto-determines next version from latest git tag
3. Builds Docker image `ghcr.io/nafania/agent-zero:v0.9.8.N`
4. Creates and pushes git tag `v0.9.8.N`
5. Triggers `repository_dispatch` in `Nafania/agent-zero-hassio`

Required secrets:
- `HASSIO_DISPATCH_TOKEN` — PAT with `repo` scope for hassio repo
- `OPENROUTER_API_KEY` — for integration tests
```

**Step 2: Commit**

```bash
git add AGENTS.md
git commit -m "docs: update release flow to reflect CI automation"
```

---

### Task 5: Verify complete workflow

**Step 1: Read final ci.yml and verify structure**

Verify all 4 jobs exist: `unit-tests`, `integration-tests`, `build-and-release`, `notify-hassio`.

Verify dependency chain: `integration-tests` needs `unit-tests`, `build-and-release` needs `integration-tests`, `notify-hassio` needs `build-and-release`.

Verify all `if` conditions are correct for main-only jobs.

**Step 2: Validate YAML syntax**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`
Expected: No errors

**Step 3: Check `act` dry-run (if available)**

Run: `act --dryrun push` (optional, if `act` is installed)

---

## Manual Steps After Implementation

1. **Create PAT:** Go to GitHub → Settings → Personal Access Tokens → Generate new token with `repo` scope
2. **Add secret:** Go to `Nafania/agent-zero` → Settings → Secrets → Add `HASSIO_DISPATCH_TOKEN` with the PAT
3. **Create hassio workflow:** In `Nafania/agent-zero-hassio`, create a workflow that listens for `repository_dispatch` event `new-release` and updates `config.yaml` version
