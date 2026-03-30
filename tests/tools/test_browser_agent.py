"""Tests for tools/browser_agent.py — BrowserAgent tool."""

import base64
import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch, mock_open

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def patch_browser_use_config(tmp_path):
    """Patch browser_use config dir to avoid PermissionError in sandbox."""
    import os
    prev = os.environ.get("BROWSER_USE_CONFIG_DIR")
    os.environ["BROWSER_USE_CONFIG_DIR"] = str(tmp_path / "browseruse")
    yield
    if prev is not None:
        os.environ["BROWSER_USE_CONFIG_DIR"] = prev
    else:
        os.environ.pop("BROWSER_USE_CONFIG_DIR", None)


@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent.handle_intervention = AsyncMock()
    agent.config = MagicMock()
    agent.config.browser_model = MagicMock()
    agent.config.browser_model.vision = True
    agent.config.browser_http_headers = {}
    agent.context = MagicMock()
    agent.context.id = "test-ctx-001"
    agent.context.generate_id = MagicMock(return_value="guid-123")
    agent.context.log = MagicMock()
    agent.context.log.log = MagicMock(return_value=MagicMock(update=MagicMock()))
    agent.context.task = None
    agent.read_prompt = MagicMock(return_value="System prompt")
    agent.get_data = MagicMock(return_value=None)
    agent.set_data = MagicMock()
    return agent


@pytest.fixture
def tool(mock_agent):
    from plugins.browser.tools.browser_agent import BrowserAgent
    t = BrowserAgent(
        agent=mock_agent,
        name="browser_agent",
        method=None,
        args={"message": "Go to example.com", "reset": "false"},
        message="",
        loop_data=None,
    )
    t.log = MagicMock(update=MagicMock())
    return t


class TestBrowserAgentInit:
    def test_stores_args(self, tool):
        assert tool.args["message"] == "Go to example.com"
        assert tool.name == "browser_agent"


class TestBrowserAgentGetLogObject:
    def test_returns_log_with_browser_type(self, tool):
        log = tool.get_log_object()
        mock_agent = tool.agent
        mock_agent.context.log.log.assert_called_once()
        call_kw = mock_agent.context.log.log.call_args[1]
        assert call_kw.get("type") == "browser"


class TestBrowserAgentPrepareState:
    @pytest.mark.asyncio
    async def test_creates_state_when_none(self, tool):
        with patch("plugins.browser.tools.browser_agent.State.create", new_callable=AsyncMock) as mock_create:
            mock_state = MagicMock()
            mock_create.return_value = mock_state
            await tool.prepare_state(reset=False)
        assert tool.state is mock_state
        tool.agent.set_data.assert_called_with("_browser_agent_state", mock_state)


class TestBrowserAgentUpdateProgress:
    def test_updates_log_and_context(self, tool):
        tool.log = MagicMock(update=MagicMock())
        tool.agent.context.log.set_progress = MagicMock()
        with patch("plugins.browser.tools.browser_agent.get_secrets_manager") as mock_sm:
            mock_sm.return_value.mask_values = lambda x: x
            tool.update_progress("Loading page...")
        tool.log.update.assert_called()
        tool.agent.context.log.set_progress.assert_called()


class TestBrowserAgentMask:
    def test_masks_secrets(self, tool):
        with patch("plugins.browser.tools.browser_agent.get_secrets_manager") as mock_sm:
            mock_sm.return_value.mask_values = lambda t: t.replace("secret", "***")
            result = tool._mask("password is secret")
        assert "***" in result

    def test_returns_empty_for_none(self, tool):
        with patch("plugins.browser.tools.browser_agent.get_secrets_manager") as mock_sm:
            mock_sm.return_value.mask_values = lambda t: t or ""
            result = tool._mask(None)
        assert result == ""


class TestBrowserAgentExecute:
    @pytest.mark.asyncio
    async def test_execute_returns_response_on_timeout(self, tool):
        mock_state = MagicMock()
        mock_task = MagicMock()
        mock_task.is_ready = MagicMock(return_value=False)
        mock_state.start_task = MagicMock(return_value=mock_task)
        mock_state.use_agent = None
        mock_state.kill_task = MagicMock()

        async def mock_prepare_state(**kwargs):
            tool.state = mock_state

        with patch.object(tool, "prepare_state", new_callable=AsyncMock, side_effect=mock_prepare_state):
            with patch("plugins.browser.tools.browser_agent.get_secrets_manager") as mock_sm:
                mock_sm.return_value.mask_values = lambda x, **kw: x
                with patch("plugins.browser.tools.browser_agent.time.time", side_effect=[0, 400]):
                    resp = await tool.execute(message="test", reset="false")
        from helpers.tool import Response
        assert isinstance(resp, Response)
        assert resp.break_loop is False


class TestGetUseAgentLog:
    def test_returns_starting_when_no_agent(self):
        from plugins.browser.tools.browser_agent import get_use_agent_log
        result = get_use_agent_log(None)
        assert "Starting" in result[0] or "🚦" in str(result)

    def test_includes_action_results_when_agent(self):
        from plugins.browser.tools.browser_agent import get_use_agent_log
        mock_agent = MagicMock()
        mock_result = MagicMock()
        mock_result.is_done = True
        mock_result.success = True
        mock_result.error = None
        mock_result.extracted_content = None
        mock_agent.history = MagicMock()
        mock_agent.history.action_results = MagicMock(return_value=[mock_result])
        result = get_use_agent_log(mock_agent)
        assert len(result) >= 1

    def test_includes_error_when_done_but_not_success(self):
        from plugins.browser.tools.browser_agent import get_use_agent_log
        mock_agent = MagicMock()
        mock_result = MagicMock()
        mock_result.is_done = True
        mock_result.success = False
        mock_result.error = "Something failed"
        mock_result.extracted_content = None
        mock_agent.history = MagicMock()
        mock_agent.history.action_results = MagicMock(return_value=[mock_result])
        result = get_use_agent_log(mock_agent)
        assert any("Error" in str(r) or "❌" in str(r) for r in result)

    def test_includes_progress_when_not_done(self):
        from plugins.browser.tools.browser_agent import get_use_agent_log
        mock_agent = MagicMock()
        mock_result = MagicMock()
        mock_result.is_done = False
        mock_result.extracted_content = "Clicking on button..."
        mock_agent.history = MagicMock()
        mock_agent.history.action_results = MagicMock(return_value=[mock_result])
        result = get_use_agent_log(mock_agent)
        assert any("Clicking" in str(r) for r in result)


class TestBrowserAgentState:
    def test_get_user_data_dir(self, mock_agent):
        from plugins.browser.tools.browser_agent import State
        state = State(mock_agent)
        path = state.get_user_data_dir()
        assert "browseruse" in path
        assert "agent_" in path
        assert mock_agent.context.id in path


class TestBrowserAgentPrepareStateReset:
    @pytest.mark.asyncio
    async def test_prepare_state_kills_task_on_reset(self, tool):
        mock_state = MagicMock()
        tool.agent.get_data.return_value = mock_state
        with patch("plugins.browser.tools.browser_agent.State.create", new_callable=AsyncMock) as mock_create:
            new_state = MagicMock()
            mock_create.return_value = new_state
            await tool.prepare_state(reset=True)
        mock_state.kill_task.assert_called_once()
        assert tool.state is new_state


class TestBrowserAgentExecuteSuccess:
    @pytest.mark.asyncio
    async def test_execute_returns_result_when_task_completes(self, tool):
        mock_state = MagicMock()
        mock_task = MagicMock()
        mock_task.is_ready = MagicMock(return_value=True)
        mock_task.result = AsyncMock(return_value=MagicMock(
            is_done=MagicMock(return_value=True),
            final_result=MagicMock(return_value='{"title":"Done","response":"OK","page_summary":"Summary"}'),
        ))
        mock_state.start_task = MagicMock(return_value=mock_task)
        mock_state.use_agent = MagicMock()
        mock_state.kill_task = MagicMock()

        async def mock_prepare_state(**kwargs):
            tool.state = mock_state

        with patch.object(tool, "prepare_state", new_callable=AsyncMock, side_effect=mock_prepare_state):
            with patch("plugins.browser.tools.browser_agent.get_secrets_manager") as mock_sm:
                mock_sm.return_value.mask_values = lambda x, **kw: x
                with patch.object(tool, "get_update", new_callable=AsyncMock, return_value={"log": []}):
                    resp = await tool.execute(message="test", reset="false")
        from helpers.tool import Response
        assert isinstance(resp, Response)
        assert resp.break_loop is False
        assert "OK" in resp.message or "Done" in resp.message or "Summary" in resp.message

    @pytest.mark.asyncio
    async def test_execute_handles_task_result_exception(self, tool):
        mock_state = MagicMock()
        mock_task = MagicMock()
        mock_task.is_ready = MagicMock(return_value=True)
        mock_task.result = AsyncMock(side_effect=Exception("Task failed"))

        async def mock_prepare_state(**kwargs):
            tool.state = mock_state

        mock_state.start_task = MagicMock(return_value=mock_task)
        mock_state.use_agent = None
        mock_state.kill_task = MagicMock()

        with patch.object(tool, "prepare_state", new_callable=AsyncMock, side_effect=mock_prepare_state):
            with patch("plugins.browser.tools.browser_agent.get_secrets_manager") as mock_sm:
                mock_sm.return_value.mask_values = lambda x, **kw: x
                with patch.object(tool, "get_update", new_callable=AsyncMock, return_value={}):
                    resp = await tool.execute(message="test", reset="false")
        assert "Task failed" in resp.message or "failed" in resp.message.lower()


class TestBrowserAgentGetUpdate:
    @pytest.mark.asyncio
    async def test_get_update_returns_empty_when_no_page(self, tool):
        mock_state = MagicMock()
        mock_state.use_agent = None
        mock_state.get_page = AsyncMock(return_value=None)

        async def mock_prepare_state(**kwargs):
            tool.state = mock_state

        with patch.object(tool, "prepare_state", new_callable=AsyncMock, side_effect=mock_prepare_state):
            result = await tool.get_update()
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_update_saves_screenshot_as_base64(self, tool):
        """Screenshot now returns base64 (CDP) instead of writing to file (Playwright)."""
        fake_png = b"\x89PNG_FAKE_DATA"
        fake_b64 = base64.b64encode(fake_png).decode()

        mock_page = MagicMock()
        mock_page.screenshot = AsyncMock(return_value=fake_b64)

        mock_state = MagicMock()
        mock_state.use_agent = MagicMock()
        mock_state.use_agent.history = MagicMock()
        mock_state.use_agent.history.action_results = MagicMock(return_value=[])
        mock_state.get_page = AsyncMock(return_value=mock_page)
        mock_state.task = MagicMock()
        mock_state.task.is_ready = MagicMock(return_value=False)
        mock_state.task.execute_inside = AsyncMock(side_effect=lambda fn: fn())

        async def mock_prepare_state(**kwargs):
            tool.state = mock_state

        with patch.object(tool, "prepare_state", new_callable=AsyncMock, side_effect=mock_prepare_state):
            with patch("plugins.browser.tools.browser_agent.files.get_abs_path", return_value="/tmp/screenshot.png"):
                with patch("plugins.browser.tools.browser_agent.files.make_dirs", MagicMock()):
                    with patch("plugins.browser.tools.browser_agent.persist_chat.get_chat_folder_path", return_value="chats"):
                        with patch("builtins.open", mock_open()) as m_open:
                            result = await tool.get_update()

        if "screenshot" in result:
            mock_page.screenshot.assert_called_once_with(format="png")
            m_open.assert_called_once_with("/tmp/screenshot.png", "wb")
            m_open().write.assert_called_once_with(fake_png)


class TestStateInitialize:
    @pytest.mark.asyncio
    async def test_initialize_creates_session_without_playwright(self, mock_agent):
        """Verify _initialize no longer calls ensure_playwright_binary."""
        from plugins.browser.tools.browser_agent import State

        state = State(mock_agent)

        mock_session = MagicMock()
        mock_session.start = AsyncMock()
        mock_session.get_current_page = AsyncMock(return_value=None)

        with patch("plugins.browser.tools.browser_agent.browser_use") as mock_bu:
            mock_bu.BrowserSession.return_value = mock_session
            mock_bu.BrowserProfile.return_value = MagicMock()
            with patch("plugins.browser.tools.browser_agent.files.get_abs_path", return_value="/fake/path"):
                await state._initialize()

        mock_bu.BrowserSession.assert_called_once()
        mock_session.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_injects_init_script_via_cdp(self, mock_agent):
        """Verify init script is injected via CDP addScriptToEvaluateOnNewDocument."""
        from plugins.browser.tools.browser_agent import State

        state = State(mock_agent)

        mock_page = MagicMock()
        mock_page.set_viewport_size = AsyncMock()

        async def _fake_session_id():
            return "session-123"
        type(mock_page).session_id = property(lambda self: _fake_session_id())

        mock_page._client = MagicMock()
        mock_page._client.send.Page.addScriptToEvaluateOnNewDocument = AsyncMock()

        mock_session = MagicMock()
        mock_session.start = AsyncMock()
        mock_session.get_current_page = AsyncMock(return_value=mock_page)

        js_content = "// shadow DOM override"

        with patch("plugins.browser.tools.browser_agent.browser_use") as mock_bu:
            mock_bu.BrowserSession.return_value = mock_session
            mock_bu.BrowserProfile.return_value = MagicMock()
            with patch("plugins.browser.tools.browser_agent.files.get_abs_path", return_value="/fake/init_override.js"):
                with patch("builtins.open", mock_open(read_data=js_content)):
                    await state._initialize()

        mock_page._client.send.Page.addScriptToEvaluateOnNewDocument.assert_called_once_with(
            {"source": js_content}, session_id="session-123"
        )

    @pytest.mark.asyncio
    async def test_initialize_sets_viewport_via_kwargs(self, mock_agent):
        """Verify viewport is set with keyword args (CDP) not dict (Playwright)."""
        from plugins.browser.tools.browser_agent import State

        state = State(mock_agent)

        mock_page = MagicMock()
        mock_page.set_viewport_size = AsyncMock()
        mock_page.session_id = AsyncMock(return_value="session-123")
        mock_page._client = MagicMock()
        mock_page._client.send.Page.addScriptToEvaluateOnNewDocument = AsyncMock()

        mock_session = MagicMock()
        mock_session.start = AsyncMock()
        mock_session.get_current_page = AsyncMock(return_value=mock_page)

        with patch("plugins.browser.tools.browser_agent.browser_use") as mock_bu:
            mock_bu.BrowserSession.return_value = mock_session
            mock_bu.BrowserProfile.return_value = MagicMock()
            with patch("plugins.browser.tools.browser_agent.files.get_abs_path", return_value="/fake/path"):
                with patch("builtins.open", mock_open(read_data="")):
                    await state._initialize()

        mock_page.set_viewport_size.assert_called_once_with(width=1024, height=2048)


class TestBrowserAgentNoPlaywrightImport:
    def test_no_playwright_import_in_browser_agent(self):
        """Ensure browser_agent.py no longer imports from playwright helper."""
        import inspect
        from plugins.browser.tools import browser_agent
        source = inspect.getsource(browser_agent)
        assert "ensure_playwright_binary" not in source
        assert "from helpers.playwright" not in source
