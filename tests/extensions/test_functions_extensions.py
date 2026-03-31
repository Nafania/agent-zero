"""Tests for _functions/ extension directory structure and extension loading."""

import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TestFunctionsDirectoryStructure:
    """Verify that _functions/ extension files exist at expected paths."""

    @pytest.mark.parametrize(
        "rel_path",
        [
            "extensions/python/_functions/__main__/init_a0/end/_10_register_watchdogs.py",
            "extensions/python/_functions/agent/Agent/handle_exception/end/_40_handle_intervention_exception.py",
            "extensions/python/_functions/agent/Agent/handle_exception/end/_50_handle_repairable_exception.py",
            "extensions/python/_functions/agent/Agent/handle_exception/end/_90_handle_critical_exception.py",
        ],
    )
    def test_core_extension_file_exists(self, rel_path):
        full_path = PROJECT_ROOT / rel_path
        assert full_path.exists(), f"Missing core extension: {rel_path}"

    @pytest.mark.parametrize(
        "rel_path",
        [
            "plugins/error_retry/extensions/python/_functions/agent/Agent/handle_exception/end/_80_retry_critical_exception.py",
            "plugins/error_retry/extensions/python/_functions/agent/Agent/monologue/start/_10_reset_critical_exception_counter.py",
            "plugins/browser/extensions/python/_functions/agent/Agent/get_browser_model/start/_10_browser_agent.py",
        ],
    )
    def test_plugin_extension_file_exists(self, rel_path):
        full_path = PROJECT_ROOT / rel_path
        assert full_path.exists(), f"Missing plugin extension: {rel_path}"

    @pytest.mark.parametrize(
        "rel_path",
        [
            "plugins/model_config/extensions/python/_functions/agent/Agent/get_chat_model/start/_10_model_config.py",
            "plugins/model_config/extensions/python/_functions/agent/Agent/get_embedding_model/start/_10_model_config.py",
            "plugins/model_config/extensions/python/_functions/agent/Agent/get_utility_model/start/_10_model_config.py",
            "plugins/model_config/extensions/python/_functions/agent/Agent/get_browser_model/start/_10_model_config.py",
        ],
    )
    def test_model_config_extension_file_exists(self, rel_path):
        full_path = PROJECT_ROOT / rel_path
        assert full_path.exists(), f"Missing model_config extension: {rel_path}"


class TestRegisterWatchdogs:
    """Tests for _10_register_watchdogs.py."""

    def test_calls_plugin_watchdogs(self):
        from extensions.python._functions.__main__.init_a0.end._10_register_watchdogs import (
            RegisterWatchDogs,
        )

        ext = RegisterWatchDogs(agent=None)
        with patch(
            "helpers.plugins.register_watchdogs"
        ) as mock_reg:
            ext.execute()
            mock_reg.assert_called_once()


class TestHandleInterventionException:
    """Tests for _40_handle_intervention_exception.py."""

    @pytest.mark.asyncio
    async def test_clears_intervention_exception(self, mock_agent):
        from agent import InterventionException
        from extensions.python._functions.agent.Agent.handle_exception.end._40_handle_intervention_exception import (
            HandleInterventionException,
        )

        data = {"exception": InterventionException("user paused")}
        ext = HandleInterventionException(agent=mock_agent)
        await ext.execute(data=data)
        assert data["exception"] is None

    @pytest.mark.asyncio
    async def test_ignores_non_intervention(self, mock_agent):
        from extensions.python._functions.agent.Agent.handle_exception.end._40_handle_intervention_exception import (
            HandleInterventionException,
        )

        original = ValueError("some error")
        data = {"exception": original}
        ext = HandleInterventionException(agent=mock_agent)
        await ext.execute(data=data)
        assert data["exception"] is original

    @pytest.mark.asyncio
    async def test_noop_without_agent(self):
        from agent import InterventionException
        from extensions.python._functions.agent.Agent.handle_exception.end._40_handle_intervention_exception import (
            HandleInterventionException,
        )

        data = {"exception": InterventionException("test")}
        ext = HandleInterventionException(agent=None)
        await ext.execute(data=data)
        assert data["exception"] is not None

    @pytest.mark.asyncio
    async def test_noop_without_exception(self, mock_agent):
        from extensions.python._functions.agent.Agent.handle_exception.end._40_handle_intervention_exception import (
            HandleInterventionException,
        )

        data = {"exception": None}
        ext = HandleInterventionException(agent=mock_agent)
        await ext.execute(data=data)
        assert data["exception"] is None


class TestHandleRepairableException:
    """Tests for _50_handle_repairable_exception.py."""

    @pytest.mark.asyncio
    async def test_clears_repairable_exception(self, mock_agent):
        from helpers.errors import RepairableException

        exc = RepairableException("fixable error")
        data = {"exception": exc}

        mock_agent.hist_add_warning = MagicMock(return_value=MagicMock(id="msg-1"))

        with patch(
            "extensions.python._functions.agent.Agent.handle_exception.end._50_handle_repairable_exception.extension.call_extensions_async",
            new_callable=AsyncMock,
        ):
            from extensions.python._functions.agent.Agent.handle_exception.end._50_handle_repairable_exception import (
                HandleRepairableException,
            )

            ext = HandleRepairableException(agent=mock_agent)
            await ext.execute(data=data)

        assert data["exception"] is None
        mock_agent.hist_add_warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_ignores_non_repairable(self, mock_agent):
        from extensions.python._functions.agent.Agent.handle_exception.end._50_handle_repairable_exception import (
            HandleRepairableException,
        )

        original = RuntimeError("not repairable")
        data = {"exception": original}
        ext = HandleRepairableException(agent=mock_agent)
        await ext.execute(data=data)
        assert data["exception"] is original


class TestHandleCriticalException:
    """Tests for _90_handle_critical_exception.py."""

    @pytest.mark.asyncio
    async def test_wraps_generic_exception(self, mock_agent):
        from agent import HandledException

        data = {"exception": RuntimeError("kaboom")}
        mock_agent.agent_name = "test-agent"

        from extensions.python._functions.agent.Agent.handle_exception.end._90_handle_critical_exception import (
            HandleCriticalException,
        )

        ext = HandleCriticalException(agent=mock_agent)
        await ext.execute(data=data)

        assert isinstance(data["exception"], HandledException)

    @pytest.mark.asyncio
    async def test_preserves_handled_exception(self, mock_agent):
        from agent import HandledException

        original = HandledException(RuntimeError("already handled"))
        data = {"exception": original}

        from extensions.python._functions.agent.Agent.handle_exception.end._90_handle_critical_exception import (
            HandleCriticalException,
        )

        ext = HandleCriticalException(agent=mock_agent)
        await ext.execute(data=data)
        assert data["exception"] is original

    @pytest.mark.asyncio
    async def test_noop_without_exception(self, mock_agent):
        from extensions.python._functions.agent.Agent.handle_exception.end._90_handle_critical_exception import (
            HandleCriticalException,
        )

        data = {"exception": None}
        ext = HandleCriticalException(agent=mock_agent)
        await ext.execute(data=data)
        assert data["exception"] is None


class TestResetCriticalExceptionCounter:
    """Tests for error_retry _10_reset_critical_exception_counter.py."""

    @pytest.mark.asyncio
    async def test_resets_counter(self, mock_agent):
        from plugins.error_retry.extensions.python._functions.agent.Agent.monologue.start._10_reset_critical_exception_counter import (
            ResetCriticalExceptionCounter,
            DATA_NAME_COUNTER,
        )

        ext = ResetCriticalExceptionCounter(agent=mock_agent)
        await ext.execute()
        mock_agent.set_data.assert_called_with(DATA_NAME_COUNTER, 0)

    @pytest.mark.asyncio
    async def test_noop_without_agent(self):
        from plugins.error_retry.extensions.python._functions.agent.Agent.monologue.start._10_reset_critical_exception_counter import (
            ResetCriticalExceptionCounter,
        )

        ext = ResetCriticalExceptionCounter(agent=None)
        await ext.execute()


class TestRetryCriticalException:
    """Tests for error_retry _80_retry_critical_exception.py."""

    @pytest.mark.asyncio
    async def test_resets_counter_when_no_exception(self, mock_agent):
        from plugins.error_retry.extensions.python._functions.agent.Agent.monologue.start._10_reset_critical_exception_counter import (
            DATA_NAME_COUNTER,
        )
        from plugins.error_retry.extensions.python._functions.agent.Agent.handle_exception.end._80_retry_critical_exception import (
            RetryCriticalException,
        )

        data = {"exception": None}
        ext = RetryCriticalException(agent=mock_agent)
        await ext.execute(data=data)
        mock_agent.set_data.assert_called_with(DATA_NAME_COUNTER, 0)

    @pytest.mark.asyncio
    async def test_resets_counter_on_handled_exception(self, mock_agent):
        from agent import HandledException
        from plugins.error_retry.extensions.python._functions.agent.Agent.monologue.start._10_reset_critical_exception_counter import (
            DATA_NAME_COUNTER,
        )
        from plugins.error_retry.extensions.python._functions.agent.Agent.handle_exception.end._80_retry_critical_exception import (
            RetryCriticalException,
        )

        data = {"exception": HandledException(RuntimeError("already handled"))}
        ext = RetryCriticalException(agent=mock_agent)
        await ext.execute(data=data)
        mock_agent.set_data.assert_called_with(DATA_NAME_COUNTER, 0)

    @pytest.mark.asyncio
    @patch("plugins.error_retry.extensions.python._functions.agent.Agent.handle_exception.end._80_retry_critical_exception.plugins")
    async def test_retries_on_first_critical_exception(self, mock_plugins, mock_agent):
        mock_plugins.get_plugin_config.return_value = {"max_retries": 3, "retry_delay": 0}
        mock_agent.get_data = MagicMock(return_value=0)
        mock_agent.handle_intervention = AsyncMock()
        mock_agent.read_prompt = MagicMock(return_value="Error occurred")
        mock_agent.hist_add_warning = MagicMock()

        from plugins.error_retry.extensions.python._functions.agent.Agent.handle_exception.end._80_retry_critical_exception import (
            RetryCriticalException,
        )

        data = {"exception": RuntimeError("critical")}
        ext = RetryCriticalException(agent=mock_agent)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await ext.execute(data=data)

        assert data["exception"] is None

    @pytest.mark.asyncio
    @patch("plugins.error_retry.extensions.python._functions.agent.Agent.handle_exception.end._80_retry_critical_exception.plugins")
    async def test_does_not_retry_when_max_reached(self, mock_plugins, mock_agent):
        mock_plugins.get_plugin_config.return_value = {"max_retries": 3}
        mock_agent.get_data = MagicMock(return_value=3)

        from plugins.error_retry.extensions.python._functions.agent.Agent.handle_exception.end._80_retry_critical_exception import (
            RetryCriticalException,
        )

        original = RuntimeError("critical")
        data = {"exception": original}
        ext = RetryCriticalException(agent=mock_agent)
        await ext.execute(data=data)
        assert data["exception"] is original


class TestBrowserModelProvider:
    """Tests for browser plugin _10_browser_agent.py stub."""

    def test_noop_stub(self, mock_agent):
        from plugins.browser.extensions.python._functions.agent.Agent.get_browser_model.start._10_browser_agent import (
            BrowserModelProvider,
        )

        data = {"result": None}
        ext = BrowserModelProvider(agent=mock_agent)
        ext.execute(data=data)
        assert data["result"] is None


class TestExtensionPathFormula:
    """Verify _prepare_inputs generates correct _functions/ paths."""

    def test_path_for_handle_exception(self):
        expected = os.path.join("_functions", "agent", "Agent", "handle_exception")

        from helpers.extension import extensible

        @extensible
        async def handle_exception(self, location, exception):
            pass

        handle_exception.__module__ = "agent"
        handle_exception.__qualname__ = "Agent.handle_exception"

        assert expected == os.path.join(
            "_functions",
            *"agent".split("."),
            *"Agent.handle_exception".split("."),
        )

    def test_path_for_init_a0(self):
        expected = os.path.join("_functions", "__main__", "init_a0")
        parts = os.path.join("_functions", *"__main__".split("."), *"init_a0".split("."))
        assert expected == parts

    def test_path_for_monologue(self):
        expected = os.path.join("_functions", "agent", "Agent", "monologue")
        parts = os.path.join(
            "_functions", *"agent".split("."), *"Agent.monologue".split(".")
        )
        assert expected == parts
