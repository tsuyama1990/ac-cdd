import json
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ac_cdd_core.domain_models import CycleManifest, ProjectManifest
from ac_cdd_core.graph_nodes import CycleNodes
from ac_cdd_core.session_manager import SessionManager
from ac_cdd_core.state import CycleState

@pytest.fixture
def mock_jules_client():
    client = MagicMock()
    client.wait_for_completion = AsyncMock(return_value={"status": "success", "pr_url": "http://pr"})
    client.run_session = AsyncMock(return_value={"status": "running", "session_name": "new-session"})
    return client

@pytest.fixture
def mock_sandbox():
    return MagicMock()

@pytest.fixture
def cycle_nodes(mock_sandbox, mock_jules_client):
    return CycleNodes(mock_sandbox, mock_jules_client)

@pytest.mark.asyncio
async def test_resume_logic_hot_resume(cycle_nodes, mock_jules_client, tmp_path):
    # Setup Manifest with existing Jules Session ID
    with patch("ac_cdd_core.session_manager.SessionManager.MANIFEST_PATH", tmp_path / "project_state.json"):
        mgr = SessionManager()
        manifest = mgr.create_manifest("sess-1", "branch-1")
        manifest.cycles.append(CycleManifest(id="01", status="in_progress", jules_session_id="existing-jules-id"))
        mgr.save_manifest(manifest)

        state = CycleState(cycle_id="01", resume_mode=True)

        result = await cycle_nodes.coder_session_node(state)

        # Should call wait_for_completion, NOT run_session
        mock_jules_client.wait_for_completion.assert_awaited_once_with("existing-jules-id")
        mock_jules_client.run_session.assert_not_awaited()

        assert result["status"] == "ready_for_audit"

@pytest.mark.asyncio
async def test_resume_logic_cold_start_persists_id(cycle_nodes, mock_jules_client, tmp_path):
    # Setup Manifest WITHOUT existing Jules Session ID
    with patch("ac_cdd_core.session_manager.SessionManager.MANIFEST_PATH", tmp_path / "project_state.json"):
        mgr = SessionManager()
        manifest = mgr.create_manifest("sess-1", "branch-1")
        manifest.cycles.append(CycleManifest(id="01", status="planned"))
        mgr.save_manifest(manifest)

        state = CycleState(cycle_id="01", resume_mode=True)

        # Mock run_session to return a new ID
        mock_jules_client.run_session.return_value = {
            "status": "success",
            "session_name": "newly-created-id",
            "pr_url": "http://pr"
        }

        result = await cycle_nodes.coder_session_node(state)

        # Should call run_session
        mock_jules_client.run_session.assert_awaited_once()

        # Verify Persistence
        loaded = mgr.load_manifest()
        cycle = loaded.cycles[0]
        assert cycle.jules_session_id == "newly-created-id"
        assert cycle.status == "in_progress"
