"""Integration tests for CLI commands."""
from unittest.mock import MagicMock, patch

import pytest
from ac_cdd_core.cli import app
from typer.testing import CliRunner

runner = CliRunner()


def test_init_command_creates_structure():
    """Test that init command creates necessary directories."""
    with (
        patch("ac_cdd_core.cli.check_environment") as mock_check,
        patch("pathlib.Path.mkdir") as mock_mkdir,
        patch("pathlib.Path.exists", return_value=False),
    ):
        mock_check.return_value = None
        
        result = runner.invoke(app, ["init"])
        
        # Should create directories
        assert mock_mkdir.called
        assert result.exit_code == 0

@pytest.fixture
def mock_project_manager():
    with patch("ac_cdd_core.cli.ProjectManager") as mock:
        mock_instance = MagicMock()
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_session_manager():
    with patch("ac_cdd_core.cli.SessionManager") as mock:
        # Mock class methods
        mock.load_session.return_value = {"session_id": "test-session", "integration_branch": "dev/test-session"}
        mock.validate_session.return_value = (True, "")
        mock.get_integration_branch.return_value = "dev/test-session"
        # Mock async method
        mock.load_or_reconcile_session = AsyncMock(return_value=("test-session", "dev/test-session", None))
        yield mock


@pytest.fixture
def mock_session_validator():
    with patch("ac_cdd_core.cli.SessionValidator") as mock:
        mock_instance = AsyncMock()
        mock.return_value = mock_instance
        mock_instance.validate.return_value = (True, "")
        yield mock_instance


@pytest.fixture
def mock_graph_builder():
    with patch("ac_cdd_core.cli.GraphBuilder") as mock:
        mock_instance = AsyncMock()
        mock.return_value = mock_instance
        # Mock ainvoke to return a state dict
        mock_instance.build_architect_graph.return_value.ainvoke = AsyncMock(
            return_value=CycleState(session_id="test-session", integration_branch="dev/test-session")
        )
        mock_instance.build_coder_graph.return_value.ainvoke = AsyncMock(
            return_value=CycleState()
        )
        yield mock_instance


@pytest.fixture
def mock_git_manager():
    # Note: cli.py imports GitManager inside finalize_session command
    # We patch it where it's used or globally if possible.
    # Since imports are inside functions, we patch ac_cdd_core.services.git_ops.GitManager
    with patch("ac_cdd_core.services.git_ops.GitManager") as mock:
        mock_instance = AsyncMock()
        mock.return_value = mock_instance
        mock_instance.create_final_pr.return_value = "https://github.com/user/repo/pull/1"
        yield mock_instance


def test_init_command(runner, mock_project_manager):
    """Test init command."""
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert "Initialization Complete" in result.stdout
    mock_project_manager.initialize_project.assert_called_once()


def test_gen_cycles_command(runner, mock_graph_builder, mock_session_manager):
    """Test gen-cycles command."""
    # We need to mock messages.ensure_api_key which is called inside gen_cycles
    with patch("ac_cdd_core.messages.ensure_api_key"):
        result = runner.invoke(app, ["gen-cycles"])
        
    if result.exit_code != 0:
        print(result.stdout)
        
    assert result.exit_code == 0
    # Graph execution
    mock_graph_builder.build_architect_graph.assert_called_once()
    # Save session
    mock_session_manager.save_session.assert_called_once()


def test_run_cycle_command(runner, mock_graph_builder, mock_session_manager, mock_session_validator):
    """Test run-cycle command."""
    with patch("ac_cdd_core.messages.ensure_api_key"):
        result = runner.invoke(app, ["run-cycle", "--id", "01"])
        
    if result.exit_code != 0:
        print(result.stdout)
        
    assert result.exit_code == 0
    mock_graph_builder.build_coder_graph.assert_called_once()
    mock_session_manager.load_or_reconcile_session.assert_called_once()
    mock_session_validator.validate.assert_called_once()


def test_finalize_session_command(runner, mock_session_manager, mock_git_manager):
    """Test finalize-session command."""
    result = runner.invoke(app, ["finalize-session"])
    
    if result.exit_code != 0:
        print(result.stdout)
        
    assert result.exit_code == 0
    mock_session_manager.load_or_reconcile_session.assert_called_once()
    mock_git_manager.create_final_pr.assert_called_once()
    mock_session_manager.clear_session.assert_called_once()


def test_check_environment_missing_keys():
    """Test check_environment detects missing API keys."""
    with (
        patch("ac_cdd_core.utils.check_api_key", return_value=False),
        patch("rich.console.Console.print") as mock_print,
    ):
        from ac_cdd_core.cli import check_environment
        
        with pytest.raises(SystemExit):
            check_environment()
        
        # Should print error message
        assert mock_print.called


def test_check_environment_all_present():
    """Test check_environment passes when all keys present."""
    with (
        patch("ac_cdd_core.utils.check_api_key", return_value=True),
        patch("subprocess.run", return_value=MagicMock(returncode=0)),
    ):
        from ac_cdd_core.cli import check_environment
        
        # Should not raise
        check_environment()
