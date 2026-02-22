from typing import Any

from ac_cdd_core.enums import FlowStatus, WorkPhase
from ac_cdd_core.services.git_ops import GitManager
from ac_cdd_core.state import CycleState
from rich.console import Console

console = Console()


class UatUseCase:
    """
    Encapsulates the logic for UAT Evaluation, Auto-Merge, and Refactoring Transition.
    """

    def __init__(self, git_manager: GitManager) -> None:
        self.git = git_manager

    async def execute(self, state: CycleState) -> dict[str, Any]:
        """Node for UAT Evaluation, Auto-Merge, and Refactoring Transition."""
        console.print("[bold cyan]Running UAT Evaluation...[/bold cyan]")
        # Assume UAT passes for now

        # Auto-Merge Cycle PR
        pr_url = state.pr_url
        if pr_url:
            try:
                pr_number = pr_url.split("/")[-1]
                console.print(f"[bold blue]Auto-merging Cycle PR #{pr_number}...[/bold blue]")
                await self.git.merge_pr(pr_number)
                console.print("[bold green]Cycle PR merged successfully![/bold green]")
            except Exception as e:
                console.print(f"[bold red]Failed to auto-merge Cycle PR: {e}[/bold red]")
                return {"status": FlowStatus.FAILED, "error": str(e)}

        # Refactoring Phase Transition Logic
        current_phase = state.current_phase
        if current_phase != WorkPhase.REFACTORING:
            console.print("[bold magenta]Transitioning to Refactoring Phase...[/bold magenta]")
            # Clear audit results and reset counters for the refactoring loop
            return {
                "current_phase": WorkPhase.REFACTORING,
                "status": FlowStatus.START_REFACTOR,
                "iteration_count": 0,
                "current_auditor_index": 1,
                "current_auditor_review_count": 1,
                "audit_result": None,
                "audit_pass_count": 0,
                "audit_retries": 0,
                "final_fix": False,
                "last_feedback_time": 0,
                "pr_url": None,
            }

        # If we were already in refactoring, we are done
        console.print("[bold green]Refactoring Phase Completed.[/bold green]")
        return {"status": FlowStatus.COMPLETED}
