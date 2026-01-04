"""Validation classes for AC-CDD workflow."""

from abc import ABC, abstractmethod

from ac_cdd_core.services.git_ops import GitManager
from ac_cdd_core.session_manager import SessionManager
from ac_cdd_core.utils import logger


class ValidationError(Exception):
    """Base exception for validation failures."""


class BaseValidator(ABC):
    """Base validator with common validation patterns."""

    @abstractmethod
    async def validate(self) -> tuple[bool, str]:
        """Run validation.

        Returns:
            (is_valid, error_message)
        """

    async def raise_if_invalid(self) -> None:
        """Validate and raise if invalid."""
        is_valid, error = await self.validate()
        if not is_valid:
            raise ValidationError(error)


class SessionValidator(BaseValidator):
    """Validates session state consistency."""

    def __init__(self, session_id: str, integration_branch: str, check_remote: bool = True) -> None:
        self.session_id = session_id
        self.integration_branch = integration_branch
        self.check_remote = check_remote

    async def validate(self) -> tuple[bool, str]:
        """Validate session consistency with Git state."""
        # 1. Check if session exists in manifest
        mgr = SessionManager()
        manifest = await mgr.load_manifest()

        if not manifest:
            return False, "Project manifest not found."

        if manifest.project_session_id != self.session_id:
            return False, f"Manifest session ID {manifest.project_session_id} does not match requested {self.session_id}"

        if manifest.integration_branch != self.integration_branch:
             return False, f"Manifest integration branch {manifest.integration_branch} does not match {self.integration_branch}"

        # 2. Remote branch check (optional)
        if self.check_remote:
            git = GitManager()
            is_valid_remote, remote_error = await git.validate_remote_branch(
                self.integration_branch
            )
            if not is_valid_remote:
                # Remote validation is a warning, not a hard failure
                logger.warning(f"Remote validation warning: {remote_error}")

        return True, ""


class CompositeValidator(BaseValidator):
    """Runs multiple validators in sequence."""

    def __init__(self, validators: list[BaseValidator]) -> None:
        self.validators = validators

    async def validate(self) -> tuple[bool, str]:
        """Run all validators, stop at first failure."""
        for validator in self.validators:
            is_valid, error = await validator.validate()
            if not is_valid:
                return False, error
        return True, ""
