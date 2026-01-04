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

    # Mock Jules run session
    mock_services.jules.run_session = AsyncMock(return_value={"pr_url": "http://pr"})
    mock_services.jules.continue_session = AsyncMock(return_value={"pr_url": "http://pr"})

    # Mock Sandbox
    mock_services.sandbox.run_lint_check = AsyncMock(return_value=(True, "OK"))

    # Mock Reviewer
    mock_services.reviewer.review_code = AsyncMock(return_value="CHANGES_REQUESTED: Please fix X.")

    # Build Graph
    builder = GraphBuilder(mock_services)

    # CRITICAL: Fix for AttributeError: property 'llm_reviewer' of 'CycleNodes' object has no setter
    # This happens because the test framework or Python sees CycleNodes as having a property from the interface
    # but the implementation uses an instance var.
    # Instead of assigning to `builder.nodes.llm_reviewer`, we can replace the internal object directly
    # by accessing `__dict__` or simply assuming it's an instance var and the previous error was due to
    # the Interface definition confusing the mocker.

    # Actually, if IGraphNodes defines it as `@property` and CycleNodes implements it as an instance var,
    # it is valid Python. But if we try `builder.nodes.llm_reviewer = ...` on an instance that has it as instance var, it works.
    # The traceback showed the error happened at `dev_src/ac_cdd_core/graph_nodes.py:30: AttributeError`.
    # Wait! The traceback shows the error happens inside `CycleNodes.__init__`:
    # > self.llm_reviewer = LLMReviewer(sandbox_runner=sandbox_runner)
    # E AttributeError: property 'llm_reviewer' of 'CycleNodes' object has no setter

    # This means inheriting from `IGraphNodes` where it is defined as a property effectively makes `self.llm_reviewer = ...` illegal
    # if `CycleNodes` does not explicitly override the property with a setter or just define a field.
    # But defining a field `self.x = 1` usually overrides the class property.

    # UNLESS `IGraphNodes` is a concrete class in the MRO that defines it as a property.
    # `IGraphNodes` is a Protocol. Inheriting from Protocol usually doesn't enforce runtime behavior like this.

    # Solution: Remove the `@property` from `IGraphNodes` or define a setter.
    # Or just don't inherit from `IGraphNodes` at runtime if it causes issues, use typing.cast.
    # But inheriting is fine if we implement it correctly.

    # For now, let's fix the test by NOT patching it this way if the init is failing.
    # Wait, the init fails when `GraphBuilder(mock_services)` is called.
    # Because `CycleNodes` is instantiated.

    # I will modify IGraphNodes to remove the property definition if it conflicts,
    # or better, just define it as a variable in the protocol: `llm_reviewer: Any`

    # Let's fix interfaces.py.

    # Re-running the test logic logic (this file is just overwriting the test content, but I need to fix interfaces.py)
    # I will revert the test file to the clean version and fix the root cause in interfaces.py

    builder.nodes.llm_reviewer.review_code = mock_services.reviewer.review_code

    builder.nodes.coder_session_node = AsyncMock(
        return_value={"status": "ready_for_audit", "pr_url": "http://pr"}
    )

    builder.nodes.uat_evaluate_node = AsyncMock(return_value={"status": "cycle_completed"})

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

    assert mock_services.reviewer.review_code.call_count == 6
    assert final_state.get("final_fix") is True
