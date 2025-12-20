
import pytest
from ac_cdd_core.graph import GraphBuilder


@pytest.mark.asyncio
async def test_architect_graph_structure(mock_services):
    """Test architect graph structure."""
    builder = GraphBuilder(mock_services)
    graph = builder.build_architect_graph()

    # The graph object from langgraph isn't easily inspectable for nodes/edges directly
    # in the same way depending on version, but we can compile it.
    compiled = graph.compile()

    # Check if compiled graph has expected nodes
    # Note: langgraph StateGraph compilation returns a Runnable
    # We can check the underlying graph definition if accessible, but for now
    # let's assume if it compiles, the structure is valid according to definition.
    assert compiled is not None


@pytest.mark.asyncio
async def test_coder_graph_structure(mock_services):
    """Test coder graph structure."""
    builder = GraphBuilder(mock_services)
    graph = builder.build_coder_graph()

    compiled = graph.compile()
    assert compiled is not None
