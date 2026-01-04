from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ac_cdd_core.cli import app
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def mock_dependencies():
    with (
        patch("ac_cdd_core.cli.GraphBuilder") as mock_graph_cls,
        patch("ac_cdd_core.cli.SessionManager") as mock_session_mgr,
        patch("ac_cdd_core.cli.ensure_api_key"),
        patch("ac_cdd_core.cli.GitManager") as mock_git_cls,
        patch("ac_cdd_core.cli.SessionValidator") as mock_validator_cls,
        patch("ac_cdd_core.cli.KeepAwake"),
        patch("ac_cdd_core.cli.ServiceContainer"),
    ):
        mock_graph_instance = mock_graph_cls.return_value
        mock_graph_instance.build_architect_graph.return_value = MagicMock()
        mock_graph_instance.build_coder_graph.return_value = MagicMock()
        mock_graph_instance.cleanup = AsyncMock()

        mock_git_instance = mock_git_cls.return_value
        mock_git_instance.create_integration_branch = AsyncMock()
        mock_git_instance.merge_to_integration = AsyncMock()
        mock_git_instance.create_final_pr = AsyncMock()

        mock_validator = mock_validator_cls.return_value
        mock_validator.validate = AsyncMock(return_value=(True, None))

        yield {
            "graph": mock_graph_instance,
            "session": mock_session_mgr,
            "git": mock_git_instance,
            "validator": mock_validator,
        }


def test_gen_cycles_command(mock_dependencies) -> None:
    # Mock async graph run
    mock_graph = mock_dependencies["graph"]
    # ainvoke returns final state (dict to support .get('error') returning None)
    mock_graph.build_architect_graph.return_value.ainvoke = AsyncMock(
        return_value={
            "project_session_id": "test-session",
            "integration_branch": "dev/test",
            "error": None,
            "pr_url": "http://pr",
        }
    )
    mock_graph.cleanup = AsyncMock()

    result = runner.invoke(app, ["gen-cycles"])
    assert result.exit_code == 0
    assert "Architect Phase" in result.stdout
    assert "Using saved session" not in result.stdout  # Should be new


def test_run_cycle_command(mock_dependencies) -> None:
    mock_graph = mock_dependencies["graph"]
    mock_session = mock_dependencies["session"]
    mock_return = {
        "project_session_id": "test",
        "integration_branch": "dev/test",
        "session_id": "test",
    }
    mock_session.load_or_reconcile_session.return_value = mock_return
    mock_session.load_session.return_value = mock_return
    mock_session.validate_session.return_value = (True, None)

    mock_graph.build_coder_graph.return_value.ainvoke = AsyncMock(
        return_value={"current_phase": "complete", "error": None}
    )
    mock_graph.cleanup = AsyncMock()  # Fix await

    # Patch SessionValidator because run_cycle instantiates it
    with patch("ac_cdd_core.validators.SessionValidator") as mock_val_cls:
        mock_val_cls.return_value.validate = AsyncMock(return_value=(True, None))

        result = runner.invoke(app, ["run-cycle", "--id", "01"])

        assert result.exit_code == 0
        assert "Cycle 01" in result.stdout
        assert "Implementation" in result.stdout
        assert "Sent" in result.stdout


def test_finalize_session_command(mock_dependencies) -> None:
    mock_session = mock_dependencies["session"]
    mock_session.load_or_reconcile_session.return_value = {
        "project_session_id": "test",
        "integration_branch": "dev/test",
    }
    mock_session.validate_session.return_value = (True, None)

    mock_git_instance = mock_dependencies["git"]
    mock_git_instance.create_final_pr = AsyncMock(return_value="https://pr")

    result = runner.invoke(app, ["finalize-session"])

    assert result.exit_code == 0
    assert "Final PR Created" in result.stdout
