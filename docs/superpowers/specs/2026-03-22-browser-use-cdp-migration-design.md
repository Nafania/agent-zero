# Browser-Use CDP Migration Design

**Date:** 2026-03-22
**Status:** Approved
**Branch:** `chore/migrate-browser-use-to-cdp`

## Problem

Agent-zero pins `browser-use==0.5.11` and `playwright==1.52.0`. The browser-use library switched from Playwright to CDP (Chrome DevTools Protocol) in August 2025 (~v0.8). The latest version is 0.12.3. Staying on the old version accumulates technical debt — no bug fixes, no performance improvements, and a growing API gap.

## Solution

Full migration from browser-use 0.5.11 (Playwright-based) to 0.12.3 (CDP-based). Remove the Playwright dependency entirely.

## Scope

### Files Modified

| File | Change |
|------|--------|
| `requirements.txt` | `browser-use` 0.5.11 → 0.12.3, remove `playwright==1.52.0` |
| `python/tools/browser_agent.py` | Adapt 6 API call sites to new CDP-based API |
| `python/helpers/browser_use.py` | Verify compatibility, update if needed |
| `docker/run/fs/ins/install_playwright.sh` | Rewrite as `install_chrome.sh` — install Chromium via apt |
| `Dockerfile` | Reference new install script |
| `tests/tools/test_browser_agent.py` | Update mocks for new API |
| `conftest.py` | Verify `_OPTIONAL_MODULES` still correct |
| `AGENTS.md` | Update browser_agent documentation |

### Files Deleted

| File | Reason |
|------|--------|
| `python/helpers/playwright.py` | `ensure_playwright_binary()` no longer needed — CDP manages Chrome directly |

### Files Unchanged

| File | Reason |
|------|--------|
| `lib/browser/init_override.js` | JS content stays the same, only injection method changes |
| `initialize.py` | `browser_model`, `browser_http_headers` config unchanged |
| `prompts/browser_agent.system.md` | System prompt unchanged |

## API Migration Details

### 1. Remove Playwright helper

```python
# DELETE import:
from python.helpers.playwright import ensure_playwright_binary

# DELETE from _initialize():
pw_binary = ensure_playwright_binary()
```

### 2. BrowserProfile changes

```python
# OLD (0.5.11):
browser_use.BrowserSession(
    browser_profile=browser_use.BrowserProfile(
        headless=True,
        disable_security=True,
        chromium_sandbox=False,
        executable_path=pw_binary,        # REMOVE
        args=["--headless=new"],           # REMOVE (auto-added by headless=True)
        # ... rest stays
    )
)

# NEW (0.12.x):
browser_use.BrowserSession(
    browser_profile=browser_use.BrowserProfile(
        headless=True,
        disable_security=True,
        chromium_sandbox=False,
        # executable_path removed — CDP finds Chrome automatically
        # args removed — headless=True adds --headless=new internally
        # ... rest stays
    )
)
```

### 3. Viewport API

```python
# OLD: Playwright Page — dict parameter
await page.set_viewport_size({"width": 1024, "height": 2048})

# NEW: CDP actor Page — keyword arguments
await page.set_viewport_size(width=1024, height=2048)
```

### 4. Screenshot API

```python
# OLD: Playwright Page — saves to file directly
await page.screenshot(path=path, full_page=False, timeout=3000)

# NEW: CDP actor Page — returns base64, manual file save
import base64
data = await page.screenshot(format="png")
with open(path, "wb") as f:
    f.write(base64.b64decode(data))
```

### 5. Init script injection

```python
# OLD: Playwright BrowserContext
await self.browser_session.browser_context.add_init_script(path=js_override)

# NEW: CDP Page.addScriptToEvaluateOnNewDocument
js_override_path = files.get_abs_path("lib/browser/init_override.js")
with open(js_override_path, "r") as f:
    js_code = f.read()
page = await self.browser_session.get_current_page()
if page:
    session_id = await page.session_id
    await page._client.send.Page.addScriptToEvaluateOnNewDocument(
        {"source": js_code}, session_id=session_id
    )
```

### 6. Agent constructor

```python
# OLD:
browser_use.Agent(
    ...,
    enable_memory=False,    # REMOVE — parameter deleted in 0.12.x
    llm_timeout=120,
    ...
)

# NEW:
browser_use.Agent(
    ...,
    # enable_memory removed
    llm_timeout=120,
    ...
)
```

`browser_session` and `controller` parameters are backwards-compatible aliases in 0.12.x.

### 7. Controller / output_model

Verify at install time whether `Controller(output_model=DoneResult)` still works or needs migration to `Tools` class with `output_model_schema` on Agent. The 0.12.x docs list `controller` as a backwards-compat alias for `tools`.

## Docker Changes

### Old: `install_playwright.sh`

```bash
uv pip install playwright
export PLAYWRIGHT_BROWSERS_PATH=/a0/tmp/playwright
playwright install chromium --only-shell
```

### New: `install_chrome.sh`

```bash
apt-get update
apt-get install -y --no-install-recommends \
    chromium fonts-unifont libnss3 libnspr4 \
    libatk1.0-0 libatspi2.0-0 libxcomposite1 \
    libxdamage1 libatk-bridge2.0-0 libcups2
apt-get clean && rm -rf /var/lib/apt/lists/*
```

### Dockerfile

```dockerfile
# OLD:
RUN bash /ins/install_playwright.sh

# NEW:
RUN bash /ins/install_chrome.sh
```

## Dependency Conflict Risks

| browser-use 0.12.x pins | agent-zero has | Risk |
|---|---|---|
| `pydantic==2.12.5` | `pydantic>=2.11.7` | Low — compatible |
| `openai==2.16.0` | openai in requirements2.txt | Medium — check version |
| `litellm>=1.82.2` | litellm in requirements2.txt | Medium — check version |
| Python >= 3.11 | Python 3.12 | None |

## Test Strategy

### Unit tests (mocked)

Update `tests/tools/test_browser_agent.py`:
- Remove mocks for `ensure_playwright_binary`
- Update screenshot mock: return base64 string instead of file write
- Update init script injection mock: CDP call instead of `add_init_script`
- Verify `State._initialize` mock matches new flow

### Manual verification

After deployment to Docker:
1. Give agent a browser task: "Go to example.com and tell me what you see"
2. Verify screenshot capture works
3. Verify init_override.js injection works (shadow DOM handling)
4. Verify browser session cleanup on task kill

## AgentHistoryList API — Verified Compatible

The following methods used by agent-zero are present and compatible in 0.12.x:
- `result.is_done()` — unchanged
- `result.final_result()` — unchanged
- `result.urls()` — unchanged
- `history.action_results()` — unchanged
- `ActionResult.is_done`, `.success`, `.error`, `.extracted_content` — unchanged

## Out of Scope

- Upgrading to browser-use cloud SDK (3.x) — not needed, using OSS library
- Adding new browser-use features (CodeAgent, skills, etc.) — separate work
- Changing browser agent prompts or behavior
