from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from ac_cdd_core.services.git_ops import GitManager


@pytest.fixture
def mock_runner() -> Generator[Any, None, None]:
    with patch("ac_cdd_core.services.git_ops.ProcessRunner") as MockRunner:
        runner_instance = MockRunner.return_value
        runner_instance.run_command = AsyncMock()
        yield runner_instance


@pytest.fixture
def git_manager(mock_runner: Any) -> GitManager:
    # Mock settings to prevent loading real config
    with patch("ac_cdd_core.services.git_ops.settings") as mock_settings:
        mock_settings.github_token = "dummy_token"  # noqa: S105
        manager = GitManager()
        # Replace the real runner with our mock
        manager.runner = mock_runner
        return manager


@pytest.mark.asyncio
async def test_merge_pr_immediate_success(git_manager: GitManager, mock_runner: Any) -> None:
    """Test that immediate merge is tried first and succeeds."""
    # Mock behavior: Immediate merge succeeds (code 0)
    # Note: merge_pr calls 'pr view' first, then 'pr merge'

    # Setup mock to return success for "pr view" (draft check) and "pr merge"
    mock_runner.run_command.side_effect = [
        ("false", "", 0),  # pr view (isDraft=false)
        ("Merged", "", 0),  # pr merge
    ]

    await git_manager.merge_pr(36, method="squash")

    # Verify calls
    assert mock_runner.run_command.call_count == 2

    # 2nd call should be merge WITHOUT --auto
    merge_cmd = mock_runner.run_command.call_args_list[1][0][0]
    assert "pr" in merge_cmd
    assert "merge" in merge_cmd
    assert "--auto" not in merge_cmd
    assert "--squash" in merge_cmd
    assert "--delete-branch" in merge_cmd


@pytest.mark.asyncio
async def test_merge_pr_fallback_to_auto(git_manager: GitManager, mock_runner: Any) -> None:
    """Test fallback to auto-merge when immediate merge fails due to status checks."""

    # Mock behavior:
    # 1. pr view -> success
    # 2. immediate merge -> fail (checks pending)
    # 3. auto merge -> success

    mock_runner.run_command.side_effect = [
        ("false", "", 0),  # pr view (isDraft=false)
        ("", "Base branch requires status checks", 1),  # immediate merge fails
        ("Auto-merge enabled", "", 0),  # auto merge succeeds
    ]

    await git_manager.merge_pr(36, method="squash")

    assert mock_runner.run_command.call_count == 3

    # 2nd call: immediate merge
    cmd2 = mock_runner.run_command.call_args_list[1][0][0]
    assert "--auto" not in cmd2

    # 3rd call: auto merge
    cmd3 = mock_runner.run_command.call_args_list[2][0][0]
    assert "--auto" in cmd3


@pytest.mark.asyncio
async def test_merge_pr_failure_no_fallback(git_manager: GitManager, mock_runner: Any) -> None:
    """Test that we do NOT fallback to auto-merge for non-recoverable errors (e.g. conflict)."""

    # Mock behavior:
    # 1. pr view -> success
    # 2. immediate merge -> fail (conflict)

    mock_runner.run_command.side_effect = [
        ("false", "", 0),
        ("", "Merge conflict", 1),  # Fail with conflict
    ]

    # Should raise RuntimeError
    with pytest.raises(RuntimeError) as exc:
        await git_manager.merge_pr(36, method="squash")

    assert "Merge conflict" in str(exc.value)

    # Should NOT try auto-merge (only 2 calls)
    assert mock_runner.run_command.call_count == 2
