from datetime import datetime, timezone
import pytest
from ac_cdd_core.domain_models import ProjectManifest, CycleManifest

class TestProjectManifest:
    def test_cycle_manifest_defaults(self):
        """Test CycleManifest default values."""
        cycle = CycleManifest(id="01")
        assert cycle.id == "01"
        assert cycle.status == "planned"
        assert cycle.jules_session_id is None
        assert isinstance(cycle.created_at, datetime)
        assert isinstance(cycle.updated_at, datetime)

    def test_project_manifest_serialization(self):
        """Test full ProjectManifest serialization loop."""
        manifest = ProjectManifest(
            project_session_id="test-session-123",
            integration_branch="dev/test/integration",
            cycles=[
                CycleManifest(id="01", status="in_progress", jules_session_id="jules-1"),
                CycleManifest(id="02", status="planned")
            ]
        )

        json_str = manifest.model_dump_json()
        restored = ProjectManifest.model_validate_json(json_str)

        assert restored.project_session_id == "test-session-123"
        assert len(restored.cycles) == 2
        assert restored.cycles[0].jules_session_id == "jules-1"
        assert restored.cycles[1].status == "planned"

    def test_manifest_validation(self):
        """Test validation rules."""
        # Missing required fields
        with pytest.raises(ValueError):
            ProjectManifest(project_session_id="only-id") # Missing integration_branch

        # Invalid cycle status
        with pytest.raises(ValueError):
            CycleManifest(id="01", status="invalid_status")
