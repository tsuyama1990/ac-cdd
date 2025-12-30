"""Session management utilities for AC-CDD."""

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from ac_cdd_core.utils import logger


class SessionValidationError(Exception):
    """Raised when session validation fails."""

    pass


class SessionInfo(TypedDict):
    session_id: str
    integration_branch: str
    resume_info: dict | None


class SessionManager:
    """Manages session persistence for AC-CDD development sessions."""

    SESSION_FILE = Path(".ac_cdd_session.json")

    @classmethod
    def save_session(cls, session_id: str, integration_branch: str) -> None:
        """Save session information to file."""
        session_data = {
            "session_id": session_id,
            "integration_branch": integration_branch,
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
        }
        cls.SESSION_FILE.write_text(json.dumps(session_data, indent=2))
        logger.info(f"Session saved: {session_id}")

    @classmethod
    def load_session(cls) -> dict | None:
        """Load session information from file."""
        if cls.SESSION_FILE.exists():
            try:
                data = json.loads(cls.SESSION_FILE.read_text())
                logger.info(f"Session loaded: {data.get('session_id')}")
                return data
            except Exception as e:
                logger.warning(f"Failed to load session file: {e}")
                return None
        return None

    @classmethod
    def clear_session(cls) -> None:
        """Clear session file."""
        if cls.SESSION_FILE.exists():
            cls.SESSION_FILE.unlink()
            logger.info("Session file cleared")

    @classmethod
    def validate_session(cls, session_id: str, integration_branch: str) -> tuple[bool, str | None]:
        """
        Validate that session state is consistent with Git state.

        Returns:
            (is_valid, error_message)
        """
        # Check if integration branch exists locally
        result = subprocess.run(  # noqa: S603
            ["git", "rev-parse", "--verify", integration_branch],  # noqa: S607
            capture_output=True,
            check=False,
        )

        if result.returncode != 0:
            from ac_cdd_core.error_messages import RecoveryMessages

            error_msg = f"Session validation failed: {RecoveryMessages.branch_not_found(integration_branch, str(cls.SESSION_FILE))}"  # noqa: E501
            return False, error_msg

        # Check if branch exists on remote
        # security: integration_branch is validated by git ops
        result = subprocess.run(  # noqa: S603
            ["git", "ls-remote", "--heads", "origin", integration_branch],  # noqa: S607
            capture_output=True,
            check=False,
        )

        if result.returncode != 0 or not result.stdout.strip():
            from ac_cdd_core.error_messages import RecoveryMessages

            error_msg = RecoveryMessages.remote_branch_missing(integration_branch)
            logger.warning(error_msg)
            # Don't fail, just warn

        return True, None

    @classmethod
    def reconcile_session(cls) -> dict | None:
        """
        Attempt to reconcile session state from Git branches if session file is missing.

        Returns:
            Reconciled session data or None if reconciliation fails
        """
        logger.info("Attempting to reconcile session from Git state...")

        # List all dev/* branches
        # We target the specific integration branches pattern
        result = subprocess.run(  # noqa: S603
            ["git", "branch", "--list", "dev/session-*/integration"],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            logger.warning("Failed to list Git branches for reconciliation")
            return None

        branches = [b.strip().lstrip("* ") for b in result.stdout.splitlines() if b.strip()]

        if not branches:
            logger.info("No session branches found for reconciliation")
            return None

        # Use the most recent branch (lexicographically last, which works for our timestamp format)
        latest_branch = sorted(branches)[-1]
        # Format: dev/session-{timestamp}/integration
        # Remove prefix "dev/" and suffix "/integration"
        session_id = latest_branch.replace("dev/", "").replace("/integration", "")

        logger.info(f"Reconciled session from branch: {latest_branch}")

        session_data = {
            "session_id": session_id,
            "integration_branch": latest_branch,
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "reconciled": True,
        }

        # Save the reconciled session
        cls.save_session(session_id, latest_branch)

        return session_data

    @classmethod
    def get_integration_branch(cls, session_id: str) -> str:
        """Get integration branch name for session.

        Args:
            session_id: Session identifier

        Returns:
            Integration branch name (e.g., 'dev/session-20251230-120000')
        """
        from ac_cdd_core.config import settings

        return f"{settings.session.integration_branch_prefix}/{session_id}/integration"

    @classmethod
    async def resume_jules_session(cls, session_name: str) -> dict:
        """
        Resumes a Jules session and waits for completion.
        Returns resume_info dict if successful.
        """
        from ac_cdd_core.services.jules_client import JulesClient

        # Normalize session name
        name = session_name if session_name.startswith("sessions/") else f"sessions/{session_name}"

        logger.info(f"Resuming Jules session: {name}")

        jules = JulesClient()
        try:
            result = await jules.wait_for_completion(name)

            if result.get("status") == "success" and result.get("pr_url"):
                resume_info = {
                    "pr_url": result["pr_url"],
                    "jules_session_name": name,
                }
                logger.info(f"Successfully resumed Jules session with PR: {result['pr_url']}")
                return resume_info
            else:
                raise SessionValidationError(
                    "Cannot resume: Jules session not successful or no PR found."
                )
        except Exception as e:
            if isinstance(e, SessionValidationError):
                raise
            raise SessionValidationError(f"Failed to resume Jules session: {e}") from e

    @classmethod
    def load_or_reconcile_session(
        cls,
        session_id: str | None = None,
        auto_reconcile: bool = True,
        resume_info: dict | None = None,
    ) -> SessionInfo:
        """Load session from parameter, file, config, or Git reconciliation.

        Args:
            session_id: Optional explicit session ID
            auto_reconcile: If True, attempt Git reconciliation if session not found
            resume_info: Optional resume info from Jules session (passed from CLI)

        Returns:
            Dict containing session_id, integration_branch, and optional resume_info

        Raises:
            SessionValidationError: If no session can be found
        """
        from ac_cdd_core.config import settings

        # If resuming, we might infer session ID from saved context if not provided
        if resume_info and not session_id:
            saved_session = cls.load_session()
            if saved_session:
                session_id = saved_session["session_id"]
            elif settings.session.session_id:
                session_id = settings.session.session_id
            else:
                # If we are resuming but can't find local context, we might fail
                # or create a new one? Assuming fail based on previous logic.
                raise SessionValidationError(
                    "Cannot resume: No session context found. Provide --session parameter."
                )

        # 1. Use explicit session ID if provided
        if session_id:
            integration_branch = cls.get_integration_branch(session_id)
            return {
                "session_id": session_id,
                "integration_branch": integration_branch,
                "resume_info": resume_info,
            }

        # 2. Try loading from session file
        saved_session = cls.load_session()
        if saved_session:
            return {
                "session_id": saved_session["session_id"],
                "integration_branch": saved_session["integration_branch"],
                "resume_info": resume_info,
            }

        # 3. Try config
        if settings.session.session_id:
            session_id_from_config = settings.session.session_id
            integration_branch = cls.get_integration_branch(session_id_from_config)
            return {
                "session_id": session_id_from_config,
                "integration_branch": integration_branch,
                "resume_info": resume_info,
            }

        # 4. Try Git reconciliation
        if auto_reconcile:
            reconciled = cls.reconcile_session()
            if reconciled:
                return {
                    "session_id": reconciled["session_id"],
                    "integration_branch": reconciled["integration_branch"],
                    "resume_info": resume_info,
                }

        # No session found
        raise SessionValidationError(
            "No session found.\n\n"
            "Recovery options:\n"
            "1. Start a new session:\n"
            "   uv run manage.py gen-cycles\n"
            "2. If you have an existing session, specify it:\n"
            "   uv run manage.py run-cycle --session <session-id>"
        )
