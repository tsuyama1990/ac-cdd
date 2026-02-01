from unittest.mock import AsyncMock, MagicMock

import pytest
from ac_cdd_core.graph_nodes import CycleNodes
from ac_cdd_core.sandbox import SandboxRunner
from ac_cdd_core.services.jules_client import JulesClient


class TestPhaseTransition:
    """Validate state reset when transitioning between phases."""

    @pytest.mark.asyncio
    async def test_refactor_phase_resets_final_fix(self) -> None:
        """Should reset final_fix flag on Refactor Phase transition."""
        # Setup mocks
        mock_sandbox = MagicMock(spec=SandboxRunner)
        mock_jules = MagicMock(spec=JulesClient)
        nodes = CycleNodes(mock_sandbox, mock_jules)
        nodes.git = AsyncMock()  # Mock git manager

        # Simulate Coder Phase state with final_fix=True (which causes the bug)
        state = {
            "current_phase": "coder",
            "final_fix": True,
            "iteration_count": 5,
            "pr_url": "https://github.com/repo/pull/1",
            "status": "cycle_approved",  # Trigger transition logic
            "last_feedback_time": 1234567890.0,
        }

        # Mock git.merge_pr to succeed, allowing transition logic to run
        nodes.git.merge_pr.return_value = None

        result = await nodes.uat_evaluate_node(state)

        # Should transition to Refactor
        assert result.get("current_phase") == "refactoring"

        # KEY ASSERTIONS - These should fail on current code
        assert result.get("final_fix") is False, "final_fix should be False"
        assert result.get("iteration_count") == 0
        assert result.get("pr_url") is None, "pr_url should be None"
        assert result.get("last_feedback_time") == 0, "last_feedback_time should be 0"
