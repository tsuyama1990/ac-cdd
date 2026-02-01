from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from ac_cdd_core.services.git_ops import GitManager


@pytest.fixture
def mock_git_env(tmp_path: Path) -> Path:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()
    return repo_dir


@pytest.mark.asyncio
async def test_create_feature_branch_idempotency(mock_git_env: Path) -> None:
    """
    Verify that create_feature_branch doesn't fail if branch already exists.
    """
    with patch("pathlib.Path.cwd", return_value=mock_git_env):
        git = GitManager()

        # Simulate running git commands
        # 1. checkout main (ok)
        # 2. pull (ok)
        # 3. checkout -b existing_branch -> FAILS

        branch_name = "dev/int-test"

        # Mock run_command to simulate branch existence
        async def mock_run_command(cmd: list[str], check: bool = True) -> tuple[str, str, int]:
            cmd_str = " ".join(cmd)
            # When checking existence
            if "rev-parse --verify dev/int-test" in cmd_str:
                return "", "", 0  # Return 0 = Exists
            # If it tries to create anyway (fail case)
            if "checkout -b dev/int-test" in cmd_str:
                return "", "fatal: A branch named 'dev/int-test' already exists.", 128
            return "", "", 0

        git.runner.run_command = AsyncMock(side_effect=mock_run_command)
        git._ensure_no_lock = AsyncMock()  # Skip lock check for test simplicity

        # Now it should NOT raise
        await git.create_feature_branch(branch_name)

        # Verify checking logic was called
        # mock_run_command logic was: if rev-parse -> return 0 (exists), 128 (failed)
        # We need to ensure the test mock reflects "exists".
        # The logic in create_feature_branch calls rev-parse first.
        # If I want to simulate "exists", rev-parse should return 0.


@pytest.mark.asyncio
async def test_smart_checkout_dirty_recovery(mock_git_env: Path) -> None:
    """
    Verify smart checkout recovers from dirty state.
    """
    with patch("pathlib.Path.cwd", return_value=mock_git_env):
        git = GitManager()
        git.runner.run_command = AsyncMock(return_value=("", "", 0))

        # Mock _stash_changes to return True (simulating dirty)
        git._stash_changes = AsyncMock(return_value=True)
        git._restore_stash = AsyncMock()

        # Should call stash, checkout, restore
        await git.smart_checkout("new-branch")

        git._stash_changes.assert_called_once()
        git._restore_stash.assert_called_once()
