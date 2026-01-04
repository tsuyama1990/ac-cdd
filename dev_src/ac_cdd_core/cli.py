import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer
from ac_cdd_core.messages import SuccessMessages, ensure_api_key
from ac_cdd_core.services.git_ops import GitManager
from ac_cdd_core.session_manager import SessionManager
from ac_cdd_core.utils import KeepAwake, logger
from langchain_core.runnables import RunnableConfig
from rich.console import Console
from rich.panel import Panel

from .config import settings
from .graph import GraphBuilder
from .service_container import ServiceContainer
from .services.audit_orchestrator import AuditOrchestrator
from .services.jules_client import JulesClient
from .state import CycleState

app = typer.Typer(help="AC-CDD: AI-Native Cycle-Based Contract-Driven Development Environment")
console = Console()


@dataclass
class RunCycleOptions:
    cycle_id: str
    resume: bool = False
    auto: bool = False
    start_iter: int = 1
    session: str | None = None


@app.command()
def gen_cycles(
    cycles: Annotated[int, typer.Option("--cycles", help="Base planned cycle count")] = 5,
    session_id: Annotated[
        str | None,
        typer.Option("--session", "--id", help="Session ID (overwrites generated one)"),
    ] = None,
    count: Annotated[
        int | None,
        typer.Option("--count", "-n", help="Force to create exactly N cycles"),
    ] = None,
) -> None:
    """
    Architect Phase: Generate cycle specs based on requirements.
    """
    asyncio.run(_run_gen_cycles(cycles, session_id, count))


async def _run_gen_cycles(cycles: int, session_id: str | None, count: int | None) -> None:
    with KeepAwake(reason="Generating Architecture and Cycles"):
        console.rule("[bold blue]Architect Phase: Generating Cycles[/bold blue]")

    ensure_api_key()
    services = ServiceContainer.default()
    builder = GraphBuilder(services)
    graph = builder.build_architect_graph()

    initial_state = CycleState(
        cycle_id=settings.DUMMY_CYCLE_ID,
        project_session_id=session_id,
        planned_cycle_count=cycles,
        requested_cycle_count=count,
    )

    try:
        thread_id = session_id or "architect-session"
        config = RunnableConfig(configurable={"thread_id": thread_id}, recursion_limit=50)
        final_state = await graph.ainvoke(initial_state, config)

        if final_state.get("error"):
            console.print(f"[red]Architect Phase Failed:[/red] {final_state['error']}")
            sys.exit(1)
        else:
            session_id_val = final_state["project_session_id"]
            integration_branch = final_state["integration_branch"]

            SessionManager.save_session(session_id_val, integration_branch)
            git = GitManager()
            try:
                await git.create_integration_branch(session_id_val, branch_name=integration_branch)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Could not prepare integration branch: {e}")

            console.print(SuccessMessages.architect_complete(session_id_val, integration_branch))

    except Exception:  # noqa: BLE001
        console.print("[bold red]Architect execution failed.[/bold red]")
        logger.exception("Architect execution failed")
        sys.exit(1)
    finally:
        await builder.cleanup()


@app.command()
def run_cycle(
    cycle_id: Annotated[str, typer.Option("--id", help="Cycle ID (e.g., 01, 02)")] = "01",
    resume: Annotated[bool, typer.Option("--resume", help="Resume an existing session")] = False,
    auto: Annotated[bool, typer.Option("--auto", help="Auto-approve steps (Headless)")] = False,
    start_iter: Annotated[int, typer.Option("--start-iter", help="Initial iteration count")] = 1,
    project_session_id: Annotated[str | None, typer.Option("--session", help="Session ID")] = None,
) -> None:
    """
    Coder Phase: Implement a specific development cycle.
    """
    options = RunCycleOptions(
        cycle_id=cycle_id,
        resume=resume,
        auto=auto,
        start_iter=start_iter,
        session=project_session_id,
    )
    asyncio.run(_run_run_cycle(options))


async def _run_run_cycle(options: RunCycleOptions) -> None:
    with KeepAwake(reason=f"Running Implementation Cycle {options.cycle_id}"):
        console.rule(f"[bold green]Coder Phase: Cycle {options.cycle_id}[/bold green]")

    ensure_api_key()
    services = ServiceContainer.default()
    builder = GraphBuilder(services)
    graph = builder.build_coder_graph()

    try:
        if options.auto:
            os.environ["AC_CDD_AUTO_APPROVE"] = "1"

        state = CycleState(
            cycle_id=options.cycle_id,
            iteration_count=options.start_iter,
            resume_mode=options.resume,
            project_session_id=options.session or SessionManager.load_session().get("session_id"),
            integration_branch=SessionManager.load_session().get("integration_branch"),
        )

        thread_id = f"cycle-{options.cycle_id}-{state.project_session_id}"
        config = RunnableConfig(configurable={"thread_id": thread_id}, recursion_limit=50)
        final_state = await graph.ainvoke(state, config)

        if final_state.get("error"):
            console.print(f"[red]Cycle {options.cycle_id} Failed:[/red] {final_state['error']}")
            sys.exit(1)

        console.print(
            SuccessMessages.cycle_complete(options.cycle_id, f"{int(options.cycle_id) + 1:02}")
        )

    except Exception:  # noqa: BLE001
        console.print(f"[bold red]Cycle {options.cycle_id} execution failed.[/bold red]")
        logger.exception("Cycle execution failed")
        sys.exit(1)
    finally:
        await builder.cleanup()


@app.command()
def start_session(
    prompt: Annotated[str, typer.Argument(help="High-level goal or requirement")],
    audit_mode: Annotated[
        bool, typer.Option("--audit", help="Enable AI-on-AI planning/audit loop")
    ] = True,
    max_retries: Annotated[int, typer.Option("--retries", help="Max audit retries")] = 3,
) -> None:
    """
    Convenience command to start an end-to-end session with planning and optional auditing.
    """
    asyncio.run(_run_start_session(prompt, audit_mode, max_retries))


async def _run_start_session(prompt: str, audit_mode: bool, max_retries: int) -> None:
    console.rule("[bold magenta]Starting Jules Session[/bold magenta]")

    docs_dir = Path(settings.paths.documents_dir)
    spec_files = {
        str(docs_dir / f): (docs_dir / f).read_text(encoding="utf-8")
        for f in settings.architect_context_files
        if (docs_dir / f).exists()
    }

    if audit_mode:
        orch = AuditOrchestrator()
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
        except Exception:  # noqa: BLE001
            console.print("[bold red]Session Failed.[/bold red]")
            logger.exception("Session Failed")
            sys.exit(1)
    else:
        client = JulesClient()
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
        except Exception:  # noqa: BLE001
            console.print("[bold red]Session Failed.[/bold red]")
            logger.exception("Session Failed")
            sys.exit(1)


@app.command()
def finalize_session(
    project_session_id: Annotated[str | None, typer.Option("--session", help="Session ID")] = None,
) -> None:
    """
    Finalize a development session by creating a PR to main.
    """
    asyncio.run(_run_finalize_session(project_session_id))


async def _run_finalize_session(project_session_id: str | None) -> None:
    console.rule("[bold cyan]Finalizing Development Session[/bold cyan]")
    ensure_api_key()

    session_data = SessionManager.load_session()
    sid = project_session_id or session_data.get("session_id")
    integration_branch = session_data.get("integration_branch")

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
        SessionManager.clear_session()
    except Exception as e:  # noqa: BLE001
        console.print(f"[bold red]Finalization failed:[/bold red] {e}")
        sys.exit(1)


@app.command()
def list_actions() -> None:
    """List recommended next actions."""
    session_data = SessionManager.load_session()
    sid = session_data.get("session_id")

    if not sid:
        msg = (
            "No active session found.\n\ne.g.,\n"
            "uv run manage.py start-session 'Change greeting to Hello World'\n"
            "or\n"
            "uv run manage.py gen-cycles"
        )
        SuccessMessages.show_panel(msg, "Recommended Actions")
    else:
        msg = (
            f"Active Session: {sid}\n\n"
            "Next steps:\n"
            "1. Run a specific cycle:\n"
            "   uv run manage.py run-cycle --id 01\n"
            "2. Finalize the session when all cycles are done:\n"
            "   uv run manage.py finalize-session"
        )
        SuccessMessages.show_panel(msg, "Recommended Actions")


if __name__ == "__main__":
    app()
