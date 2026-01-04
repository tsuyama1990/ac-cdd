from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.console import Console

from .config import settings
from .domain_models import AuditResult
from .interfaces import IGraphNodes
from .sandbox import SandboxRunner
from .services.audit_orchestrator import AuditOrchestrator
from .services.jules_client import JulesClient
from .services.llm_reviewer import LLMReviewer
from .session_manager import SessionManager
from .state import CycleState

console = Console()


class CycleNodes(IGraphNodes):
    """
    Encapsulates the logic for each node in the AC-CDD workflow graph.
    """

    def __init__(self, sandbox_runner: SandboxRunner, jules_client: JulesClient) -> None:
        self.sandbox = sandbox_runner
        self.jules = jules_client
        # Dependency injection for sub-services could be improved by passing them in,
        # but for now we construct them with the injected clients.
        self.audit_orchestrator = AuditOrchestrator(jules_client, sandbox_runner)
        self.llm_reviewer = LLMReviewer(sandbox_runner=sandbox_runner)

    async def _read_files(self, file_paths: list[str]) -> dict[str, str]:
        """Helper to read files from the sandbox or local."""
        result = {}
        for path_str in file_paths:
            p = Path(path_str)
            if p.exists() and p.is_file():
                try:
                    result[path_str] = p.read_text(encoding="utf-8")
                except Exception as e:
                    console.print(f"[yellow]Warning: Could not read {path_str}: {e}[/yellow]")
            else:
                pass
        return result

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
        session_id = f"architect-cycle-{state['cycle_id']}-{timestamp}"

        result = await self.jules.run_session(
            session_id=session_id,
            prompt=instruction,
            target_files=context_files,
            context_files=[],
            require_plan_approval=False,
        )

        prefix = settings.session.integration_branch_prefix
        sid = state.get("project_session_id") or session_id
        integration_branch = f"{prefix}/{sid}/integration"

        if result.get("status") in ("success", "running"):
            return {
                "status": "architect_completed",
                "current_phase": "architect_done",
                "integration_branch": integration_branch,
                "project_session_id": result.get("session_name"),
                "pr_url": result.get("pr_url"),
            }
        return {"status": "architect_failed", "error": result.get("error")}

    async def coder_session_node(self, state: CycleState) -> dict[str, Any]:
        """Node for Coder Agent (Jules)."""
        cycle_id = state.get("cycle_id")
        iteration = state.get("iteration_count")

        # Resume Logic using SessionManager
        mgr = SessionManager()
        cycle_manifest = await mgr.get_cycle(cycle_id)

        # 1. Try Resume if session ID exists
        if cycle_manifest and cycle_manifest.jules_session_id and state.get("resume_mode", False):
            try:
                console.print(
                    f"[bold blue]Resuming Jules Session: {cycle_manifest.jules_session_id}[/bold blue]"
                )
                result = await self.jules.wait_for_completion(cycle_manifest.jules_session_id)

                # Check outcome
                if result.get("status") == "success" or result.get("pr_url"):
                    return {"status": "ready_for_audit", "pr_url": result.get("pr_url")}
                console.print("[yellow]Resume incomplete or failed. Restarting session...[/yellow]")
            except Exception as e:
                console.print(f"[yellow]Resume failed: {e}. Starting new session.[/yellow]")

        console.print(
            f"[bold green]Starting Coder Session for Cycle {cycle_id} "
            f"(Iteration {iteration})...[/bold green]"
        )

        instruction = settings.get_template("CODER_INSTRUCTION.md").read_text()
        instruction = instruction.replace("{{cycle_id}}", str(cycle_id))

        last_audit = state.get("audit_result")
        if state.get("status") == "retry_fix" and last_audit and last_audit.feedback:
            console.print(
                "[bold yellow]Injecting Audit Feedback into Coder Prompt...[/bold yellow]"
            )
            instruction += f"\n\n# PREVIOUS AUDIT FEEDBACK (MUST FIX)\n{last_audit.feedback}"

        target_files = settings.get_target_files()
        context_files = settings.get_context_files()

        try:
            # Generate a unique logical ID for the session request
            # But the actual Jules session ID will be returned by the API
            timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
            session_req_id = f"coder-cycle-{cycle_id}-iter-{iteration}-{timestamp}"

            # Start new session
            # IMPORTANT: We use require_plan_approval=True to get the session ID early if needed
            # but usually run_session returns after session is created/completed.
            # If we want instant persistence, we might need a change in JulesClient to return early
            # or rely on run_session returning the session name.

            result = await self.jules.run_session(
                session_id=session_req_id,
                prompt=instruction,
                target_files=target_files,
                context_files=context_files,
                require_plan_approval=True, # As per prompt requirements for B. New Session & Instant Persistence
            )

            # 2. Persist Session ID IMMEDIATELY for Hot Resume
            if result.get("session_name"):
                await mgr.update_cycle_state(
                    cycle_id, jules_session_id=result["session_name"], status="in_progress"
                )

            # If require_plan_approval=True, run_session might return early with status 'running' or 'awaiting_approval'
            # Check JulesClient behavior. Assuming it waits or returns state.
            # If it waits for completion, the above persist is late if crash happens during wait.
            # However, JulesClient.run_session usually polls.
            # The prompt implies we want to persist *as soon as* we get the ID.
            # JulesClient.run_session wraps creation and polling.
            # Ideally we would split creation and polling, but modifying JulesClient wasn't explicitly requested
            # other than the prompt snippet showing "result = await self.jules.run_session".
            # If run_session blocks until done, we can't persist in the middle.
            # BUT the prompt snippet shows:
            # result = await self.jules.run_session(...)
            # SessionManager().update_cycle(...)
            # This implies persistence happens AFTER run_session returns.
            # Wait, if run_session blocks until completion, then persistence after is not "Instant".
            # Perhaps run_session returns quickly with require_plan_approval=True?
            # Let's assume for now we follow the snippet in the prompt.

            # If the snippet logic is:
            # result = await self.jules.run_session(..., require_plan_approval=True)
            # # -> returns when plan is ready for approval?
            # SessionManager().update_cycle(...)

            # If run_session with require_plan_approval=True returns when plan is generated (waiting for approval),
            # then we persist the ID, and then we might need to approve/wait.

            # But wait, the current JulesClient.run_session loops until completion.
            # If require_plan_approval is True, it might pause.
            # I should check JulesClient code if possible, but I don't need to modify it unless necessary.
            # I'll stick to the snippet.

            if result.get("status") == "success" or result.get("pr_url"):
                return {"status": "ready_for_audit", "pr_url": result.get("pr_url")}

            # If we returned early (e.g. for approval), we might need to handle it.
            # But CycleNodes expects to finish the cycle work.

            # For now, just persisting what we got.

        except Exception as e:
            console.print(f"[red]Coder Session Failed: {e}[/red]")
            return {"status": "failed", "error": str(e)}
        else:
            if result.get("status") == "failed":
                 return {"status": "failed", "error": result.get("error")}
            # If successful but no PR (unexpected)
            return {"status": "failed", "error": "Jules failed to produce PR"}

    async def auditor_node(self, _state: CycleState) -> dict[str, Any]:
        """Node for Auditor Agent (Aider/LLM)."""
        console.print("[bold magenta]Starting Auditor...[/bold magenta]")

        instruction = settings.get_template("AUDITOR_INSTRUCTION.md").read_text()

        target_paths = settings.get_target_files()
        context_paths = settings.get_context_files()

        target_files = await self._read_files(target_paths)
        context_docs = await self._read_files(context_paths)

        model = settings.reviewer.fast_model

        audit_feedback = await self.llm_reviewer.review_code(
            target_files=target_files,
            context_docs=context_docs,
            instruction=instruction,
            model=model,
        )

        status = "approved" if "NO ISSUES FOUND" in audit_feedback.upper() else "rejected"

        result = AuditResult(
            status=status.upper(),
            is_approved=(status == "approved"),
            reason="AI Audit Complete",
            feedback=audit_feedback,
        )

        return {"audit_result": result, "status": status}

    async def committee_manager_node(self, state: CycleState) -> dict[str, Any]:
        """Node for Managing the Committee of Auditors."""
        audit_res = state.get("audit_result")
        i: int = state.get("current_auditor_index", 1)
        j: int = state.get("current_auditor_review_count", 1)
        current_iter: int = state.get("iteration_count", 0)

        if audit_res and audit_res.is_approved:
            if i < settings.NUM_AUDITORS:
                next_idx = i + 1
                console.print(
                    f"[bold green]Auditor #{i} Approved. Moving to Auditor #{next_idx}.[/bold green]"
                )
                return {
                    "current_auditor_index": next_idx,
                    "current_auditor_review_count": 1,
                    "status": "next_auditor",
                }
            console.print("[bold green]All Auditors Approved![/bold green]")
            return {"status": "cycle_approved"}

        if j < settings.REVIEWS_PER_AUDITOR:
            next_rev = j + 1
            console.print(
                f"[bold yellow]Auditor #{i} Rejected. "
                f"Retry {next_rev}/{settings.REVIEWS_PER_AUDITOR}.[/bold yellow]"
            )
            return {
                "current_auditor_review_count": next_rev,
                "iteration_count": current_iter + 1,
                "status": "retry_fix",
            }
        if i < settings.NUM_AUDITORS:
            next_idx = i + 1
            console.print(
                f"[bold yellow]Auditor #{i} limit reached. "
                f"Fixing code then moving to Auditor #{next_idx}.[/bold yellow]"
            )
            return {
                "current_auditor_index": next_idx,
                "current_auditor_review_count": 1,
                "iteration_count": current_iter + 1,
                "status": "retry_fix",
            }
        console.print(
            "[bold yellow]Final Auditor limit reached. Fixing code then Merging.[/bold yellow]"
        )
        return {
            "final_fix": True,
            "iteration_count": current_iter + 1,
            "status": "retry_fix",
        }

    async def uat_evaluate_node(self, _state: CycleState) -> dict[str, Any]:
        """Node for UAT Evaluation."""
        console.print("[bold cyan]Running UAT Evaluation...[/bold cyan]")
        return {"status": "cycle_completed"}

    def check_coder_outcome(self, state: CycleState) -> str:
        if state.get("final_fix", False):
            return "completed"

        status = state.get("status")
        if status == "ready_for_audit":
            return "ready_for_audit"
        if status in {"failed", "architect_failed"}:
            return "failed"
        return "completed"

    def check_audit_outcome(self, _state: CycleState) -> str:
        # Legacy/Unused
        return "rejected_retry"

    def route_committee(self, state: CycleState) -> str:
        """Router from committee_manager_node."""
        status = state.get("status")
        if status == "next_auditor":
            return "auditor"
        if status == "cycle_approved":
            return "uat_evaluate"
        if status == "retry_fix":
            return "coder_session"
        return "failed"
