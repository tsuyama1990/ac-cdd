from pathlib import Path
from typing import Any

from rich.console import Console

from .config import settings
from .domain_models import AuditResult
from .sandbox import SandboxRunner
from .services.audit_orchestrator import AuditOrchestrator
from .services.jules_client import JulesClient
from .services.llm_reviewer import LLMReviewer
from .state import CycleState

console = Console()


class CycleNodes:
    """
    Encapsulates the logic for each node in the AC-CDD workflow graph.
    Decoupled from the graph topology definition in GraphBuilder.
    """

    def __init__(self, sandbox_runner: SandboxRunner, jules_client: JulesClient):
        self.sandbox = sandbox_runner
        self.jules = jules_client
        self.audit_orchestrator = AuditOrchestrator(jules_client, sandbox_runner)
        # LLMReviewer now accepts sandbox_runner (though mainly for consistent init signature)
        self.llm_reviewer = LLMReviewer(sandbox_runner=sandbox_runner)

    async def _read_files(self, file_paths: list[str]) -> dict[str, str]:
        """Helper to read files from the sandbox (or local if path exists locally)."""
        result = {}
        for path_str in file_paths:
            # We assume paths are absolute container paths (/app/...) or relative.
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
        context_files = settings.get_context_files()

        session_id = f"architect-cycle-{state['cycle_id']}"

        result = await self.jules.run_session(
            session_id=session_id,
            prompt=instruction,
            target_files=context_files,  # Architect edits specs
            context_files=[],  # Input requirements (like ALL_SPEC) could go here if distinct
            completion_signal_file=Path("completion_signal"),
            require_plan_approval=True,
        )

        if result.get("status") == "success" or result.get("status") == "running":
            return {"status": "architect_completed", "current_phase": "architect_done"}
        else:
            return {"status": "architect_failed", "error": result.get("error")}

    async def coder_session_node(self, state: CycleState) -> dict[str, Any]:
        """Node for Coder Agent (Jules)."""
        cycle_id = state["cycle_id"]
        iteration = state["iteration_count"]

        console.print(
            f"[bold green]Starting Coder Session for Cycle {cycle_id} "
            f"(Iteration {iteration})...[/bold green]"
        )

        instruction = settings.get_template("CODER_INSTRUCTION.md").read_text()
        target_files = settings.get_target_files()
        context_files = settings.get_context_files()

        try:
            session_id = f"coder-cycle-{cycle_id}-iter-{iteration}"

            # Pass separated files to updated JulesClient
            result = await self.jules.run_session(
                session_id=session_id,
                prompt=instruction,
                target_files=target_files,
                context_files=context_files,
                completion_signal_file=Path("completion_signal"),
                require_plan_approval=False,
            )

            if result.get("status") == "success" or result.get("pr_url"):
                return {"status": "ready_for_audit", "pr_url": result.get("pr_url")}
            else:
                return {"status": "failed", "error": "Jules failed to produce PR"}

        except Exception as e:
            console.print(f"[red]Coder Session Failed: {e}[/red]")
            return {"status": "failed", "error": str(e)}

    async def auditor_node(self, state: CycleState) -> dict[str, Any]:
        """Node for Auditor Agent (Aider/LLM)."""
        console.print("[bold magenta]Starting Auditor...[/bold magenta]")

        instruction = settings.get_template("AUDITOR_INSTRUCTION.md").read_text()

        target_paths = settings.get_target_files()
        context_paths = settings.get_context_files()

        target_files = await self._read_files(target_paths)
        context_docs = await self._read_files(context_paths)

        model = "claude-3-5-sonnet"

        audit_feedback = await self.llm_reviewer.review_code(
            target_files=target_files,
            context_docs=context_docs,
            instruction=instruction,
            model=model,
        )

        status = "approved" if "NO ISSUES FOUND" in audit_feedback.upper() else "rejected"

        # Use the Domain Model AuditResult instead of SimpleAuditResult
        result = AuditResult(
            status=status.upper(),  # 'APPROVED' or 'REJECTED'
            is_approved=(status == "approved"),
            reason="AI Audit Complete",
            feedback=audit_feedback,
        )

        return {"audit_result": result, "status": status}

    async def uat_evaluate_node(self, state: CycleState) -> dict[str, Any]:
        """Node for UAT Evaluation."""
        console.print("[bold cyan]Running UAT Evaluation...[/bold cyan]")
        return {"status": "cycle_completed"}

    def check_coder_outcome(self, state: CycleState) -> str:
        status = state.get("status")
        if status == "ready_for_audit":
            return "ready_for_audit"
        elif status == "failed" or status == "architect_failed":
            return "failed"
        return "completed"

    def check_audit_outcome(self, state: CycleState) -> str:
        audit_res = state.get("audit_result")
        if not audit_res:
            return "rejected_retry"

        if audit_res.is_approved:
            return "approved"

        if state["iteration_count"] >= settings.max_audit_retries:
            console.print("[bold red]Max audit retries reached. Stopping.[/bold red]")
            return "rejected_max_retries"

        return "rejected_retry"
