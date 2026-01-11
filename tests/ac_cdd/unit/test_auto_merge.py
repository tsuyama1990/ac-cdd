from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_auto_merge_logic() -> None:
    """Test the auto-merge decision logic used in CLI."""

    # Setup test data
    auto_merge = True
    final_state = {
        "status": "architect_completed",
        "pr_url": "https://github.com/user/repo/pull/123",
    }

    # Mock GitManager
    with patch("ac_cdd_core.services.git_ops.GitManager") as mock_git_class:
        mock_git = MagicMock()
        mock_git.merge_pr = AsyncMock()
        mock_git_class.return_value = mock_git

        # Simulate successful cycle with PR URL
        if auto_merge and final_state.get("pr_url"):
            from ac_cdd_core.services.git_ops import GitManager

            git = GitManager()
            pr_number = final_state["pr_url"].split("/")[-1]
            await git.merge_pr(pr_number)

        # Verify merge was called
        mock_git.merge_pr.assert_called_once_with("123")


@pytest.mark.asyncio
async def test_no_auto_merge_if_disabled() -> None:
    """Test auto-merge is skipped if flag is False."""

    auto_merge = False  # Disabled
    final_state = {
        "status": "architect_completed",
        "pr_url": "https://github.com/user/repo/pull/123",
    }

    with patch("ac_cdd_core.services.git_ops.GitManager") as mock_git_class:
        mock_git = MagicMock()
        mock_git.merge_pr = AsyncMock()
        mock_git_class.return_value = mock_git

        # Execute auto-merge logic
        if auto_merge and final_state.get("pr_url"):
            from ac_cdd_core.services.git_ops import GitManager

            git = GitManager()
            pr_number = final_state["pr_url"].split("/")[-1]
            await git.merge_pr(pr_number)

        # Verify merge was NOT called
        mock_git.merge_pr.assert_not_called()


@pytest.mark.asyncio
async def test_no_auto_merge_if_no_pr() -> None:
    """Test auto-merge is skipped if no PR URL."""

    auto_merge = True
    final_state = {
        "status": "architect_completed",
        # No PR URL
    }

    with patch("ac_cdd_core.services.git_ops.GitManager") as mock_git_class:
        mock_git = MagicMock()
        mock_git.merge_pr = AsyncMock()
        mock_git_class.return_value = mock_git

        # Execute auto-merge logic
        if auto_merge and final_state.get("pr_url"):
            from ac_cdd_core.services.git_ops import GitManager

            git = GitManager()
            pr_number = final_state["pr_url"].split("/")[-1]
            await git.merge_pr(pr_number)

        # Verify merge was NOT called
        mock_git.merge_pr.assert_not_called()


@pytest.mark.asyncio
async def test_auto_merge_failure_handling() -> None:
    """Test handling of merge failures."""

    auto_merge = True
    final_state = {
        "status": "architect_completed",
        "pr_url": "https://github.com/user/repo/pull/123",
    }

    with patch("ac_cdd_core.services.git_ops.GitManager") as mock_git_class:
        mock_git = MagicMock()
        # Simulate merge failure
        mock_git.merge_pr = AsyncMock(side_effect=RuntimeError("Merge conflict detected"))
        mock_git_class.return_value = mock_git

        # Execute auto-merge logic with error handling (simulating CLI code)
        merge_succeeded = False
        error_message = ""
        try:
            if auto_merge and final_state.get("pr_url"):
                from ac_cdd_core.services.git_ops import GitManager

                git = GitManager()
                pr_number = final_state["pr_url"].split("/")[-1]
                await git.merge_pr(pr_number)
                merge_succeeded = True
        except Exception as e:
            error_message = str(e)

        # Verify merge was attempted
        mock_git.merge_pr.assert_called_once()

        # Verify failure handled
        assert not merge_succeeded
        assert "Merge conflict detected" in error_message
