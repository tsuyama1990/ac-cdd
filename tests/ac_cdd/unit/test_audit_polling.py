from unittest.mock import AsyncMock, MagicMock

import pytest
from ac_cdd_core.enums import FlowStatus
from ac_cdd_core.services.auditor_usecase import AuditorUseCase
from ac_cdd_core.state import CycleState


class TestAuditPolling:
    """Tests for the Audit Polling Logic in AuditorUseCase."""

    @pytest.mark.asyncio
    async def test_audit_polling_pulls_changes(self) -> None:
        """
        Verifies that when the auditor detects the same commit that was already audited,
        and Jules is still running, it returns 'WAITING_FOR_JULES' to let LangGraph loop.
        """
        mock_jules = MagicMock()
        mock_git = AsyncMock()
        mock_llm = MagicMock()

        # Git: current commit matches the already-audited commit
        mock_git.checkout_pr = AsyncMock()
        mock_git.get_current_commit = AsyncMock(return_value="commit_A")
        mock_git.get_pr_base_branch = AsyncMock(return_value="main")
        mock_git.get_changed_files = AsyncMock(return_value=["file.py"])

        # Jules is still in progress (active, non-terminal state)
        mock_jules.get_session_state = AsyncMock(return_value="IN_PROGRESS")

        usecase = AuditorUseCase(mock_jules, mock_git, mock_llm)

        state = CycleState(
            cycle_id="99",
            pr_url="https://github.com/org/repo/pull/123",
            last_audited_commit="commit_A",
            feature_branch="feature/branch",
            jules_session_name="sessions/123",
        )

        # Run the auditor
        result = await usecase.execute(state)

        # Should short-circuit with WAITING_FOR_JULES when commit hasn't changed
        assert result["status"] == FlowStatus.WAITING_FOR_JULES
        assert result["last_audited_commit"] == "commit_A"
        mock_jules.get_session_state.assert_called_with("sessions/123")
