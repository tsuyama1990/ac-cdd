from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ac_cdd_core.domain_models import CycleManifest
from ac_cdd_core.enums import FlowStatus
from ac_cdd_core.services.coder_usecase import CoderUseCase
from ac_cdd_core.state import CycleState


@pytest.mark.asyncio
class TestResumeLogic:
    @pytest.fixture
    def mock_jules(self) -> MagicMock:
        jules = MagicMock()
        jules.wait_for_completion = AsyncMock()
        jules.run_session = AsyncMock()
        return jules

    @patch("ac_cdd_core.services.coder_usecase.StateManager")
    async def test_hot_resume_active(self, mock_sm_cls: MagicMock, mock_jules: MagicMock) -> None:
        """Test that CoderUseCase resumes if session ID exists in manifest."""
        mock_mgr = mock_sm_cls.return_value
        cycle = CycleManifest(id="01", jules_session_id="jules-existing-123")
        mock_mgr.get_cycle = MagicMock(return_value=cycle)

        mock_jules.wait_for_completion.return_value = {"status": "success", "pr_url": "http://pr"}

        usecase = CoderUseCase(mock_jules)
        state = CycleState(cycle_id="01", iteration_count=1, resume_mode=True)

        with patch("ac_cdd_core.services.coder_usecase.settings") as mock_settings:
            mock_settings.get_template.return_value.read_text.return_value = "Instruction"
            mock_settings.get_target_files.return_value = []
            mock_settings.get_context_files.return_value = []
            result = await usecase.execute(state)

        mock_jules.wait_for_completion.assert_awaited_once_with("jules-existing-123")
        mock_jules.run_session.assert_not_awaited()
        assert result["status"] == FlowStatus.READY_FOR_AUDIT
        assert result["pr_url"] == "http://pr"

    @patch("ac_cdd_core.services.coder_usecase.StateManager")
    async def test_fallback_to_new_session_and_persist(
        self, mock_sm_cls: MagicMock, mock_jules: MagicMock
    ) -> None:
        """Test that if no session exists, a new one is started and immediately persisted."""
        mock_mgr = mock_sm_cls.return_value
        cycle = CycleManifest(id="01", jules_session_id=None)
        mock_mgr.get_cycle = MagicMock(return_value=cycle)
        mock_mgr.update_cycle_state = MagicMock()

        mock_jules.run_session.return_value = {
            "session_name": "jules-new-456",
            "status": "success",
            "pr_url": "http://pr-new",
        }

        usecase = CoderUseCase(mock_jules)
        state = CycleState(cycle_id="01", iteration_count=1, resume_mode=True)

        with patch("ac_cdd_core.services.coder_usecase.settings") as mock_settings:
            mock_settings.get_template.return_value.read_text.return_value = "Instruction"
            mock_settings.get_target_files.return_value = []
            mock_settings.get_context_files.return_value = []
            result = await usecase.execute(state)

        mock_jules.run_session.assert_awaited_once()
        assert mock_jules.run_session.await_args.kwargs["require_plan_approval"] is False

        assert any(
            call.args == ("01",)
            and call.kwargs.get("jules_session_id") == "jules-new-456"
            and call.kwargs.get("status") == "in_progress"
            for call in mock_mgr.update_cycle_state.call_args_list
        ), (
            f"Expected update_cycle_state call with session_id not found. Calls: {mock_mgr.update_cycle_state.call_args_list}"
        )

        assert result["status"] == FlowStatus.READY_FOR_AUDIT
