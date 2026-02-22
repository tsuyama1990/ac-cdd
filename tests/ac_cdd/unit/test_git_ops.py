from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from ac_cdd_core.services.git_ops import GitManager


@pytest.fixture
def mock_runner() -> Generator[Any, None, None]:
    with patch("ac_cdd_core.services.git.base.ProcessRunner") as MockRunner:
        runner_instance = MockRunner.return_value
        runner_instance.run_command = AsyncMock(return_value=("output", "", 0))
        yield runner_instance


@pytest.fixture
def git_manager(mock_runner: Any) -> GitManager:
    return GitManager()


@pytest.mark.asyncio
async def test_ensure_no_lock_removes_file(git_manager: GitManager) -> None:
    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("pathlib.Path.unlink") as mock_unlink,
    ):
        await git_manager._ensure_no_lock()
        mock_unlink.assert_called_once()


@pytest.mark.asyncio
async def test_run_git_checks_lock(git_manager: GitManager, mock_runner: Any) -> None:
    with patch.object(git_manager, "_ensure_no_lock") as mock_ensure:
        await git_manager._run_git(["status"])
        mock_ensure.assert_called_once()
        mock_runner.run_command.assert_called_with(["git", "status"], check=True)


@pytest.mark.asyncio
async def test_smart_checkout_success(git_manager: GitManager) -> None:
    git_manager._stash_changes = AsyncMock(return_value=False)
    git_manager._run_git = AsyncMock()

    await git_manager.smart_checkout("feature-branch")

    git_manager._run_git.assert_called_with(["checkout", "feature-branch"])


@pytest.mark.asyncio
async def test_smart_checkout_with_auto_commit(git_manager: GitManager) -> None:
    # Simulate dirty state that needs auto-commit
    git_manager._auto_commit_if_dirty = AsyncMock()
    git_manager._run_git = AsyncMock()

    await git_manager.smart_checkout("feature-branch")

    git_manager._auto_commit_if_dirty.assert_called_once()
    git_manager._run_git.assert_called_with(["checkout", "feature-branch"])
