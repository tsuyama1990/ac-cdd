import asyncio
import re
from datetime import UTC, datetime
from typing import Any

from ac_cdd_core.config import settings
from ac_cdd_core.domain_models import CycleManifest
from ac_cdd_core.enums import FlowStatus, WorkPhase
from ac_cdd_core.services.jules_client import JulesClient
from ac_cdd_core.state import CycleState
from ac_cdd_core.state_manager import StateManager
from rich.console import Console

console = Console()

# Jules API states that mean "session is still active/in-flight"
_ACTIVE_STATES = {
    "IN_PROGRESS",
    "QUEUED",
    "PLANNING",
    "AWAITING_PLAN_APPROVAL",
    "AWAITING_USER_FEEDBACK",
    "PAUSED",
}

# Jules API states where an existing session can receive new messages
_REUSABLE_STATES = {"IN_PROGRESS", "COMPLETED", "AWAITING_USER_FEEDBACK", "PAUSED"}


class CoderUseCase:
    """
    Encapsulates the logic and interactions with the Coder AI (Jules).
    """

    def __init__(self, jules_client: JulesClient) -> None:
        self.jules = jules_client

    # ------------------------------------------------------------------ #
    #  Public entry point                                                  #
    # ------------------------------------------------------------------ #

    async def execute(self, state: CycleState) -> dict[str, Any]:  # noqa: PLR0911
        """Routes the coder session through its many possible modes."""
        cycle_id = state.cycle_id
        iteration = state.iteration_count
        current_phase = state.current_phase
        phase_label = "REFACTORING" if current_phase == WorkPhase.REFACTORING else "CODER"

        mgr = StateManager()
        cycle_manifest = mgr.get_cycle(cycle_id)

        # 1. Poll mode: wait for Jules to complete work already in progress
        result = await self._try_wait_for_completion(state, cycle_manifest)
        if result:
            return result

        # 2. Resume mode: reconnect to a session started in a previous run
        result = await self._try_resume(state, cycle_manifest)
        if result:
            return result

        # 3. Session reuse: send feedback to the existing session instead of launching a new one
        result = await self._try_reuse_session(cycle_manifest, state)
        if result:
            return result

        # 4. Build the instruction prompt (+ optional feedback injection)
        console.print(
            f"[bold green]Starting {phase_label} Session for Cycle {cycle_id} "
            f"(Iteration {iteration})...[/bold green]"
        )
        instruction = self._build_instruction(cycle_id, current_phase, state, cycle_manifest)

        target_files = settings.get_target_files()
        context_files = settings.get_context_files()

        # 4. Launch (or restart) the Jules session
        try:
            timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
            prefix = "refactor" if current_phase == WorkPhase.REFACTORING else "coder"
            session_req_id = f"{prefix}-cycle-{cycle_id}-iter-{iteration}-{timestamp}"

            jules_session_name, result = await self._run_jules_session(
                session_req_id, instruction, target_files, context_files, cycle_id, mgr
            )

            if result.get("status") == "success" or result.get("pr_url"):
                # 5. Self-Critic phase: initial PR only, skip on audit retries
                is_initial_pr = iteration == 0 and state.status != FlowStatus.RETRY_FIX
                if is_initial_pr and jules_session_name:
                    result = await self._run_critic_phase(cycle_id, jules_session_name) or result

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

    # ------------------------------------------------------------------ #
    #  Private helpers                                                     #
    # ------------------------------------------------------------------ #

    async def _try_wait_for_completion(
        self, state: CycleState, cycle_manifest: CycleManifest | None
    ) -> dict[str, Any] | None:
        """Handle WAIT_FOR_JULES_COMPLETION mode: poll an in-flight session."""
        if state.status != FlowStatus.WAIT_FOR_JULES_COMPLETION:
            return None

        if cycle_manifest and cycle_manifest.jules_session_id:
            console.print(
                f"[bold blue]Waiting for Jules to produce new commit: "
                f"{cycle_manifest.jules_session_id}[/bold blue]"
            )
            try:
                result = await self.jules.wait_for_completion(cycle_manifest.jules_session_id)
                if result.get("status") == "success" or result.get("pr_url"):
                    return {"status": FlowStatus.READY_FOR_AUDIT, "pr_url": result.get("pr_url")}
                console.print("[yellow]Jules session did not produce PR. Continuing...[/yellow]")
            except Exception as e:
                console.print(f"[yellow]Wait for completion failed: {e}[/yellow]")
        else:
            console.print("[yellow]No active Jules session found. Continuing...[/yellow]")

        return None

    async def _try_resume(
        self, state: CycleState, cycle_manifest: CycleManifest | None
    ) -> dict[str, Any] | None:
        """Handle resume_mode: reconnect to a session from a previous run."""
        if not (
            cycle_manifest
            and cycle_manifest.jules_session_id
            and state.resume_mode
            and state.status != FlowStatus.RETRY_FIX
        ):
            return None

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

        return None

    def _build_instruction(
        self,
        cycle_id: str,
        current_phase: WorkPhase | str | None,
        state: CycleState,
        cycle_manifest: CycleManifest | None,
    ) -> str:
        """Assemble the Jules instruction prompt, injecting feedback when retrying."""
        if current_phase == WorkPhase.REFACTORING:
            instruction = settings.get_template("REFACTOR_INSTRUCTION.md").read_text()
        else:
            instruction = settings.get_template("CODER_INSTRUCTION.md").read_text()

        instruction = instruction.replace("{{cycle_id}}", str(cycle_id))

        last_audit = state.audit_result
        if state.status == FlowStatus.RETRY_FIX and last_audit and last_audit.feedback:
            instruction += "\n\n" + self._build_feedback_injection(
                last_audit.feedback, cycle_manifest.pr_url if cycle_manifest else None
            )

        return str(instruction)

    async def _try_reuse_session(
        self, cycle_manifest: CycleManifest | None, state: CycleState
    ) -> dict[str, Any] | None:
        """Attempt to send audit feedback to an existing session instead of starting fresh."""
        last_audit = state.audit_result
        if not (
            state.status == FlowStatus.RETRY_FIX
            and last_audit
            and last_audit.feedback
            and cycle_manifest
            and cycle_manifest.jules_session_id
        ):
            return None

        session_state = await self.jules.get_session_state(cycle_manifest.jules_session_id)
        if session_state not in _REUSABLE_STATES:
            console.print(
                f"[yellow]Session in unexpected/failed state ({session_state}). "
                f"Creating new session...[/yellow]"
            )
            return None

        console.print(
            f"[dim]Reusing session ({session_state}): {cycle_manifest.jules_session_id}[/dim]"
        )
        return await self._send_audit_feedback_to_session(
            cycle_manifest.jules_session_id, last_audit.feedback
        )

    async def _run_jules_session(
        self,
        session_req_id: str,
        instruction: str,
        target_files: list[str],
        context_files: list[str],
        cycle_id: str,
        mgr: StateManager,
    ) -> tuple[str | None, dict[str, Any]]:
        """Launch a new Jules session and wait for it to complete.

        Returns (jules_session_name, result_dict). The session_name is saved
        separately so it survives the wait_for_completion() result overwrite.
        """
        result = await self.jules.run_session(
            session_id=session_req_id,
            prompt=instruction,
            target_files=target_files,
            context_files=context_files,
            require_plan_approval=False,
        )

        # Capture session_name BEFORE wait_for_completion() overwrites result —
        # wait_for_completion() does NOT include session_name in its return value.
        jules_session_name: str | None = result.get("session_name")

        if jules_session_name:
            mgr.update_cycle_state(
                cycle_id, jules_session_id=jules_session_name, status="in_progress"
            )

        if result.get("status") == "running" and jules_session_name:
            console.print(
                f"[bold blue]Session {jules_session_name} created. Waiting for completion...[/bold blue]"
            )
            result = await self.jules.wait_for_completion(jules_session_name)

        return jules_session_name, result

    async def _run_critic_phase(
        self, cycle_id: str, jules_session_name: str
    ) -> dict[str, Any] | None:
        """Send CODER_CRITIC_INSTRUCTION to Jules and wait for the revised PR.

        Returns the updated result dict, or None if the phase should be skipped.
        """
        console.print(
            "[bold cyan]Initial Coder PR created. "
            "Invoking Coder Critic for self-reflection before Auditor review...[/bold cyan]"
        )
        try:
            critic_instruction = settings.get_template("CODER_CRITIC_INSTRUCTION.md").read_text()
            critic_instruction = critic_instruction.replace("{{cycle_id}}", str(cycle_id))

            session_url = self.jules._get_session_url(jules_session_name)
            await self.jules._send_message(session_url, critic_instruction)

            console.print("[dim]Waiting for Coder Critic to finish review and push fixes...[/dim]")
            await asyncio.sleep(10)

            return dict(await self.jules.wait_for_completion(jules_session_name))
        except Exception as e:
            console.print(f"[yellow]Warning: Coder Critic phase error, proceeding: {e}[/yellow]")
            return None

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
            for attempt in range(12):  # 12 * 5s = 60s
                await asyncio.sleep(5)
                current_state = await self.jules.get_session_state(session_id)
                console.print(f"[dim]State check ({attempt + 1}/12): {current_state}[/dim]")

                if current_state in _ACTIVE_STATES:
                    state_transitioned = True
                    console.print(
                        f"[green]Jules session is now active ({current_state}). Proceeding to monitor...[/green]"
                    )
                    break
                if current_state == "FAILED":
                    console.print("[red]Jules session failed during feedback wait.[/red]")
                    return None
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

    # ------------------------------------------------------------------ #
    #  Utility helpers                                                     #
    # ------------------------------------------------------------------ #

    def _handle_session_failure(
        self, cycle_manifest: Any, cycle_id: str, error_msg: str, mgr: StateManager
    ) -> dict[str, Any]:
        """Handle session failures and manage restart counting."""
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
        """Build feedback injection block from template."""
        template = str(settings.get_template("AUDIT_FEEDBACK_INJECTION.md").read_text())
        result = template.replace("{{feedback}}", feedback)
        if pr_url:
            result = str(
                re.sub(
                    r"\{\{#pr_url\}\}\s*Previous PR: \{\{pr_url\}\}\s*\{\{/pr_url\}\}",
                    f"Previous PR: {pr_url}",
                    result,
                    flags=re.DOTALL,
                )
            )
        else:
            result = str(re.sub(r"\{\{#pr_url\}\}.*?\{\{/pr_url\}\}", "", result, flags=re.DOTALL))
        return result.strip()
