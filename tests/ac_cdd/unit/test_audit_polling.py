import asyncio
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
        # 1. First check: returns "commit_A" (same as last audited) -> triggers polling
        # 2. Polling loop iteration 1: returns "commit_B" (new commit) -> exits loop
        nodes.git.get_current_commit.side_effect = [
            "commit_A",  # Initial check (already audited)
            "commit_B",  # After poll 1
        ]

        # Patch asyncio.sleep to run instantly
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            # We also need to mock _read_files and llm_reviewer since run_audit continues after polling
            nodes._read_files = AsyncMock(return_value={"file.py": "content"})
            nodes._run_static_analysis = AsyncMock(return_value=(True, ""))
            nodes.llm_reviewer = AsyncMock()
            nodes.llm_reviewer.review_code = AsyncMock(return_value="-> APPROVE")

            # Run the node
            result = await nodes.auditor_node(state)

            # Assertions
            
            # 1. Verify checkout_pr was called
            nodes.git.checkout_pr.assert_called_with("https://github.com/org/repo/pull/123")
            
            # 2. Verify get_current_commit was called twice
            assert nodes.git.get_current_commit.call_count == 2
            
            # 3. CRITICAL: Verify pull_changes was called inside the polling loop
            # This is what we are fixing!
            assert nodes.git.pull_changes.call_count >= 1

            # 4. Verify we proceeded with the new commit
            assert result["last_audited_commit"] == "commit_B"
