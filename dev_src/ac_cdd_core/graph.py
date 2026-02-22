from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from .graph_nodes import CycleNodes
from .interfaces import IGraphNodes
from .sandbox import SandboxRunner
from .service_container import ServiceContainer
from .services.jules_client import JulesClient
from .state import CycleState
from .enums import FlowStatus


class GraphBuilder:
    def __init__(self, services: ServiceContainer) -> None:
        # Initialize SandboxRunner via ServiceContainer or directly if not present (though it's not a service in ServiceContainer definition currently)
        # Refactoring to avoid direct instantiation if possible, but SandboxRunner is specific to execution.
        # For now, we keep it here but we can inject it if we extend ServiceContainer.
        self.sandbox = SandboxRunner()

        # Use jules from services, fallback to direct instantiation if None
        self.jules = services.jules if services.jules else JulesClient()

        # Inject dependencies into CycleNodes
        self.nodes: IGraphNodes = CycleNodes(self.sandbox, self.jules)

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
                FlowStatus.READY_FOR_AUDIT.value: "auditor",
                FlowStatus.FAILED.value: END,
                FlowStatus.COMPLETED.value: "uat_evaluate",
                FlowStatus.CODER_RETRY.value: "coder_session",
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

        # Conditional edge from uat_evaluate for Refactoring Phase
        workflow.add_conditional_edges(
            "uat_evaluate",
            self.nodes.route_uat,
            {
                "coder_session": "coder_session",
                "end": END,
            },
        )

        return workflow

    def build_architect_graph(self) -> CompiledStateGraph[CycleState, Any, Any, Any]:
        return self._create_architect_graph().compile(checkpointer=MemorySaver())

    def build_coder_graph(self) -> CompiledStateGraph[CycleState, Any, Any, Any]:
        return self._create_coder_graph().compile(checkpointer=MemorySaver())

    def _create_qa_graph(self) -> StateGraph[CycleState]:
        """Create the graph for the QA/Tutorial generation phase."""
        workflow = StateGraph(CycleState)

        workflow.add_node("qa_session", self.nodes.qa_session_node)
        workflow.add_node("qa_auditor", self.nodes.qa_auditor_node)

        workflow.add_edge(START, "qa_session")

        # Custom logic for QA session routing (similar to coder_session)
        # If qa_session fails or succeeds
        workflow.add_conditional_edges(
            "qa_session",
            lambda state: "qa_auditor" if state.get("status") == "ready_for_audit" else END,
            {"qa_auditor": "qa_auditor", END: END},
        )

        # Router from Auditor
        workflow.add_conditional_edges(
            "qa_auditor",
            self.nodes.route_qa,
            {
                "end": END,
                "retry_fix": "qa_session",
                "failed": END,
            },
        )
        return workflow

    def build_qa_graph(self) -> CompiledStateGraph[CycleState, Any, Any, Any]:
        return self._create_qa_graph().compile(checkpointer=MemorySaver())
