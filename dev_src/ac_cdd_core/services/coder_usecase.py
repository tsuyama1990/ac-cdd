import asyncio
from datetime import UTC, datetime
from typing import Any

from ac_cdd_core.config import settings
from ac_cdd_core.enums import FlowStatus, WorkPhase
from ac_cdd_core.services.jules_client import JulesClient
from ac_cdd_core.state import CycleState
from ac_cdd_core.state_manager import StateManager
from rich.console import Console

console = Console()


class CoderUseCase:
    """
    Encapsulates the logic and interactions with the Coder AI (Jules).
    """

    def __init__(self, jules_client: JulesClient) -> None:
        self.jules = jules_client

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
            feedback_template = settings.get_template("AUDIT_FEEDBACK_MESSAGE.md").read_text()
            feedback_msg = feedback_template.replace("{{feedback}}", feedback)
            await self.jules._send_message(self.jules._get_session_url(session_id), feedback_msg)

            console.print(
                "[dim]Waiting for Jules to process feedback (expecting IN_PROGRESS)...[/dim]"
            )

            state_transitioned = False
            # Official Jules API states that mean "session is still active/in-flight":
            # QUEUED, PLANNING, AWAITING_PLAN_APPROVAL, AWAITING_USER_FEEDBACK, IN_PROGRESS, PAUSED
            ACTIVE_STATES = {
                "IN_PROGRESS",
                "QUEUED",
                "PLANNING",
                "AWAITING_PLAN_APPROVAL",
                "AWAITING_USER_FEEDBACK",
                "PAUSED",
            }
            for attempt in range(12):  # 12 * 5s = 60s
                await asyncio.sleep(5)
                current_state = await self.jules.get_session_state(session_id)
                console.print(f"[dim]State check ({attempt + 1}/12): {current_state}[/dim]")

                if current_state in ACTIVE_STATES:
                    state_transitioned = True
                    console.print(
                        f"[green]Jules session is now active ({current_state}). Proceeding to monitor...[/green]"
                    )
                    break
                if current_state == "FAILED":
                    console.print("[red]Jules session failed during feedback wait.[/red]")
                    return None
                # COMPLETED means Jules finished quickly - proceed immediately
                if current_state == "COMPLETED":
                    console.print("[green]Jules session completed quickly.[/green]")
                    state_transitioned = True
                    break

            if not state_transitioned:
                console.print(
                    "[yellow]Warning: Jules session state did not change to IN_PROGRESS after 60s. "
                    "Assuming message received but state lagging, or task finished very quickly.[/yellow]"
                )

            result = await self.jules.wait_for_completion(session_id)

            if result.get("status") == "success" or result.get("pr_url"):
                return {"status": FlowStatus.READY_FOR_AUDIT, "pr_url": result.get("pr_url")}

            console.print(
                "[yellow]Jules session finished without new PR. Creating new session...[/yellow]"
            )
            return None  # noqa: TRY300

        except Exception as e:
            console.print(
                f"[yellow]Failed to send feedback to existing session: {e}. Creating new session...[/yellow]"
            )
        return None

    async def execute(self, state: CycleState) -> dict[str, Any]:  # noqa: C901, PLR0911, PLR0912, PLR0915
        """Runs the coder session logic, handling retries, feedback ingestion, and session initiation."""
        cycle_id = state.cycle_id
        iteration = state.iteration_count
        current_phase = state.current_phase

        mgr = StateManager()
        cycle_manifest = mgr.get_cycle(cycle_id)

        # 1. Wait for Jules Completion Mode
        if state.status == FlowStatus.WAIT_FOR_JULES_COMPLETION:
            if cycle_manifest and cycle_manifest.jules_session_id:
                console.print(
                    f"[bold blue]Waiting for Jules to produce new commit: {cycle_manifest.jules_session_id}[/bold blue]"
                )
                try:
                    result = await self.jules.wait_for_completion(cycle_manifest.jules_session_id)
                    if result.get("status") == "success" or result.get("pr_url"):
                        return {
                            "status": FlowStatus.READY_FOR_AUDIT,
                            "pr_url": result.get("pr_url"),
                        }
                    console.print(
                        "[yellow]Jules session did not produce PR. Continuing...[/yellow]"
                    )
                except Exception as e:
                    console.print(f"[yellow]Wait for completion failed: {e}[/yellow]")
            else:
                console.print("[yellow]No active Jules session found. Continuing...[/yellow]")

        # 2. Try Resume Mode
        if (
            cycle_manifest
            and cycle_manifest.jules_session_id
            and state.resume_mode
            and state.status != FlowStatus.RETRY_FIX
        ):
            try:
                console.print(
                    f"[bold blue]Resuming Jules Session: {cycle_manifest.jules_session_id}[/bold blue]"
                )
                result = await self.jules.wait_for_completion(cycle_manifest.jules_session_id)
                if result.get("status") == "success" or result.get("pr_url"):
                    return {"status": FlowStatus.READY_FOR_AUDIT, "pr_url": result.get("pr_url")}
                console.print("[yellow]Resume incomplete or failed. Restarting session...[/yellow]")
            except Exception as e:
                console.print(f"[yellow]Resume failed: {e}. Starting new session.[/yellow]")

        # 3. Setup Prompt and Session Data
        phase_label = "REFACTORING" if current_phase == WorkPhase.REFACTORING else "CODER"
        console.print(
            f"[bold green]Starting {phase_label} Session for Cycle {cycle_id} "
            f"(Iteration {iteration})...[/bold green]"
        )

        if current_phase == WorkPhase.REFACTORING:
            instruction = settings.get_template("REFACTOR_INSTRUCTION.md").read_text()
        else:
            instruction = settings.get_template("CODER_INSTRUCTION.md").read_text()
            instruction = instruction.replace("{{cycle_id}}", str(cycle_id))

        # 4. Handle Feedback Injection / Reuse session
        last_audit = state.audit_result
        if state.status == FlowStatus.RETRY_FIX and last_audit and last_audit.feedback:
            if cycle_manifest and cycle_manifest.jules_session_id:
                session_state = await self.jules.get_session_state(cycle_manifest.jules_session_id)

                # Official Jules API reusable states:
                # IN_PROGRESS = actively working
                # COMPLETED = finished (can receive sendMessage to continue)
                # AWAITING_USER_FEEDBACK = Jules asked a question, waiting for response
                # PAUSED = paused but not failed
                REUSABLE_STATES = {"IN_PROGRESS", "COMPLETED", "AWAITING_USER_FEEDBACK", "PAUSED"}
                if session_state in REUSABLE_STATES:
                    console.print(
                        f"[dim]Reusing session ({session_state}): {cycle_manifest.jules_session_id}[/dim]"
                    )
                    retry_result = await self._send_audit_feedback_to_session(
                        cycle_manifest.jules_session_id, last_audit.feedback
                    )
                    if retry_result:
                        return retry_result

                    console.print(
                        "[yellow]Session reuse failed. Creating NEW session with feedback injected...[/yellow]"
                    )
                    instruction += "\n\n" + self._build_feedback_injection(
                        last_audit.feedback, cycle_manifest.pr_url if cycle_manifest else None
                    )
                else:
                    console.print(
                        f"[yellow]Session in unexpected/failed state ({session_state}). Creating new session...[/yellow]"
                    )
                    instruction += "\n\n" + self._build_feedback_injection(
                        last_audit.feedback, cycle_manifest.pr_url if cycle_manifest else None
                    )
            else:
                console.print(
                    "[bold yellow]Injecting Audit Feedback into Coder Prompt...[/bold yellow]"
                )
                instruction += "\n\n" + self._build_feedback_injection(last_audit.feedback, None)

        target_files = settings.get_target_files()
        context_files = settings.get_context_files()

        # 5. Start / Restart Session
        try:
            timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
            prefix = "refactor" if current_phase == WorkPhase.REFACTORING else "coder"
            session_req_id = f"{prefix}-cycle-{cycle_id}-iter-{iteration}-{timestamp}"

            result = await self.jules.run_session(
                session_id=session_req_id,
                prompt=instruction,
                target_files=target_files,
                context_files=context_files,
                require_plan_approval=False,
            )

            if result.get("session_name"):
                mgr.update_cycle_state(
                    cycle_id, jules_session_id=result["session_name"], status="in_progress"
                )

            if result.get("status") == "running" and result.get("session_name"):
                console.print(
                    f"[bold blue]Session {result['session_name']} created. Waiting for completion...[/bold blue]"
                )
                result = await self.jules.wait_for_completion(result["session_name"])

            if result.get("status") == "success" or result.get("pr_url"):
                if cycle_manifest:
                    mgr.update_cycle_state(cycle_id, session_restart_count=0)
                return {"status": FlowStatus.READY_FOR_AUDIT, "pr_url": result.get("pr_url")}

        except Exception as e:
            console.print(f"[red]{phase_label} Session Failed: {e}[/red]")
            return self._handle_session_failure(cycle_manifest, cycle_id, str(e), mgr)
        else:
            if result.get("status") == "failed":
                return self._handle_session_failure(
                    cycle_manifest, cycle_id, result.get("error", "Unknown error"), mgr
                )
            return {"status": FlowStatus.FAILED, "error": "Jules failed to produce PR"}

    def _handle_session_failure(
        self, cycle_manifest: Any, cycle_id: str, error_msg: str, mgr: StateManager
    ) -> dict[str, Any]:
        """Handles session failures and manages restart counting."""
        if cycle_manifest:
            restart_count = cycle_manifest.session_restart_count
            max_restarts = cycle_manifest.max_session_restarts

            if restart_count < max_restarts:
                new_restart_count = restart_count + 1
                console.print(
                    f"[yellow]Restarting session (attempt {new_restart_count}/{max_restarts + 1})...[/yellow]"
                )

                mgr.update_cycle_state(
                    cycle_id,
                    jules_session_id=None,
                    session_restart_count=new_restart_count,
                    last_error=error_msg,
                )

                return {
                    "status": FlowStatus.CODER_RETRY,
                    "session_restart_count": new_restart_count,
                }

            console.print(
                f"[red]Max session restarts ({max_restarts}) reached. Failing cycle.[/red]"
            )

        return {"status": FlowStatus.FAILED, "error": error_msg}

    def _build_feedback_injection(self, feedback: str, pr_url: str | None) -> str:
        """Builds feedback injection block from template."""
        import re

        template = str(settings.get_template("AUDIT_FEEDBACK_INJECTION.md").read_text())
        result = template.replace("{{feedback}}", feedback)
        if pr_url:
            # Replace the conditional {{#pr_url}}...{{/pr_url}} block with the resolved content
            result = str(
                re.sub(
                    r"\{\{#pr_url\}\}\s*Previous PR: \{\{pr_url\}\}\s*\{\{/pr_url\}\}",
                    f"Previous PR: {pr_url}",
                    result,
                    flags=re.DOTALL,
                )
            )
        else:
            # Remove the conditional block entirely if no PR URL
            result = str(re.sub(r"\{\{#pr_url\}\}.*?\{\{/pr_url\}\}", "", result, flags=re.DOTALL))
        return result.strip()
