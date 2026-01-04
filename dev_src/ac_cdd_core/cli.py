import asyncio
import shutil
from typing import Annotated

import typer
from ac_cdd_core import utils
from ac_cdd_core.config import settings
from ac_cdd_core.messages import SuccessMessages
from ac_cdd_core.services.project import ProjectManager
from ac_cdd_core.services.workflow import WorkflowService
from ac_cdd_core.session_manager import SessionManager
from rich.console import Console

app = typer.Typer(help="AC-CDD: AI-Native Cycle-Based Contract-Driven Development Environment")
console = Console()
workflow_service = WorkflowService()


def check_environment() -> None:
    """Check that all required tools and keys are present."""
    if not utils.check_api_key():
        console.print("[bold red]Error:[/bold red] Missing API keys.")
        raise typer.Exit(code=1)

    if not shutil.which("git"):
        console.print("[bold red]Error:[/bold red] Git is not installed or not in PATH.")
        raise typer.Exit(code=1)


@app.command()
def init() -> None:
    """Initialize a new AC-CDD project."""
    check_environment()
    ProjectManager().initialize_project(settings.paths.templates)

    # Initialize empty project state if not exists
    mgr = SessionManager()
    if not mgr.load_manifest():
        try:
            # Create a dummy initial manifest or just ensure directory
            # Real manifest is created at gen-cycles
            mgr.MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
            if not mgr.MANIFEST_PATH.exists():
                mgr.MANIFEST_PATH.write_text("{}", encoding="utf-8")
        except Exception as e:
            console.print(f"[yellow]Warning: Failed to touch project_state.json: {e}[/yellow]")

    console.print("[bold green]Initialization Complete. Happy Coding![/bold green]")


@app.command()
def gen_cycles(
    cycles: Annotated[int, typer.Option("--cycles", help="Base planned cycle count")] = 5,
    project_session_id: Annotated[
        str | None,
        typer.Option("--session", "--id", help="Session ID (overwrites generated one)"),
    ] = None,
) -> None:
    """
    Architect Phase: Generate cycle specs based on requirements.
    """
    asyncio.run(workflow_service.run_gen_cycles(cycles, project_session_id))


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
    asyncio.run(
        workflow_service.run_cycle(
            cycle_id=cycle_id,
            resume=resume,
            auto=auto,
            start_iter=start_iter,
            project_session_id=project_session_id,
        )
    )


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
    asyncio.run(workflow_service.start_session(prompt, audit_mode, max_retries))


@app.command()
def finalize_session(
    project_session_id: Annotated[str | None, typer.Option("--session", help="Session ID")] = None,
) -> None:
    """
    Finalize a development session by creating a PR to main.
    """
    asyncio.run(workflow_service.finalize_session(project_session_id))


@app.command()
def list_actions() -> None:
    """List recommended next actions."""
    mgr = SessionManager()
    manifest = mgr.load_manifest()

    sid = manifest.project_session_id if manifest else None

    if not sid:
        msg = (
            "No active session found.\n\ne.g.,\n"
            "uv run manage.py start-session 'Change greeting to Hello World'\n"
            "or\n"
            "uv run manage.py gen-cycles"
        )
        SuccessMessages.show_panel(msg, "Recommended Actions")
    else:
        # Check incomplete cycles
        next_cycle = next((c.id for c in manifest.cycles if c.status != "completed"), None)
        cycle_cmd = (
            f"uv run manage.py run-cycle --id {next_cycle}"
            if next_cycle
            else "uv run manage.py finalize-session"
        )

        msg = f"Active Session: {sid}\n\nNext steps:\n1. Continue development:\n   {cycle_cmd}\n"
        SuccessMessages.show_panel(msg, "Recommended Actions")


if __name__ == "__main__":
    app()
