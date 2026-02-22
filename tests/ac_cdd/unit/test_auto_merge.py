"""Tests for auto-merge logic in WorkflowService.finalize_session."""

from unittest.mock import AsyncMock, patch

import pytest
from ac_cdd_core.domain_models import ProjectManifest
from ac_cdd_core.services.workflow import WorkflowService


@pytest.fixture
def workflow() -> WorkflowService:
    with (
        patch("ac_cdd_core.services.workflow.ServiceContainer"),
        patch("ac_cdd_core.services.workflow.GraphBuilder"),
    ):
        return WorkflowService()


@pytest.mark.asyncio
async def test_finalize_creates_final_pr(workflow: WorkflowService) -> None:
    """finalize_session calls create_final_pr with integration branch from manifest."""
    manifest = ProjectManifest(
        project_session_id="p1",
        feature_branch="feat/p1",
        integration_branch="dev/p1/integration",
    )

    with (
        patch("ac_cdd_core.services.workflow.StateManager") as mock_sm_cls,
        patch("ac_cdd_core.services.workflow.GitManager") as mock_git_cls,
        patch("ac_cdd_core.services.workflow.ensure_api_key"),
    ):
        mock_sm_cls.return_value.load_manifest.return_value = manifest

        mock_git = AsyncMock()
        mock_git.create_final_pr = AsyncMock(return_value="https://github.com/repo/pull/1")
        mock_git_cls.return_value = mock_git
        workflow.git = mock_git

        # Patch _archive_and_reset_state to avoid file system operations
        workflow._archive_and_reset_state = AsyncMock()

        await workflow.finalize_session(project_session_id=None)

        mock_git.create_final_pr.assert_awaited_once()
        call_kwargs = mock_git.create_final_pr.await_args.kwargs
        assert call_kwargs["integration_branch"] == "dev/p1/integration"
        assert "p1" in call_kwargs["title"]


@pytest.mark.asyncio
async def test_finalize_exits_when_no_session(workflow: WorkflowService) -> None:
    """finalize_session calls sys.exit if no manifest found."""
    import sys

    with (
        patch("ac_cdd_core.services.workflow.StateManager") as mock_sm_cls,
        patch("ac_cdd_core.services.workflow.ensure_api_key"),
        patch.object(sys, "exit") as mock_exit,
    ):
        mock_sm_cls.return_value.load_manifest.return_value = None

        await workflow.finalize_session(project_session_id=None)

        mock_exit.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_finalize_merge_failure_is_handled(workflow: WorkflowService) -> None:
    """finalize_session handles create_final_pr failure gracefully (exits)."""
    import sys

    manifest = ProjectManifest(
        project_session_id="p1",
        feature_branch="feat/p1",
        integration_branch="dev/p1/integration",
    )

    with (
        patch("ac_cdd_core.services.workflow.StateManager") as mock_sm_cls,
        patch("ac_cdd_core.services.workflow.GitManager") as mock_git_cls,
        patch("ac_cdd_core.services.workflow.ensure_api_key"),
        patch.object(sys, "exit") as mock_exit,
    ):
        mock_sm_cls.return_value.load_manifest.return_value = manifest

        mock_git = AsyncMock()
        mock_git.create_final_pr = AsyncMock(side_effect=RuntimeError("Merge conflict"))
        mock_git_cls.return_value = mock_git
        workflow.git = mock_git

        await workflow.finalize_session(project_session_id=None)

        mock_exit.assert_called_once_with(1)
