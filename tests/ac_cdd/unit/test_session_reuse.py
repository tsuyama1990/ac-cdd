
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ac_cdd_core.graph_nodes import CycleNodes
from ac_cdd_core.sandbox import SandboxRunner
from ac_cdd_core.services.jules_client import JulesClient


class TestSessionReuse:
    """Validate session reuse and fallback logic."""

    @pytest.fixture
    def mock_nodes(self):
        sandbox = MagicMock(spec=SandboxRunner)
        jules = MagicMock(spec=JulesClient)
        jules.run_session = AsyncMock()
        jules.wait_for_completion = AsyncMock()

        with patch("ac_cdd_core.graph_nodes.GitManager"), \
             patch("ac_cdd_core.graph_nodes.settings") as mock_settings:
            # Mock settings file access
            mock_settings.get_template.return_value.read_text.return_value = "Instruction"
            mock_settings.get_target_files.return_value = []
            mock_settings.get_context_files.return_value = []

            nodes = CycleNodes(sandbox, jules)
            nodes.git = AsyncMock()
            # Mock _send_audit_feedback_to_session to track calls
            nodes._send_audit_feedback_to_session = AsyncMock(return_value={"status": "ready_for_audit"})
            yield nodes

    @pytest.mark.asyncio
    async def test_reuse_completed_session_for_auditor_reject(self, mock_nodes):
        """Should REUSE COMPLETED session for Auditor Reject (send feedback to same session)."""
        # Setup state with audit rejection
        state = {
            "status": "retry_fix",
            "audit_result": MagicMock(feedback="Fix this issue"),
            "cycle_id": "01",
            "current_phase": "refactoring"
        }

        # Mock JulesClient.get_session_state to return COMPLETED
        mock_nodes.jules.get_session_state = AsyncMock(return_value="COMPLETED")

        # Mock StateManager to return a cycle with a session ID
        mock_manifest = MagicMock()
        mock_manifest.jules_session_id = "sessions/123"

        with patch("ac_cdd_core.graph_nodes.StateManager") as MockManager:
             instance = MockManager.return_value
             instance.get_cycle.return_value = mock_manifest

             result = await mock_nodes.coder_session_node(state)

        # Verification
        # 1. Should have checked session state
        mock_nodes.jules.get_session_state.assert_called_with("sessions/123")

        # 2. Should REUSE the COMPLETED session (send feedback to it)
        mock_nodes._send_audit_feedback_to_session.assert_called_once_with(
            "sessions/123", "Fix this issue"
        )

        # 3. Should NOT create a new session
        mock_nodes.jules.run_session.assert_not_called()

        # 4. Should return success
        assert result["status"] == "ready_for_audit"

    @pytest.mark.asyncio
    async def test_create_new_session_if_failed(self, mock_nodes):
        """Should create NEW session if previous session FAILED."""
        # Setup state with audit rejection
        state = {
            "status": "retry_fix",
            "audit_result": MagicMock(feedback="Fix this issue"),
            "cycle_id": "01",
            "current_phase": "refactoring"
        }

        # Mock JulesClient.get_session_state to return FAILED
        mock_nodes.jules.get_session_state = AsyncMock(return_value="FAILED")

        # Mock StateManager
        mock_manifest = MagicMock()
        mock_manifest.jules_session_id = "sessions/123"
        mock_manifest.pr_url = "https://pr"

        # Mock run_session to create new session
        mock_nodes.jules.run_session.return_value = {
            "session_name": "sessions/new_456",
            "status": "running"
        }
        mock_nodes.jules.wait_for_completion.return_value = {"status": "success"}

        with patch("ac_cdd_core.graph_nodes.StateManager") as MockManager:
             instance = MockManager.return_value
             instance.get_cycle.return_value = mock_manifest

             await mock_nodes.coder_session_node(state)

        # Verification
        # 1. Should have checked session state
        mock_nodes.jules.get_session_state.assert_called_with("sessions/123")

        # 2. Should NOT try to reuse FAILED session
        mock_nodes._send_audit_feedback_to_session.assert_not_called()

        # 3. Should create a new session
        mock_nodes.jules.run_session.assert_called()

        # 4. Feedback should be injected into new session prompt
        call_args = mock_nodes.jules.run_session.call_args
        prompt = call_args.kwargs["prompt"]
        assert "Fix this issue" in prompt
        assert "PREVIOUS AUDIT FEEDBACK" in prompt

    @pytest.mark.asyncio
    async def test_reuse_in_progress_session(self, mock_nodes):
        """Should REUSE IN_PROGRESS session (original behavior)."""
        state = {
            "status": "retry_fix",
            "audit_result": MagicMock(feedback="Fix this"),
            "cycle_id": "01",
            "current_phase": "refactoring"
        }

        # Mock JulesClient.get_session_state to return IN_PROGRESS
        mock_nodes.jules.get_session_state = AsyncMock(return_value="IN_PROGRESS")

        mock_manifest = MagicMock()
        mock_manifest.jules_session_id = "sessions/123"

        with patch("ac_cdd_core.graph_nodes.StateManager") as MockManager:
             instance = MockManager.return_value
             instance.get_cycle.return_value = mock_manifest

             result = await mock_nodes.coder_session_node(state)

        # Should reuse IN_PROGRESS session
        mock_nodes._send_audit_feedback_to_session.assert_called_once_with(
            "sessions/123", "Fix this"
        )
        mock_nodes.jules.run_session.assert_not_called()
        assert result["status"] == "ready_for_audit"
