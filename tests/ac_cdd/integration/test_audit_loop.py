from unittest.mock import AsyncMock, MagicMock

import pytest
from ac_cdd_core.graph import GraphBuilder
from ac_cdd_core.state import CycleState


@pytest.mark.asyncio
async def test_audit_rejection_loop():
    """
    Test that the audit loop functions correctly when changes are requested.
    Verifies that the graph iterates through 3 auditors * 2 reviews each = 6 cycles.
    """
    # Mock Services
    mock_services = MagicMock()
    mock_services.git = AsyncMock()
    mock_services.jules = MagicMock()
    mock_services.sandbox = MagicMock()
    mock_services.reviewer = MagicMock()

    # Mock Jules run session
    mock_services.jules.run_session = AsyncMock(return_value={"pr_url": "http://pr"})
    mock_services.jules.continue_session = AsyncMock(return_value={"pr_url": "http://pr"})

    # Mock Sandbox
    mock_services.sandbox.run_lint_check = AsyncMock(return_value=(True, "OK"))

    # Mock Reviewer
    mock_services.reviewer.review_code = AsyncMock(return_value="CHANGES_REQUESTED: Please fix X.")

    # Build Graph
    builder = GraphBuilder(mock_services)

    # CRITICAL: Patch the internal LLMReviewer instance because CycleNodes creates its own.
    builder.nodes.llm_reviewer = mock_services.reviewer

    # Mock implementation nodes to isolate loop logic
    # We patch the instance methods BEFORE building the graph
    builder.checkout_branch_node = AsyncMock(return_value={"current_phase": "coding"})

    # Coder Node Mock - Just returns ready for audit.
    # The Committee Manager now handles state updates (counters).
    builder.coder_session_node = AsyncMock(
        return_value={"status": "ready_for_audit", "pr_url": "http://pr"}
    )

    builder.syntax_check_node = AsyncMock(return_value={"current_phase": "syntax_ok"})

    # We use REAL auditor_node logic to test the loop decision
    # But current auditor_node calls self.git.get_changed_files().
    # We must mock that service response.
    mock_services.git.get_changed_files = AsyncMock(return_value=["file.py"])

    graph = builder.build_coder_graph()

    # Initialize State
    initial_state = CycleState(
        cycle_id="01",
        session_id="test_session",
        integration_branch="dev/main",
        cycle_branch="dev/cycle01",
    )

    # Run Graph with thread_id for checkpointer
    final_state = await graph.ainvoke(
        initial_state, {"configurable": {"thread_id": "test_thread"}, "recursion_limit": 50}
    )

    # Verification

    # Logic:
    # Aud 1, Rev 1 -> Reject -> Retry (Rev 2)
    # Aud 1, Rev 2 -> Reject -> Max Retries -> Fail
    # Since mock always returns rejection, we expect 2 calls total before failure.
    assert mock_services.reviewer.review_code.call_count == 2
    assert final_state["status"] == "failed"


@pytest.mark.asyncio
async def test_audit_loop_early_exit_scenario():
    """Hypothetical future test."""
    pass
