import asyncio
from pathlib import Path
from typing import Any

from ac_cdd_core.config import settings
from ac_cdd_core.services.jules_client import JulesClient
from ac_cdd_core.services.plan_auditor import PlanAuditor
from rich.console import Console
from rich.panel import Panel

console = Console()


class AuditOrchestrator:
    """
    Orchestrates the interactive planning loop between Jules (Planner) and
    the PlanAuditor (Reviewer).
    """

    def __init__(self, jules_client: JulesClient | None = None, sandbox_runner: Any | None = None):
        self.jules = jules_client or JulesClient()
        self.auditor = PlanAuditor()
        self.sandbox = sandbox_runner

    async def run_interactive_session(
        self, prompt: str, source_name: str, spec_files: dict[str, str], max_retries: int = 3
    ) -> dict[str, Any]:
        """
        Starts a session with plan approval requirement and manages the audit loop.
        """
        console.print(Panel("[bold cyan]Starting AI-on-AI Audit Session[/bold cyan]", expand=False))

        # 1. Start Session (requirePlanApproval=True)
        # Note: run_session usually polls for completion, but we modified it to return early
        # if require_plan_approval is True.

        # We need to construct the file list for context from spec_files keys
        # But run_session expects file paths. We will assume the keys are paths or just pass empty
        # and rely on the prompt context if files are already read.
        # However, Jules needs file context.
        # For simplicity, we assume spec_files keys are paths relative to repo root.
        file_paths = list(spec_files.keys())

        # Note: We need to pass paths to Jules so it can read them.
        # create_session expects a prompt.

        session_data = await self.jules.run_session(
            session_id=settings.current_session_id,
            prompt=prompt,
            files=file_paths,
            completion_signal_file=Path("completion_signal"),  # Dummy/Not used in this flow
            require_plan_approval=True,
        )

        session_name = session_data["session_name"]
        console.print(f"[green]Session Created: {session_name}[/green]")

        retry_count = 0
        current_plan_id = None  # Track current plan ID to avoid re-auditing

        while retry_count <= max_retries:
            console.print(f"\n[bold yellow]--- Audit Round {retry_count + 1} ---[/bold yellow]")

            # 2. Wait for Plan Generation
            console.print("[dim]Waiting for Jules to generate a plan...[/dim]")

            # If we rejected a plan, we need to wait for a NEW one.
            if current_plan_id:
                activity_details = await self._wait_for_new_plan(session_name, current_plan_id)
                if not activity_details:
                    # Fallback if _wait_for_new_plan times out or returns empty
                    raise TimeoutError("Timed out waiting for revised plan.")
                plan_details = activity_details

            else:
                # First time: just wait for any plan
                activity = await self.jules.wait_for_activity_type(
                    session_name,
                    target_type="planGenerated",
                    timeout=300,  # 5 minutes timeout for plan generation
                )

                if not activity:
                    raise TimeoutError("Timed out waiting for plan generation.")

                plan_details = activity.get("planGenerated")

            if not plan_details:
                # Should not happen if wait_for_activity_type works correctly
                raise ValueError("Plan activity found but no details.")

            plan_id = plan_details.get("planId")
            current_plan_id = plan_id
            console.print(f"[blue]Plan Generated (ID: {plan_id})[/blue]")

            # 3. Audit the Plan
            audit_result = await self.auditor.audit_plan(plan_details, spec_files)

            # Display Result
            style = "green" if audit_result.status == "APPROVED" else "red"
            console.print(
                Panel(
                    f"Status: {audit_result.status}\nReason: {audit_result.reason}",
                    title="Audit Result",
                    border_style=style,
                )
            )

            # 4. Branch Logic
            if audit_result.status == "APPROVED":
                console.print(
                    "[bold green]Plan Approved. Proceeding to implementation...[/bold green]"
                )
                await self.jules.approve_plan(session_name, plan_id)

                # Now we wait for the final outcome (PR creation)
                # reuse wait_for_completion from JulesClient
                return await self.jules.wait_for_completion(session_name)

            else:
                # REJECTED
                retry_count += 1
                if retry_count > max_retries:
                    console.print("[bold red]Max retries exceeded. Aborting session.[/bold red]")
                    raise RuntimeError("Max audit retries exceeded.")

                feedback = audit_result.feedback or audit_result.reason
                feedback_prompt = (
                    f"Your plan was REJECTED by the Lead Architect.\n"
                    f"Reason: {audit_result.reason}\n"
                    f"Instruction: {feedback}\n"
                    f"Please revise the plan accordingly."
                )

                console.print(f"[magenta]Sending Feedback to Jules:[/magenta] {feedback}")
                await self.jules.send_message(session_name, feedback_prompt)

    async def _wait_for_new_plan(self, session_name: str, current_plan_id: str, timeout: int = 300):
        """Helper to poll until a plan with a different ID appears."""
        console.print("[dim]Waiting for revised plan...[/dim]")
        start_time = asyncio.get_event_loop().time()

        # Exponential backoff parameters
        base_delay = 10
        max_delay = 60
        current_delay = base_delay

        while asyncio.get_event_loop().time() - start_time < timeout:
            latest = await self.jules.get_latest_plan(session_name)
            if latest and latest.get("planId") != current_plan_id:
                return latest

            # Wait with exponential backoff
            await asyncio.sleep(current_delay)
            current_delay = min(current_delay * 2, max_delay)

        raise TimeoutError("Timed out waiting for revised plan.")
