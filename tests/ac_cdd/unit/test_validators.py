"""Tests for validation logic."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ac_cdd_core.validators import (
    CompositeValidator,
    SessionValidator,
    ValidationError,
)


@pytest.mark.asyncio
async def test_session_validator_valid() -> None:
    """Test SessionValidator with valid session state."""
    validator = SessionValidator("session-test", "dev/session-test")

    with patch("ac_cdd_core.session_manager.SessionManager.validate_session") as mock_validate:
        mock_validate.return_value = (True, None)

        is_valid, error = await validator.validate()

        assert is_valid
        assert error == ""


@pytest.mark.asyncio
async def test_session_validator_invalid() -> None:
    """Test SessionValidator with invalid session state."""
    validator = SessionValidator("session-test", "dev/session-test")

    with patch("ac_cdd_core.session_manager.SessionManager.validate_session") as mock_validate:
        mock_validate.return_value = (False, "Branch does not exist")

        is_valid, error = await validator.validate()

        assert not is_valid
        assert "Branch does not exist" in error


@pytest.mark.asyncio
async def test_session_validator_raise_if_invalid() -> None:
    """Test SessionValidator raises ValidationError when invalid."""
    validator = SessionValidator("session-test", "dev/session-test")

    with patch("ac_cdd_core.session_manager.SessionManager.validate_session") as mock_validate:
        mock_validate.return_value = (False, "Invalid state")

        with pytest.raises(ValidationError):
            await validator.raise_if_invalid()


@pytest.mark.asyncio
async def test_session_validator_with_remote_check() -> None:
    """Test SessionValidator with remote branch validation."""
    validator = SessionValidator("session-test", "dev/session-test", check_remote=True)

    with (
        patch("ac_cdd_core.session_manager.SessionManager.validate_session") as mock_local,
        patch("ac_cdd_core.services.git_ops.GitManager") as mock_git,
    ):
        mock_local.return_value = (True, None)

        mock_git_instance = MagicMock()
        mock_git.return_value = mock_git_instance
        mock_git_instance.validate_remote_branch = AsyncMock(return_value=(True, None))

        is_valid, _error = await validator.validate()

        assert is_valid


@pytest.mark.asyncio
async def test_composite_validator_all_pass() -> None:
    """Test CompositeValidator when all validators pass."""
    validator1 = MagicMock()
    validator1.validate = AsyncMock(return_value=(True, ""))

    validator2 = MagicMock()
    validator2.validate = AsyncMock(return_value=(True, ""))

    composite = CompositeValidator([validator1, validator2])

    is_valid, error = await composite.validate()

    assert is_valid
    assert error == ""


@pytest.mark.asyncio
async def test_composite_validator_first_fails() -> None:
    """Test CompositeValidator stops at first failure."""
    validator1 = MagicMock()
    validator1.validate = AsyncMock(return_value=(False, "First validator failed"))

    validator2 = MagicMock()
    validator2.validate = AsyncMock(return_value=(True, ""))

    composite = CompositeValidator([validator1, validator2])

    is_valid, error = await composite.validate()

    assert not is_valid
    assert "First validator failed" in error
    # Second validator should not be called
    validator2.validate.assert_not_called()
