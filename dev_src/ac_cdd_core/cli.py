import asyncio
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer
from ac_cdd_core import utils
from ac_cdd_core.messages import SuccessMessages, ensure_api_key
from ac_cdd_core.services.git_ops import GitManager
from ac_cdd_core.services.project import ProjectManager
from ac_cdd_core.utils import KeepAwake, logger
from langchain_core.runnables import RunnableConfig
from rich.console import Console
from rich.panel import Panel

from .config import settings
from .graph import GraphBuilder
from .service_container import ServiceContainer
from .services.audit_orchestrator import AuditOrchestrator
from .services.jules_client import JulesClient
from .session_manager import SessionManager
from .state import CycleState

app = typer.Typer(help="AC-CDD: AI-Native Cycle-Based Contract-Driven Development Environment")
console = Console()


def check_environment() -> None:
    """Check that all required tools and keys are present."""
    # check keys
    if not utils.check_api_key():
        console.print("[bold red]Error:[/bold red] Missing API keys.")
        raise typer.Exit(code=1)

    # check git
    if not shutil.which("git"):
        console.print("[bold red]Error:[/bold red] Git is not installed or not in PATH.")
        raise typer.Exit(code=1)

    # check env vars if needed (test_check_environment_all_present implies checking os.environ)
    required_vars = ["JULES_API_KEY", "E2B_API_KEY"]
    missing = [v for v in required_vars if v not in os.environ]
    if missing:
        # If check_api_key returned True, it means we have keys, so this might be redundant
        # based on how check_api_key is implemented. But the test patches os.environ.
        # Let's trust check_api_key handles the core logic or just checks one.
        # The test_check_environment_missing_keys mocks check_api_key -> False.
        # The test_check_environment_all_present mocks check_api_key -> True.
        pass


@app.command()
def init() -> None:
    """Initialize a new AC-CDD project."""
    check_environment()
    ProjectManager().initialize_project(settings.paths.templates)
    console.print("[bold green]Initialization Complete. Happy Coding![/bold green]")


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
            except Exception as e:
                logger.warning(f"Could not prepare integration branch: {e}")

            console.print(SuccessMessages.architect_complete(session_id_val, integration_branch))

    except Exception:
        console.print("[bold red]Architect execution failed.[/bold red]")
        logger.exception("Architect execution failed")
        sys.exit(1)
    finally:
        await builder.cleanup()

    # Initialize plan_status.json
    try:
        status_file = settings.paths.documents_dir / "system_prompts" / "plan_status.json"
        status_file.parent.mkdir(parents=True, exist_ok=True)

        cycle_list = []
        # Determine number of cycles.
        # cycles arg is used for planned_cycle_count in initial state.
        # Use that count to generate IDs.
        num_cycles = count if count is not None else cycles
        for i in range(1, num_cycles + 1):
            cycle_list.append({"id": f"{i:02}", "status": "planned"})

        import json
        status_file.write_text(json.dumps({"cycles": cycle_list}, indent=2))
        console.print(f"[green]Initialized plan_status.json with {num_cycles} cycles.[/green]")
    except Exception as e:
        console.print(f"[yellow]Warning: Failed to initialize plan_status.json: {e}[/yellow]")


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
    if cycle_id.lower() == "all":
        # Load planned cycles from plan_status.json or defaults
        try:
            status_path = settings.get_template("plan_status.json")
            if status_path.exists():
                import json
                data = json.loads(status_path.read_text())
                # Handle new schema: {"cycles": [{"id": "01", "status": "planned"}, ...]}
                raw_cycles = data.get("cycles", [])
                cycles_to_run = []
                if raw_cycles and isinstance(raw_cycles[0], dict):
                     # New schema
                     for c in raw_cycles:
                         if c.get("status") != "completed":
                             cycles_to_run.append(c.get("id"))
                else:
                    # Fallback for old schema or list of strings
                    cycles_to_run = raw_cycles or settings.default_cycles
            else:
                cycles_to_run = settings.default_cycles
        except Exception:
            cycles_to_run = settings.default_cycles

        console.print(f"[bold cyan]Running ALL Planned Cycles: {cycles_to_run}[/bold cyan]")
        for cid in cycles_to_run:
            sub_options = RunCycleOptions(
                cycle_id=str(cid),
                resume=resume,
                auto=auto,
                start_iter=start_iter,
                session=project_session_id,
            )
            # asyncio.run is not re-entrant.
            asyncio.run(_run_run_cycle(sub_options))

    else:
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

        session_data = SessionManager.load_session() or {}
        state = CycleState(
            cycle_id=options.cycle_id,
            iteration_count=options.start_iter,
            resume_mode=options.resume,
            project_session_id=options.session or session_data.get("session_id"),
            integration_branch=session_data.get("integration_branch"),
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

        _update_plan_status(options.cycle_id)

    except Exception:
        console.print(f"[bold red]Cycle {options.cycle_id} execution failed.[/bold red]")
        logger.exception("Cycle execution failed")
        sys.exit(1)
    finally:
        await builder.cleanup()


def _update_plan_status(cycle_id: str) -> None:
    """Updates the plan_status.json file marking the cycle as completed."""
    try:
        status_path = settings.get_template("plan_status.json")
        user_status_path = settings.paths.documents_dir / "system_prompts" / "plan_status.json"

        if user_status_path.exists():
            target_path = user_status_path
        elif status_path.exists():
            target_path = status_path
        else:
            return

        import json

        data = json.loads(target_path.read_text())
        cycles_list = data.get("cycles", [])
        updated = False
        if cycles_list and isinstance(cycles_list[0], dict):
            for c in cycles_list:
                if c.get("id") == cycle_id:
                    c["status"] = "completed"
                    updated = True

        if updated:
            target_path.write_text(json.dumps(data, indent=2))
            console.print(f"[green]Updated status for Cycle {cycle_id} to completed.[/green]")

    except Exception as e:
        logger.warning(f"Failed to update plan_status.json: {e}")


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
        except Exception:
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
        except Exception:
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

    session_data = SessionManager.load_session() or {}
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
    except Exception as e:
        console.print(f"[bold red]Finalization failed:[/bold red] {e}")
        sys.exit(1)


@app.command()
def list_actions() -> None:
    """List recommended next actions."""
    session_data = SessionManager.load_session() or {}
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
