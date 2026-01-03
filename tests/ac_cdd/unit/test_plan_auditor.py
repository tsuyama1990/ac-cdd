from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ac_cdd_core.domain_models import PlanAuditResult
from ac_cdd_core.services.plan_auditor import PlanAuditor


@pytest.fixture
def mock_agent() -> Generator[MagicMock, None, None]:
    with patch("ac_cdd_core.services.plan_auditor.Agent") as mock_agent_cls:
        mock_instance = mock_agent_cls.return_value
        yield mock_instance


@pytest.fixture
def plan_auditor(mock_agent: MagicMock) -> PlanAuditor:  # noqa: ARG001
    return PlanAuditor()


@pytest.mark.asyncio
async def test_audit_plan_approved(plan_auditor: PlanAuditor, mock_agent: MagicMock) -> None:
    # Setup mock response
    expected_result = PlanAuditResult(status="APPROVED", reason="Plan looks good", feedback="")
    # The run method returns a RunResult which has a .data attribute
    mock_run_result = MagicMock()
    mock_run_result.data = expected_result
    mock_agent.run = AsyncMock(return_value=mock_run_result)

    plan_details = {"planId": "123", "steps": [{"id": "1", "description": "Do stuff"}]}
    spec_context = {"SPEC.md": "Requirements"}

    result = await plan_auditor.audit_plan(plan_details, spec_context)

    assert result.status == "APPROVED"
    assert result.reason == "Plan looks good"
    mock_agent.run.assert_called_once()


@pytest.mark.asyncio
async def test_audit_plan_rejected(plan_auditor: PlanAuditor, mock_agent: MagicMock) -> None:
    expected_result = PlanAuditResult(status="REJECTED", reason="Bad plan", feedback="Fix it")
    mock_run_result = MagicMock()
    mock_run_result.data = expected_result
    mock_agent.run = AsyncMock(return_value=mock_run_result)

    plan_details = {"planId": "123", "steps": []}
    spec_context = {}

    result = await plan_auditor.audit_plan(plan_details, spec_context)

    assert result.status == "REJECTED"
    assert result.feedback == "Fix it"
