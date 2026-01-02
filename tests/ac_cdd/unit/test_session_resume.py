import json
from unittest.mock import AsyncMock, patch

import pytest
from ac_cdd_core.session_manager import SessionManager, SessionValidationError


@pytest.fixture
def mock_session_file(tmp_path):
    session_file = tmp_path / ".ac_cdd_session.json"
    data = {
        "session_id": "session-123",
        "integration_branch": "dev/session-123/integration",
        "jules_session_id": "sessions/existing-id",
        "active_cycle_id": "01",
    }
    session_file.write_text(json.dumps(data), encoding="utf-8")
    return session_file


@pytest.fixture
def clean_session_manager(mock_session_file):
    # Patch the SESSSION_FILE constant or the method using it
    with patch("ac_cdd_core.session_manager.SessionManager.SESSION_FILE", mock_session_file):
        yield


@pytest.mark.asyncio
async def test_update_session_active_cycle(clean_session_manager, mock_session_file):
    """Test that active_cycle_id can be updated."""
    SessionManager.update_session(active_cycle_id="03")

    content = json.loads(mock_session_file.read_text())
    assert content["active_cycle_id"] == "03"
    assert content["session_id"] == "session-123"  # Unchanged
    assert content["jules_session_id"] == "sessions/existing-id"  # Unchanged


@pytest.mark.asyncio
async def test_resume_jules_session_auto_load(clean_session_manager):
    """Test resume_jules_session loads ID from file if argument is None."""

    mock_jules_instance = AsyncMock()
    mock_jules_instance.wait_for_completion.return_value = {
        "status": "success",
        "pr_url": "http://github.com/pr/1",
    }

    with patch("ac_cdd_core.services.jules_client.JulesClient", return_value=mock_jules_instance):
        result = await SessionManager.resume_jules_session(session_name=None)

        assert result["pr_url"] == "http://github.com/pr/1"
        assert result["jules_session_name"] == "sessions/existing-id"

        # Verify it called wait_for_completion with the LOADED id
        mock_jules_instance.wait_for_completion.assert_called_once_with("sessions/existing-id")


@pytest.mark.asyncio
async def test_resume_jules_session_no_id_found(tmp_path):
    """Test that resume raises error if no ID is found anywhere."""
    empty_file = tmp_path / ".no_session.json"

    with patch("ac_cdd_core.session_manager.SessionManager.SESSION_FILE", empty_file):
        with pytest.raises(SessionValidationError, match="No Jules Session ID provided or found"):
            await SessionManager.resume_jules_session(None)
