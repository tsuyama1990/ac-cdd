"""Session management utilities for AC-CDD."""

import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ac_cdd_core.domain_models import CycleManifest, ProjectManifest
from ac_cdd_core.utils import logger


class SessionValidationError(Exception):
    """Raised when session validation fails."""


class SessionManager:
    """Manages session persistence using a unified project manifest."""

    MANIFEST_PATH = Path("dev_documents/project_state.json")

    def __init__(self) -> None:
        self.MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)

    def load_manifest(self) -> ProjectManifest | None:
        """Loads manifest from JSON. Returns None if it doesn't exist or is invalid."""
        if not self.MANIFEST_PATH.exists():
            return None

        try:
            content = self.MANIFEST_PATH.read_text(encoding="utf-8")
            data = json.loads(content)
            return ProjectManifest(**data)
        except (OSError, json.JSONDecodeError, Exception) as e:
            logger.error(f"Failed to load project manifest: {e}")
            return None

    def save_manifest(self, manifest: ProjectManifest, commit_msg: str | None = None) -> None:
        """Saves manifest to JSON. If commit_msg is provided, performs git add/commit."""
        try:
            # Atomic write
            manifest.last_updated = datetime.now(UTC)
            temp_path = self.MANIFEST_PATH.with_suffix(".tmp")
            temp_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
            shutil.move(str(temp_path), str(self.MANIFEST_PATH))

            if commit_msg:
                self._commit_manifest(commit_msg)
        except Exception as e:
            logger.exception(f"Failed to save manifest: {e}")
            raise

    def create_manifest(self, project_session_id: str, integration_branch: str) -> ProjectManifest:
        """Creates and saves a new project manifest."""
        manifest = ProjectManifest(
            project_session_id=project_session_id, integration_branch=integration_branch
        )
        self.save_manifest(
            manifest, commit_msg=f"Initialize project state for session {project_session_id}"
        )
        return manifest

    def get_cycle(self, cycle_id: str) -> CycleManifest | None:
        """Helper to get a specific cycle from the manifest."""
        manifest = self.load_manifest()
        if not manifest:
            return None

        for cycle in manifest.cycles:
            if cycle.id == cycle_id:
                return cycle
        return None

    def update_cycle_state(self, cycle_id: str, **kwargs: Any) -> None:
        """
        Updates specific fields of a cycle and saves the manifest.

        Example: update_cycle_state("01", status="in_progress", jules_session_id="...")
        """
        manifest = self.load_manifest()
        if not manifest:
            msg = "No active project manifest found."
            raise SessionValidationError(msg)

        cycle = next((c for c in manifest.cycles if c.id == cycle_id), None)
        if not cycle:
            msg = f"Cycle {cycle_id} not found in manifest."
            raise SessionValidationError(msg)

        updated = False
        for key, value in kwargs.items():
            if hasattr(cycle, key):
                setattr(cycle, key, value)
                updated = True

        if updated:
            cycle.updated_at = datetime.now(UTC)
            # If crucial fields like jules_session_id or status are updated, we might want to commit
            commit_msg = None
            if "jules_session_id" in kwargs or "status" in kwargs:
                commit_msg = f"Update cycle {cycle_id} state: {kwargs.get('status', 'update')}"

            self.save_manifest(manifest, commit_msg=commit_msg)

    def _commit_manifest(self, message: str) -> None:
        """Commits the manifest file to git."""
        try:
            # Stage the file
            subprocess.run(  # noqa: S603
                ["git", "add", str(self.MANIFEST_PATH)],  # noqa: S607
                check=True,
                capture_output=True,
            )
            # Commit
            subprocess.run(  # noqa: S603
                ["git", "commit", "-m", f"chore(state): {message}"],  # noqa: S607
                check=False,  # Don't fail if nothing to commit
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to commit project manifest: {e}")

    # --- Backward Compatibility / Helper Methods (Optional but useful for existing calls) ---

    @classmethod
    def get_active_session_id(cls) -> str | None:
        """Static helper to get current session ID."""
        mgr = cls()
        manifest = mgr.load_manifest()
        return manifest.project_session_id if manifest else None

    @classmethod
    def clear_session(cls) -> None:
        """Deletes the manifest file (equivalent to clearing session)."""
        if cls.MANIFEST_PATH.exists():
            cls.MANIFEST_PATH.unlink()
