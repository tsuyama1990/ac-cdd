from unittest.mock import MagicMock

import pytest
from ac_cdd_core.domain_models import AuditResult
from ac_cdd_core.enums import FlowStatus
from ac_cdd_core.graph_nodes import CycleNodes
from ac_cdd_core.state import CycleState


@pytest.mark.asyncio
async def test_committee_logic_flow() -> None:
    # Mock settings
    mock_settings = MagicMock()
    mock_settings.NUM_AUDITORS = 3
    mock_settings.REVIEWS_PER_AUDITOR = 2

    # Instantiate nodes with mocks
    sandbox = MagicMock()
    jules = MagicMock()

    # We need to patch where settings is used.
    # graph_nodes.py does `from .config import settings` at top level.
    # So we must patch ac_cdd_core.graph_nodes.settings
    with pytest.MonkeyPatch.context() as m:
        m.setattr("ac_cdd_core.services.committee_usecase.settings", mock_settings)

        nodes = CycleNodes(sandbox, jules)

        # --- Scenario 1: All Approved (Happy Path) ---
        # Auditor 1: Approved
        state = CycleState(cycle_id="1", current_auditor_index=1, current_auditor_review_count=1)
        state.audit_result = AuditResult(
            status="APPROVED", is_approved=True, reason="OK", feedback="LGTM"
        )

        res = await nodes.committee_manager_node(state)
        assert res["status"] == FlowStatus.NEXT_AUDITOR
        assert res["current_auditor_index"] == 2
        assert res["current_auditor_review_count"] == 1

        # Check routing
        route = nodes.route_committee(CycleState(cycle_id="r", status=FlowStatus.NEXT_AUDITOR))
        assert route == "auditor"

        # Auditor 2: Approved
        state.current_auditor_index = 2
        res = await nodes.committee_manager_node(state)
        assert res["status"] == FlowStatus.NEXT_AUDITOR
        assert res["current_auditor_index"] == 3

        # Auditor 3: Approved (Last one)
        state.current_auditor_index = 3
        res = await nodes.committee_manager_node(state)
        assert res["status"] == FlowStatus.CYCLE_APPROVED

        # Check routing - Expecting 'uat_evaluate' per requirements
        route = nodes.route_committee(CycleState(cycle_id="r", status=FlowStatus.CYCLE_APPROVED))
        assert route == "uat_evaluate"

        # --- Scenario 2: Rejected & Retry (Loop Back) ---
        # Auditor 2: Rejected (Attempt 1 of 2)
        state = CycleState(
            cycle_id="2", current_auditor_index=2, current_auditor_review_count=1, iteration_count=5
        )
        state.audit_result = AuditResult(
            status="REJECTED", is_approved=False, reason="Issues found", feedback="Fix this"
        )

        res = await nodes.committee_manager_node(state)
        assert res["status"] == FlowStatus.RETRY_FIX
        assert res["current_auditor_review_count"] == 2
        assert res["iteration_count"] == 6  # Should increment iteration

        route = nodes.route_committee(CycleState(cycle_id="r", status=FlowStatus.RETRY_FIX))
        assert route == "coder_session"

        # --- Scenario 3: Max Retries Exceeded (Pipeline Handover) ---
        # Auditor 2: Rejected (Attempt 2 of 2) -> Should move to Auditor 3
        state = CycleState(
            cycle_id="3",
            current_auditor_index=2,
            current_auditor_review_count=2,
            iteration_count=10,
        )
        state.audit_result = AuditResult(
            status="REJECTED", is_approved=False, reason="Still bad", feedback="Still broken"
        )

        res = await nodes.committee_manager_node(state)
        # Old behavior: assert res["status"] == "failed"
        # New behavior: Handover to Auditor 3
        assert res["status"] == FlowStatus.RETRY_FIX
        assert res["current_auditor_index"] == 3
        assert res["current_auditor_review_count"] == 1
        assert res["iteration_count"] == 11

        route = nodes.route_committee(CycleState(cycle_id="r", status=FlowStatus.RETRY_FIX))
        assert route == "coder_session"


@pytest.mark.asyncio
async def test_committee_pipeline_handover() -> None:
    """Test pipeline handover: when review limit reached, move to next auditor."""
    # Mock settings: 2 Auditors × 1 Review each (small for testing)
    mock_settings = MagicMock()
    mock_settings.NUM_AUDITORS = 2
    mock_settings.REVIEWS_PER_AUDITOR = 1

    sandbox = MagicMock()
    jules = MagicMock()

    with pytest.MonkeyPatch.context() as m:
        m.setattr("ac_cdd_core.services.committee_usecase.settings", mock_settings)
        nodes = CycleNodes(sandbox, jules)

        # Scenario 1: Auditor 1 (Rev 1/Limit) → Reject → Handover to Auditor 2
        state = CycleState(
            cycle_id="handover-1",
            current_auditor_index=1,
            current_auditor_review_count=1,
            iteration_count=0,
        )
        state.audit_result = AuditResult(
            status="REJECTED", is_approved=False, reason="Issues found", feedback="Fix these issues"
        )

        res = await nodes.committee_manager_node(state)

        # Should move to Auditor 2 (not fail)
        assert res["status"] == FlowStatus.RETRY_FIX
        assert res["current_auditor_index"] == 2
        assert res["current_auditor_review_count"] == 1
        assert res["iteration_count"] == 1
        assert "final_fix" not in res or res.get("final_fix") is False

        # Scenario 2: Auditor 2 (Rev 1/Limit) → Reject → Final Fix
        state = CycleState(
            cycle_id="handover-2",
            current_auditor_index=2,
            current_auditor_review_count=1,
            iteration_count=1,
        )
        state.audit_result = AuditResult(
            status="REJECTED",
            is_approved=False,
            reason="Still issues",
            feedback="More fixes needed",
        )

        res = await nodes.committee_manager_node(state)

        # Should set final_fix and prepare for merge
        assert res["status"] == FlowStatus.RETRY_FIX
        assert res["final_fix"] is True
        assert res["iteration_count"] == 2

        # Verify check_coder_outcome returns "completed" for final_fix
        state_with_final_fix = CycleState(cycle_id="test", final_fix=True)
        outcome = nodes.check_coder_outcome(state_with_final_fix)
        assert outcome == FlowStatus.COMPLETED.value
