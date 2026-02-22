import asyncio
import time
from typing import Any

from ac_cdd_core.config import settings
from ac_cdd_core.enums import FlowStatus
from ac_cdd_core.state import CycleState
from rich.console import Console

console = Console()

class CommitteeUseCase:
    """
    Encapsulates the logic for managing the Committee of Auditors.
    """

    async def execute(self, state: CycleState) -> dict[str, Any]:
        """Node for Managing the Committee of Auditors."""
        if state.status == FlowStatus.WAITING_FOR_JULES:
            console.print(
                "[bold yellow]No new commit detected. Waiting for Jules to complete work...[/bold yellow]"
            )
            return {
                "status": FlowStatus.WAIT_FOR_JULES_COMPLETION,
            }

        audit_res = state.audit_result
        i: int = state.current_auditor_index
        j: int = state.current_auditor_review_count
        current_iter: int = state.iteration_count

        if audit_res and audit_res.is_approved:
            if i < settings.NUM_AUDITORS:
                next_idx = i + 1
                console.print(
                    f"[bold green]Auditor #{i} Approved. Moving to Auditor #{next_idx}.[/bold green]"
                )
                return {
                    "current_auditor_index": next_idx,
                    "current_auditor_review_count": 1,
                    "status": FlowStatus.NEXT_AUDITOR,
                }
            console.print("[bold green]All Auditors Approved![/bold green]")
            return {"status": FlowStatus.CYCLE_APPROVED}

        if j < settings.REVIEWS_PER_AUDITOR:
            next_rev = j + 1
            console.print(
                f"[bold yellow]Auditor #{i} Rejected. "
                f"Retry {next_rev}/{settings.REVIEWS_PER_AUDITOR}.[/bold yellow]"
            )
            last_fb = state.get("last_feedback_time", 0)
            now = time.time()
            cooldown = 180
            elapsed = now - last_fb

            if elapsed < cooldown and last_fb > 0:
                wait = cooldown - elapsed
                console.print(
                    f"[bold yellow]Cooldown: Waiting {int(wait)}s before next Coder session...[/bold yellow]"
                )
                await asyncio.sleep(wait)

            return {
                "current_auditor_review_count": next_rev,
                "iteration_count": current_iter + 1,
                "status": FlowStatus.RETRY_FIX,
                "last_feedback_time": time.time(),
            }

        if i < settings.NUM_AUDITORS:
            next_idx = i + 1
            console.print(
                f"[bold yellow]Auditor #{i} limit reached. "
                f"Fixing code then moving to Auditor #{next_idx}.[/bold yellow]"
            )
            last_fb = state.get("last_feedback_time", 0)
            now = time.time()
            cooldown = 180
            elapsed = now - last_fb

            if elapsed < cooldown and last_fb > 0:
                wait = cooldown - elapsed
                console.print(
                    f"[bold yellow]Cooldown: Waiting {int(wait)}s before next Coder session...[/bold yellow]"
                )
                await asyncio.sleep(wait)

            return {
                "current_auditor_index": next_idx,
                "current_auditor_review_count": 1,
                "iteration_count": current_iter + 1,
                "status": FlowStatus.RETRY_FIX,
                "last_feedback_time": time.time(),
            }

        console.print(
            "[bold yellow]Final Auditor limit reached. Fixing code then Merging.[/bold yellow]"
        )
        return {
            "final_fix": True,
            "iteration_count": current_iter + 1,
            "status": FlowStatus.RETRY_FIX,
        }
