from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ac_cdd_core.domain_models import CycleManifest
from ac_cdd_core.graph_nodes import CycleNodes


@pytest.fixture
def cycle_nodes():
    return CycleNodes(MagicMock(), MagicMock())

@pytest.fixture
def mock_jules_client(cycle_nodes):
    return cycle_nodes.jules

@pytest.mark.asyncio
async def test_resume_logic_hot_resume(cycle_nodes, mock_jules_client):
    """Test hot resume functionality."""
    # Mock SessionManager
    with patch("ac_cdd_core.graph_nodes.SessionManager") as mock_sm_cls:
        mock_mgr = mock_sm_cls.return_value

        # Setup cycle with existing session ID
        cycle = CycleManifest(id="01", jules_session_id="existing-session")
        mock_mgr.get_cycle = AsyncMock(return_value=cycle)

        # Mock Jules Client
        mock_jules_client.wait_for_completion = AsyncMock(return_value={"status": "success", "pr_url": "http://pr"})

        state = {"cycle_id": "01", "iteration_count": 1, "resume_mode": True}
        result = await cycle_nodes.coder_session_node(state)

        # Verify
        mock_jules_client.wait_for_completion.assert_awaited_with("existing-session")
        assert result["status"] == "ready_for_audit"

@pytest.mark.asyncio
async def test_resume_logic_cold_start_persists_id(cycle_nodes, mock_jules_client):
    """Test cold start (no previous ID) persists new ID."""
    # Mock SessionManager
    with patch("ac_cdd_core.graph_nodes.SessionManager") as mock_sm_cls:
        mock_mgr = mock_sm_cls.return_value

        # Setup cycle WITHOUT session ID
        cycle = CycleManifest(id="01", jules_session_id=None)
        mock_mgr.get_cycle = AsyncMock(return_value=cycle)
        mock_mgr.update_cycle_state = AsyncMock()

        # Mock Jules Client
        mock_jules_client.run_session = AsyncMock(return_value={
            "session_name": "new-session", "status": "success", "pr_url": "http://pr"
        })

        state = {"cycle_id": "01", "iteration_count": 1, "resume_mode": True}
        await cycle_nodes.coder_session_node(state)

        # Verify
        mock_jules_client.run_session.assert_awaited()
        # Verify persistence
        mock_mgr.update_cycle_state.assert_awaited_with(
            "01", jules_session_id="new-session", status="in_progress"
        )
