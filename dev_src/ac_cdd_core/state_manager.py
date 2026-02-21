"""State management using local JSON file."""

import contextlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .domain_models import CycleManifest, ProjectManifest
from .session_manager import SessionValidationError

logger = logging.getLogger(__name__)


class StateManager:
    """
    Manages project state using a local JSON file.

    This replaces the previous Git orphan branch approach with a simple
    file-based solution that is easier to debug and faster to access.
    """

    def __init__(self, project_root: str = ".") -> None:
        self.root = Path(project_root)
        self.STATE_DIR = self.root / ".ac_cdd"
        self.STATE_FILE = self.STATE_DIR / "project_state_local.json"
        
        # Migration: Rename old file if it exists and new one doesn't
        old_state_file = self.STATE_DIR / "project_state.json"
        if old_state_file.exists() and not self.STATE_FILE.exists():
            try:
                # Rename/Move the file
                old_state_file.rename(self.STATE_FILE)
                logger.info(f"Migrated project state to {self.STATE_FILE}")
            except Exception as e:
                logger.warning(f"Failed to migrate project state file: {e}")

    def load_manifest(self) -> ProjectManifest | None:
        """
        Load project manifest from local file.

        Returns:
            ProjectManifest if file exists and is valid, None otherwise.
        """
        if not self.STATE_FILE.exists():
            return None

        try:
            data = json.loads(self.STATE_FILE.read_text())
            return ProjectManifest(**data)
        except (json.JSONDecodeError, ValueError, TypeError):
            logger.exception("Failed to load project manifest")
            return None
        except Exception:
            logger.exception("Unexpected error loading manifest")
            return None

    def save_manifest(self, manifest: ProjectManifest) -> None:
        """
        Save project manifest to local file.

        Args:
            manifest: ProjectManifest to save.

        Raises:
            Exception: If save fails.
        """
        try:
            # Ensure directory exists
            self.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

            # Update timestamp
            manifest.last_updated = datetime.now(UTC)

            # Write to file
            self.STATE_FILE.write_text(manifest.model_dump_json(indent=2))

            # Fix permissions to allow host user editing (essential for Docker usage)
            with contextlib.suppress(Exception):
                self.STATE_FILE.chmod(0o666)

            logger.debug(f"Saved manifest to {self.STATE_FILE}")
        except Exception:
            logger.exception("Failed to save manifest")
            raise

    def create_manifest(
        self, project_session_id: str, feature_branch: str, integration_branch: str
    ) -> ProjectManifest:
        """
        Create and save a new project manifest.

        Args:
            project_session_id: Unique session identifier.
            feature_branch: Main development branch name.
            integration_branch: Final integration branch name.

        Returns:
            Created ProjectManifest.
        """
        manifest = ProjectManifest(
            project_session_id=project_session_id,
            feature_branch=feature_branch,
            integration_branch=integration_branch,
        )
        self.save_manifest(manifest)
        return manifest

    def _normalize_id(self, cycle_id: str | int) -> str:
        """Normalizes cycle ID to 2-digit string (e.g., '1' -> '01')."""
        cid = str(cycle_id)
        if cid.isdigit() and len(cid) == 1:
            return f"0{cid}"
        return cid

    def get_cycle(self, cycle_id: str) -> CycleManifest | None:
        """
        Get a specific cycle from the manifest.

        Args:
            cycle_id: Cycle identifier (e.g., "01", "02").

        Returns:
            CycleManifest if found, None otherwise.
        """
        manifest = self.load_manifest()
        if not manifest:
            return None

        normalized_id = self._normalize_id(cycle_id)
        for cycle in manifest.cycles:
            if cycle.id in (cycle_id, normalized_id):
                return cycle
        return None

    def update_cycle_state(self, cycle_id: str, **kwargs: Any) -> None:
        """
        Update specific fields of a cycle and save immediately.

        Args:
            cycle_id: Cycle identifier.
            **kwargs: Fields to update (e.g., status="in_progress").

        Raises:
            SessionValidationError: If manifest or cycle not found.

        Example:
            manager.update_cycle_state("01", status="in_progress", jules_session_id="...")
        """
        manifest = self.load_manifest()
        if not manifest:
            msg = "No active project manifest found."
            raise SessionValidationError(msg)

        normalized_id = self._normalize_id(cycle_id)
        cycle = next(
            (c for c in manifest.cycles if c.id in (cycle_id, normalized_id)),
            None,
        )
        if not cycle:
            msg = f"Cycle {cycle_id} not found in manifest."
            raise SessionValidationError(msg)

        # Update fields
        for key, value in kwargs.items():
            if hasattr(cycle, key):
                setattr(cycle, key, value)

        # Update timestamp
        cycle.updated_at = datetime.now(UTC)

        # Save
        self.save_manifest(manifest)

        logger.info(f"Updated cycle {cycle_id}: {kwargs}")

    def update_project_state(self, **kwargs: Any) -> None:
        """
        Update root-level fields of the project manifest and save immediately.

        Args:
            **kwargs: Fields to update (e.g., qa_session_id="...").

        Raises:
            SessionValidationError: If manifest not found.
        """
        manifest = self.load_manifest()
        if not manifest:
            msg = "No active project manifest found."
            raise SessionValidationError(msg)

        # Update fields
        for key, value in kwargs.items():
            if hasattr(manifest, key):
                setattr(manifest, key, value)
            else:
                logger.warning(f"Attempted to update unknown manifest field: {key}")

        # Update timestamp
        manifest.last_updated = datetime.now(UTC)

        # Save
        self.save_manifest(manifest)

        logger.info(f"Updated project state: {kwargs}")
