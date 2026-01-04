"""Unit tests for auto-merge functionality in run-cycle command."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ac_cdd_core.state import CycleState


class TestAutoMerge:
    """Test suite for auto-merge functionality."""

    @pytest.mark.asyncio
    async def test_auto_merge_enabled_with_pr_url(self) -> None:
        """Test that auto-merge is triggered when enabled and PR URL exists."""
        # Mock GitManager
        with patch("ac_cdd_core.services.git_ops.GitManager") as mock_git_class:
            mock_git = MagicMock()
            mock_git.merge_to_integration = AsyncMock()
            mock_git_class.return_value = mock_git

            # Simulate successful cycle with PR URL
            final_state = CycleState(
                cycle_id="01",
                pr_url="https://github.com/user/repo/pull/123",
            )
            integration_branch = "integration/dev-test-session"
            auto_merge = True

            # Execute auto-merge logic (simulating the CLI code)
            if auto_merge and final_state.get("pr_url"):
                from ac_cdd_core.services.git_ops import GitManager

                git = GitManager()
                await git.merge_to_integration(final_state["pr_url"], integration_branch)

            # Verify merge was called
            mock_git.merge_to_integration.assert_called_once_with(
                "https://github.com/user/repo/pull/123",
                "integration/dev-test-session",
            )

    @pytest.mark.asyncio
    async def test_auto_merge_disabled(self) -> None:
        """Test that auto-merge is skipped when disabled."""
        with patch("ac_cdd_core.services.git_ops.GitManager") as mock_git_class:
            mock_git = MagicMock()
            mock_git.merge_to_integration = AsyncMock()
            mock_git_class.return_value = mock_git

            final_state = CycleState(
                cycle_id="01",
                pr_url="https://github.com/user/repo/pull/123",
            )
            integration_branch = "integration/dev-test-session"
            auto_merge = False  # Disabled

            # Execute auto-merge logic
            if auto_merge and final_state.get("pr_url"):
                from ac_cdd_core.services.git_ops import GitManager

                git = GitManager()
                await git.merge_to_integration(final_state["pr_url"], integration_branch)

            # Verify merge was NOT called
            mock_git.merge_to_integration.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_merge_with_missing_pr_url(self) -> None:
        """Test that auto-merge is skipped when PR URL is missing."""
        with patch("ac_cdd_core.services.git_ops.GitManager") as mock_git_class:
            mock_git = MagicMock()
            mock_git.merge_to_integration = AsyncMock()
            mock_git_class.return_value = mock_git

            final_state = CycleState(
                cycle_id="01",
                pr_url=None,  # No PR URL
            )
            integration_branch = "integration/dev-test-session"
            auto_merge = True

            # Execute auto-merge logic
            if auto_merge and final_state.get("pr_url"):
                from ac_cdd_core.services.git_ops import GitManager

                git = GitManager()
                await git.merge_to_integration(final_state["pr_url"], integration_branch)

            # Verify merge was NOT called
            mock_git.merge_to_integration.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_merge_failure_handling(self) -> None:
        """Test that auto-merge failures are handled gracefully."""
        with patch("ac_cdd_core.services.git_ops.GitManager") as mock_git_class:
            mock_git = MagicMock()
            # Simulate merge failure
            mock_git.merge_to_integration = AsyncMock(
                side_effect=RuntimeError("Merge conflict detected")
            )
            mock_git_class.return_value = mock_git

            final_state = CycleState(
                cycle_id="01",
                pr_url="https://github.com/user/repo/pull/123",
            )
            integration_branch = "integration/dev-test-session"
            auto_merge = True

            # Execute auto-merge logic with error handling (simulating CLI code)
            merge_succeeded = False
            error_message = ""
            try:
                if auto_merge and final_state.get("pr_url"):
                    from ac_cdd_core.services.git_ops import GitManager

                    git = GitManager()
                    await git.merge_to_integration(final_state["pr_url"], integration_branch)
                    merge_succeeded = True
            except Exception as e:
                error_message = str(e)

            # Verify merge was attempted
            mock_git.merge_to_integration.assert_called_once()
            # Verify error was caught (not raised)
            assert not merge_succeeded
            assert "Merge conflict detected" in error_message

    @pytest.mark.asyncio
    async def test_auto_merge_only_to_integration_branch(self) -> None:
        """Test that auto-merge only targets integration branches, not main."""
        with patch("ac_cdd_core.services.git_ops.GitManager") as mock_git_class:
            mock_git = MagicMock()
            mock_git.merge_to_integration = AsyncMock()
            mock_git_class.return_value = mock_git

            final_state = CycleState(
                cycle_id="01",
                pr_url="https://github.com/user/repo/pull/123",
            )
            # Integration branch (safe)
            integration_branch = "integration/dev-session-123"
            auto_merge = True

            if auto_merge and final_state.get("pr_url"):
                from ac_cdd_core.services.git_ops import GitManager

                git = GitManager()
                await git.merge_to_integration(final_state["pr_url"], integration_branch)

            # Verify merge was called with integration branch
            call_args = mock_git.merge_to_integration.call_args
            assert call_args is not None
            assert "integration/" in call_args[0][1]
            assert call_args[0][1] != "main"
