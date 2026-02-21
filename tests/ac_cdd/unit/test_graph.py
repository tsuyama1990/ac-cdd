from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ac_cdd_core.graph import GraphBuilder
from ac_cdd_core.service_container import ServiceContainer
from ac_cdd_core.state import CycleState
from langgraph.graph.state import CompiledStateGraph


@pytest.fixture
def mock_sandbox() -> MagicMock:
    sandbox = MagicMock()
    # Mock run_command to return success tuple
    sandbox.run_command = AsyncMock(return_value=("PASS", "", 0))
    return sandbox


@pytest.fixture
def mock_jules() -> MagicMock:
    client = MagicMock()
    # Mock methods used in graph nodes
    client.start_architect_session = AsyncMock(return_value={"status": "success"})

    async def mock_run_session(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "status": "success",
            "pr_url": "http://pr",
            "session_name": kwargs.get("session_id", "sess-123"),
        }

    client.run_session = AsyncMock(side_effect=mock_run_session)
    client.continue_session = AsyncMock(return_value={"status": "success", "pr_url": "http://pr"})
    return client


@pytest.fixture
def services(mock_sandbox: MagicMock, mock_jules: MagicMock) -> ServiceContainer:
    # GraphBuilder now expects a ServiceContainer, not raw clients.
    container = ServiceContainer.default()
    # We replace the real instances with our mocks
    container.sandbox = mock_sandbox
    container.jules = mock_jules
    return container


@pytest.fixture
def graph_builder(services: ServiceContainer) -> GraphBuilder:
    # Updated GraphBuilder signature: (services)
    return GraphBuilder(services)


@pytest.mark.asyncio
async def test_architect_graph_structure(graph_builder: GraphBuilder) -> None:
    """Test that architect graph is built correctly."""
    graph = graph_builder.build_architect_graph()
    assert isinstance(graph, CompiledStateGraph)


@pytest.mark.asyncio
async def test_coder_graph_structure(graph_builder: GraphBuilder) -> None:
    """Test that coder graph is built correctly."""
    graph = graph_builder.build_coder_graph()
    assert isinstance(graph, CompiledStateGraph)


@pytest.mark.asyncio
async def test_architect_graph_execution(services: ServiceContainer, mock_jules: MagicMock) -> None:
    """Test architect graph execution flow."""
    with patch("ac_cdd_core.graph_nodes.GitManager") as mock_git_cls:
        # Configure the mock instance methods as AsyncMock
        mock_git = mock_git_cls.return_value
        mock_git.create_feature_branch = AsyncMock()

        # Create builder under patch so CycleNodes picks up the mock
        graph_builder = GraphBuilder(services)
        graph = graph_builder.build_architect_graph()

        initial_state = CycleState(cycle_id="00", session_id="test-session")
        config = {"configurable": {"thread_id": "1"}}

        result = await graph.ainvoke(initial_state, config)

    # In CycleNodes.architect_session_node, we return {"status": "architect_completed"}
    # This should merge into CycleState.
    assert result["status"] == "architect_completed"

    # Verify project_session_id has timestamp (session_id in state maps to project_session_id in logic)
    # Actually CycleNodes updates 'project_session_id' key in returned dict
    assert result["project_session_id"].startswith("architect-")


@pytest.mark.asyncio
async def test_coder_graph_execution(services: ServiceContainer, mock_jules: MagicMock) -> None:
    """Test coder graph execution flow."""
    initial_state = CycleState(cycle_id="01", iteration_count=0)

    with (
        patch("ac_cdd_core.graph_nodes.AuditOrchestrator") as mock_audit_cls,
        patch("ac_cdd_core.graph_nodes.LLMReviewer") as mock_reviewer_cls,
        patch("ac_cdd_core.graph_nodes.GitManager") as mock_git_cls,
        patch("ac_cdd_core.graph_nodes.StateManager") as mock_sm_cls,
    ):
        mock_git = mock_git_cls.return_value
        mock_git.get_remote_url = AsyncMock(return_value="https://github.com/repo")
        
        mock_sm = mock_sm_cls.return_value
        mock_manifest = MagicMock()
        mock_manifest.branch_name = "feature-abc"
        mock_manifest.jules_session_id = None
        mock_sm.get_cycle.return_value = mock_manifest
        
        # Mock Auditor (for older flow if used)
        mock_audit_instance = mock_audit_cls.return_value
        mock_audit_instance.run_audit = AsyncMock(return_value=MagicMock(status="approved"))

        # Mock Reviewer (for new flow: auditor_node)
        mock_reviewer_instance = mock_reviewer_cls.return_value
        mock_reviewer_instance.review_code = AsyncMock(return_value="NO ISSUES FOUND")

        builder = GraphBuilder(services)
        graph = builder.build_coder_graph()

        config = {"configurable": {"thread_id": "1"}}
        # We need to assign result to satisfy F841 or simply await it
        _ = await graph.ainvoke(initial_state, config)

        # Ideally we should assert something about the result, but preserving existing behavior
