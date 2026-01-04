from unittest.mock import AsyncMock, patch

import pytest
from ac_cdd_core.cli import app
from typer.testing import CliRunner

runner = CliRunner()

@pytest.fixture
def mock_deps():
    with (
        patch("ac_cdd_core.cli.utils.check_api_key", return_value=True),
        patch("shutil.which", return_value="/usr/bin/git"),
        patch("ac_cdd_core.cli.ProjectManager"),
        patch("ac_cdd_core.cli.SessionManager"),
        patch("ac_cdd_core.cli.workflow_service"),
    ):
        yield

def test_gen_cycles_command(mock_deps):
    with patch("ac_cdd_core.cli.workflow_service.run_gen_cycles", new_callable=AsyncMock) as mock_run:
        result = runner.invoke(app, ["gen-cycles", "--cycles", "3"])
        assert result.exit_code == 0
        mock_run.assert_awaited_once()

def test_run_cycle_command(mock_deps):
    with patch("ac_cdd_core.cli.workflow_service.run_cycle", new_callable=AsyncMock) as mock_run:
        result = runner.invoke(app, ["run-cycle", "--id", "01"])
        assert result.exit_code == 0
        mock_run.assert_awaited_once()

def test_finalize_session_command(mock_deps):
    with patch("ac_cdd_core.cli.workflow_service.finalize_session", new_callable=AsyncMock) as mock_run:
        result = runner.invoke(app, ["finalize-session"])
        assert result.exit_code == 0
        mock_run.assert_awaited_once()
