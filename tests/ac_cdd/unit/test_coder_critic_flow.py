from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from ac_cdd_core.enums import FlowStatus
from ac_cdd_core.services.coder_usecase import CoderUseCase
from ac_cdd_core.state import CycleState
from ac_cdd_core.domain_models import CycleManifest

@pytest.mark.asyncio
class TestCoderCriticFlow:
    @pytest.fixture
    def mock_jules(self) -> MagicMock:
        jules = MagicMock()
        jules.wait_for_completion = AsyncMock(return_value={"status": "success", "pr_url": "http://pr"})
        jules.run_session = AsyncMock(return_value={"status": "success", "pr_url": "http://pr", "session_name": "sessions/123"})
        jules._get_session_url = MagicMock(return_value="http://session/url")
        jules._send_message = AsyncMock()
        return jules

    @pytest.fixture
    def mock_sm(self) -> MagicMock:
        with patch("ac_cdd_core.services.coder_usecase.StateManager") as mock:
            yield mock.return_value

    @pytest.fixture
    def mock_settings(self) -> MagicMock:
        with patch("ac_cdd_core.services.coder_usecase.settings") as mock:
            mock.get_template.return_value.read_text.return_value = "Instruction {{cycle_id}}"
            mock.get_target_files.return_value = []
            mock.get_context_files.return_value = []
            yield mock

    async def test_critic_called_on_initial_run(self, mock_jules, mock_sm, mock_settings):
        """Standard flow: iteration 0, new session -> should call critic."""
        mock_sm.get_cycle.return_value = None
        
        state = CycleState(cycle_id="cycle-1", iteration_count=0)
        usecase = CoderUseCase(mock_jules)
        
        # We need to mock _run_critic_phase to check if it's called
        with patch.object(CoderUseCase, "_run_critic_phase", wraps=usecase._run_critic_phase) as mock_critic:
            # Re-wrap since patch.object replaces the method. We want to see if it's called and let it run or mock it.
            # To be simple, let's just mock it.
            mock_critic.return_value = {"status": "success", "pr_url": "http://pr-critic"}
            
            result = await usecase.execute(state)
            
            mock_critic.assert_called_once()
            assert result["pr_url"] == "http://pr-critic"

    async def test_critic_called_on_resume_mode(self, mock_jules, mock_sm, mock_settings):
        """Phase 1 fix: resume_mode SHOULD call critic if it's the initial PR."""
        cycle = CycleManifest(id="cycle-1", jules_session_id="sessions/123")
        mock_sm.get_cycle.return_value = cycle
        
        state = CycleState(cycle_id="cycle-1", iteration_count=0, resume_mode=True)
        usecase = CoderUseCase(mock_jules)
        
        with patch.object(CoderUseCase, "_run_critic_phase", AsyncMock()) as mock_critic:
            mock_critic.return_value = {"status": "success", "pr_url": "http://pr-critic"}
            result = await usecase.execute(state)
            mock_critic.assert_called_once()
            assert result["pr_url"] == "http://pr-critic"

    async def test_critic_called_on_wait_mode(self, mock_jules, mock_sm, mock_settings):
        """Phase 1 fix: WAIT_FOR_JULES_COMPLETION SHOULD call critic if it's the initial PR."""
        cycle = CycleManifest(id="cycle-1", jules_session_id="sessions/123")
        mock_sm.get_cycle.return_value = cycle
        
        state = CycleState(cycle_id="cycle-1", iteration_count=0, status=FlowStatus.WAIT_FOR_JULES_COMPLETION)
        usecase = CoderUseCase(mock_jules)
        
        with patch.object(CoderUseCase, "_run_critic_phase", AsyncMock()) as mock_critic:
            mock_critic.return_value = {"status": "success", "pr_url": "http://pr-critic"}
            result = await usecase.execute(state)
            mock_critic.assert_called_once()
            assert result["pr_url"] == "http://pr-critic"

    async def test_critic_skipped_on_retry(self, mock_jules, mock_sm, mock_settings):
        """Standard behavior: iteration > 0 should skip critic."""
        mock_sm.get_cycle.return_value = None
        
        state = CycleState(cycle_id="cycle-1", iteration_count=1)
        usecase = CoderUseCase(mock_jules)
        
        with patch.object(CoderUseCase, "_run_critic_phase", AsyncMock()) as mock_critic:
            await usecase.execute(state)
            mock_critic.assert_not_called()
