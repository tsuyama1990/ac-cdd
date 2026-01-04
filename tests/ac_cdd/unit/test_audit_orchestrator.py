from unittest.mock import AsyncMock, patch

import pytest
from ac_cdd_core.domain_models import PlanAuditResult
from ac_cdd_core.services.audit_orchestrator import AuditOrchestrator


@pytest.fixture
def mock_jules():
    with patch("ac_cdd_core.services.audit_orchestrator.JulesClient") as MockJules:
        instance = MockJules.return_value
        instance.run_session = AsyncMock(
            return_value={"session_name": "sess-1", "status": "running"}
        )
        instance.wait_for_activity_type = AsyncMock()
        instance.approve_plan = AsyncMock()
        instance._send_message = AsyncMock()
        instance.send_message = AsyncMock()
        instance.wait_for_completion = AsyncMock(return_value={"pr_url": "http://pr"})
        instance.get_latest_plan = AsyncMock()
        yield instance


@pytest.fixture
def mock_auditor():
    with patch("ac_cdd_core.services.audit_orchestrator.PlanAuditor") as MockAuditor:
        instance = MockAuditor.return_value
        instance.audit_plan = AsyncMock()
        yield instance


@pytest.fixture
def orchestrator(mock_jules, mock_auditor):
    return AuditOrchestrator()


@pytest.mark.asyncio
async def test_run_session_approved_first_try(orchestrator, mock_jules, mock_auditor) -> None:
    # Setup happy path
    mock_jules.wait_for_activity_type.return_value = {
        "planGenerated": {"planId": "plan-1", "steps": []}
    }
    mock_auditor.audit_plan.return_value = PlanAuditResult(
        status="APPROVED", reason="Good", feedback=""
    )

    result = await orchestrator.run_interactive_session("prompt", "source", {"spec": "data"})

    assert result["pr_url"] == "http://pr"
    mock_jules.approve_plan.assert_called_with("sess-1", "plan-1")
    mock_jules.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_run_session_rejected_then_approved(orchestrator, mock_jules, mock_auditor) -> None:
    # First plan: Rejected
    # Second plan: Approved

    # 1. wait_for_activity_type returns the first plan initially
    mock_jules.wait_for_activity_type.return_value = {
        "planGenerated": {"planId": "plan-1", "steps": []}
    }

    # 2. get_latest_plan returns the NEW plan when polled after rejection
    mock_jules.get_latest_plan.side_effect = [
        {"planId": "plan-1"},  # First poll, still old
        {"planId": "plan-2", "steps": []},  # Second poll, new plan!
    ]

    # 3. audit_plan responses
    mock_auditor.audit_plan.side_effect = [
        PlanAuditResult(status="REJECTED", reason="Bad", feedback="Fix X"),
        PlanAuditResult(status="APPROVED", reason="Good", feedback=""),
    ]

    # Note: wait_for_activity_type is called in loop start.
    # In the second iteration of loop, it's called again.
    # We need to ensure it returns plan-2 details then.
    mock_jules.wait_for_activity_type.side_effect = [
        {"planGenerated": {"planId": "plan-1", "steps": []}},
        {"planGenerated": {"planId": "plan-2", "steps": []}},
    ]

    await orchestrator.run_interactive_session("prompt", "source", {"spec": "data"})

    # Check that we sent feedback
    mock_jules.send_message.assert_called_once()
    assert "Fix X" in mock_jules.send_message.call_args[0][1]

    # Check that we eventually approved plan-2
    mock_jules.approve_plan.assert_called_with("sess-1", "plan-2")


@pytest.mark.asyncio
async def test_max_retries_exceeded(orchestrator, mock_jules, mock_auditor) -> None:
    mock_jules.wait_for_activity_type.return_value = {
        "planGenerated": {"planId": "plan-1", "steps": []}
    }
    mock_jules.get_latest_plan.return_value = {"planId": "plan-new"}  # Always find new plan quickly

    # Always reject
    mock_auditor.audit_plan.return_value = PlanAuditResult(
        status="REJECTED", reason="Bad", feedback="Fix"
    )

    with pytest.raises(RuntimeError, match="Max audit retries exceeded"):
        await orchestrator.run_interactive_session("prompt", "source", {}, max_retries=1)

    assert mock_jules.send_message.call_count == 1
