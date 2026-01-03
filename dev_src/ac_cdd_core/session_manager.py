"""Session management utilities for AC-CDD."""

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

from ac_cdd_core.utils import logger


class SessionValidationError(Exception):
    """Raised when session validation fails."""



class SessionInfo(TypedDict, total=False):
    project_session_id: str
    integration_branch: str
    agent_session_id: str | None
    active_cycle_id: str | None
    resume_info: dict[str, Any] | None


class SessionManager:
    """Manages session persistence for AC-CDD development sessions."""

    SESSION_FILE = Path(".ac_cdd_session.json")

    @classmethod
    def save_session(cls, project_session_id: str, integration_branch: str) -> None:
        """Save session information to file."""
        session_data = {
            "project_session_id": project_session_id,
            "integration_branch": integration_branch,
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
        }
        cls.SESSION_FILE.write_text(json.dumps(session_data, indent=2))
        logger.info(f"Session saved: {project_session_id}")

    @classmethod
    def update_session(cls, **kwargs: Any) -> None:
        """
        Update existing session file with new data.
        Preserves existing keys not in kwargs.
        """
        if not cls.SESSION_FILE.exists():
            logger.warning("Cannot update session: File does not exist.")
            return

        try:
            data = json.loads(cls.SESSION_FILE.read_text())
            data.update(kwargs)
            data["last_updated"] = datetime.now().isoformat()
            cls.SESSION_FILE.write_text(json.dumps(data, indent=2))
            logger.info(f"Session updated with keys: {list(kwargs.keys())}")
        except Exception as e:
            logger.error(f"Failed to update session: {e}")

    @classmethod
    def load_session(cls) -> dict[str, Any] | None:
        """Load session information from file."""
        if cls.SESSION_FILE.exists():
            try:
                data: dict[str, Any] = json.loads(cls.SESSION_FILE.read_text())
                logger.info(f"Session loaded: {data.get('project_session_id')}")
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
    def validate_session(cls, project_session_id: str, integration_branch: str) -> tuple[bool, str | None]:
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
            # Local missing? Check Remote explicitly before failing
            remote_check = subprocess.run(  # noqa: S603
                ["git", "ls-remote", "--heads", "origin", integration_branch],  # noqa: S607
                capture_output=True,
                check=False,
            )

            if remote_check.returncode == 0 and remote_check.stdout.strip():
                # Found on remote! Fetch it.
                logger.info(f"Branch {integration_branch} found on remote. Fetching...")
                fetch_res = subprocess.run(  # noqa: S603
                    [
                        "git",
                        "fetch",
                        "origin",
                        f"{integration_branch}:{integration_branch}",
                    ],
                    capture_output=True,
                    check=False,
                )
                if fetch_res.returncode == 0:
                    return True, None
                logger.error(f"Failed to fetch branch: {fetch_res.stderr.decode()}")

            from ac_cdd_core.error_messages import RecoveryMessages

            error_msg = f"Session validation failed: {RecoveryMessages.branch_not_found(integration_branch, str(cls.SESSION_FILE))}"
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
    def reconcile_session(cls) -> dict[str, Any] | None:
        """
        Attempt to reconcile session state from Git branches if session file is missing.

        Returns:
            Reconciled session data or None if reconciliation fails
        """
        logger.info("Attempting to reconcile session from Git state...")

        # List all dev/* branches
        # We target the specific integration branches pattern
        result = subprocess.run(
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
            "project_session_id": session_id,
            "integration_branch": latest_branch,
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "reconciled": True,
        }

        # Save the reconciled session
        cls.save_session(session_id, latest_branch)

        return session_data

    @classmethod
    def get_integration_branch(cls, project_session_id: str) -> str:
        """Get integration branch name for session.

        Args:
            project_session_id: Session identifier

        Returns:
            Integration branch name (e.g., 'dev/session-20251230-120000')
        """
        from ac_cdd_core.config import settings

        return f"{settings.session.integration_branch_prefix}/{project_session_id}/integration"

    @classmethod
    async def resume_jules_session(cls, session_name: str | None = None) -> dict[str, Any]:
        """
        Resumes a Jules session and waits for completion.
        If session_name is None, attempts to load it from the session file.
        Returns resume_info dict if successful.
        """
        from ac_cdd_core.services.jules_client import JulesClient

        if not session_name:
            # Try to load from persisted session
            session_data = cls.load_session()
            if session_data:
                session_name = session_data.get("agent_session_id")

        if not session_name:
            raise SessionValidationError(
                "Cannot resume: No Jules Session ID provided or found in file."
            )

        # Normalize session name
        name = session_name if session_name.startswith("sessions/") else f"sessions/{session_name}"

        logger.info(f"Resuming Jules session: {name}")

        jules = JulesClient()
        try:
            result = await jules.wait_for_completion(name)

            # We accept success OR just completion if we simply want to resume control context
            if result.get("status") == "success":
                resume_info = {
                    "pr_url": result.get(
                        "pr_url"
                    ),  # Might be None if manually completed without PR
                    "jules_session_name": name,
                }
                if result.get("pr_url"):
                    logger.info(f"Successfully resumed Jules session with PR: {result['pr_url']}")
                else:
                    logger.info(
                        "Resumed Jules session completed successfully (No PR URL potentially)."
                    )
                return resume_info
            raise SessionValidationError(
                f"Cannot resume: Jules session ended with status: {result.get('status')}"
            )
        except Exception as e:
            if isinstance(e, SessionValidationError):
                raise
            raise SessionValidationError(f"Failed to resume Jules session: {e}") from e

    @classmethod
    def load_or_reconcile_session(
        cls,
        project_session_id: str | None = None,
        auto_reconcile: bool = True,
        resume_info: dict | None = None,
        override_branch: str | None = None,
    ) -> SessionInfo:
        """Load session from parameter, file, config, or Git reconciliation.

        Args:
            project_session_id: Optional explicit session ID
            auto_reconcile: If True, attempt Git reconciliation if session not found
            resume_info: Optional resume info from Jules session (passed from CLI)
            override_branch: Optional branch name to force usage of

        Returns:
            Dict containing session_id, integration_branch, and optional resume_info

        Raises:
            SessionValidationError: If no session can be found
        """
        from ac_cdd_core.config import settings

        # Handle Branch Override FIRST
        # If provided, it updates persistent state if session exists
        if override_branch:
             cls.update_session(integration_branch=override_branch)

        # If resuming, we might infer session ID from saved context if not provided
        if resume_info and not project_session_id:
            saved_session = cls.load_session()
            if saved_session:
                project_session_id = saved_session["project_session_id"]
            elif settings.session.session_id:
                project_session_id = settings.session.session_id
            else:
                # If we are resuming but can't find local context, we might fail
                # or create a new one? Assuming fail based on previous logic.
                raise SessionValidationError(
                    "Cannot resume: No session context found. Provide --session parameter."
                )

        # 1. Use explicit session ID if provided
        if project_session_id:
            if override_branch:
                integration_branch = override_branch
            else:
                integration_branch = cls.get_integration_branch(project_session_id)

            return {
                "project_session_id": project_session_id,
                "integration_branch": integration_branch,
                "resume_info": resume_info,
            }

        # 2. Try loading from session file
        saved_session = cls.load_session()
        if saved_session:
            return {
                "project_session_id": saved_session["project_session_id"],
                "integration_branch": override_branch or saved_session["integration_branch"],
                "agent_session_id": saved_session.get("agent_session_id"),
                "active_cycle_id": saved_session.get("active_cycle_id"),
                "resume_info": resume_info,
            }

        # 3. Try config
        if settings.session.session_id:
            session_id_from_config = settings.session.session_id
            integration_branch = cls.get_integration_branch(session_id_from_config)
            return {
                "project_session_id": session_id_from_config,
                "integration_branch": integration_branch,
                "resume_info": resume_info,
            }

        # 4. Try Git reconciliation
        if auto_reconcile:
            reconciled = cls.reconcile_session()
            if reconciled:
                return {
                    "project_session_id": str(reconciled["project_session_id"]),
                    "integration_branch": str(reconciled["integration_branch"]),
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
