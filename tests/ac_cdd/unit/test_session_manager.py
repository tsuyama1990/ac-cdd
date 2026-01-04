from unittest.mock import patch

import pytest
from ac_cdd_core.domain_models import ProjectManifest
from ac_cdd_core.session_manager import SessionManager


@pytest.mark.asyncio
class TestSessionManager:

    @pytest.fixture
    def manager(self):
        return SessionManager()

    @patch("ac_cdd_core.services.git_ops.GitManager.read_state_file")
    async def test_load_manifest_success(self, mock_read, manager):
        json_data = '{"project_session_id": "p1", "integration_branch": "dev/p1", "cycles": []}'
        mock_read.return_value = json_data

        manifest = await manager.load_manifest()

        assert manifest is not None
        assert manifest.project_session_id == "p1"
        assert isinstance(manifest, ProjectManifest)
        mock_read.assert_awaited_once_with("project_state.json")

    @patch("ac_cdd_core.services.git_ops.GitManager.read_state_file")
    async def test_load_manifest_not_found(self, mock_read, manager):
        mock_read.return_value = None

        manifest = await manager.load_manifest()

        assert manifest is None

    @patch("ac_cdd_core.services.git_ops.GitManager.read_state_file")
    async def test_load_manifest_invalid_json(self, mock_read, manager):
        mock_read.return_value = "{invalid_json}"

        manifest = await manager.load_manifest()

        assert manifest is None

    @patch("ac_cdd_core.services.git_ops.GitManager.save_state_file")
    async def test_save_manifest(self, mock_save, manager):
        manifest = ProjectManifest(
            project_session_id="p1",
            integration_branch="dev/p1"
        )

        await manager.save_manifest(manifest, commit_msg="Test update")

        mock_save.assert_awaited_once()
        call_args = mock_save.await_args
        assert call_args[0][0] == "project_state.json"
        assert "p1" in call_args[0][1] # Content
        assert call_args[0][2] == "Test update"

    @patch("ac_cdd_core.services.git_ops.GitManager.save_state_file")
    async def test_create_manifest(self, mock_save, manager):
        manifest = await manager.create_manifest("p_new", "dev/p_new")

        assert manifest.project_session_id == "p_new"
        mock_save.assert_awaited_once()

    @patch("ac_cdd_core.services.git_ops.GitManager.read_state_file")
    async def test_get_cycle(self, mock_read, manager):
        json_data = """
        {
            "project_session_id": "p1", "integration_branch": "dev/p1",
            "cycles": [{"id": "01", "status": "planned"}]
        }
        """
        mock_read.return_value = json_data

        cycle = await manager.get_cycle("01")
        assert cycle is not None
        assert cycle.id == "01"

        cycle = await manager.get_cycle("99")
        assert cycle is None

    @patch("ac_cdd_core.services.git_ops.GitManager.save_state_file")
    @patch("ac_cdd_core.services.git_ops.GitManager.read_state_file")
    async def test_update_cycle_state(self, mock_read, mock_save, manager):
        json_data = """
        {
            "project_session_id": "p1", "integration_branch": "dev/p1",
            "cycles": [{"id": "01", "status": "planned"}]
        }
        """
        mock_read.return_value = json_data

        await manager.update_cycle_state("01", status="in_progress")

        mock_save.assert_awaited_once()
        content = mock_save.await_args[0][1]
        assert '"status": "in_progress"' in content.replace(" ", "") or '"status":"in_progress"' in content.replace(" ", "")

    @patch("ac_cdd_core.services.git_ops.GitManager.read_state_file")
    async def test_update_cycle_not_found(self, mock_read, manager):
        mock_read.return_value = '{"project_session_id": "p1", "integration_branch": "dev/p1", "cycles": []}'

        from ac_cdd_core.session_manager import SessionValidationError
        with pytest.raises(SessionValidationError):
            await manager.update_cycle_state("01", status="in_progress")
