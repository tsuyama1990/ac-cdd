"""Tests for GitManager class."""

from unittest.mock import AsyncMock, patch

import pytest
from ac_cdd_core.services.git_ops import GitManager


@pytest.fixture
def git_manager() -> GitManager:
    """Create a GitManager instance."""
    return GitManager()


def test_ensure_clean_state_clean(git_manager: GitManager) -> None:
    """Test ensure_clean_state when working directory is clean."""
    with patch.object(git_manager.runner, "run_command", new_callable=AsyncMock) as mock_run:
        # Mock git status to return empty (clean state)
        # Returns tuple: (stdout, stderr, code)
        mock_run.return_value = ("", "", 0)

        # Should not raise
        # Note: ensure_clean_state is async
        import asyncio

        asyncio.run(git_manager.ensure_clean_state())
        assert mock_run.called


@pytest.mark.asyncio
async def test_ensure_clean_state_dirty_auto_stash(git_manager: GitManager) -> None:
    """Test ensure_clean_state with dirty state and auto-stash."""
    with patch.object(git_manager.runner, "run_command", new_callable=AsyncMock) as mock_run:
        # First call: git status returns changes
        # Second call: git add .
        # Third call: git commit -m
        mock_run.side_effect = [(" M file.py", "", 0), ("", "", 0), ("", "", 0)]

        await git_manager.ensure_clean_state(force_stash=True)

        # Should call auto-commit commands
        assert mock_run.call_count == 3


@pytest.mark.asyncio
async def test_create_integration_branch(git_manager: GitManager) -> None:
    """Test creating integration branch."""
    session_id = "session-20251230-120000"

    with patch.object(git_manager.runner, "run_command", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = ("", "", 0)

        branch = await git_manager.create_integration_branch(session_id)

        assert branch == "dev/session-20251230-120000/integration"
        assert mock_run.called


@pytest.mark.asyncio
async def test_create_session_branch_arch(git_manager: GitManager) -> None:
    """Test creating architecture branch."""
    session_id = "session-20251230-120000"
    integration_branch = "dev/session-20251230-120000/integration"

    with patch.object(git_manager.runner, "run_command", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = ("", "", 0)

        branch = await git_manager.create_session_branch(session_id, "arch", "", integration_branch)

        assert branch == "dev/session-20251230-120000/arch"
        assert mock_run.called


@pytest.mark.asyncio
async def test_create_session_branch_cycle(git_manager: GitManager) -> None:
    """Test creating cycle branch."""
    session_id = "session-20251230-120000"
    integration_branch = "dev/session-20251230-120000/integration"

    with patch.object(git_manager.runner, "run_command", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = ("", "", 0)

        branch = await git_manager.create_session_branch(
            session_id, "cycle", "01", integration_branch
        )

        assert branch == "dev/session-20251230-120000/cycle01"


@pytest.mark.asyncio
async def test_merge_pr(git_manager: GitManager) -> None:
    """Test merging PR with auto-merge."""
    pr_number = 123

    with patch.object(git_manager.runner, "run_command", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = ("", "", 0)

        # Merge with default method (squash)
        await git_manager.merge_pr(pr_number)

        # Verify command arguments
        # args[0] is the command list passed to run_command
        # Note: merge_pr calls 'pr view' first, then 'pr merge'
        # The LAST call should be the merge command

        # We need to find the merge command in call_args_list because pr view might be called
        merge_calls = [
            call[0][0]
            for call in mock_run.call_args_list
            if "merge" in call[0][0] and "pr" in call[0][0]
        ]
        assert merge_calls
        last_merge_args = merge_calls[-1]

        # New behavior: tries immediate merge first (no --auto)
        assert last_merge_args == ["gh", "pr", "merge", "123", "--squash", "--delete-branch"]

        # Merge with explicit method
        mock_run.reset_mock()
        await git_manager.merge_pr(pr_number, method="merge")

        merge_calls = [
            call[0][0]
            for call in mock_run.call_args_list
            if "merge" in call[0][0] and "pr" in call[0][0]
        ]
        last_merge_args = merge_calls[-1]
        assert last_merge_args == ["gh", "pr", "merge", "123", "--merge", "--delete-branch"]


@pytest.mark.asyncio
async def test_create_final_pr_new(git_manager: GitManager) -> None:
    """Test creating new final PR to main."""
    integration_branch = "dev/session-20251230-120000/integration"
    title = "Session: Complete Implementation"
    body = "Final PR for session"

    with patch.object(git_manager.runner, "run_command", new_callable=AsyncMock) as mock_run:
        # Mock gh pr list to return empty (no existing PR) -> check=False
        # Mock push (checkout, pull, push) -> check=True
        # Mock gh pr create to return new PR URL -> check=True

        mock_run.side_effect = [
            ("", "", 0),  # gh pr list (empty)
            ("", "", 0),  # git checkout
            ("", "", 0),  # git pull (added in refactor)
            ("", "", 0),  # git push
            ("https://github.com/user/repo/pull/456", "", 0),  # gh pr create
        ]

        pr_url = await git_manager.create_final_pr(integration_branch, title, body)

        assert "pull/456" in pr_url
        assert mock_run.call_count == 5


@pytest.mark.asyncio
async def test_create_final_pr_existing(git_manager: GitManager) -> None:
    """Test returning existing final PR."""
    integration_branch = "dev/session-20251230-120000/integration"

    with patch.object(git_manager.runner, "run_command", new_callable=AsyncMock) as mock_run:
        # Mock gh pr list to return existing PR
        existing_pr = "https://github.com/user/repo/pull/789"
        mock_run.return_value = (existing_pr, "", 0)

        pr_url = await git_manager.create_final_pr(integration_branch, "title", "body")

        assert pr_url == existing_pr
        # Should only call gh pr list, not create
        assert mock_run.call_count == 1


@pytest.mark.asyncio
async def test_validate_remote_branch_success(git_manager: GitManager) -> None:
    """Test validating branch that exists on remote."""
    branch = "dev/session-20251230-120000"

    with patch.object(git_manager.runner, "run_command", new_callable=AsyncMock) as mock_run:
        # Mock git ls-remote to return the branch
        # Then fetch, rev-parse local, rev-parse remote, merge-base

        mock_run.side_effect = [
            (f"abc1234 refs/heads/{branch}", "", 0),  # ls-remote
            ("", "", 0),  # fetch
            ("hash1", "", 0),  # rev-parse local
            ("hash1", "", 0),  # rev-parse remote
            # No merge-base call if hashes equal
        ]

        is_valid, error = await git_manager.validate_remote_branch(branch)

        assert is_valid
        assert error == ""


@pytest.mark.asyncio
async def test_validate_remote_branch_not_found(git_manager: GitManager) -> None:
    """Test validating branch that doesn't exist on remote."""
    branch = "nonexistent-branch"

    with patch.object(git_manager.runner, "run_command", new_callable=AsyncMock) as mock_run:
        # Mock git ls-remote to return empty
        mock_run.return_value = ("", "", 0)

        is_valid, error = await git_manager.validate_remote_branch(branch)

        assert not is_valid
        assert "does not exist" in error


@pytest.mark.asyncio
async def test_get_changed_files(git_manager: GitManager) -> None:
    """Test getting list of changed files."""
    with patch.object(git_manager.runner, "run_command", new_callable=AsyncMock) as mock_run:
        # Mock git diff to return file list
        mock_run.side_effect = [
            ("file1.py\nfile2.py", "", 0),  # committed changes
            ("file3.py", "", 0),  # staged changes
            ("file4.py", "", 0),  # unstaged changes
            ("file5.py", "", 0),  # untracked files
        ]

        files = await git_manager.get_changed_files()

        assert len(files) == 5
        assert "file1.py" in files
        assert "file5.py" in files
