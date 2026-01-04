from unittest.mock import AsyncMock, patch

import pytest
from ac_cdd_core.domain_models import ProjectManifest
from ac_cdd_core.services.workflow import WorkflowService


@pytest.mark.asyncio
class TestEndToEndWorkflow:

    @pytest.fixture
    def workflow(self):
        # We need to ensure we patch dependencies that WorkflowService initializes
        with patch("ac_cdd_core.services.workflow.ServiceContainer"), \
             patch("ac_cdd_core.services.workflow.GraphBuilder"):
            return WorkflowService()

    @patch("ac_cdd_core.services.workflow.SessionManager")
    @patch("ac_cdd_core.services.workflow.GitManager")
    @patch("ac_cdd_core.services.workflow.ensure_api_key")
    async def test_full_gen_cycles_workflow(self, mock_auth, mock_git_cls, mock_sm_cls, workflow):
        # Setup Graph Mock
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {
            "project_session_id": "p1",
            "integration_branch": "dev/p1"
        }
        workflow.builder.build_architect_graph.return_value = mock_graph

        # Setup SessionManager Mock
        mock_mgr = mock_sm_cls.return_value
        mock_mgr.create_manifest = AsyncMock(return_value=ProjectManifest(project_session_id="p1", integration_branch="dev/p1"))
        mock_mgr.save_manifest = AsyncMock()

        # Setup GitManager Mock
        mock_git = mock_git_cls.return_value
        mock_git.create_integration_branch = AsyncMock()

        # Mock cleanup
        workflow.builder.cleanup = AsyncMock()

        # Execute
        await workflow.run_gen_cycles(cycles=2, project_session_id=None)

        # Verify
        workflow.builder.build_architect_graph.assert_called_once()
        mock_graph.ainvoke.assert_called_once()
        mock_mgr.create_manifest.assert_awaited()
        mock_mgr.save_manifest.assert_awaited()
        mock_git.create_integration_branch.assert_awaited()
        workflow.builder.cleanup.assert_awaited()

    @patch("ac_cdd_core.services.workflow.SessionManager")
    @patch("ac_cdd_core.services.workflow.ensure_api_key")
    async def test_full_run_cycle_workflow(self, mock_auth, mock_sm_cls, workflow):
        # Setup Graph Mock
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {"status": "completed"}
        workflow.builder.build_coder_graph.return_value = mock_graph

        # Setup SessionManager Mock
        mock_mgr = mock_sm_cls.return_value
        manifest = ProjectManifest(project_session_id="p1", integration_branch="dev/p1")
        mock_mgr.load_manifest = AsyncMock(return_value=manifest)
        mock_mgr.update_cycle_state = AsyncMock()

        # Setup Cleanup
        workflow.builder.cleanup = AsyncMock()

        # Execute
        await workflow.run_cycle("01", resume=False, auto=True, start_iter=1, project_session_id=None)

        # Verify
        mock_graph.ainvoke.assert_called_once()
        mock_mgr.update_cycle_state.assert_awaited_with("01", status="completed")
        workflow.builder.cleanup.assert_awaited()

    @patch("ac_cdd_core.services.workflow.SessionManager")
    async def test_session_persistence_across_commands(self, mock_sm_cls, workflow):
        # This test previously verified file persistence. Now we verify interaction with Git-backed SessionManager.
        mock_mgr = mock_sm_cls.return_value

        # Simulate loading manifest
        manifest = ProjectManifest(project_session_id="p1", integration_branch="dev/p1")
        mock_mgr.load_manifest = AsyncMock(return_value=manifest)

        # Setup Cleanup
        workflow.builder.cleanup = AsyncMock()

        # Setup build_coder_graph
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {"status": "completed"}
        workflow.builder.build_coder_graph.return_value = mock_graph

        await workflow._run_all_cycles(resume=False, auto=True, start_iter=1, project_session_id=None)

        mock_mgr.load_manifest.assert_awaited()
