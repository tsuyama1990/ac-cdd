"""Tests for SessionManager class."""
from unittest.mock import MagicMock, patch

import pytest
from ac_cdd_core.session_manager import SessionManager


@pytest.fixture
def temp_session_file(tmp_path):
    """Create a temporary session file path."""
    session_file = tmp_path / ".ac_cdd_session.json"
    # Temporarily override the SESSION_FILE constant
    original_file = SessionManager.SESSION_FILE
    SessionManager.SESSION_FILE = session_file
    yield session_file
    SessionManager.SESSION_FILE = original_file


def test_save_and_load_session(temp_session_file):
    """Test saving and loading session data."""
    session_id = "session-20251230-120000"
    integration_branch = "dev/session-20251230-120000"
    
    # Save session
    SessionManager.save_session(session_id, integration_branch)
    
    # Verify file exists
    assert temp_session_file.exists()
    
    # Load session
    loaded = SessionManager.load_session()
    assert loaded is not None
    assert loaded["session_id"] == session_id
    assert loaded["integration_branch"] == integration_branch


def test_load_session_file_not_found(temp_session_file):
    """Test loading session when file doesn't exist."""
    result = SessionManager.load_session()
    assert result is None


def test_clear_session(temp_session_file):
    """Test clearing session file."""
    # Create a session first
    SessionManager.save_session("test-session", "dev/test")
    assert temp_session_file.exists()
    
    # Clear it
    SessionManager.clear_session()
    assert not temp_session_file.exists()


def test_validate_session_success():
    """Test session validation with valid state."""
    session_id = "session-20251230-120000"
    integration_branch = "dev/session-20251230-120000"
    
    with patch("subprocess.run") as mock_run:
        # Mock git branch --list to return the integration branch
        mock_run.return_value = MagicMock(
            stdout=integration_branch,
            returncode=0
        )
        
        is_valid, error = SessionManager.validate_session(session_id, integration_branch)
        assert is_valid
        assert error is None


def test_validate_session_branch_mismatch():
    """Test session validation when branch doesn't exist."""
    session_id = "session-20251230-120000"
    integration_branch = "dev/session-20251230-120000"
    
    with patch("subprocess.run") as mock_run:
        # Mock git branch --list to return empty (branch doesn't exist)
        mock_run.return_value = MagicMock(
            stdout="",
            returncode=0
        )
        
        is_valid, error = SessionManager.validate_session(session_id, integration_branch)
        assert not is_valid
        assert "does not exist" in error


def test_reconcile_session_from_git():
    """Test reconciling session from Git branches."""
    with patch("subprocess.run") as mock_run:
        # Mock git branch --list to return integration branches
        mock_run.return_value = MagicMock(
            stdout="  dev/session-20251230-120000\n  dev/session-20251230-120001\n",
            returncode=0
        )
        
        result = SessionManager.reconcile_session()
        assert result is not None
        assert "session_id" in result
        assert "integration_branch" in result
        assert result["integration_branch"].startswith("dev/session-")


def test_reconcile_session_no_branches():
    """Test reconciling session when no integration branches exist."""
    with patch("subprocess.run") as mock_run:
        # Mock git branch --list to return empty
        mock_run.return_value = MagicMock(
            stdout="",
            returncode=0
        )
        
        result = SessionManager.reconcile_session()
        assert result is None


def test_get_integration_branch_format():
    """Test integration branch name format."""
    session_id = "session-20251230-120000"
    branch = SessionManager.get_integration_branch(session_id)
    assert branch == "dev/session-20251230-120000"


def test_load_or_reconcile_with_explicit_id(temp_session_file):
    """Test loading session with explicit session ID."""
    session_id = "session-explicit"
    
    with patch.object(SessionManager, "validate_session", return_value=(True, None)):
        result = SessionManager.load_or_reconcile_session(session_id=session_id)
        assert result["session_id"] == session_id


def test_load_or_reconcile_from_file(temp_session_file):
    """Test loading session from file when no explicit ID provided."""
    # Save a session first
    SessionManager.save_session("session-from-file", "dev/session-from-file")
    
    with patch.object(SessionManager, "validate_session", return_value=(True, None)):
        result = SessionManager.load_or_reconcile_session()
        assert result["session_id"] == "session-from-file"
