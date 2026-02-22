from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ac_cdd_core.domain_models import AuditResult
from ac_cdd_core.enums import FlowStatus
from ac_cdd_core.services.coder_usecase import CoderUseCase
from ac_cdd_core.state import CycleState


class TestSessionReuse:
    """Validate session reuse and fallback logic."""

    @pytest.fixture
    def mock_jules(self) -> MagicMock:
        jules = MagicMock()
        jules.run_session = AsyncMock()
        jules.wait_for_completion = AsyncMock()
        jules.get_session_state = AsyncMock()
        jules._send_message = AsyncMock()
        jules._get_session_url = MagicMock(return_value="https://jules/session/url")
        return jules

    @pytest.mark.asyncio
    async def test_reuse_completed_session_for_auditor_reject(self, mock_jules: MagicMock) -> None:
        """Should REUSE COMPLETED session for Auditor Reject (send feedback to same session)."""
        mock_jules.get_session_state.return_value = "COMPLETED"
        mock_jules.wait_for_completion.return_value = {"status": "success", "pr_url": "http://pr"}

        mock_manifest = MagicMock()
        mock_manifest.jules_session_id = "sessions/123"
        mock_manifest.pr_url = None

        audit = AuditResult(
            status="REJECTED", is_approved=False, reason="Needs work", feedback="Fix this issue"
        )
        state = CycleState(
            cycle_id="01",
            status=FlowStatus.RETRY_FIX,
            audit_result=audit,
        )

        usecase = CoderUseCase(mock_jules)

        with patch("ac_cdd_core.services.coder_usecase.StateManager") as MockManager:
            instance = MockManager.return_value
            instance.get_cycle.return_value = mock_manifest

            with patch("ac_cdd_core.services.coder_usecase.settings") as mock_settings:
                mock_settings.get_template.return_value.read_text.return_value = "Instruction"
                mock_settings.get_target_files.return_value = []
                mock_settings.get_context_files.return_value = []
                result = await usecase.execute(state)

        mock_jules.get_session_state.assert_called_with("sessions/123")
        mock_jules._send_message.assert_called_once()  # Feedback was sent to existing session
        
        # Verify the actual feedback content sent
        sent_message = mock_jules._send_message.call_args.args[1] if mock_jules._send_message.call_args.args else mock_jules._send_message.call_args.kwargs.get("message", "")
        assert "Fix this issue" in sent_message
        
        mock_jules.run_session.assert_not_called()
        assert result["status"] == FlowStatus.READY_FOR_AUDIT

    @pytest.mark.asyncio
    async def test_create_new_session_if_failed(self, mock_jules: MagicMock) -> None:
        """Should create NEW session if previous session FAILED."""
        mock_jules.get_session_state.return_value = "FAILED"
        mock_jules.run_session.return_value = {
            "session_name": "sessions/new_456",
            "status": "success",
            "pr_url": "http://pr-new",
        }

        mock_manifest = MagicMock()
        mock_manifest.jules_session_id = "sessions/123"
        mock_manifest.pr_url = "https://pr"

        audit = AuditResult(
            status="REJECTED", is_approved=False, reason="Needs work", feedback="Fix this issue"
        )
        state = CycleState(
            cycle_id="01",
            status=FlowStatus.RETRY_FIX,
            audit_result=audit,
        )

        usecase = CoderUseCase(mock_jules)

        with patch("ac_cdd_core.services.coder_usecase.StateManager") as MockManager:
            instance = MockManager.return_value
            instance.get_cycle.return_value = mock_manifest

            with patch("ac_cdd_core.services.coder_usecase.settings") as mock_settings:

                def mock_get_template(name: str) -> MagicMock:
                    m = MagicMock()
                    if name == "AUDIT_FEEDBACK_INJECTION.md":
                        m.read_text.return_value = "# PREVIOUS AUDIT FEEDBACK (MUST FIX)\n\n{{feedback}}\n\n{{#pr_url}}\nPrevious PR: {{pr_url}}\n{{/pr_url}}"
                    else:
                        m.read_text.return_value = "Instruction"
                    return m

                mock_settings.get_template.side_effect = mock_get_template
                mock_settings.get_target_files.return_value = []
                mock_settings.get_context_files.return_value = []
                await usecase.execute(state)

        mock_jules.get_session_state.assert_called_with("sessions/123")
        mock_jules._send_message.assert_not_called()  # Should NOT reuse FAILED session
        mock_jules.run_session.assert_called()

        prompt = mock_jules.run_session.call_args.kwargs["prompt"]
        assert "Fix this issue" in prompt
        assert "PREVIOUS AUDIT FEEDBACK" in prompt

    @pytest.mark.asyncio
    async def test_reuse_in_progress_session(self, mock_jules: MagicMock) -> None:
        """Should REUSE IN_PROGRESS session (original behavior)."""
        mock_jules.get_session_state.return_value = "IN_PROGRESS"
        mock_jules.wait_for_completion.return_value = {"status": "success", "pr_url": "http://pr"}

        mock_manifest = MagicMock()
        mock_manifest.jules_session_id = "sessions/123"
        mock_manifest.pr_url = None

        audit = AuditResult(
            status="REJECTED", is_approved=False, reason="Needs work", feedback="Fix this"
        )
        state = CycleState(
            cycle_id="01",
            status=FlowStatus.RETRY_FIX,
            audit_result=audit,
        )

        usecase = CoderUseCase(mock_jules)

        with patch("ac_cdd_core.services.coder_usecase.StateManager") as MockManager:
            instance = MockManager.return_value
            instance.get_cycle.return_value = mock_manifest

            with patch("ac_cdd_core.services.coder_usecase.settings") as mock_settings:
                mock_settings.get_template.return_value.read_text.return_value = "Instruction"
                mock_settings.get_target_files.return_value = []
                mock_settings.get_context_files.return_value = []
                result = await usecase.execute(state)

        mock_jules._send_message.assert_called_once()  # Feedback was sent
        
        # Verify the actual feedback content sent
        sent_message = mock_jules._send_message.call_args.args[1] if mock_jules._send_message.call_args.args else mock_jules._send_message.call_args.kwargs.get("message", "")
        assert "Fix this" in sent_message
        
        mock_jules.run_session.assert_not_called()
        assert result["status"] == FlowStatus.READY_FOR_AUDIT
