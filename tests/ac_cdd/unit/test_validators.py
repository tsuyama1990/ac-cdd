from unittest.mock import AsyncMock, patch

import pytest
from ac_cdd_core.domain_models import ProjectManifest
from ac_cdd_core.validators import SessionValidator, ValidationError


@pytest.mark.asyncio
class TestSessionValidator:
    @patch("ac_cdd_core.validators.StateManager.load_manifest")
    async def test_session_validator_valid(self, mock_load: AsyncMock) -> None:
        manifest = ProjectManifest(
            project_session_id="s1", integration_branch="dev/s1", feature_branch="feat/s1"
        )
        mock_load.return_value = manifest

        validator = SessionValidator("s1", "dev/s1", check_remote=False)
        is_valid, err = await validator.validate()

        assert is_valid
        assert not err

    @patch("ac_cdd_core.validators.StateManager.load_manifest")
    async def test_session_validator_invalid_id(self, mock_load: AsyncMock) -> None:
        manifest = ProjectManifest(
            project_session_id="s2", integration_branch="dev/s1", feature_branch="feat/s1"
        )
        mock_load.return_value = manifest

        validator = SessionValidator("s1", "dev/s1", check_remote=False)
        is_valid, err = await validator.validate()

        assert not is_valid
        assert "Manifest session ID" in err

    @patch("ac_cdd_core.validators.StateManager.load_manifest")
    async def test_session_validator_no_manifest(self, mock_load: AsyncMock) -> None:
        mock_load.return_value = None

        validator = SessionValidator("s1", "dev/s1", check_remote=False)
        is_valid, err = await validator.validate()

        assert not is_valid
        assert "manifest not found" in err

    @patch("ac_cdd_core.validators.GitManager.validate_remote_branch")
    @patch("ac_cdd_core.validators.StateManager.load_manifest")
    async def test_session_validator_with_remote_check(
        self, mock_load: AsyncMock, mock_git_validate: AsyncMock
    ) -> None:
        manifest = ProjectManifest(
            project_session_id="s1", integration_branch="dev/s1", feature_branch="feat/s1"
        )
        mock_load.return_value = manifest
        mock_git_validate.return_value = (True, "")

        validator = SessionValidator("s1", "dev/s1", check_remote=True)
        is_valid, err = await validator.validate()

        assert is_valid
        assert err == ""
        mock_git_validate.assert_awaited_once_with("dev/s1")

    @patch("ac_cdd_core.validators.GitManager.validate_remote_branch")
    @patch("ac_cdd_core.validators.StateManager.load_manifest")
    async def test_session_validator_with_remote_check_failure(
        self, mock_load: AsyncMock, mock_git_validate: AsyncMock
    ) -> None:
        manifest = ProjectManifest(
            project_session_id="s1", integration_branch="dev/s1", feature_branch="feat/s1"
        )
        mock_load.return_value = manifest
        mock_git_validate.return_value = (False, "Remote branch dev/s1 not found")

        validator = SessionValidator("s1", "dev/s1", check_remote=True)
        is_valid, err = await validator.validate()

        assert is_valid
        assert err == ""
        mock_git_validate.assert_awaited_once_with("dev/s1")

    @patch("ac_cdd_core.validators.StateManager.load_manifest")
    async def test_raise_if_invalid(self, mock_load: AsyncMock) -> None:
        mock_load.return_value = None

        validator = SessionValidator("s1", "dev/s1", check_remote=False)
        with pytest.raises(ValidationError):
            await validator.raise_if_invalid()
