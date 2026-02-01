import asyncio
import shutil
from typing import Annotated

import typer
from ac_cdd_core import utils
from ac_cdd_core.config import settings
from ac_cdd_core.messages import SuccessMessages
from ac_cdd_core.services.project import ProjectManager
from ac_cdd_core.services.workflow import WorkflowService
from ac_cdd_core.state_manager import StateManager
from ac_cdd_core.utils import get_command_prefix
from rich.console import Console

app = typer.Typer(help="AC-CDD: AI-Native Cycle-Based Contract-Driven Development Environment")
console = Console()


class _WorkflowServiceHolder:
    """Holder for lazy-initialized workflow service."""

    _instance: WorkflowService | None = None

    @classmethod
    def get(cls) -> WorkflowService:
        """Get or create the workflow service instance."""
        if cls._instance is None:
            cls._instance = WorkflowService()
        return cls._instance


def _is_docker_environment() -> bool:
    """Detect if running inside a Docker container."""
    import os
    from pathlib import Path

    # Method 1: Check for /.dockerenv file (most reliable)
    if Path("/.dockerenv").exists():
        return True

    # Method 2: Check cgroup for docker
    try:
        with Path("/proc/self/cgroup").open() as f:
            if "docker" in f.read():
                return True
    except (FileNotFoundError, PermissionError):
        pass

    # Method 3: Check environment variable
    return os.environ.get("DOCKER_CONTAINER") == "true"


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
    """Initialize a new AC-CDD project structure and create .env template."""
    import os

    # Warn if running with sudo
    if os.geteuid() == 0:
        console.print("[bold red]⚠ WARNING: Running with sudo/root privileges![/bold red]")
        console.print("[yellow]This may create files with incorrect ownership.[/yellow]")
        console.print("[yellow]Please run without sudo: uv run manage.py init[/yellow]\n")
        if not typer.confirm("Continue anyway?"):
            raise typer.Abort()

    # Don't check environment yet - .env doesn't exist
    asyncio.run(ProjectManager().initialize_project(str(settings.paths.templates)))

    # Get appropriate command prefix
    cmd = get_command_prefix()

    # Show next steps
    console.print("\n[bold green]✓ Project Structure Created![/bold green]\n")
    console.print("[bold cyan]Next Steps:[/bold cyan]")
    console.print("  1. Configure your API keys:")
    console.print("     [yellow]cp .ac_cdd/.env.example .ac_cdd/.env[/yellow]")
    console.print("     Then edit [yellow].ac_cdd/.env[/yellow] and add your API keys\n")
    console.print("  2. Verify your configuration:")
    console.print(f"     [yellow]{cmd} env-verify[/yellow]\n")
    console.print("  3. Define your project requirements:")
    console.print("     Edit [yellow]dev_documents/ALL_SPEC.md[/yellow]\n")
    console.print("  4. Define your target user experience:")
    console.print("     Edit [yellow]dev_documents/USER_TEST_SCENARIO.md[/yellow]\n")
    console.print("  5. Generate development cycles:")
    console.print(f"     [yellow]{cmd} gen-cycles[/yellow]\n")


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
    asyncio.run(_WorkflowServiceHolder.get().run_gen_cycles(cycles, project_session_id))


@app.command()
def run_cycle(
    cycle_id: Annotated[str, typer.Option("--id", help="Cycle ID (e.g., 01, 02)")] = "01",
    resume: Annotated[bool, typer.Option("--resume", help="Resume an existing session")] = False,
    auto: Annotated[
        bool,
        typer.Option(
            "--auto/--no-auto",
            help="Auto-approve steps and run auditors automatically (default: enabled)",
        ),
    ] = True,  # Changed default to True - automated auditing is the core feature
    start_iter: Annotated[int, typer.Option("--start-iter", help="Initial iteration count")] = 1,
    project_session_id: Annotated[str | None, typer.Option("--session", help="Session ID")] = None,
) -> None:
    """
    Coder Phase: Implement a specific development cycle.

    By default, runs with automated code review (Committee of Auditors).
    Use --no-auto to disable automated auditing (not recommended).
    """
    asyncio.run(
        _WorkflowServiceHolder.get().run_cycle(
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
    asyncio.run(_WorkflowServiceHolder.get().start_session(prompt, audit_mode, max_retries))


@app.command()
def resume_session(
    feature_branch: Annotated[
        str,
        typer.Argument(
            help="Existing feature branch (e.g., feat/generate-architecture-20260110-1640)"
        ),
    ],
    integration_branch: Annotated[
        str | None, typer.Option("--integration", help="Integration branch")
    ] = None,
    cycles: Annotated[int, typer.Option("--cycles", help="Number of cycles")] = 8,
) -> None:
    """
    Resume development with an existing architecture branch.

    This skips gen-cycles and creates a manifest using existing branches.
    Useful when you already have SPEC.md files and want to continue development.

    Example:
        ac-cdd resume-session feat/generate-architecture-20260110-1640 --cycles 8
    """
    _resume_session(feature_branch, integration_branch, cycles)


def _resume_session(feature_branch: str, integration_branch: str | None, cycles: int) -> None:
    """Resume session with existing branches."""
    from datetime import UTC, datetime

    from rich.console import Console

    from .domain_models import CycleManifest, ProjectManifest
    from .state_manager import StateManager

    console = Console()

    # Generate session ID
    session_id = f"resume-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"

    # Use feature branch name for integration if not provided
    if not integration_branch:
        # Extract timestamp from feature branch
        # feat/generate-architecture-20260110-1640 -> dev/architect-cycle-00-20260110-1640/integration
        parts = feature_branch.split("-")
        if len(parts) >= 3:
            timestamp = "-".join(parts[-2:])
            integration_branch = f"dev/architect-cycle-00-{timestamp}/integration"
        else:
            integration_branch = f"dev/{feature_branch}/integration"

    console.print("[bold cyan]Resuming session with existing branches:[/bold cyan]")
    console.print(f"  Feature branch: [green]{feature_branch}[/green]")
    console.print(f"  Integration branch: [green]{integration_branch}[/green]")
    console.print(f"  Cycles: [green]{cycles}[/green]")

    # Create manifest
    mgr = StateManager()
    manifest = ProjectManifest(
        project_session_id=session_id,
        feature_branch=feature_branch,
        integration_branch=integration_branch,
        cycles=[CycleManifest(id=f"{i:02}", status="planned") for i in range(1, cycles + 1)],
    )

    mgr.save_manifest(manifest)

    console.print("\n[bold green]✅ Session resumed![/bold green]")
    console.print(f"Session ID: [cyan]{session_id}[/cyan]")
    console.print("\nYou can now run:")
    console.print("  [bold]ac-cdd run-cycle --id 01[/bold]")
    console.print("  [bold]ac-cdd run-cycle --id all[/bold]")


@app.command()
def finalize_session(
    project_session_id: Annotated[str | None, typer.Option("--session", help="Session ID")] = None,
) -> None:
    """
    Finalize a development session by creating a PR to main.
    """
    asyncio.run(_WorkflowServiceHolder.get().finalize_session(project_session_id))


@app.command()
def list_actions() -> None:
    """List recommended next actions."""

    async def _list() -> None:
        mgr = StateManager()
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
        elif manifest:
            # Check incomplete cycles
            next_cycle = next((c.id for c in manifest.cycles if c.status != "completed"), None)
            cycle_cmd = (
                f"uv run manage.py run-cycle --id {next_cycle}"
                if next_cycle
                else "uv run manage.py finalize-session"
            )

            msg = (
                f"Active Session: {sid}\n\nNext steps:\n1. Continue development:\n   {cycle_cmd}\n"
            )
            SuccessMessages.show_panel(msg, "Recommended Actions")

    asyncio.run(_list())


@app.command()
def env_verify() -> None:  # noqa: PLR0915
    """Verify environment configuration and API keys."""
    import os
    from pathlib import Path

    from rich.panel import Panel
    from rich.table import Table

    console.print("\n[bold cyan]🔍 Environment Configuration Verification[/bold cyan]\n")

    # Check which .env file is being used
    ac_cdd_env = Path.cwd() / ".ac_cdd" / ".env"
    root_env = Path.cwd() / ".env"

    env_file_used = None
    if ac_cdd_env.exists():
        env_file_used = str(ac_cdd_env)
        console.print(f"[green]✓[/green] Using: [yellow]{ac_cdd_env}[/yellow]")
    elif root_env.exists():
        env_file_used = str(root_env)
        console.print(f"[green]✓[/green] Using: [yellow]{root_env}[/yellow]")
    else:
        console.print("[red]✗[/red] No .env file found!")
        console.print("  Run: [yellow]cp .ac_cdd/.env.example .ac_cdd/.env[/yellow]")
        raise typer.Exit(code=1)

    console.print()

    # Check API Keys
    console.print("[bold]API Keys:[/bold]")
    api_keys = {
        "JULES_API_KEY": os.getenv("JULES_API_KEY"),
        "E2B_API_KEY": os.getenv("E2B_API_KEY"),
        "OPENROUTER_API_KEY": os.getenv("OPENROUTER_API_KEY"),
    }

    missing_keys = []
    for key, value in api_keys.items():
        if value and value != f"your-{key.lower().replace('_', '-')}-here":
            # Mask the key for security
            masked = value[:8] + "..." + value[-4:] if len(value) > 12 else "***"
            console.print(f"  [green]✓[/green] {key}: {masked}")
        else:
            console.print(f"  [red]✗[/red] {key}: Not set")
            missing_keys.append(key)

    console.print()

    # Check Model Configuration
    console.print("[bold]Model Configuration:[/bold]")

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Component", style="cyan")
    table.add_column("Model", style="yellow")
    table.add_column("Source", style="dim")

    # Check environment variables
    smart_model = os.getenv("SMART_MODEL")
    fast_model = os.getenv("FAST_MODEL")

    # Show what's configured
    table.add_row("SMART_MODEL (env)", smart_model or "[red]Not set[/red]", "Environment")
    table.add_row("FAST_MODEL (env)", fast_model or "[red]Not set[/red]", "Environment")
    table.add_row("", "", "")

    # Show actual settings being used
    table.add_row("Auditor Agent", settings.agents.auditor_model, "Resolved")
    table.add_row("QA Analyst Agent", settings.agents.qa_analyst_model, "Resolved")
    table.add_row("Reviewer (Smart)", settings.reviewer.smart_model, "Resolved")
    table.add_row("Reviewer (Fast)", settings.reviewer.fast_model, "Resolved")

    console.print(table)
    console.print()

    # Test model initialization
    console.print("[bold]Model Connectivity Test:[/bold]")
    try:
        from ac_cdd_core.agents import get_model

        test_models = [
            ("Auditor", settings.agents.auditor_model),
            ("QA Analyst", settings.agents.qa_analyst_model),
        ]

        for name, model_name in test_models:
            try:
                get_model(model_name)  # Test model initialization
                console.print(f"  [green]✓[/green] {name}: {model_name}")
            except Exception as e:
                console.print(f"  [red]✗[/red] {name}: {model_name} - {str(e)[:50]}")
    except Exception as e:
        console.print(f"  [yellow]⚠[/yellow] Could not test models: {e}")

    console.print()

    # Summary
    if missing_keys:
        panel = Panel(
            "[yellow]⚠ Missing API Keys:[/yellow]\n"
            + "\n".join(f"  • {key}" for key in missing_keys)
            + f"\n\nPlease edit: [cyan]{env_file_used}[/cyan]",
            title="[bold yellow]Configuration Incomplete[/bold yellow]",
            border_style="yellow",
        )
        console.print(panel)
        raise typer.Exit(code=1)

    cmd = get_command_prefix()
    panel = Panel(
        "[green]All required API keys are configured![/green]\n"
        "[green]Model configuration is valid![/green]\n\n"
        "You're ready to start development!\n"
        f"Next step: [yellow]{cmd} gen-cycles[/yellow]",
        title="[bold green]✓ Configuration Valid[/bold green]",
        border_style="green",
    )
    console.print(panel)


if __name__ == "__main__":
    app()
