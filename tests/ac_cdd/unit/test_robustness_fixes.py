import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from ac_cdd_core.services.jules_client import JulesClient
from ac_cdd_core.services.git.checkout import GitCheckoutMixin

class TestJulesGitContextRobustness:
    """Tests for robustness improvements in JulesClient."""

    @pytest.mark.asyncio
    async def test_detached_head_creates_temp_branch(self) -> None:
        """Verifies detached HEAD creates a jules-sync branch."""
        # Setup
        client = JulesClient()
        client.git = AsyncMock()
        client.git.get_remote_url = AsyncMock(return_value="https://github.com/owner/repo.git")
        client.git.get_current_branch = AsyncMock(return_value="HEAD")
        client.git.runner = AsyncMock()
        client.git.runner.run_command = AsyncMock(return_value=("", "", 0)) # success
        
        # Act
        await client._prepare_git_context()
        
        # Assert
        # Check if git checkout -b jules-sync-... was called
        checkout_calls = [
            args[0] for args, _ in client.git.runner.run_command.call_args_list 
            if args[0][0] == "git" and args[0][1] == "checkout" and args[0][2] == "-b"
        ]
        assert len(checkout_calls) == 1
        created_branch = checkout_calls[0][3]
        assert created_branch.startswith("jules-sync-")

class TestGitCheckoutRobustness:
    """Tests for robustness improvements in GitCheckoutMixin."""
    
    @pytest.mark.asyncio
    async def test_auto_commit_raises_on_conflict(self) -> None:
        """Verifies _auto_commit_if_dirty raises RuntimeError on conflicts."""
        mixin = GitCheckoutMixin()
        mixin.runner = AsyncMock()
        mixin._run_git = AsyncMock()
        
        # Simulate 'git status --porcelain' returning conflict
        # UU = both modified (conflict)
        mixin.runner.run_command = AsyncMock(return_value=("UU conflicting_file.py\n M normal_file.py", "", 0))
        
        # Act & Assert
        with pytest.raises(RuntimeError) as excinfo:
            await mixin._auto_commit_if_dirty()
        
        assert "Cannot auto-commit due to unresolved conflicts" in str(excinfo.value)
        assert "conflicting_file.py" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_auto_commit_proceeds_on_clean_dirty(self) -> None:
        """Verifies _auto_commit_if_dirty proceeds if just modified (no conflict)."""
        mixin = GitCheckoutMixin()
        mixin.runner = AsyncMock()
        mixin._run_git = AsyncMock()
        
        # M = modified (safe)
        mixin.runner.run_command = AsyncMock(return_value=(" M file.py", "", 0))
        
        await mixin._auto_commit_if_dirty()
        
        # Should have called git add and commit
        assert mixin._run_git.call_count == 2
        args = mixin._run_git.call_args_list[0][0][0]
        assert args == ["add", "."]

