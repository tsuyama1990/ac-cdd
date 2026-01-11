import os
import sys

from ac_cdd_core.config import settings
from ac_cdd_core.domain_models import CycleManifest
from ac_cdd_core.graph import GraphBuilder
from ac_cdd_core.messages import SuccessMessages, ensure_api_key
from ac_cdd_core.service_container import ServiceContainer
from ac_cdd_core.services.audit_orchestrator import AuditOrchestrator
from ac_cdd_core.services.git_ops import GitManager
from ac_cdd_core.services.jules_client import JulesClient
from ac_cdd_core.state import CycleState
from ac_cdd_core.state_manager import StateManager
from ac_cdd_core.utils import KeepAwake, logger
from langchain_core.runnables import RunnableConfig
from rich.console import Console
from rich.panel import Panel

console = Console()


class WorkflowService:
    def __init__(self) -> None:
        self.services = ServiceContainer.default()
        self.builder = GraphBuilder(self.services)

    async def run_gen_cycles(self, cycles: int, project_session_id: str | None) -> None:
        with KeepAwake(reason="Generating Architecture and Cycles"):
            console.rule("[bold blue]Architect Phase: Generating Cycles[/bold blue]")

        ensure_api_key()
        graph = self.builder.build_architect_graph()

        initial_state = CycleState(
            cycle_id=settings.DUMMY_CYCLE_ID,
            project_session_id=project_session_id,
            planned_cycle_count=cycles,
            requested_cycle_count=cycles,
        )

        try:
            thread_id = project_session_id or "architect-session"
            config = RunnableConfig(configurable={"thread_id": thread_id}, recursion_limit=50)
            final_state = await graph.ainvoke(initial_state, config)

            if final_state.get("error"):
                console.print(f"[red]Architect Phase Failed:[/red] {final_state['error']}")
                sys.exit(1)
            else:
                session_id_val = final_state["project_session_id"]
                integration_branch = final_state["integration_branch"]

                # In new strategy, integration_branch IS the feature branch
                feature_branch = integration_branch

                # Create Manifest with Cycles
                mgr = StateManager()
                manifest = mgr.create_manifest(
                    session_id_val,
                    feature_branch=feature_branch,
                    integration_branch=integration_branch,
                )
                manifest.cycles = [
                    CycleManifest(id=f"{i:02}", status="planned") for i in range(1, cycles + 1)
                ]
                mgr.save_manifest(manifest)

                console.print(
                    SuccessMessages.architect_complete(session_id_val, integration_branch)
                )

        except Exception:
            console.print("[bold red]Architect execution failed.[/bold red]")
            logger.exception("Architect execution failed")
            sys.exit(1)
        finally:
            await self.builder.cleanup()

    async def run_cycle(
        self,
        cycle_id: str,
        resume: bool,
        auto: bool,
        start_iter: int,
        project_session_id: str | None,
    ) -> None:
        if cycle_id.lower() == "all":
            await self._run_all_cycles(resume, auto, start_iter, project_session_id)
            return

        await self._run_single_cycle(cycle_id, resume, auto, start_iter, project_session_id)

    async def _run_all_cycles(
        self, resume: bool, auto: bool, start_iter: int, project_session_id: str | None
    ) -> None:
        mgr = StateManager()
        manifest = mgr.load_manifest()

        if manifest:
            cycles_to_run = [c.id for c in manifest.cycles if c.status != "completed"]
        else:
            cycles_to_run = settings.default_cycles

        console.print(f"[bold cyan]Running ALL Planned Cycles: {cycles_to_run}[/bold cyan]")

        for idx, cid in enumerate(cycles_to_run, 1):
            console.print(
                f"[bold yellow]Starting Cycle {cid} ({idx}/{len(cycles_to_run)})[/bold yellow]"
            )
            await self._run_single_cycle(str(cid), resume, auto, start_iter, project_session_id)
            console.print(
                f"[bold green]Completed Cycle {cid} ({idx}/{len(cycles_to_run)})[/bold green]"
            )

    async def _run_single_cycle(
        self,
        cycle_id: str,
        resume: bool,
        auto: bool,
        start_iter: int,
        project_session_id: str | None,
    ) -> None:
        with KeepAwake(reason=f"Running Implementation Cycle {cycle_id}"):
            console.rule(f"[bold green]Coder Phase: Cycle {cycle_id}[/bold green]")

        ensure_api_key()
        graph = self.builder.build_coder_graph()

        try:
            if auto:
                os.environ["AC_CDD_AUTO_APPROVE"] = "1"

            mgr = StateManager()
            manifest = mgr.load_manifest()

            # Fallback if manifest doesn't exist (shouldn't happen in proper flow)
            pid = project_session_id
            ib = None
            if manifest:
                pid = pid or manifest.project_session_id
                ib = manifest.integration_branch
            else:
                console.print("[red]No active session found. Run gen-cycles first.[/red]")
                sys.exit(1)

            # CRITICAL: Checkout feature branch before starting coder session
            # This is the main development branch where all cycles accumulate
            fb = manifest.feature_branch if manifest else None
            if fb:
                logger.info(f"Checking out feature branch: {fb}")
                git = GitManager()
                try:
                    await git.checkout_branch(fb)
                    logger.info(f"Successfully checked out feature branch: {fb}")
                except Exception as e:
                    logger.warning(f"Could not checkout feature branch: {e}")
                    logger.warning("Proceeding with current branch (may cause issues!)")
            else:
                logger.warning("No feature branch found in manifest. Using current branch.")

            state = CycleState(
                cycle_id=cycle_id,
                iteration_count=start_iter,
                resume_mode=resume,
                project_session_id=pid,
                feature_branch=fb,  # Main development branch
                integration_branch=ib,  # For future finalize-session
            )

            thread_id = f"cycle-{cycle_id}-{state.project_session_id}"
            config = RunnableConfig(configurable={"thread_id": thread_id}, recursion_limit=50)
            final_state = await graph.ainvoke(state, config)

            if final_state.get("error"):
                console.print(f"[red]Cycle {cycle_id} Failed:[/red] {final_state['error']}")
                sys.exit(1)

            console.print(SuccessMessages.cycle_complete(cycle_id, f"{int(cycle_id) + 1:02}"))

            # Update status to completed
            if manifest:
                mgr.update_cycle_state(cycle_id, status="completed")

        except Exception:
            console.print(f"[bold red]Cycle {cycle_id} execution failed.[/bold red]")
            logger.exception("Cycle execution failed")
            sys.exit(1)
        finally:
            await self.builder.cleanup()

    async def start_session(self, prompt: str, audit_mode: bool, max_retries: int) -> None:
        console.rule("[bold magenta]Starting Jules Session[/bold magenta]")

        docs_dir = settings.paths.documents_dir
        spec_files = {
            str(docs_dir / f): (docs_dir / f).read_text(encoding="utf-8")
            for f in settings.architect_context_files
            if (docs_dir / f).exists()
        }

        if audit_mode:
            orch = AuditOrchestrator(self.services.jules, self.builder.sandbox)
            try:
                result = await orch.run_interactive_session(
                    prompt=prompt,
                    spec_files=spec_files,
                    max_retries=max_retries,
                )
                if result and result.get("pr_url"):
                    console.print(
                        Panel(
                            f"Audit & Implementation Complete.\nPR: {result['pr_url']}",
                            style="bold green",
                        )
                    )
            except Exception:
                console.print("[bold red]Session Failed.[/bold red]")
                logger.exception("Session Failed")
                sys.exit(1)
        else:
            client = self.services.jules or JulesClient()
            try:
                result = await client.run_session(
                    session_id=settings.current_session_id,
                    prompt=prompt,
                    files=list(spec_files.keys()),
                )
                if result and result.get("pr_url"):
                    console.print(
                        Panel(
                            f"Implementation Sent.\nPR: {result['pr_url']}",
                            style="bold green",
                        )
                    )
            except Exception:
                console.print("[bold red]Session Failed.[/bold red]")
                logger.exception("Session Failed")
                sys.exit(1)

    async def finalize_session(self, project_session_id: str | None) -> None:
        console.rule("[bold cyan]Finalizing Development Session[/bold cyan]")
        ensure_api_key()

        mgr = StateManager()
        manifest = mgr.load_manifest()

        sid = project_session_id or (manifest.project_session_id if manifest else None)
        integration_branch = manifest.integration_branch if manifest else None

        if not sid or not integration_branch:
            console.print("[red]No active session found to finalize.[/red]")
            sys.exit(1)

        git = GitManager()
        try:
            pr_url = await git.create_final_pr(
                integration_branch=integration_branch,
                title=f"Finalize Development Session: {sid}",
                body=f"This PR merges all implemented cycles from session {sid} into main.",
            )
            console.print(SuccessMessages.session_finalized(pr_url))
        except Exception as e:
            console.print(f"[bold red]Finalization failed:[/bold red] {e}")
            sys.exit(1)
