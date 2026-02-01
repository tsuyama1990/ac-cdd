from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ac_cdd_core.domain_models import CycleManifest
from ac_cdd_core.graph_nodes import CycleNodes


@pytest.mark.asyncio
class TestResumeLogic:
    @pytest.fixture
    def mock_dependencies(self) -> tuple[MagicMock, MagicMock]:
        sandbox = MagicMock()
        jules = MagicMock()
        jules.wait_for_completion = AsyncMock()
        jules.run_session = AsyncMock()
        return sandbox, jules

    @patch("ac_cdd_core.graph_nodes.StateManager")
    async def test_hot_resume_active(
        self, mock_sm_cls: MagicMock, mock_dependencies: tuple[MagicMock, MagicMock]
    ) -> None:
        """Test that coder_session_node resumes if session ID exists in manifest."""
        sandbox, jules = mock_dependencies
        nodes = CycleNodes(sandbox, jules)

        # Setup Manifest with existing Jules Session
        mock_mgr = mock_sm_cls.return_value
        cycle = CycleManifest(id="01", jules_session_id="jules-existing-123")
        mock_mgr.get_cycle = MagicMock(return_value=cycle)

        # Setup Jules Client to return success on wait
        jules.wait_for_completion.return_value = {"status": "success", "pr_url": "http://pr"}

        state = {"cycle_id": "01", "iteration_count": 1, "resume_mode": True}

        # Execute
        result = await nodes.coder_session_node(state)

        # Assertions
        jules.wait_for_completion.assert_awaited_once_with("jules-existing-123")
        jules.run_session.assert_not_awaited()  # Should NOT start new session
        assert result["status"] == "ready_for_audit"
        assert result["pr_url"] == "http://pr"

    @patch("ac_cdd_core.graph_nodes.StateManager")
    async def test_fallback_to_new_session_and_persist(
        self, mock_sm_cls: MagicMock, mock_dependencies: tuple[MagicMock, MagicMock]
    ) -> None:
        """Test that if no session exists, a new one is started and immediately persisted."""
        sandbox, jules = mock_dependencies
        nodes = CycleNodes(sandbox, jules)

        # Setup Manifest with NO existing session
        mock_mgr = mock_sm_cls.return_value
        cycle = CycleManifest(id="01", jules_session_id=None)
        mock_mgr.get_cycle = MagicMock(return_value=cycle)
        mock_mgr.update_cycle_state = MagicMock()

        # Setup Jules to return a new session
        jules.run_session.return_value = {
            "session_name": "jules-new-456",
            "status": "success",
            "pr_url": "http://pr-new",
        }

        state = {"cycle_id": "01", "iteration_count": 1, "resume_mode": True}

        # Execute
        result = await nodes.coder_session_node(state)

        # Assertions
        jules.run_session.assert_awaited_once()
        assert jules.run_session.await_args.kwargs["require_plan_approval"] is False

        # Verify Immediate Persistence (session ID was saved)
        # Note: There may be multiple calls (e.g., to reset session_restart_count)
        assert any(
            call.args == ("01",)
            and call.kwargs.get("jules_session_id") == "jules-new-456"
            and call.kwargs.get("status") == "in_progress"
            for call in mock_mgr.update_cycle_state.call_args_list
        ), (
            f"Expected update_cycle_state call with session_id not found. Calls: {mock_mgr.update_cycle_state.call_args_list}"
        )

        assert result["status"] == "ready_for_audit"
