import asyncio
from typing import TYPE_CHECKING, Any

from ac_cdd_core.config import settings
from ac_cdd_core.services.jules_client import JulesClient
from ac_cdd_core.services.plan_auditor import PlanAuditor
from rich.console import Console
from rich.panel import Panel

if TYPE_CHECKING:
    from ac_cdd_core.sandbox import SandboxRunner

console = Console()


class AuditOrchestrator:
    """
    Orchestrates the interactive planning loop between Jules and PlanAuditor.
    """

    def __init__(
        self,
        jules_client: JulesClient | None = None,
        sandbox_runner: "SandboxRunner | None" = None,
        plan_auditor: PlanAuditor | None = None,
    ) -> None:
        self.jules = jules_client or JulesClient()
        self.auditor = plan_auditor or PlanAuditor()
        self.sandbox = sandbox_runner

    async def run_interactive_session(
        self, prompt: str, spec_files: dict[str, str], max_retries: int = 3
    ) -> dict[str, Any]:
        """
        Starts a session with plan approval requirement and manages the audit loop.
        """
        console.print(Panel("[bold cyan]Starting AI-on-AI Audit Session[/bold cyan]", expand=False))

        file_paths = list(spec_files.keys())

        session_data = await self.jules.run_session(
            session_id=settings.current_session_id,
            prompt=prompt,
            files=file_paths,
            require_plan_approval=True,
        )

        session_name = session_data["session_name"]
        console.print(f"[green]Session Created: {session_name}[/green]")

        retry_count = 0
        current_plan_id = None

        while retry_count <= max_retries:
            console.print(f"\n[bold yellow]--- Audit Round {retry_count + 1} ---[/bold yellow]")
            console.print("[dim]Waiting for Jules to generate a plan...[/dim]")

            if current_plan_id:
                plan_details = await self._wait_for_new_plan(session_name, current_plan_id)
            else:
                activity = await self.jules.wait_for_activity_type(
                    session_name,
                    target_type="planGenerated",
                    timeout_seconds=300,
                )

                if not activity:
                    t_msg = "Timed out waiting for plan generation."
                    raise TimeoutError(t_msg)

                plan_details = activity.get("planGenerated")

            if not plan_details:
                v_msg = "Plan activity found but no details."
                raise ValueError(v_msg)

            plan_id = plan_details.get("planId")
            current_plan_id = plan_id
            console.print(f"[blue]Plan Generated (ID: {plan_id})[/blue]")

            audit_result = await self.auditor.audit_plan(
                plan_details, spec_files, phase="architect"
            )

            style = "green" if audit_result.status == "APPROVED" else "red"
            console.print(
                Panel(
                    f"Status: {audit_result.status}\nReason: {audit_result.reason}",
                    title="Audit Result",
                    border_style=style,
                )
            )

            if audit_result.status == "APPROVED":
                console.print(
                    "[bold green]Plan Approved. Proceeding to implementation...[/bold green]"
                )
                await self.jules.approve_plan(session_name, plan_id)
                result = await self.jules.wait_for_completion(session_name)
                return dict(result)

            retry_count += 1
            if retry_count > max_retries:
                console.print("[bold red]Max retries exceeded. Aborting session.[/bold red]")
                r_msg = "Max audit retries exceeded."
                raise RuntimeError(r_msg)

            feedback = audit_result.feedback or audit_result.reason
            feedback_prompt = (
                f"Your plan was REJECTED by the Lead Architect.\n"
                f"Reason: {audit_result.reason}\n"
                f"Instruction: {feedback}\n"
                f"Please revise the plan accordingly."
            )

            console.print(f"[magenta]Sending Feedback to Jules:[/magenta] {feedback}")
            await self.jules.send_message(session_name, feedback_prompt)

        u_msg = "Session ended unexpectedly."
        raise RuntimeError(u_msg)

    async def _wait_for_new_plan(
        self, session_name: str, current_plan_id: str, timeout_seconds: int = 300
    ) -> dict[str, Any]:
        """Helper to poll until a plan with a different ID appears."""
        console.print("[dim]Waiting for revised plan...[/dim]")

        base_delay = 10
        max_delay = 60
        current_delay = base_delay

        try:
            async with asyncio.timeout(timeout_seconds):
                while True:
                    latest = await self.jules.get_latest_plan(session_name)
                    if latest and latest.get("planId") != current_plan_id:
                        return dict(latest)
                    await asyncio.sleep(current_delay)
                    current_delay = min(current_delay * 2, max_delay)
        except TimeoutError:
            t_msg = "Timed out waiting for revised plan."
            raise TimeoutError(t_msg) from None
