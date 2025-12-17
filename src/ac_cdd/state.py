from typing import TypedDict

from .domain_models import AuditResult, CyclePlan, FileOperation, UatAnalysis


class CycleState(TypedDict):
    """LangGraph state for the development cycle."""

    cycle_id: str
    sandbox_id: str | None
    plan: CyclePlan | None
    code_changes: list[FileOperation]
    audit_result: AuditResult | None
    uat_analysis: UatAnalysis | None
    test_logs: str
    audit_logs: str
    current_phase: str
    loop_count: int
    error: str | None
    correction_history: list[str]  # History of failed fixes
    dry_run: bool
    interactive: bool
    goal: str | None
    approved: bool | None # For human-in-the-loop approval
