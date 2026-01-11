"""State management using local JSON file."""
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

    STATE_FILE = Path(".ac_cdd/project_state.json")

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
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.error(f"Failed to load project manifest: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error loading manifest: {e}")
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
            
            logger.debug(f"Saved manifest to {self.STATE_FILE}")
        except Exception as e:
            logger.exception(f"Failed to save manifest: {e}")
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

        for cycle in manifest.cycles:
            if cycle.id == cycle_id:
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

        cycle = next((c for c in manifest.cycles if c.id == cycle_id), None)
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
