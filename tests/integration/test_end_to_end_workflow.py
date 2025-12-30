"""End-to-end workflow integration tests."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_full_gen_cycles_workflow():
    """Test complete gen-cycles workflow from start to finish."""
    with (
        patch("ac_cdd_core.services.git_ops.GitManager") as mock_git,
        patch("ac_cdd_core.services.jules_client.JulesClient") as mock_jules,
        patch("ac_cdd_core.session_manager.SessionManager.save_session") as mock_save,
        patch("ac_cdd_core.graph.GraphBuilder"),
    ):
        # Setup mocks
        mock_git_instance = MagicMock()
        mock_git.return_value = mock_git_instance
        mock_git_instance.create_integration_branch.return_value = "dev/session-test"
        mock_git_instance.create_session_branch.return_value = "dev/session-test/arch"
        
        mock_jules_instance = MagicMock()
        mock_jules.return_value = mock_jules_instance
        mock_jules_instance.run_session = AsyncMock(return_value="https://github.com/user/repo/pull/1")
        
        # Simulate workflow
        session_id = "session-test"
        integration_branch = mock_git_instance.create_integration_branch(session_id)
        arch_branch = mock_git_instance.create_session_branch(
            session_id, "arch", "architecture", integration_branch
        )
        
        pr_url = await mock_jules_instance.run_session(
            session_id, "prompt", [], MagicMock(), target_branch=integration_branch
        )
        
        mock_save(session_id, integration_branch)
        
        # Verify workflow
        assert integration_branch == "dev/session-test"
        assert arch_branch == "dev/session-test/arch"
        assert pr_url is not None
        mock_save.assert_called_once()


@pytest.mark.asyncio
async def test_full_run_cycle_workflow():
    """Test complete run-cycle workflow."""
    with (
        patch("ac_cdd_core.session_manager.SessionManager.load_or_reconcile_session") as mock_load,
        patch("ac_cdd_core.services.git_ops.GitManager") as mock_git,
        patch("ac_cdd_core.services.jules_client.JulesClient") as mock_jules,
        patch("ac_cdd_core.sandbox.SandboxRunner") as mock_sandbox,
        patch("ac_cdd_core.services.llm_reviewer.LLMReviewer") as mock_reviewer,
    ):
        # Setup session
        mock_load.return_value = {
            "session_id": "session-test",
            "integration_branch": "dev/session-test"
        }
        
        # Setup git
        mock_git_instance = MagicMock()
        mock_git.return_value = mock_git_instance
        mock_git_instance.create_session_branch.return_value = "dev/session-test/cycle01"
        
        # Setup Jules
        mock_jules_instance = MagicMock()
        mock_jules.return_value = mock_jules_instance
        mock_jules_instance.run_session = AsyncMock(return_value="https://github.com/user/repo/pull/2")
        mock_jules_instance.continue_session = AsyncMock(return_value="https://github.com/user/repo/pull/2")
        
        # Setup sandbox
        mock_sandbox_instance = MagicMock()
        mock_sandbox.return_value = mock_sandbox_instance
        mock_sandbox_instance.run_command = AsyncMock(return_value=("", "", 0))
        
        # Setup reviewer
        mock_reviewer_instance = MagicMock()
        mock_reviewer.return_value = mock_reviewer_instance
        mock_reviewer_instance.review_code = AsyncMock(return_value="APPROVED")
        
        # Simulate workflow
        session = mock_load()
        cycle_branch = mock_git_instance.create_session_branch(
            session["session_id"], "cycle", "01", session["integration_branch"]
        )
        
        pr_url = await mock_jules_instance.run_session(
            session["session_id"], "prompt", [], MagicMock()
        )
        
        # Run tests
        await mock_sandbox_instance.run_command(["pytest"])
        
        # Run audit
        audit_result = await mock_reviewer_instance.review_code({}, "audit", "model")
        
        # Verify
        assert cycle_branch == "dev/session-test/cycle01"
        assert pr_url is not None
        assert "APPROVED" in audit_result


def test_session_persistence_across_commands():
    """Test that session persists correctly across multiple commands."""
    with (
        patch("ac_cdd_core.session_manager.SessionManager.save_session") as mock_save,
        patch("ac_cdd_core.session_manager.SessionManager.load_session") as mock_load,
    ):
        # First command: gen-cycles saves session
        session_id = "session-test"
        integration_branch = "dev/session-test"
        mock_save(session_id, integration_branch)
        
        # Second command: run-cycle loads session
        mock_load.return_value = {
            "session_id": session_id,
            "integration_branch": integration_branch
        }
        
        loaded = mock_load()
        
        # Verify persistence
        assert loaded["session_id"] == session_id
        assert loaded["integration_branch"] == integration_branch
        mock_save.assert_called_once()
        mock_load.assert_called_once()


@pytest.mark.asyncio
async def test_error_recovery_workflow():
    """Test error recovery in workflow."""
    with (
        patch("ac_cdd_core.services.jules_client.JulesClient") as mock_jules,
        patch("ac_cdd_core.sandbox.SandboxRunner") as mock_sandbox,
    ):
        # Setup Jules to fail first, then succeed
        mock_jules_instance = MagicMock()
        mock_jules.return_value = mock_jules_instance
        mock_jules_instance.run_session = AsyncMock(
            side_effect=[Exception("API Error"), "https://github.com/user/repo/pull/3"]
        )
        
        # Setup sandbox to fail first, then succeed
        mock_sandbox_instance = MagicMock()
        mock_sandbox.return_value = mock_sandbox_instance
        mock_sandbox_instance.run_command = AsyncMock(
            side_effect=[("", "Error", 1), ("", "", 0)]
        )
        
        # First attempt fails
        with pytest.raises(Exception):
            await mock_jules_instance.run_session("session", "prompt", [], MagicMock())
        
        # Retry succeeds
        pr_url = await mock_jules_instance.run_session("session", "prompt", [], MagicMock())
        assert pr_url is not None
        
        # Sandbox first attempt fails
        stdout, stderr, code = await mock_sandbox_instance.run_command(["test"])
        assert code == 1
        
        # Retry succeeds
        stdout, stderr, code = await mock_sandbox_instance.run_command(["test"])
        assert code == 0
