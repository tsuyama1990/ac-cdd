from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ac_cdd_core.enums import FlowStatus
from ac_cdd_core.services.coder_usecase import CoderUseCase
from ac_cdd_core.services.jules_client import JulesSessionError
from ac_cdd_core.state import CycleState


class TestSessionRestart:
    """Test session restart logic on failure."""

    @pytest.fixture
    def mock_jules(self) -> MagicMock:
        jules = MagicMock()
        jules.run_session = AsyncMock()
        jules.wait_for_completion = AsyncMock()
        return jules

    @pytest.fixture
    def mock_manifest(self) -> MagicMock:
        manifest = MagicMock()
        manifest.jules_session_id = None
        manifest.session_restart_count = 0
        manifest.max_session_restarts = 2
        return manifest

    @pytest.mark.asyncio
    async def test_session_restart_on_failure(
        self, mock_jules: MagicMock, mock_manifest: MagicMock
    ) -> None:
        """Should restart session when Jules fails, up to max_session_restarts."""
        state = CycleState(cycle_id="01", iteration_count=1)
        call_count = 0

        def run_session_side_effect(*args, **kwargs):  # type: ignore[no-untyped-def]
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"session_name": "sessions/fail_123", "status": "running"}
            return {"session_name": "sessions/success_456", "status": "running"}

        def wait_for_completion_side_effect(session_id):  # type: ignore[no-untyped-def]
            if "fail" in session_id:
                raise JulesSessionError("Jules Session Failed: Unknown error")
            return {"status": "success", "pr_url": "https://github.com/pr/1"}

        mock_jules.run_session.side_effect = run_session_side_effect
        mock_jules.wait_for_completion.side_effect = wait_for_completion_side_effect

        usecase = CoderUseCase(mock_jules)
        update_calls = []

        def track_updates(cycle_id, **kwargs):  # type: ignore[no-untyped-def]
            update_calls.append(kwargs)
            if "session_restart_count" in kwargs:
                mock_manifest.session_restart_count = kwargs["session_restart_count"]
            if "jules_session_id" in kwargs:
                mock_manifest.jules_session_id = kwargs["jules_session_id"]

        with patch("ac_cdd_core.services.coder_usecase.StateManager") as MockManager:
            instance = MockManager.return_value
            instance.get_cycle.return_value = mock_manifest
            instance.update_cycle_state.side_effect = track_updates

            with patch("ac_cdd_core.services.coder_usecase.settings") as mock_settings:
                mock_settings.get_template.return_value.read_text.return_value = "Instruction"
                mock_settings.get_target_files.return_value = []
                mock_settings.get_context_files.return_value = []
                result = await usecase.execute(state)

        assert result["status"] == FlowStatus.CODER_RETRY

        with patch("ac_cdd_core.services.coder_usecase.StateManager") as MockManager2:
            instance2 = MockManager2.return_value
            instance2.get_cycle.return_value = mock_manifest

            with patch("ac_cdd_core.services.coder_usecase.settings") as mock_settings2:
                mock_settings2.get_template.return_value.read_text.return_value = "Instruction"
                mock_settings2.get_target_files.return_value = []
                mock_settings2.get_context_files.return_value = []
                result2 = await usecase.execute(state)

        assert result2["status"] == FlowStatus.READY_FOR_AUDIT
        assert result2["pr_url"] == "https://github.com/pr/1"
        assert mock_jules.run_session.call_count == 2
        assert any(
            "session_restart_count" in call and call["session_restart_count"] == 1
            for call in update_calls
        )

    @pytest.mark.asyncio
    async def test_session_restart_max_limit(
        self, mock_jules: MagicMock, mock_manifest: MagicMock
    ) -> None:
        """Should fail after max_session_restarts attempts."""
        state = CycleState(cycle_id="01", iteration_count=1)

        mock_jules.run_session.return_value = {
            "session_name": "sessions/fail_123",
            "status": "running",
        }
        mock_jules.wait_for_completion.side_effect = JulesSessionError(
            "Jules Session Failed: Unknown error"
        )

        usecase = CoderUseCase(mock_jules)

        async def run_once() -> dict:
            with patch("ac_cdd_core.services.coder_usecase.StateManager") as MockManager:
                instance = MockManager.return_value
                instance.get_cycle.return_value = mock_manifest

                def track_updates(cycle_id, **kwargs):  # type: ignore[no-untyped-def]
                    if "session_restart_count" in kwargs:
                        mock_manifest.session_restart_count = kwargs["session_restart_count"]

                instance.update_cycle_state.side_effect = track_updates

                with patch("ac_cdd_core.services.coder_usecase.settings") as mock_settings:
                    mock_settings.get_template.return_value.read_text.return_value = "Instruction"
                    mock_settings.get_target_files.return_value = []
                    mock_settings.get_context_files.return_value = []
                    return await usecase.execute(state)

        result1 = await run_once()
        assert result1["status"] == FlowStatus.CODER_RETRY

        result2 = await run_once()
        assert result2["status"] == FlowStatus.CODER_RETRY

        result3 = await run_once()
        assert result3["status"] == FlowStatus.FAILED
        assert "Unknown error" in result3["error"]
        assert mock_jules.run_session.call_count == 3
