from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from ac_cdd_core.graph import GraphBuilder
from ac_cdd_core.state import CycleState


@pytest.mark.asyncio
async def test_audit_rejection_loop() -> None:
    """
    Test that the audit loop functions correctly when changes are requested.
    Verifies that the graph iterates through 3 auditors * 2 reviews each = 6 cycles.
    """
    # Mock Services
    mock_services = MagicMock()
    mock_services.git = AsyncMock()
    mock_services.jules = AsyncMock()  # JulesClient is async
    mock_services.sandbox = MagicMock()
    mock_services.reviewer = MagicMock()
    
    # Mock Git to return a unique commit each time to simulate a new Jules commit
    commit_counter = [0]
    async def mock_get_commit() -> str:
        commit_counter[0] += 1
        return f"commit_{commit_counter[0]}"
        
    mock_services.git.get_current_commit = AsyncMock(side_effect=mock_get_commit)
    # The auditor needs changed files to proceed
    mock_services.git.get_changed_files = AsyncMock(return_value=["file.py"])

    # Mock Jules run session
    mock_services.jules.run_session = AsyncMock(return_value={"pr_url": "http://pr"})
    mock_services.jules.continue_session = AsyncMock(return_value={"pr_url": "http://pr"})

    # Mock Sandbox
    mock_services.sandbox.run_lint_check = AsyncMock(return_value=(True, "OK"))

    # Mock Reviewer
    mock_services.reviewer.review_code = AsyncMock(return_value="CHANGES_REQUESTED: Please fix X.")

    # Mock PlanAuditor to avoid model initialization
    from unittest.mock import patch
    from ac_cdd_core.domain_models import AuditResult

    mock_auditor = MagicMock()
    async def mock_run_audit(*args: Any, **kwargs: Any) -> tuple[AuditResult, str]:
        print(f"DEBUG run_audit mock called")
        return (AuditResult(is_approved=False), "Feedback")
        
    mock_auditor.run_audit = AsyncMock(side_effect=mock_run_audit)
    with patch("ac_cdd_core.services.plan_auditor.PlanAuditor", return_value=mock_auditor):
        # Build Graph
        builder = GraphBuilder(mock_services)

        builder.nodes.llm_reviewer.review_code = mock_services.reviewer.review_code

        # Increment iteration count to avoid infinite loop
        async def mock_coder_session(state: CycleState) -> dict:
            current_iter = state.get("iteration_count", 1)
            print(f"DEBUG coder_session IN: iter={current_iter}, i={state.get('current_auditor_index')}, j={state.get('current_auditor_review_count')}, final_fix={state.get('final_fix')}")
            return {"status": "ready_for_audit", "pr_url": "http://pr", "iteration_count": current_iter + 1}

        builder.nodes.coder_session_node = AsyncMock(side_effect=mock_coder_session)

        async def mock_uat(state: CycleState) -> dict:
            print(f"DEBUG uat_evaluate IN: iter={state.get('iteration_count')}")
            return {"status": "cycle_completed"}
            
        builder.nodes.uat_evaluate_node = AsyncMock(side_effect=mock_uat)

        graph = builder.build_coder_graph()

        initial_state = CycleState(
            cycle_id="01",
            project_session_id="test_session",
            integration_branch="dev/main",
            active_branch="dev/cycle01",
        )

        final_state = await graph.ainvoke(
            initial_state, {"configurable": {"thread_id": "test_thread"}, "recursion_limit": 50}
        )

        # 6 runs of the auditor node
        assert mock_auditor.run_audit.call_count == 6
        assert final_state.get("final_fix") is True
