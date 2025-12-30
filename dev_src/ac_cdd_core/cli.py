import sys
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel

from .config import settings

# from .graph import build_architect_graph, build_coder_graph
from .service_container import ServiceContainer
from .state import CycleState
from .utils import logger

app = typer.Typer(help="AC-CDD: AI-Native Cycle-Based Contract-Driven Development Environment")
console = Console()


@app.callback()
def main() -> None:
    """AC-CDD CLI Entry Point"""
    pass


def check_environment() -> None:
    """Checks for required tools and API keys."""
    import os
    import shutil

    from dotenv import load_dotenv

    load_dotenv()

    missing_tools = []
    missing_vars = []

    # 1. Executables
    # Removing 'aider' and 'jules' from local requirements as we aim for fully remote architecture.
    # 'git' and 'uv' are still needed for local project management.
    # 'gh' is optional but recommended for PRs.
    required_tools = ["uv", "git"]
    for tool in required_tools:
        if not shutil.which(tool):
            missing_tools.append(tool)

    # 2. Environment Variables
    # Check strict requirements. Note: OpenRouter is optional if Gemini is used directly,
    # but we should check at least one LLM key.
    # Jules requires JULES_API_KEY.
    required_vars = ["JULES_API_KEY", "E2B_API_KEY"]

    # We need at least one model provider
    if (
        not os.environ.get("GEMINI_API_KEY")
        and not os.environ.get("GOOGLE_API_KEY")
        and not os.environ.get("OPENROUTER_API_KEY")
    ):
        missing_vars.append("GEMINI_API_KEY (or GOOGLE_API_KEY / OPENROUTER_API_KEY)")

    for var in required_vars:
        if not os.environ.get(var):
            missing_vars.append(var)

    if missing_tools or missing_vars:
        console.print(Panel("Environment Check Failed", style="bold red"))

        if missing_tools:
            console.print("[bold red]Missing Executables:[/bold red]")
            for tool in missing_tools:
                console.print(f"- {tool}")
            console.print(
                "\n[yellow]Please install these tools and ensure they are in your PATH.[/yellow]\n"
            )

        if missing_vars:
            console.print("[bold red]Missing Environment Variables:[/bold red]")
            for var in missing_vars:
                console.print(f"- {var}")
            console.print("\n[yellow]Please check your .env file.[/yellow]\n")

        # We don't exit strict here to allow users to fix while running,
        # but we prompt them heavily.
        if not typer.confirm("Do you want to proceed anyway? (May cause runtime errors)"):
            raise typer.Exit(code=1)
    else:
        console.print("[bold green]✓ Environment Check Passed[/bold green]")


@app.command()
def init() -> None:
    """
    Initialize the AC-CDD environment.
    Checks environment and creates necessary directories and files.
    """
    check_environment()

    from .services.project import ProjectManager

    manager = ProjectManager()
    try:
        manager.initialize_project(settings.paths.templates)
        msg = (
            "✅ Initialization Complete!\n\n"
            "Next Steps:\n"
            "1. Edit the requirements file:\n"
            f"   {settings.paths.documents_dir}/ALL_SPEC.md\n"
            "   (This file was copied from templates. Please define your project goals here.)\n\n"
            "2. Generate architecture and cycle plans:\n"
            "   uv run manage.py gen-cycles"
        )
        console.print(Panel(msg, title="Next Action Guide", style="bold green", expand=False))
    except Exception as e:
        console.print(f"[red]Initialization failed:[/red] {e}")
        raise typer.Exit(code=1) from e


@app.command(name="gen-cycles")
def gen_cycles(
    cycles: Annotated[int, typer.Option(help="Max number of cycles to plan")] = 5,
    session_id: Annotated[
        str, typer.Option(help="Session ID (auto-generated if not provided)")
    ] = None,
) -> None:
    """
    Run the Architect Phase and start a new development session.
    Creates an integration branch for isolated development.
    """
    import asyncio

    async def _run() -> None:
        console.rule("[bold blue]Architect Phase: Generating Cycles[/bold blue]")

        # Check API availability first
        from ac_cdd_core.messages import ensure_api_key
        ensure_api_key()

        services = ServiceContainer.default()
        from .graph import GraphBuilder

        # Instantiate builder to manage resources
        builder = GraphBuilder(services)
        graph = builder.build_architect_graph()

        # Initialize state with session
        initial_state = CycleState(cycle_id=settings.DUMMY_CYCLE_ID, session_id=session_id)

        # Run the graph
        try:
            # We use aconfig={"recursion_limit": 50} for safety if needed
            final_state = await graph.ainvoke(initial_state)

            if final_state.get("error"):
                console.print(f"[red]Architect Phase Failed:[/red] {final_state['error']}")
                sys.exit(1)
            else:
                session_id_final = final_state.session_id
                integration_branch = final_state.integration_branch

                # Save session for future use
                from ac_cdd_core.messages import SuccessMessages

                from .session_manager import SessionManager

                SessionManager.save_session(session_id_final, integration_branch)

                # Show success message
                SuccessMessages.show_panel(
                    SuccessMessages.architect_complete(session_id_final, integration_branch)
                )

        except Exception as e:
            console.print(f"[red]Error during execution:[/red] {e}")
            logger.exception("Graph execution failed")
            sys.exit(1)
        finally:
            # Graceful cleanup
            await builder.cleanup()

    asyncio.run(_run())


@app.command(name="run-cycle")
def run_cycle(
    cycle_id: Annotated[str, typer.Option("--id", help="Cycle ID (e.g., '01') or 'all'")] = "01",
    session_id: Annotated[str, typer.Option("--session", help="Session ID")] = None,
    auto: Annotated[bool, typer.Option(help="Run without manual confirmation")] = False,
    start_iter: Annotated[
        int,
        typer.Option(
            "--start-iter", help="Force start at specific iteration (0=Creator, 1=Refiner)"
        ),
    ] = 0,
    resume_session: Annotated[
        str, typer.Option("--resume", help="Resume from existing Jules Session ID")
    ] = None,
) -> None:
    """
    Run a Development Cycle within a session.
    Implements features, runs tests, performs UAT, and Audits.
    """
    import asyncio

    async def execute_single_cycle(target_cycle: str) -> None:
        console.rule(
            f"[bold green]Running Cycle {target_cycle} (Start Iter: {start_iter})[/bold green]"
        )

        # Check API availability
        from ac_cdd_core.messages import ensure_api_key
        ensure_api_key()

        services = ServiceContainer.default()
        from .graph import GraphBuilder

        # Instantiate builder to manage resources
        builder = GraphBuilder(services)
        graph = builder.build_coder_graph()

        # Load session using consolidated helper (with optional resume)
        from .session_manager import SessionManager, SessionValidationError
        from .validators import SessionValidator, ValidationError
        
        try:
            session_id_to_use, integration_branch, resume_info = await SessionManager.load_or_reconcile_session(
                session_id=session_id,
                auto_reconcile=True,
                resume_jules_session=resume_session,  # Integrated!
            )
            
            # Show appropriate message
            if resume_info:
                console.print(f"[green]✓ Resumed Jules session with PR: {resume_info['pr_url']}[/green]")
            elif not session_id:
                if SessionManager.load_session() is None:
                    console.print(f"[green]✓ Reconciled session: {session_id_to_use}[/green]")
                else:
                    console.print(f"[dim]Using saved session: {session_id_to_use}[/dim]")
        except SessionValidationError as e:
            console.print(f"[red]{e}[/red]")
            sys.exit(1)

        # Validate session using validator class
        try:
            validator = SessionValidator(session_id_to_use, integration_branch, check_remote=True)
            is_valid, error_msg = await validator.validate()
            if not is_valid:
                console.print(f"[red]{error_msg}[/red]")
                sys.exit(1)
        except ValidationError as e:
            console.print(f"[red]{e}[/red]")
            sys.exit(1)

        # Initialize state
        initial_state = CycleState(
            cycle_id=target_cycle,
            iteration_count=start_iter,
            session_id=session_id_to_use,
            integration_branch=integration_branch,
        )

        # Apply resume info if present
        if resume_info:
            initial_state.resume_mode = True
            initial_state.pr_url = resume_info["pr_url"]
            initial_state.jules_session_name = resume_info["jules_session_name"]

        try:
            # We iterate through events to show progress if needed, or just invoke
            # invoke returns the final state
            final_state = await graph.ainvoke(initial_state, {"recursion_limit": 50})

            if final_state.get("error"):
                console.print(f"[red]Cycle {target_cycle} Failed:[/red] {final_state['error']}")
                # Check specific phase failures
                phase = final_state.get("current_phase")
                console.print(f"Failed at phase: [bold]{phase}[/bold]")
                sys.exit(1)
            else:
                if auto and cycle_id.lower() == "all":
                    console.print(
                        f"[bold green]Cycle {target_cycle} Completed Successfully![/bold green]"
                    )
                elif auto:
                    from ac_cdd_core.messages import SuccessMessages
                    SuccessMessages.show_panel(SuccessMessages.all_cycles_complete())
                else:
                    # Calculate next cycle ID
                    try:
                        next_id_int = int(target_cycle) + 1
                        next_cycle_id = f"{next_id_int:02d}"
                    except ValueError:
                        next_cycle_id = "XX"

                    from ac_cdd_core.messages import SuccessMessages
                    SuccessMessages.show_panel(
                        SuccessMessages.cycle_complete(target_cycle, next_cycle_id)
                    )

        except Exception as e:
            console.print(f"[red]Error during execution:[/red] {e}")
            logger.exception("Graph execution failed")
            sys.exit(1)
        finally:
            # Graceful cleanup
            await builder.cleanup()

    async def _run_all() -> None:
        cycles_to_run = ["01", "02", "03", "04", "05"] if cycle_id.lower() == "all" else [cycle_id]

        for c_id in cycles_to_run:
            await execute_single_cycle(c_id)

        if cycle_id.lower() == "all":
            from ac_cdd_core.messages import SuccessMessages
            SuccessMessages.show_panel(
                SuccessMessages.all_cycles_complete(),
                title="All Cycles Completed"
            )

    asyncio.run(_run_all())


@app.command()
def info() -> None:
    """Show configuration and status."""
    console.print(Panel(str(settings.model_dump()), title="Current Configuration"))


@app.command(name="finalize-session")
def finalize_session(
    session_id: Annotated[str, typer.Option("--session", help="Session ID")] = None,
) -> None:
    """
    Finalize a development session by creating a PR to main.
    """
    import asyncio
    import json
    from pathlib import Path

    async def _run() -> None:
        from .session_manager import SessionManager, SessionValidationError
        
        # Load session using consolidated helper
        try:
            session_id_to_use, integration_branch, _ = await SessionManager.load_or_reconcile_session(
                session_id=session_id,
                auto_reconcile=False  # Don't auto-reconcile for finalize
            )
        except SessionValidationError as e:
            console.print(f"[red]{e}[/red]")
            sys.exit(1)
        
        # Validate session
        is_valid, error_msg = SessionManager.validate_session(session_id_to_use, integration_branch)
        if not is_valid:
            console.print(f"[red]{error_msg}[/red]")
            sys.exit(1)
        
        # Optional: Validate all cycles are complete
        plan_status_file = Path(settings.paths.documents_dir) / "plan_status.json"
        if plan_status_file.exists():
            try:
                plan_data = json.loads(plan_status_file.read_text())
                planned_cycles = plan_data.get("cycles", [])
                if planned_cycles:
                    console.print(f"[dim]Planned cycles: {', '.join(planned_cycles)}[/dim]")
                    # Note: We don't enforce completion check yet, just inform
            except Exception as e:
                logger.warning(f"Could not read plan status: {e}")

        from .services.git_ops import GitManager
        git = GitManager()

        # Create final PR
        title = f"Session {session_id_to_use}: Complete Implementation"
        body = (
            f"This PR contains all work from development session {session_id_to_use}.\\n\\n"
            "Includes:\\n"
            "- System architecture and specifications\\n"
            "- All cycle implementations\\n"
            "- Full audit and test coverage\\n\\n"
            "Please review and merge to main."
        )

        try:
            pr_url = await git.create_final_pr(integration_branch, title, body)
            
            # Clear session file after successful PR creation
            SessionManager.clear_session()
            console.print("[dim]Session file cleared. Start a new session with 'gen-cycles'.[/dim]")

            from ac_cdd_core.messages import SuccessMessages
            SuccessMessages.show_panel(
                SuccessMessages.session_finalized(pr_url),
                title="Session Finalized"
            )
        except Exception as e:
            console.print(f"[red]Error creating final PR:[/red] {e}")
            logger.exception("Failed to create final PR")
            sys.exit(1)

    asyncio.run(_run())
