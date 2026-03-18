# Skills Marketplace Design

## Summary

Rework the Agent Zero skills system to support automatic installation from [skills.sh](https://skills.sh/) marketplace via settings UI, with automatic context-based activation in chats — similar to how Cursor handles skills.

## Decisions

| Decision | Choice |
|----------|--------|
| UI location | New tab in Settings (replacing current Skills tab) |
| Skill activation | Automatic by context — agent sees catalog, decides what to load |
| Catalog source | skills.sh via `npx skills find`, cached in background (1h TTL) |
| Installation method | `npx skills` CLI natively (Node.js added to Docker image) |
| Architecture | `npx skills` as single backend for all marketplace operations |

## Architecture

```
┌──────────────────────────────────────────────────┐
│  Settings UI (tab "Skills")                      │
│  ┌─────────────────┐  ┌───────────────────────┐  │
│  │ Catalog (search) │  │ Installed skills      │  │
│  │ npx skills find  │  │ skills.py (disk)      │  │
│  └────────┬────────┘  └──────────┬────────────┘  │
│           │ install/remove        │ enable/disable│
└───────────┼──────────────────────┼───────────────┘
            ▼                      ▼
┌───────────────────┐   ┌──────────────────────────┐
│ skills_cli.py     │   │ skills.py (existing)      │
│ wrapper over npx  │   │ discover, parse, validate │
│ find/add/remove   │   │ list_skills, find_skill   │
└───────────────────┘   └──────────┬───────────────┘
                                   ▼
                        ┌──────────────────────────┐
                        │ _60_skills_catalog.py     │
                        │ catalog in system prompt  │
                        ├──────────────────────────┤
                        │ _65_include_loaded_skills │
                        │ full content injection    │
                        └──────────────────────────┘
```

## Components

### New

| Component | File | Role |
|-----------|------|------|
| CLI wrapper | `python/helpers/skills_cli.py` | Wrapper over `npx skills` — find, add, remove, check, update. Parses text output, returns Python dataclasses. Caches find results. |
| Catalog API | `python/api/skills_catalog.py` | Endpoint `/skills_catalog` — search via skills_cli.find, cache 1h. |
| Skills catalog extension | `python/extensions/message_loop_prompts_after/_60_skills_catalog.py` | Injects compact skill catalog (name + description) into system prompt every loop iteration. |
| Settings UI | `webui/components/settings/skills/` | Alpine.js component: search catalog, install, list installed, remove, check updates. Replaces current UI entirely. |

### Modified

| Component | Change |
|-----------|--------|
| `python/api/skill_install.py` | Refactor: use `npx skills add` instead of git clone |
| `python/api/skills.py` | Add `update` action, refactor `delete` to use `npx skills remove` |
| `python/extensions/message_loop_prompts_after/_65_include_loaded_skills.py` | No structural change — continues injecting loaded skill content |
| `Dockerfile` | Add Node.js (`apt-get install nodejs npm`) |

### Unchanged

| Component | Why |
|-----------|-----|
| `python/helpers/skills.py` | Core SKILL.md parsing, discovery, validation — works well as-is |
| `python/tools/skills_tool.py` | Agent tool list/load — still needed for agent-initiated loading |
| `usr/skills/` storage | Persistent volume for installed skills |

### Deleted

| File | Reason |
|------|--------|
| `webui/components/settings/skills/skills-settings.html` | Replaced by new unified UI |
| `webui/components/settings/skills/list.html` | Merged into new component |
| `webui/components/settings/skills/import.html` | Merged into new component |
| `webui/components/settings/skills/skills-list-store.js` | Replaced by new store |
| `webui/components/settings/skills/skills-install-store.js` | Replaced by new store |

## Automatic Skill Activation

### Level 1 — Catalog in system prompt (always)

New extension `_60_skills_catalog.py` injects a compact list of all installed skills into `extras`:

```
Available skills (use skills_tool method=load to activate):
- brainstorming: Use before any creative work — creating features, building components
- test-driven-development: Use when implementing any feature or bugfix
- systematic-debugging: Use when encountering any bug, test failure, or unexpected behavior
```

Cost: ~50 tokens per skill. At 10-20 skills: 500-1000 tokens — acceptable.

### Level 2 — Full content loading (on demand)

`_65_include_loaded_skills.py` unchanged. Agent sees catalog, determines a skill is relevant, calls `skills_tool method=load` — full SKILL.md content injected into prompt.

## CLI Wrapper (`skills_cli.py`)

### Interface

```python
async def find(query: str) -> list[CatalogSkill]
async def add(source: str) -> InstallResult
async def remove(skill_name: str) -> bool
async def check() -> list[UpdateInfo]
async def update() -> list[UpdateResult]
```

### Caching

- In-memory cache: `dict[query -> (results, timestamp)]`
- TTL: 1 hour
- Max 50 cached queries (LRU)
- Cache cleared on install/remove

### Installation directory

`npx skills` defaults to `.agents/skills/`. We need skills in `usr/skills/` (persistent Docker volume). Options in priority order:
1. `--dir usr/skills` if CLI supports it
2. Symlink `.agents/skills -> usr/skills`
3. Post-install move from `.agents/skills/` to `usr/skills/`

### Timeouts

- `add`: 60s (clones repo)
- `find`: 30s
- `remove`, `check`, `update`: 30s

### Error handling

- Node.js/npx not found → "Install Node.js to use Skills marketplace"
- Network unavailable → "Network error, try again later"
- Repo doesn't exist → pass through CLI error
- Timeout → "Installation timed out"

## Settings UI

### Layout

Two sections in one tab:

1. **Search catalog** — input field + search button, results with "Add" buttons. Also direct install field (`owner/repo`).
2. **Installed skills** — list with name, description, path. Each has "Update" and "Delete" buttons. "Check for updates" button at bottom.

### API endpoints

| Endpoint | Method | Action |
|----------|--------|--------|
| `/skills_catalog` | POST `{query}` | Search via `npx skills find`, cached 1h |
| `/skill_install` | POST `{source}` | Install via `npx skills add` |
| `/skills` action=list | POST | List installed (existing) |
| `/skills` action=delete | POST | Remove via `npx skills remove` |
| `/skills_update` | POST | Check/update via `npx skills check/update` |

## Docker

Add Node.js to Dockerfile:
```dockerfile
RUN apt-get update && apt-get install -y nodejs npm
```

Check current base image during implementation — may need different package manager.

## Testing

| What | How |
|------|-----|
| `skills_cli.py` — output parsing | Unit tests with mocked subprocess (fixture with real CLI output) |
| `skills_catalog.py` API | Unit tests: cache hit/miss, TTL, CLI errors |
| `_60_skills_catalog.py` extension | Unit test: catalog prompt formatting |
| `skill_install.py` (refactor) | Unit test: npx skills add call, result parsing |
| Existing `test_skills.py` tests | Update for any changes to skills.py interface |
| E2E | Manual: install skill via UI, verify agent sees and uses it |

## Out of Scope

- Project-scoped skills — keep as-is
- Hooks and commands from `.cursor-plugin` — Cursor-specific, not supported
- Auto-update skills — only manual via button
- Custom hand-written skills — continue working via `usr/skills/`

## Git Workflow

- Create feature branch from `main`: `feat/skills-marketplace`
- All commits and pushes to feature branch only
- Full test coverage for new code, update existing relevant tests
- PR to `main` when complete
