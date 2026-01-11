from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ac_cdd_core.cli import app
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def mock_deps() -> Iterator[None]:
    with (
        patch("ac_cdd_core.cli.utils.check_api_key", return_value=True),
        patch("shutil.which", return_value="/usr/bin/git"),
        patch("ac_cdd_core.cli.ProjectManager"),
        patch("ac_cdd_core.cli.StateManager"),
        patch("ac_cdd_core.cli._WorkflowServiceHolder.get"),
    ):
        yield


def test_gen_cycles_command(mock_deps: None) -> None:
    mock_workflow = MagicMock()
    mock_workflow.run_gen_cycles = AsyncMock()
    with patch("ac_cdd_core.cli._WorkflowServiceHolder.get", return_value=mock_workflow):
        result = runner.invoke(app, ["gen-cycles", "--cycles", "3"])
        assert result.exit_code == 0
        mock_workflow.run_gen_cycles.assert_awaited_once()


def test_run_cycle_command(mock_deps: None) -> None:
    mock_workflow = MagicMock()
    mock_workflow.run_cycle = AsyncMock()
    with patch("ac_cdd_core.cli._WorkflowServiceHolder.get", return_value=mock_workflow):
        result = runner.invoke(app, ["run-cycle", "--id", "01"])
        assert result.exit_code == 0
        mock_workflow.run_cycle.assert_awaited_once()


def test_finalize_session_command(mock_deps: None) -> None:
    mock_workflow = MagicMock()
    mock_workflow.finalize_session = AsyncMock()
    with patch("ac_cdd_core.cli._WorkflowServiceHolder.get", return_value=mock_workflow):
        result = runner.invoke(app, ["finalize-session"])
        assert result.exit_code == 0
        mock_workflow.finalize_session.assert_awaited_once()
