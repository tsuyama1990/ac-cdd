import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from ac_cdd_core.domain_models import CycleManifest, ProjectManifest
from ac_cdd_core.session_manager import SessionManager, SessionValidationError

# --- Tests for Domain Models ---

def test_cycle_manifest_serialization():
    manifest = CycleManifest(id="01", status="planned")
    json_str = manifest.model_dump_json()
    restored = CycleManifest.model_validate_json(json_str)
    assert restored.id == "01"
    assert restored.status == "planned"
    assert restored.current_iteration == 1

def test_project_manifest_serialization():
    cycle = CycleManifest(id="01")
    manifest = ProjectManifest(
        project_session_id="test-session",
        integration_branch="test-branch",
        cycles=[cycle]
    )
    json_str = manifest.model_dump_json()
    restored = ProjectManifest.model_validate_json(json_str)
    assert restored.project_session_id == "test-session"
    assert len(restored.cycles) == 1
    assert restored.cycles[0].id == "01"


# --- Tests for SessionManager ---

@pytest.fixture
def session_manager(tmp_path):
    # Mock MANIFEST_PATH to point to a temporary file
    with patch("ac_cdd_core.session_manager.SessionManager.MANIFEST_PATH", tmp_path / "project_state.json"):
        yield SessionManager()

def test_session_manager_init(session_manager):
    assert session_manager.MANIFEST_PATH.parent.exists()

def test_create_and_load_manifest(session_manager):
    manifest = session_manager.create_manifest("sess-1", "branch-1")
    loaded = session_manager.load_manifest()

    assert loaded is not None
    assert loaded.project_session_id == "sess-1"
    assert loaded.integration_branch == "branch-1"

def test_update_cycle_state(session_manager):
    # Setup initial state
    manifest = session_manager.create_manifest("sess-1", "branch-1")
    manifest.cycles.append(CycleManifest(id="01", status="planned"))
    session_manager.save_manifest(manifest)

    # Test update
    session_manager.update_cycle_state("01", status="in_progress", jules_session_id="jules-123")

    loaded = session_manager.load_manifest()
    cycle = loaded.cycles[0]
    assert cycle.status == "in_progress"
    assert cycle.jules_session_id == "jules-123"

def test_update_cycle_not_found(session_manager):
    session_manager.create_manifest("sess-1", "branch-1")
    with pytest.raises(SessionValidationError):
        session_manager.update_cycle_state("99", status="completed")

def test_git_commit_called_on_save(session_manager):
    with patch("subprocess.run") as mock_run:
        session_manager.create_manifest("sess-1", "branch-1")
        # create_manifest calls save_manifest with commit_msg
        assert mock_run.called
        # Verify git add and git commit calls
        calls = mock_run.call_args_list
        assert any("git" in str(c) and "add" in str(c) for c in calls)
        assert any("git" in str(c) and "commit" in str(c) for c in calls)
