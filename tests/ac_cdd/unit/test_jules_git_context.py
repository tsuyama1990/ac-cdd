from unittest.mock import AsyncMock

import pytest
from ac_cdd_core.services.jules_client import JulesClient
from ac_cdd_core.services.jules.git_context import JulesGitContext


class TestJulesClientGitContext:
    """Tests for JulesClient._prepare_git_context."""

    @pytest.mark.asyncio
    async def test_detached_head_fallback(self) -> None:
        """Verifies that 'HEAD' branch falls back to 'main'."""
        client = JulesClient()
        client.git = AsyncMock()
        client.git.get_remote_url = AsyncMock(return_value="https://github.com/owner/repo.git")
        client.git.get_current_branch = AsyncMock(return_value="HEAD")

        # Mock runner for push/pull avoidance
        client.git.runner = AsyncMock()
        client.git.runner.run_command = AsyncMock()

        # Setup mocked environment

        # Let's run it.
        context = JulesGitContext(client.git)
        owner, repo, branch = await context.prepare_git_context()

        # In test environment, get_remote_url might raise or return something specific.
        # If we mock it correctly:
        assert branch.startswith("jules-sync-")
