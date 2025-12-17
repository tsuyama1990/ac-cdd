from unittest.mock import AsyncMock, patch

import pytest

from ac_cdd.domain_models import CyclePlan, FileArtifact
from ac_cdd.graph import GraphBuilder
from ac_cdd.state import CycleState


@pytest.mark.asyncio
async def test_structurer_node_skipped(mock_services):
    """Test that structurer is skipped if ALL_SPEC.md is missing."""
    builder = GraphBuilder(mock_services)

    # Mock file system: ALL_SPEC.md does not exist
    with patch("pathlib.Path.exists", return_value=False):
        state = CycleState(cycle_id="01")
        result = await builder.structurer_node(state)
        assert result["current_phase"] == "structuring_skipped"


@pytest.mark.asyncio
async def test_planner_node_existing_plan(mock_services):
    """Test that planner skips if plan exists."""
    builder = GraphBuilder(mock_services)

    with patch("pathlib.Path.exists", return_value=True):
        state = CycleState(cycle_id="01")
        result = await builder.planner_node(state)
        assert result["current_phase"] == "planning_complete"


@pytest.mark.asyncio
async def test_planner_node_generation(mock_services, mock_agent_result):
    """Test planner generation."""
    builder = GraphBuilder(mock_services)

    # Mock CyclePlan
    plan = CyclePlan(
        spec_file=FileArtifact(path="SPEC.md", content="spec content"),
        schema_file=FileArtifact(path="schema.py", content="schema content", language="python"),
        uat_file=FileArtifact(path="UAT.md", content="uat content"),
        thought_process="My thought process"
    )

    # Mock agent
    with patch("ac_cdd.graph.planner_agent.run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = mock_agent_result(plan)

        # We need to control Path.exists to force generation
        # exists() returns False for SPEC.md, False for SYSTEM_ARCHITECTURE.json, etc.
        # But we need to be careful not to break other path checks.

        # Let's mock side_effect for exists
        def exists_side_effect(self):
            # If checking for SPEC.md, return False (so we generate)
            if "SPEC.md" in str(self):
                return False
            # Return False for inputs to force template usage or whatever default path
            return False

        # We also need to mock read_text for templates if they are accessed

        with patch("pathlib.Path.exists", return_value=False):
            state = CycleState(cycle_id="01")
            result = await builder.planner_node(state)

            assert result["current_phase"] == "planning_complete"
            assert result["plan"] == plan
            mock_services.artifact_manager.save_plan_artifacts.assert_called_once()


@pytest.mark.asyncio
async def test_graph_structure(mock_services):
    """Test graph structure and compilation."""
    builder = GraphBuilder(mock_services)
    graph = builder.build_main_graph()

    # Verify nodes
    assert "structurer" in graph.nodes
    assert "planner" in graph.nodes
    assert "spec_writer" in graph.nodes
    assert "test_generator" in graph.nodes
    assert "coder" in graph.nodes
    assert "tester" in graph.nodes
    assert "auditor" in graph.nodes
    assert "uat" in graph.nodes
