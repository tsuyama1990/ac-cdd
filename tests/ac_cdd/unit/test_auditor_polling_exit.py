from unittest.mock import AsyncMock, MagicMock

import pytest
from ac_cdd_core.graph_nodes import CycleNodes
from ac_cdd_core.state import CycleState


class TestAuditorPollingExit:
    """Tests for auditor_node polling logic."""

    @pytest.mark.asyncio
    async def test_auditor_breaks_on_completed_session(self) -> None:
        """Verifies that polling breaks if Jules session is COMPLETED."""
        # Setup mocks
        sandbox = MagicMock()
        jules = MagicMock()
        jules.get_session_state = AsyncMock(
            side_effect=["RUNNING", "COMPLETED"]
        )  # Simulate transition

        nodes = CycleNodes(sandbox, jules)
        nodes.git = AsyncMock()

        # Git behavior:
        # get_current_commit returns same hash "abc" (no new commit)
        nodes.git.get_current_commit = AsyncMock(return_value="abc")
        nodes.git.pull_changes = AsyncMock()
        nodes.git.checkout_pr = AsyncMock()  # Skip PR checkout logic
        nodes.git.get_changed_files = AsyncMock(return_value=["test.py"])  # To proceed to review
        nodes.git.runner = AsyncMock()  # Used in static analysis
        nodes.git.runner.run_command = AsyncMock(return_value=("", "", 0))

        # Mock reviewer to avoid LLM call
        nodes.llm_reviewer = AsyncMock()
        nodes.llm_reviewer.review_code = AsyncMock(return_value="NO ISSUES FOUND -> APPROVE")

        # Initial state: last_audited same as current ("abc")
        state = CycleState(
            cycle_id="01",
            last_audited_commit="abc",
            pr_url="https://github.com/test/pr/1",
            jules_session_name="sessions/123",
        )

        # Run auditor
        result = await nodes.auditor_node(state)

        # Assertions
        # 1. It should have called pull_changes at least once
        assert nodes.git.pull_changes.called
        # 2. It should have called get_session_state
        assert jules.get_session_state.called
        # 3. It should return a valid result (not waiting_for_jules)
        # Because it broke the loop and proceeded to audit
        assert result["status"] == "approved"
        # 4. last_audited_commit should be updated (or remain same "abc")
        assert result["last_audited_commit"] == "abc"
