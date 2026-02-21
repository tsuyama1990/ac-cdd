from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ac_cdd_core.graph_nodes import CycleNodes
from ac_cdd_core.sandbox import SandboxRunner
from ac_cdd_core.services.jules_client import JulesClient


class TestAuditPolling:
    """Tests for the Audit Polling Logic in CycleNodes.auditor_node."""

    @pytest.mark.asyncio
    async def test_audit_polling_pulls_changes(self) -> None:
        """
        Verifies that the auditor node pulls changes from remote while polling
        for a new commit.
        """
        # Setup mocks
        mock_sandbox = MagicMock(spec=SandboxRunner)
        mock_jules = MagicMock(spec=JulesClient)
        nodes = CycleNodes(mock_sandbox, mock_jules)

        # Mock GitManager and its methods
        nodes.git = AsyncMock()
        nodes.git.checkout_pr = AsyncMock()
        nodes.git.get_current_commit = AsyncMock()
        nodes.git.pull_changes = AsyncMock()
        nodes.git.get_pr_base_branch = AsyncMock(return_value="main")
        nodes.git.get_changed_files = AsyncMock(return_value=["file.py"])

        # Mock State
        state = {
            "pr_url": "https://github.com/org/repo/pull/123",
            "last_audited_commit": "commit_A",
            "feature_branch": "feature/branch",
        }

        # Scenario:
        # If current_commit == last_audited and Jules is running,
        # it should return 'waiting_for_jules' to let LangGraph loop.
        nodes.git.get_current_commit.return_value = "commit_A"
        mock_jules.get_session_state = AsyncMock(return_value="RUNNING")

        state = {
            "pr_url": "https://github.com/org/repo/pull/123",
            "last_audited_commit": "commit_A",
            "feature_branch": "feature/branch",
            "jules_session_name": "sessions/123",
        }

        # Run the node
        result = await nodes.auditor_node(state)

        # Assertions
        assert result["status"] == "waiting_for_jules"
        assert result["last_audited_commit"] == "commit_A"
        mock_jules.get_session_state.assert_called_with("sessions/123")
