import sys
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel

from .config import settings

# from .graph import build_architect_graph, build_coder_graph
from .service_container import ServiceContainer
from .state import CycleState
from .utils import check_api_key, logger

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
    if not os.environ.get("GEMINI_API_KEY") and not os.environ.get("GOOGLE_API_KEY") and not os.environ.get("OPENROUTER_API_KEY"):
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
            console.print("\n[yellow]Please install these tools and ensure they are in your PATH.[/yellow]\n")

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
) -> None:
    """
    Run the Architect Phase.
    Generates SYSTEM_ARCHITECTURE.md and ALL_SPEC.md.
    """
    import asyncio

    async def _run() -> None:
        console.rule("[bold blue]Architect Phase: Generating Cycles[/bold blue]")
        
        # Check API availability first
        try:
            check_api_key()
        except ValueError as e:
            console.print(f"[red]Configuration Error:[/red] {e}")
            sys.exit(1)

        services = ServiceContainer.default()
        from .graph import GraphBuilder

        # Instantiate builder to manage resources
        builder = GraphBuilder(services)
        graph = builder.build_architect_graph()

        # Initialize state
        initial_state = CycleState(cycle_id=settings.DUMMY_CYCLE_ID)

        # Run the graph
        try:
            # We use aconfig={"recursion_limit": 50} for safety if needed
            final_state = await graph.ainvoke(initial_state)

            if final_state.get("error"):
                console.print(f"[red]Architect Phase Failed:[/red] {final_state['error']}")
                sys.exit(1)
            else:
                msg = (
                    "✅ Architect Phase Request Sent!\n\n"
                    "Jules has created a Pull Request with the architectural plans.\n\n"
                    "Next Steps:\n"
                    "1. Review the Pull Request on GitHub.\n"
                    "2. Merge the PR if the architecture looks correct.\n"
                    "3. Pull the changes locally:\n"
                    "   git pull origin main  (or your working branch)\n"
                    "4. Verify the generated documents exist:\n"
                    f"   ls {settings.paths.documents_dir}/SYSTEM_ARCHITECTURE.md\n"
                    "5. Start implementation for the first cycle:\n"
                    "   uv run manage.py run-cycle --id 01"
                )
                console.print(
                    Panel(msg, title="Next Action Guide", style="bold green", expand=False)
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
    cycle_id: Annotated[str, typer.Option("--id", help="Cycle ID (e.g., '01')")] = "01",
    auto: Annotated[bool, typer.Option(help="Run without manual confirmation")] = False,
) -> None:
    """
    Run a Development Cycle.
    Implements features, runs tests, performs UAT, and Audits.
    """
    import asyncio

    async def _run() -> None:
        console.rule(f"[bold green]Running Cycle {cycle_id}[/bold green]")

        # Check API availability
        try:
            check_api_key()
        except ValueError as e:
            console.print(f"[red]Configuration Error:[/red] {e}")
            sys.exit(1)

        services = ServiceContainer.default()
        from .graph import GraphBuilder

        # Instantiate builder to manage resources
        builder = GraphBuilder(services)
        graph = builder.build_coder_graph()

        # Initialize state
        initial_state = CycleState(cycle_id=cycle_id)

        try:
            # We iterate through events to show progress if needed, or just invoke
            # invoke returns the final state
            final_state = await graph.ainvoke(initial_state, {"recursion_limit": 50})

            if final_state.get("error"):
                console.print(f"[red]Cycle {cycle_id} Failed:[/red] {final_state['error']}")
                # Check specific phase failures
                phase = final_state.get("current_phase")
                console.print(f"Failed at phase: [bold]{phase}[/bold]")
                sys.exit(1)
            else:
                if auto:
                    msg = (
                        "✅ All Cycles Completed!\n\n"
                        "Next Steps:\n"
                        "1. Perform a final system-wide audit.\n"
                        "2. Deploy your application!"
                    )
                else:
                    # Calculate next cycle ID
                    try:
                        next_id_int = int(cycle_id) + 1
                        next_cycle_id = f"{next_id_int:02d}"
                    except ValueError:
                        next_cycle_id = "XX"

                    msg = (
                        f"✅ Cycle {cycle_id} Implementation Request Sent!\n\n"
                        "Jules has created a Pull Request with the implementation.\n\n"
                        "Next Steps:\n"
                        "1. Review the Pull Request on GitHub.\n"
                        "2. Merge the PR if the implementation and tests pass.\n"
                        "3. Pull the changes locally:\n"
                        "   git checkout main && git pull\n"
                        "4. Proceed to the next cycle:\n"
                        f"   uv run manage.py run-cycle --id {next_cycle_id}"
                    )

                console.print(
                    Panel(msg, title="Next Action Guide", style="bold green", expand=False)
                )

        except Exception as e:
            console.print(f"[red]Error during execution:[/red] {e}")
            logger.exception("Graph execution failed")
            sys.exit(1)
        finally:
            # Graceful cleanup
            await builder.cleanup()

    asyncio.run(_run())

@app.command()
def info() -> None:
    """Show configuration and status."""
    console.print(Panel(str(settings.model_dump()), title="Current Configuration"))
