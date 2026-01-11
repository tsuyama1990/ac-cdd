"""Tests for StateManager (file-based state management)."""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from ac_cdd_core.domain_models import ProjectManifest, CycleManifest
from ac_cdd_core.state_manager import StateManager
from ac_cdd_core.session_manager import SessionValidationError


class TestStateManager:
    """Test suite for StateManager."""

    @pytest.fixture
    def temp_state_file(self, tmp_path: Path) -> Path:
        """Create a temporary state file path."""
        state_dir = tmp_path / ".ac_cdd"
        state_dir.mkdir(parents=True, exist_ok=True)
        return state_dir / "project_state.json"

    @pytest.fixture
    def manager(self, temp_state_file: Path) -> StateManager:
        """Create StateManager with temporary file."""
        mgr = StateManager()
        mgr.STATE_FILE = temp_state_file
        return mgr

    def test_load_manifest_not_found(self, manager: StateManager, temp_state_file: Path) -> None:
        """Test loading manifest when file doesn't exist."""
        # Ensure file doesn't exist
        if temp_state_file.exists():
            temp_state_file.unlink()
        
        manifest = manager.load_manifest()
        
        assert manifest is None

    def test_save_and_load_manifest(self, manager: StateManager, temp_state_file: Path) -> None:
        """Test saving and loading manifest."""
        # Create manifest
        original = ProjectManifest(
            project_session_id="test-session-123",
            feature_branch="feat/test-branch",
            integration_branch="dev/test-integration",
            cycles=[
                CycleManifest(id="01", status="planned"),
                CycleManifest(id="02", status="planned"),
            ]
        )
        
        # Save
        manager.save_manifest(original)
        
        # Verify file exists
        assert temp_state_file.exists()
        
        # Load
        loaded = manager.load_manifest()
        
        # Verify
        assert loaded is not None
        assert loaded.project_session_id == "test-session-123"
        assert loaded.feature_branch == "feat/test-branch"
        assert loaded.integration_branch == "dev/test-integration"
        assert len(loaded.cycles) == 2
        assert loaded.cycles[0].id == "01"
        assert loaded.cycles[1].id == "02"

    def test_load_manifest_invalid_json(self, manager: StateManager, temp_state_file: Path) -> None:
        """Test loading manifest with invalid JSON."""
        # Write invalid JSON
        temp_state_file.write_text("{invalid json}")
        
        manifest = manager.load_manifest()
        
        assert manifest is None

    def test_load_manifest_missing_required_fields(
        self, manager: StateManager, temp_state_file: Path
    ) -> None:
        """Test loading manifest with missing required fields."""
        # Write JSON missing required fields
        temp_state_file.write_text('{"project_session_id": "test"}')
        
        manifest = manager.load_manifest()
        
        # Should fail validation and return None
        assert manifest is None

    def test_create_manifest(self, manager: StateManager, temp_state_file: Path) -> None:
        """Test creating a new manifest."""
        manifest = manager.create_manifest(
            project_session_id="new-session",
            feature_branch="feat/new-feature",
            integration_branch="dev/new-integration"
        )
        
        # Verify returned manifest
        assert manifest.project_session_id == "new-session"
        assert manifest.feature_branch == "feat/new-feature"
        assert manifest.integration_branch == "dev/new-integration"
        
        # Verify file was created
        assert temp_state_file.exists()
        
        # Verify can be loaded
        loaded = manager.load_manifest()
        assert loaded is not None
        assert loaded.project_session_id == "new-session"

    def test_get_cycle_found(self, manager: StateManager, temp_state_file: Path) -> None:
        """Test getting an existing cycle."""
        # Create manifest with cycles
        manifest = ProjectManifest(
            project_session_id="test",
            feature_branch="feat/test",
            integration_branch="dev/test",
            cycles=[
                CycleManifest(id="01", status="planned"),
                CycleManifest(id="02", status="in_progress"),
            ]
        )
        manager.save_manifest(manifest)
        
        # Get cycle
        cycle = manager.get_cycle("02")
        
        assert cycle is not None
        assert cycle.id == "02"
        assert cycle.status == "in_progress"

    def test_get_cycle_not_found(self, manager: StateManager, temp_state_file: Path) -> None:
        """Test getting a non-existent cycle."""
        # Create manifest with cycles
        manifest = ProjectManifest(
            project_session_id="test",
            feature_branch="feat/test",
            integration_branch="dev/test",
            cycles=[CycleManifest(id="01", status="planned")]
        )
        manager.save_manifest(manifest)
        
        # Get non-existent cycle
        cycle = manager.get_cycle("99")
        
        assert cycle is None

    def test_get_cycle_no_manifest(self, manager: StateManager, temp_state_file: Path) -> None:
        """Test getting cycle when no manifest exists."""
        cycle = manager.get_cycle("01")
        
        assert cycle is None

    def test_update_cycle_state(self, manager: StateManager, temp_state_file: Path) -> None:
        """Test updating cycle state."""
        # Create manifest
        manifest = ProjectManifest(
            project_session_id="test",
            feature_branch="feat/test",
            integration_branch="dev/test",
            cycles=[
                CycleManifest(id="01", status="planned"),
                CycleManifest(id="02", status="planned"),
            ]
        )
        manager.save_manifest(manifest)
        
        # Update cycle
        manager.update_cycle_state("01", status="in_progress", jules_session_id="session-123")
        
        # Verify update
        loaded = manager.load_manifest()
        assert loaded is not None
        cycle = next(c for c in loaded.cycles if c.id == "01")
        assert cycle.status == "in_progress"
        assert cycle.jules_session_id == "session-123"
        
        # Verify other cycle unchanged
        cycle2 = next(c for c in loaded.cycles if c.id == "02")
        assert cycle2.status == "planned"

    def test_update_cycle_state_no_manifest(
        self, manager: StateManager, temp_state_file: Path
    ) -> None:
        """Test updating cycle when no manifest exists."""
        with pytest.raises(SessionValidationError, match="No active project manifest"):
            manager.update_cycle_state("01", status="in_progress")

    def test_update_cycle_state_cycle_not_found(
        self, manager: StateManager, temp_state_file: Path
    ) -> None:
        """Test updating non-existent cycle."""
        # Create manifest
        manifest = ProjectManifest(
            project_session_id="test",
            feature_branch="feat/test",
            integration_branch="dev/test",
            cycles=[CycleManifest(id="01", status="planned")]
        )
        manager.save_manifest(manifest)
        
        # Try to update non-existent cycle
        with pytest.raises(SessionValidationError, match="Cycle 99 not found"):
            manager.update_cycle_state("99", status="in_progress")

    def test_manifest_updates_timestamp(
        self, manager: StateManager, temp_state_file: Path
    ) -> None:
        """Test that saving updates the timestamp."""
        from datetime import datetime, UTC
        
        # Create and save manifest
        manifest = ProjectManifest(
            project_session_id="test",
            feature_branch="feat/test",
            integration_branch="dev/test",
        )
        
        # Save
        manager.save_manifest(manifest)
        
        # Load and check timestamp
        loaded = manager.load_manifest()
        assert loaded is not None
        assert loaded.last_updated is not None
        
        # Timestamp should be recent (within last minute)
        now = datetime.now(UTC)
        time_diff = (now - loaded.last_updated).total_seconds()
        assert time_diff < 60  # Less than 1 minute

    def test_file_permissions(self, manager: StateManager, temp_state_file: Path) -> None:
        """Test that state file is created with correct permissions."""
        manifest = ProjectManifest(
            project_session_id="test",
            feature_branch="feat/test",
            integration_branch="dev/test",
        )
        
        manager.save_manifest(manifest)
        
        # Verify file is readable
        assert temp_state_file.exists()
        assert temp_state_file.is_file()
        
        # Verify content is valid JSON
        content = temp_state_file.read_text()
        data = json.loads(content)
        assert data["project_session_id"] == "test"

    def test_concurrent_updates(self, manager: StateManager, temp_state_file: Path) -> None:
        """Test that updates don't corrupt the file."""
        # Create initial manifest
        manifest = ProjectManifest(
            project_session_id="test",
            feature_branch="feat/test",
            integration_branch="dev/test",
            cycles=[
                CycleManifest(id="01", status="planned"),
                CycleManifest(id="02", status="planned"),
            ]
        )
        manager.save_manifest(manifest)
        
        # Multiple updates
        manager.update_cycle_state("01", status="in_progress")
        manager.update_cycle_state("02", status="in_progress")
        manager.update_cycle_state("01", status="completed")
        
        # Verify final state
        loaded = manager.load_manifest()
        assert loaded is not None
        cycle1 = next(c for c in loaded.cycles if c.id == "01")
        cycle2 = next(c for c in loaded.cycles if c.id == "02")
        assert cycle1.status == "completed"
        assert cycle2.status == "in_progress"
