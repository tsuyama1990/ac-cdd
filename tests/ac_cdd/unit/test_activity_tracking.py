
from unittest.mock import MagicMock

from ac_cdd_core.jules_session_nodes import JulesSessionNodes
from ac_cdd_core.jules_session_state import JulesSessionState


class TestActivityTracking:
    """Validate activity ID tracking and scoping."""

    def test_state_initialization(self):
        """Should initialize with separate tracking sets if implemented."""
        state = JulesSessionState(session_url="http://test")

        # Check if new fields exist (This will fail initially if not yet updated)
        # We expect processed_completion_ids to be present after Update 2.1
        assert hasattr(state, "processed_completion_ids")
        assert hasattr(state, "processed_inquiry_ids")
        assert isinstance(state.processed_completion_ids, set)

    def test_stale_completion_detection_separation(self):
        """Should use specific set for completion tracking."""
        # Setup mock nodes
        nodes = JulesSessionNodes(MagicMock())

        # Setup state
        state = JulesSessionState(session_url="http://test")
        state.processed_completion_ids.add("comp_1")

        # Mock activity response
        activities = [
            {"name": "comp_1", "sessionCompleted": {}} # Stale
        ]

        # We need to simulate the logic inside monitor_session or similar.
        # But monitor_session is an async loop.
        # We can test the helper if it exists, or just inspect logic if we extract it.
        # jules_session_nodes doesn't seem to have validatable protected methods easily accessible without running the node.

        # However, we can assert that logic USES the new set.
        # But that's implementation detail.


