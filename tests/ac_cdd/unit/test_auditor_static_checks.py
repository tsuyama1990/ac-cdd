from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ac_cdd_core.graph_nodes import CycleNodes


@pytest.fixture
def mock_dependencies() -> tuple[Any, Any]:
    sandbox = MagicMock()
    jules = MagicMock()
    return sandbox, jules


@pytest.mark.asyncio
async def test_auditor_node_includes_static_errors(mock_dependencies: tuple[Any, Any]) -> None:
    """
    Verify that if static analysis fails, the feedback includes errors and status is rejected.
    """
    sandbox, jules = mock_dependencies

    # Patch dependencies inside CycleNodes init or instance
    # Since we can't easily patch GitManager inside __init__ without patching the class import,
    # we'll instantiate first and then mock the attribute.

    with (
        patch("ac_cdd_core.graph_nodes.GitManager") as MockGit,
        patch("ac_cdd_core.graph_nodes.AuditOrchestrator"),
        patch("ac_cdd_core.graph_nodes.LLMReviewer"),
        patch("ac_cdd_core.graph_nodes.settings"),
    ):
        # Setup mocks
        mock_git_instance = MockGit.return_value

        # Mock LLM Reviewer to return Approval
        mock_llm = MagicMock()
        mock_llm.review_code = AsyncMock(return_value="NO ISSUES FOUND")

        nodes = CycleNodes(sandbox, jules)
        nodes.llm_reviewer = mock_llm
        nodes.git = mock_git_instance  # Ensure our mock instance is used

        # Mock _read_files to return empty dict
        nodes._read_files = AsyncMock(return_value={})

        # Mock Git behavior for retrieving files (happy path)
        mock_git_instance.get_changed_files = AsyncMock(return_value=["test.py"])
        # Mock check-ignore
        mock_git_instance.runner.run_command = AsyncMock(
            return_value=("", "", 1)
        )  # 1 means not ignored

        async def mock_run_command_side_effect(
            cmd: list[str], check: bool = False, **kwargs: Any
        ) -> tuple[str, str, int]:
            cmd_str = " ".join(cmd)
            if "mypy" in cmd_str:
                return "mypy failure", "error", 1  # Fail
            if "ruff" in cmd_str:
                return "ruff success", "", 0  # Pass
            if "check-ignore" in cmd_str:
                return "", "", 1  # 1 means NOT ignored
            return "", "", 0

        mock_git_instance.runner.run_command = AsyncMock(side_effect=mock_run_command_side_effect)

        # Run auditor_node
        state = {"pr_url": "http://pr", "feature_branch": "feat/1"}
        result = await nodes.auditor_node(state)

        # Assertions
        assert result["status"] == "rejected"
        audit_res = result["audit_result"]
        assert not audit_res.is_approved
        assert "AUTOMATED CHECKS FAILED" in audit_res.feedback
        assert "mypy failure" in audit_res.feedback
        assert "NO ISSUES FOUND" in audit_res.feedback  # LLM text is still there
