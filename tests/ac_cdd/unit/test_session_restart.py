from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ac_cdd_core.graph_nodes import CycleNodes
from ac_cdd_core.sandbox import SandboxRunner
from ac_cdd_core.services.jules_client import JulesClient, JulesSessionError


class TestSessionRestart:
    """Test session restart logic on failure."""

    @pytest.fixture
    def mock_nodes(self):  # type: ignore[no-untyped-def]
        sandbox = MagicMock(spec=SandboxRunner)
        jules = MagicMock(spec=JulesClient)
        jules.run_session = AsyncMock()
        jules.wait_for_completion = AsyncMock()

        with (
            patch("ac_cdd_core.graph_nodes.GitManager"),
            patch("ac_cdd_core.graph_nodes.settings") as mock_settings,
        ):
            mock_settings.get_template.return_value.read_text.return_value = "Instruction"
            mock_settings.get_target_files.return_value = []
            mock_settings.get_context_files.return_value = []

            nodes = CycleNodes(sandbox, jules)
            nodes.git = AsyncMock()
            yield nodes

    @pytest.mark.asyncio
    async def test_session_restart_on_failure(self, mock_nodes) -> None:  # type: ignore[no-untyped-def]
        """Should restart session when Jules fails, up to max_session_restarts."""
        # Setup state
        state = {
            "cycle_id": "01",
            "iteration_count": 1,
            "current_phase": "coder",
            "status": "start",
        }

        # Mock StateManager
        mock_manifest = MagicMock()
        mock_manifest.jules_session_id = None
        mock_manifest.session_restart_count = 0
        mock_manifest.max_session_restarts = 2

        # First attempt fails, second succeeds
        call_count = 0

        def run_session_side_effect(*args, **kwargs):  # type: ignore[no-untyped-def]
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First attempt - return session that will fail
                return {"session_name": "sessions/fail_123", "status": "running"}
            # Second attempt - return session that will succeed
            return {"session_name": "sessions/success_456", "status": "running"}

        def wait_for_completion_side_effect(session_id):  # type: ignore[no-untyped-def]
            if "fail" in session_id:
                msg = "Jules Session Failed: Unknown error"
                raise JulesSessionError(msg)
            return {"status": "success", "pr_url": "https://github.com/pr/1"}

        mock_nodes.jules.run_session.side_effect = run_session_side_effect
        mock_nodes.jules.wait_for_completion.side_effect = wait_for_completion_side_effect

        with patch("ac_cdd_core.graph_nodes.StateManager") as MockManager:
            instance = MockManager.return_value

            # Track updates to manifest
            update_calls = []

            def track_updates(cycle_id, **kwargs):  # type: ignore[no-untyped-def]
                update_calls.append(kwargs)
                # Update mock manifest based on calls
                if "session_restart_count" in kwargs:
                    mock_manifest.session_restart_count = kwargs["session_restart_count"]
                if "jules_session_id" in kwargs:
                    mock_manifest.jules_session_id = kwargs["jules_session_id"]

            instance.get_cycle.return_value = mock_manifest
            instance.update_cycle_state.side_effect = track_updates

            result = await mock_nodes.coder_session_node(state)

        # With the new Graph loop design, the node returns 'coder_retry', 
        # then the graph routes back to 'coder_session_node' with updated state.
        assert result["status"] == "coder_retry"

        # Now simulate the retry graph edge by calling it again
        result2 = await mock_nodes.coder_session_node(state)
        
        # This time wait_for_completion succeeds
        assert result2["status"] == "ready_for_audit"
        assert result2["pr_url"] == "https://github.com/pr/1"

        # Verify run_session was called twice (initial + 1 restart)
        assert mock_nodes.jules.run_session.call_count == 2

        # Verify restart counter was incremented
        assert any(
            "session_restart_count" in call and call["session_restart_count"] == 1
            for call in update_calls
        )

    @pytest.mark.asyncio
    async def test_session_restart_max_limit(self, mock_nodes) -> None:  # type: ignore[no-untyped-def]
        """Should fail after max_session_restarts attempts."""
        state = {
            "cycle_id": "01",
            "iteration_count": 1,
            "current_phase": "coder",
            "status": "start",
        }

        mock_manifest = MagicMock()
        mock_manifest.jules_session_id = None
        mock_manifest.session_restart_count = 0
        mock_manifest.max_session_restarts = 2

        # All attempts fail
        mock_nodes.jules.run_session.return_value = {
            "session_name": "sessions/fail_123",
            "status": "running",
        }
        msg = "Jules Session Failed: Unknown error"
        mock_nodes.jules.wait_for_completion.side_effect = JulesSessionError(msg)

        with patch("ac_cdd_core.graph_nodes.StateManager") as MockManager:
            instance = MockManager.return_value

            def track_updates(cycle_id, **kwargs):  # type: ignore[no-untyped-def]
                if "session_restart_count" in kwargs:
                    mock_manifest.session_restart_count = kwargs["session_restart_count"]

            instance.get_cycle.return_value = mock_manifest
            instance.update_cycle_state.side_effect = track_updates

            # First call (failure) -> Returns coder_retry
            result1 = await mock_nodes.coder_session_node(state)
            assert result1["status"] == "coder_retry"
            
            # Second call (failure) -> Returns coder_retry 
            # (session_restart_count is now 1)
            result2 = await mock_nodes.coder_session_node(state)
            assert result2["status"] == "coder_retry"

            # Third call (failure) -> Hits max limit -> Returns failed
            result3 = await mock_nodes.coder_session_node(state)

        # Should fail after 3 total attempts (initial + 2 restarts)
        assert result3["status"] == "failed"
        assert "Unknown error" in result3["error"]

        # Verify run_session was called 3 times
        assert mock_nodes.jules.run_session.call_count == 3
