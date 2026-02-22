import asyncio
from datetime import UTC, datetime
from typing import Any

from rich.console import Console

from .config import settings
from .interfaces import IGraphNodes
from .sandbox import SandboxRunner
from .services.audit_orchestrator import AuditOrchestrator
from .services.git_ops import GitManager
from .services.jules_client import JulesClient
from .services.llm_reviewer import LLMReviewer
from .services.project import ProjectManager
from .state import CycleState

console = Console()


class CycleNodes(IGraphNodes):
    """
    Encapsulates the logic for each node in the AC-CDD workflow graph.
    """

    def __init__(self, sandbox_runner: SandboxRunner, jules_client: JulesClient) -> None:
        self.sandbox = sandbox_runner
        self.jules = jules_client
        self.git = GitManager()
        # Dependency injection for sub-services could be improved by passing them in,
        # but for now we construct them with the injected clients.
        self.audit_orchestrator = AuditOrchestrator(jules_client, sandbox_runner)
        self.llm_reviewer = LLMReviewer(sandbox_runner=sandbox_runner)

    async def architect_session_node(self, state: CycleState) -> dict[str, Any]:
        """Node for Architect Agent (Jules)."""
        console.print("[bold blue]Starting Architect Session...[/bold blue]")

        instruction = settings.get_template("ARCHITECT_INSTRUCTION.md").read_text()

        # Logic moved from CLI: requested_cycle_count is now the primary driver if present
        if state.get("requested_cycle_count"):
            n = state.get("requested_cycle_count")
            instruction += (
                f"\n\nIMPORTANT CONSTRAINT: The development plan MUST be divided into "
                f"exactly {n} implementation cycles."
            )
        # Fallback if just planned_cycle_count is used (backward compatibility)
        elif state.get("planned_cycle_count"):
            n = state.get("planned_cycle_count")
            instruction += (
                f"\n\nIMPORTANT CONSTRAINT: The development plan MUST be divided into "
                f"exactly {n} implementation cycles."
            )

        context_files = settings.get_context_files()

        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")

        # New Branch Strategy: Create Integration Branch as the working base
        integration_branch = f"dev/int-{timestamp}"

        # Create integration branch from main (works same as feature branch creation)
        await self.git.create_feature_branch(integration_branch, from_branch="main")

        result = await self.jules.run_session(
            session_id=f"architect-{timestamp}",  # Logical ID for request
            prompt=instruction,
            target_files=context_files,
            context_files=[],
            require_plan_approval=False,
        )

        if result.get("status") in ("success", "running") and result.get("pr_url"):
            pr_url = result["pr_url"]
            pr_number = pr_url.split("/")[-1]

            # Auto-Merge Architecture PR
            try:
                console.print(
                    f"[bold blue]Auto-merging Architecture PR #{pr_number}...[/bold blue]"
                )
                await self.git.merge_pr(pr_number)
                console.print("[bold green]Architecture merged successfully![/bold green]")

                # Prepare environment (fix perms, sync dependencies)
                try:
                    await ProjectManager().prepare_environment()
                except Exception as e:
                    console.print(f"[yellow]Warning: Environment preparation issue: {e}[/yellow]")

            except Exception as e:
                console.print(f"[bold red]Failed to auto-merge Architecture PR: {e}[/bold red]")
                # We don't fail the cycle here, but manual intervention will be needed

            return {
                "status": "architect_completed",
                "current_phase": "architect_done",
                "integration_branch": integration_branch,
                "active_branch": integration_branch,  # Working on integration branch
                "project_session_id": result.get("session_name"),
                "pr_url": pr_url,
            }

        if result.get("error"):
            return {"status": "architect_failed", "error": result.get("error")}

        return {"status": "architect_failed", "error": "Unknown Jules error or no PR URL"}

    async def _send_audit_feedback_to_session(
        self, session_id: str, feedback: str
    ) -> dict[str, Any] | None:
        """Send audit feedback to existing Jules session and wait for new PR.

        Returns result dict if successful, None if should create new session.
        """
        console.print(
            f"[bold yellow]Sending Audit Feedback to existing Jules session: {session_id}[/bold yellow]"
        )
        try:
            feedback_msg = (
                f"# AUDIT FEEDBACK - PLEASE ADDRESS THESE ISSUES\n\n"
                f"{feedback}\n\n"
                f"Please revise your implementation to address the above feedback and create a new PR."
            )
            # Send message
            await self.jules._send_message(self.jules._get_session_url(session_id), feedback_msg)
            # Replace fixed sleep with smart polling for state transition
            console.print(
                "[dim]Waiting for Jules to process feedback (expecting IN_PROGRESS)...[/dim]"
            )

            # Poll for state change (up to 60s)
            state_transitioned = False
            for attempt in range(12):  # 12 * 5s = 60s
                await asyncio.sleep(5)
                current_state = await self.jules.get_session_state(session_id)
                console.print(f"[dim]State check ({attempt + 1}/12): {current_state}[/dim]")

                if current_state in {
                    "IN_PROGRESS", "QUEUED", "PLANNING",
                    "AWAITING_PLAN_APPROVAL", "AWAITING_USER_FEEDBACK", "PAUSED",
                }:
                    state_transitioned = True
                    console.print(
                        "[green]Jules session is now active. Proceeding to monitor...[/green]"
                    )
                    break
                if current_state == "FAILED":
                    console.print("[red]Jules session failed during feedback wait.[/red]")
                    return None

            if not state_transitioned:
                console.print(
                    "[yellow]Warning: Jules session state did not change to IN_PROGRESS after 60s. "
                    "Assuming message received but state lagging, or task finished very quickly.[/yellow]"
                )

            # Wait for Jules to process feedback and create new PR
            # We pass a flag or rely on wait_for_completion to handle the "re-completion"
            result = await self.jules.wait_for_completion(session_id)

            if result.get("status") == "success" or result.get("pr_url"):
                return {"status": "ready_for_audit", "pr_url": result.get("pr_url")}

            # If we get here, it means wait_for_completion returned but no success/PR
            console.print(
                "[yellow]Jules session finished without new PR. Creating new session...[/yellow]"
            )
            return None  # noqa: TRY300

        except Exception as e:
            console.print(
                f"[yellow]Failed to send feedback to existing session: {e}. Creating new session...[/yellow]"
            )
        return None

    async def coder_session_node(self, state: CycleState) -> dict[str, Any]:
        from ac_cdd_core.services.coder_usecase import CoderUseCase

        usecase = CoderUseCase(self.jules)
        return dict(await usecase.execute(state))

    async def auditor_node(self, state: CycleState) -> dict[str, Any]:
        from ac_cdd_core.services.auditor_usecase import AuditorUseCase

        usecase = AuditorUseCase(self.jules, self.git, self.llm_reviewer)
        return dict(await usecase.execute(state))

    async def committee_manager_node(self, state: CycleState) -> dict[str, Any]:
        from ac_cdd_core.services.committee_usecase import CommitteeUseCase

        usecase = CommitteeUseCase()
        return dict(await usecase.execute(state))

    async def uat_evaluate_node(self, state: CycleState) -> dict[str, Any]:
        from ac_cdd_core.services.uat_usecase import UatUseCase

        usecase = UatUseCase(self.git)
        return dict(await usecase.execute(state))

    def check_coder_outcome(self, state: CycleState) -> str:
        from ac_cdd_core.enums import FlowStatus

        if state.get("final_fix", False):
            return str(FlowStatus.COMPLETED.value)

        status = state.get("status")
        if status == FlowStatus.CODER_RETRY:
            return str(FlowStatus.CODER_RETRY.value)
        if status == FlowStatus.READY_FOR_AUDIT:
            return str(FlowStatus.READY_FOR_AUDIT.value)
        if status in {FlowStatus.FAILED, FlowStatus.ARCHITECT_FAILED}:
            return str(FlowStatus.FAILED.value)
        return str(FlowStatus.COMPLETED.value)

    def check_audit_outcome(self, _state: CycleState) -> str:
        return "rejected_retry"

    def route_committee(self, state: CycleState) -> str:
        from ac_cdd_core.enums import FlowStatus

        status = state.get("status")
        if status == FlowStatus.NEXT_AUDITOR:
            return "auditor"
        if status == FlowStatus.CYCLE_APPROVED:
            return "uat_evaluate"
        if status in {FlowStatus.RETRY_FIX, FlowStatus.WAIT_FOR_JULES_COMPLETION}:
            return "coder_session"
        return "failed"

    def route_uat(self, state: CycleState) -> str:
        from ac_cdd_core.enums import FlowStatus

        status = state.get("status")
        if status == FlowStatus.START_REFACTOR:
            return "coder_session"
        if status == FlowStatus.COMPLETED:
            return "end"
        return "end"

    async def qa_session_node(self, state: CycleState) -> dict[str, Any]:
        from ac_cdd_core.services.qa_usecase import QaUseCase

        usecase = QaUseCase(self.jules, self.git, self.llm_reviewer)
        return dict(await usecase.execute_qa_session(state))

    async def qa_auditor_node(self, state: CycleState) -> dict[str, Any]:
        from ac_cdd_core.services.qa_usecase import QaUseCase

        usecase = QaUseCase(self.jules, self.git, self.llm_reviewer)
        return dict(await usecase.execute_qa_audit(state))

    def route_qa(self, state: CycleState) -> str:
        from ac_cdd_core.enums import FlowStatus

        status = state.get("status")
        if status == FlowStatus.APPROVED:
            return "end"
        if status == FlowStatus.REJECTED:
            return "retry_fix"
        return "failed"
