import os
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

# Helper for AsyncMock if not available in standard unittest.mock (py3.8+)
try:
    from unittest.mock import AsyncMock
except ImportError:

    class AsyncMock(MagicMock):
        async def __call__(self, *args, **kwargs):
            return super().__call__(*args, **kwargs)


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_project_manager():
    return MagicMock()


@pytest.fixture
def mock_graph_builder():
    m = MagicMock()
    # Ensure cleanup is async-awaitable
    m.cleanup = AsyncMock()
    return m


@pytest.fixture
def mock_session_manager():
    return MagicMock()


@pytest.fixture
def mock_session_validator():
    return MagicMock()


@pytest.fixture
def mock_git_manager():
    return MagicMock()


def test_init_command_creates_structure(runner):
    """Test init command creates project structure."""
    with (
        patch("ac_cdd_core.cli.check_environment") as mock_check,
        patch("ac_cdd_core.services.project.ProjectManager.initialize_project") as mock_init,
        patch("rich.console.Console.print"),
    ):
        from ac_cdd_core.cli import app

        result = runner.invoke(app, ["init"])

        assert result.exit_code == 0
        mock_check.assert_called_once()
        mock_init.assert_called_once()


def test_check_environment_missing_keys():
    """Test check_environment detects missing API keys."""
    # We use a context manager to patch check_api_key to return False (invalid)
    with (
        patch("ac_cdd_core.utils.check_api_key", return_value=False),
        patch("rich.console.Console.print"),
    ):
        from ac_cdd_core.cli import check_environment

        # With missing keys, it should raise typer.Exit
        with pytest.raises((typer.Exit, SystemExit)):
            check_environment()


def test_check_environment_all_present():
    """Test check_environment passes when all keys present."""
    # We patch check_api_key to return True
    # AND we must ensure os.environ has the required vars to pass the second check
    with (
        patch("ac_cdd_core.utils.check_api_key", return_value=True),
        patch.dict(os.environ, {"JULES_API_KEY": "test", "E2B_API_KEY": "test"}),
        patch("subprocess.run", return_value=MagicMock(returncode=0)),
        patch("shutil.which", return_value="/usr/bin/git"),
    ):
        from ac_cdd_core.cli import check_environment

        # Should not raise
        check_environment()


def test_init_command(runner, mock_project_manager):
    """Test init command execution."""
    with patch("ac_cdd_core.cli.check_environment"):
        from ac_cdd_core.cli import app

        # Patch ProjectManager inside cli scope or where it's instantiated
        # The cli.init instantiates ProjectManager().
        # We need to patch the class ProjectManager to return our mock instance
        with patch(
            "ac_cdd_core.services.project.ProjectManager", return_value=mock_project_manager
        ):
            result = runner.invoke(app, ["init"])

            assert result.exit_code == 0
            assert "Initialization Complete" in result.stdout


def test_gen_cycles_command(runner, mock_graph_builder, mock_session_manager):
    """Test gen-cycles command."""
    from ac_cdd_core.cli import app

    with (
        patch("ac_cdd_core.messages.ensure_api_key"),
        patch("ac_cdd_core.cli.ServiceContainer"),
        # Patch where the classes are defined, not in cli (lazy imports)
        patch("ac_cdd_core.graph.GraphBuilder", return_value=mock_graph_builder),
        patch("ac_cdd_core.session_manager.SessionManager", mock_session_manager),
        patch("ac_cdd_core.cli.CycleState") as MockCycleState,
    ):
        # Mock graph execution
        mock_graph = MagicMock()
        mock_state = MagicMock()
        mock_state.session_id = "test-session"
        mock_state.integration_branch = "dev/test"
        mock_state.get.return_value = None  # for .get("error")

        mock_graph.ainvoke = AsyncMock(return_value=mock_state)
        mock_graph_builder.build_architect_graph.return_value = mock_graph

        # Invoke with explicit cycles count
        result = runner.invoke(app, ["gen-cycles", "--cycles", "3"])

        assert result.exit_code == 0
        assert "Architect Phase: Generating Cycles" in result.stdout

        # Verify CycleState was initialized with planned_cycle_count=3
        MockCycleState.assert_called_once()
        _, kwargs = MockCycleState.call_args
        assert kwargs.get("planned_cycle_count") == 3


def test_run_cycle_command(
    runner, mock_graph_builder, mock_session_manager, mock_session_validator
):
    """Test run-cycle command."""
    from ac_cdd_core.cli import app

    with (
        patch("ac_cdd_core.messages.ensure_api_key"),
        patch("ac_cdd_core.cli.ServiceContainer"),
        patch("ac_cdd_core.graph.GraphBuilder", return_value=mock_graph_builder),
        patch("ac_cdd_core.session_manager.SessionManager", mock_session_manager),
        patch("ac_cdd_core.validators.SessionValidator", return_value=mock_session_validator),
    ):
        # Setup mocks
        mock_session_manager.load_or_reconcile_session.return_value = {
            "session_id": "test",
            "integration_branch": "dev/test",
        }
        mock_session_validator.validate = AsyncMock(return_value=(True, ""))

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value={"current_phase": "complete"})
        mock_graph_builder.build_coder_graph.return_value = mock_graph

        result = runner.invoke(app, ["run-cycle", "--id", "01"])

        assert result.exit_code == 0


def test_finalize_session_command(runner, mock_session_manager, mock_git_manager):
    """Test finalize-session command."""
    from ac_cdd_core.cli import app

    with (
        patch("ac_cdd_core.session_manager.SessionManager", mock_session_manager),
        patch("ac_cdd_core.services.git_ops.GitManager", return_value=mock_git_manager),
        patch("pathlib.Path.exists", return_value=True),
        patch("pathlib.Path.read_text", return_value='{"cycles": ["01"]}'),
    ):
        mock_session_manager.load_or_reconcile_session.return_value = {
            "session_id": "test",
            "integration_branch": "dev/test",
        }
        mock_session_manager.validate_session.return_value = (True, "")
        mock_git_manager.create_final_pr = AsyncMock(return_value="https://pr")

        result = runner.invoke(app, ["finalize-session"])

        assert result.exit_code == 0
        assert "Session Finalized" in result.stdout
