"""Tests for SessionManager class."""

from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from ac_cdd_core.session_manager import SessionManager


@pytest.fixture
def temp_session_file(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary session file path."""
    session_file = tmp_path / ".ac_cdd_session.json"
    # Temporarily override the SESSION_FILE constant
    original_file = SessionManager.SESSION_FILE
    SessionManager.SESSION_FILE = session_file
    yield session_file
    SessionManager.SESSION_FILE = original_file


@pytest.mark.usefixtures("temp_session_file")
def test_save_and_load_session(temp_session_file: Path) -> None:
    """Test saving and loading session data."""
    project_session_id = "session-20251230-120000"
    integration_branch = "dev/session-20251230-120000/integration"

    # Save session
    SessionManager.save_session(project_session_id, integration_branch)

    # Verify file exists
    assert temp_session_file.exists()

    # Load session
    loaded = SessionManager.load_session()
    assert loaded is not None
    assert loaded["project_session_id"] == project_session_id
    assert loaded["integration_branch"] == integration_branch


@pytest.mark.usefixtures("temp_session_file")
def test_load_session_file_not_found() -> None:
    """Test loading session when file doesn't exist."""
    result = SessionManager.load_session()
    assert result is None


@pytest.mark.usefixtures("temp_session_file")
def test_clear_session(temp_session_file: Path) -> None:
    """Test clearing session file."""
    # Create a session first
    SessionManager.save_session("test-session", "dev/test")
    assert temp_session_file.exists()

    # Clear it
    SessionManager.clear_session()
    assert not temp_session_file.exists()


def test_validate_session_success() -> None:
    """Test session validation with valid state."""
    project_session_id = "session-20251230-120000"
    integration_branch = "dev/session-20251230-120000/integration"

    with patch("subprocess.run") as mock_run:
        # Mock git branch --list to return the integration branch
        mock_run.return_value = MagicMock(stdout=integration_branch, returncode=0)

        is_valid, error = SessionManager.validate_session(project_session_id, integration_branch)
        assert is_valid
        assert error is None


def test_validate_session_branch_mismatch() -> None:
    """Test session validation when branch doesn't exist."""
    project_session_id = "session-20251230-120000"
    integration_branch = "dev/session-20251230-120000/integration"

    with patch("subprocess.run") as mock_run:
        # Mock git branch --list to return empty (branch doesn't exist)
        mock_run.return_value = MagicMock(stdout="", returncode=1)

        is_valid, error = SessionManager.validate_session(project_session_id, integration_branch)
        assert not is_valid
        assert error and "not found locally" in error


def test_validate_session_fetch_remote_success() -> None:
    """Test session validation when local branch missing but remote exists."""
    project_session_id = "session-20251230-120000"
    integration_branch = "dev/session-20251230-120000/integration"

    with patch("subprocess.run") as mock_run:
        # Define side effects for sequential calls:
        # 1. git rev-parse (local check) -> Fail (1)
        # 2. git ls-remote (remote check) -> Success (0) with output
        # 3. git fetch -> Success (0)
        mock_run.side_effect = [
            MagicMock(returncode=1),  # local check fails
            MagicMock(stdout="refs/heads/" + integration_branch, returncode=0),  # remote exists
            MagicMock(returncode=0),  # fetch succeeds
        ]

        is_valid, error = SessionManager.validate_session(project_session_id, integration_branch)

        assert is_valid
        assert error is None

        # Verify fetch was called
        args = mock_run.call_args_list[2][0][0]
        assert "fetch" in args
        assert f"{integration_branch}:{integration_branch}" in args[3]


def test_reconcile_session_from_git() -> None:
    """Test reconciling session from Git branches."""
    with patch("subprocess.run") as mock_run:
        # Mock git branch --list to return integration branches
        mock_run.return_value = MagicMock(
            stdout=(
                "  dev/session-20251230-120000/integration\n"
                "  dev/session-20251230-120001/integration\n"
            ),
            returncode=0,
        )

        result = SessionManager.reconcile_session()
        assert result is not None
        assert result["project_session_id"] == "session-20251230-120001"
        assert result["integration_branch"] == "dev/session-20251230-120001/integration"


def test_reconcile_session_no_branches() -> None:
    """Test reconciling session when no integration branches exist."""
    with patch("subprocess.run") as mock_run:
        # Mock git branch --list to return empty
        mock_run.return_value = MagicMock(stdout="", returncode=0)

        result = SessionManager.reconcile_session()
        assert result is None


def test_get_integration_branch_format() -> None:
    """Test integration branch name format."""
    project_session_id = "session-20251230-120000"
    branch = SessionManager.get_integration_branch(project_session_id)
    assert branch == "dev/session-20251230-120000/integration"


@pytest.mark.usefixtures("temp_session_file")
def test_load_or_reconcile_with_explicit_id() -> None:
    """Test loading session with explicit session ID."""
    project_session_id = "session-explicit"

    with patch.object(SessionManager, "validate_session", return_value=(True, None)):
        result = SessionManager.load_or_reconcile_session(project_session_id=project_session_id)
        assert result["project_session_id"] == project_session_id


@pytest.mark.usefixtures("temp_session_file")
def test_load_or_reconcile_from_file() -> None:
    """Test loading session from file when no explicit ID provided."""
    # Save a session first
    SessionManager.save_session("session-from-file", "dev/session-from-file")

    with patch.object(SessionManager, "validate_session", return_value=(True, None)):
        result = SessionManager.load_or_reconcile_session()
        assert result["project_session_id"] == "session-from-file"
