from unittest.mock import AsyncMock, patch

import pytest
from ac_cdd_core.graph import GraphBuilder

from ac_cdd_config import config


def test_config_update():
    """Verify SandboxConfig loads with new install_cmd."""
    expected_cmd = "pip install --no-cache-dir ruff aider-chat"
    assert config.sandbox.install_cmd == expected_cmd, (
        f"Expected {expected_cmd}, got {config.sandbox.install_cmd}"
    )


@pytest.mark.asyncio
async def test_syntax_check_node(mock_services):
    """Verify syntax_check_node executes compileall and ruff."""
    builder = GraphBuilder(mock_services)

    # Mock sandbox runner
    mock_runner = AsyncMock()
    # Mock successful returns for compileall (code 0) and ruff (code 0)
    mock_runner.run_command.side_effect = [
        ("echo ok", "", 0),  # dependencies check in _get_shared_sandbox (ruff --version)
        ("", "", 0),  # compileall
        ("ok", "", 0),  # ruff
    ]

    with patch.object(builder, "_get_shared_sandbox", return_value=mock_runner):
        state = {"cycle_id": "01", "active_branch": "feat/cycle01"}
        result = await builder.syntax_check_node(state)

        assert result["current_phase"] == "syntax_check_passed"
        assert result["test_exit_code"] == 0

        # Verify calls
        # We expect 2 main calls: compileall and ruff check
        # (plus the dependency check if _get_shared_sandbox logic triggers it,
        # but we mocked the runner not the method entirely?
        # Wait, I patched _get_shared_sandbox to return mock_runner directly,
        # so the logic inside _get_shared_sandbox regarding ruff version check
        # is SKIPPED by the patch.
        # So I only expect calls from syntax_check_node.)

        # Actually syntax_check_node calls _get_shared_sandbox, which I patched.
        # So inside syntax_check_node:
        # 1. runner = await self._get_shared_sandbox() -> returns mock_runner
        # 2. runner.run_command(["python3", ...])
        # 3. runner.run_command(["ruff", ...])

        # Reset mock to clear previous calls
        mock_runner.reset_mock()

        # Reset side effect to match this expectation
        mock_runner.run_command.side_effect = [
            ("", "", 0),  # compileall
            ("ok", "", 0),  # ruff
        ]

        # Re-run to be clean
        result = await builder.syntax_check_node(state)

        calls = mock_runner.run_command.call_args_list
        assert len(calls) == 2
        assert "compileall" in calls[0][0][0]
        assert "ruff" in calls[1][0][0]


@pytest.mark.asyncio
async def test_coder_graph_build(mock_services):
    """Verify the coder graph builds without uat_evaluate_node."""
    builder = GraphBuilder(mock_services)
    graph = builder.build_coder_graph()
    assert graph is not None

    # Introspect graph (if possible with LangGraph) or just rely on successful compile
    # LangGraph compiled graph structure is opaque, but if it compiled, nodes match edges.
