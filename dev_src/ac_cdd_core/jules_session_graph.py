"""LangGraph builder for Jules session management."""

from typing import Literal

from ac_cdd_core.jules_session_nodes import JulesSessionNodes
from ac_cdd_core.jules_session_state import JulesSessionState
from langgraph.graph import END, StateGraph


def route_monitor(
    state: JulesSessionState,
) -> Literal["answer_inquiry", "validate_completion", "end", "monitor"]:
    """Route from monitor node based on detected state."""
    if state.status == "inquiry_detected":
        return "answer_inquiry"
    if state.status == "validating_completion":
        return "validate_completion"
    if state.status in ["failed", "timeout"]:
        return "end"
    return "monitor"


def route_validation(
    state: JulesSessionState,
) -> Literal["monitor", "check_pr"]:
    """Route from validation node."""
    if state.status == "monitoring":
        return "monitor"
    return "check_pr"


def route_pr_check(
    state: JulesSessionState,
) -> Literal["end", "request_pr"]:
    """Route from PR check node."""
    if state.status == "success":
        return "end"
    return "request_pr"


def route_pr_wait(
    state: JulesSessionState,
) -> Literal["end", "monitor", "wait_pr"]:
    """Route from PR wait node."""
    if state.status == "success":
        return "end"
    if state.status == "monitoring":
        return "monitor"
    if state.status in ["timeout", "failed"]:
        return "end"
    return "wait_pr"


def build_jules_session_graph(jules_client: "JulesClient") -> StateGraph[JulesSessionState]:  # type: ignore[name-defined] # noqa: F821
    """Build LangGraph for Jules session management.

    Args:
        jules_client: JulesClient instance for API calls

    Returns:
        Compiled LangGraph for session management
    """
    nodes = JulesSessionNodes(jules_client)

    workflow: StateGraph[JulesSessionState] = StateGraph(JulesSessionState)

    # Add nodes
    workflow.add_node("monitor", nodes.monitor_session)
    workflow.add_node("answer_inquiry", nodes.answer_inquiry)
    workflow.add_node("validate_completion", nodes.validate_completion)
    workflow.add_node("check_pr", nodes.check_pr)
    workflow.add_node("request_pr", nodes.request_pr_creation)
    workflow.add_node("wait_pr", nodes.wait_for_pr)

    # Set entry point
    workflow.set_entry_point("monitor")

    # Add edges
    workflow.add_conditional_edges(
        "monitor",
        route_monitor,
        {
            "answer_inquiry": "answer_inquiry",
            "validate_completion": "validate_completion",
            "end": END,
            "monitor": "monitor",
        },
    )

    workflow.add_edge("answer_inquiry", "monitor")

    workflow.add_conditional_edges(
        "validate_completion",
        route_validation,
        {"monitor": "monitor", "check_pr": "check_pr"},
    )

    workflow.add_conditional_edges(
        "check_pr", route_pr_check, {"end": END, "request_pr": "request_pr"}
    )

    workflow.add_edge("request_pr", "wait_pr")

    workflow.add_conditional_edges(
        "wait_pr",
        route_pr_wait,
        {"end": END, "monitor": "monitor", "wait_pr": "wait_pr"},
    )

    return workflow.compile()  # type: ignore[return-value]
