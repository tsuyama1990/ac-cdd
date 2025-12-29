import pytest
from ac_cdd_core.graph import GraphBuilder


@pytest.mark.asyncio
async def test_architect_graph_structure(mock_services):
    """Test architect graph structure."""
    builder = GraphBuilder(mock_services)
    graph = builder.build_architect_graph()

    # The build_architect_graph method returns a CompiledStateGraph, so no need to compile again.
    assert graph is not None


@pytest.mark.asyncio
async def test_coder_graph_structure(mock_services):
    """Test coder graph structure."""
    builder = GraphBuilder(mock_services)
    graph = builder.build_coder_graph()

    # The build_coder_graph method returns a CompiledStateGraph.
    assert graph is not None
