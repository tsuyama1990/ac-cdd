from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from .graph_nodes import CycleNodes
from .sandbox import SandboxRunner
from .service_container import ServiceContainer
from .services.jules_client import JulesClient
from .state import CycleState


class GraphBuilder:
    def __init__(self, services: ServiceContainer) -> None:
        # Initialize SandboxRunner directly as it's not part of ServiceContainer
        self.sandbox = SandboxRunner()

        # Use jules from services, fallback to direct instantiation if None
        self.jules = services.jules if services.jules else JulesClient()

        self.nodes = CycleNodes(self.sandbox, self.jules)

    async def cleanup(self) -> None:
        """Cleanup resources, specifically the sandbox."""
        if self.sandbox:
            await self.sandbox.cleanup()

    def _create_architect_graph(self) -> StateGraph[CycleState]:
        """Create the graph for the Architect phase (gen-cycles)."""
        workflow = StateGraph(CycleState)

        workflow.add_node("architect_session", self.nodes.architect_session_node)

        workflow.add_edge(START, "architect_session")
        workflow.add_edge("architect_session", END)

        return workflow

    def _create_coder_graph(self) -> StateGraph[CycleState]:
        """Create the graph for the Coder/Auditor phase (run-cycle)."""
        workflow = StateGraph(CycleState)

        workflow.add_node("coder_session", self.nodes.coder_session_node)
        workflow.add_node("auditor", self.nodes.auditor_node)
        workflow.add_node("committee_manager", self.nodes.committee_manager_node)
        workflow.add_node("uat_evaluate", self.nodes.uat_evaluate_node)

        workflow.add_edge(START, "coder_session")

        # Conditional edge from coder_session
        workflow.add_conditional_edges(
            "coder_session",
            self.nodes.check_coder_outcome,
            {
                "ready_for_audit": "auditor",
                "failed": END,
                "completed": "uat_evaluate",
            },
        )

        # Auditor -> Committee Manager
        workflow.add_edge("auditor", "committee_manager")

        # Conditional edge from committee_manager
        workflow.add_conditional_edges(
            "committee_manager",
            self.nodes.route_committee,
            {
                "uat_evaluate": "uat_evaluate",
                "auditor": "auditor",
                "coder_session": "coder_session",
                "failed": END,
            },
        )

        workflow.add_edge("uat_evaluate", END)

        return workflow

    def build_architect_graph(self) -> CompiledStateGraph[CycleState, Any]:
        return self._create_architect_graph().compile(checkpointer=MemorySaver())

    def build_coder_graph(self) -> CompiledStateGraph[CycleState, Any]:
        return self._create_coder_graph().compile(checkpointer=MemorySaver())
