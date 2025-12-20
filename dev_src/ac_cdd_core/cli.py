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


@app.command()
def init() -> None:
    """
    Initialize the AC-CDD environment.
    Creates necessary directories and files.
    """
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
        from .graph import build_architect_graph
        graph = build_architect_graph(services)

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
                    "✅ Architecture & Planning Complete!\n\n"
                    "Next Steps:\n"
                    "1. Review the generated architecture:\n"
                    f"   {settings.paths.documents_dir}/SYSTEM_ARCHITECTURE.md\n\n"
                    "2. Review the cycle specifications:\n"
                    f"   {settings.paths.documents_dir}/CYCLE01/SPEC.md\n"
                    f"   {settings.paths.documents_dir}/CYCLE01/UAT.md\n"
                    "   ...\n\n"
                    "3. Start implementation for the first cycle:\n"
                    "   uv run manage.py run-cycle 01\n\n"
                    "(Or run all cycles automatically with: uv run manage.py run-cycle --auto)"
                )
                console.print(
                    Panel(msg, title="Next Action Guide", style="bold green", expand=False)
                )

        except Exception as e:
            console.print(f"[red]Error during execution:[/red] {e}")
            logger.exception("Graph execution failed")
            sys.exit(1)

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
        from .graph import build_coder_graph
        graph = build_coder_graph(services)

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
                        f"✅ Cycle {cycle_id} Implementation Complete!\n\n"
                        "Next Steps:\n"
                        f"1. Review the changes in branch: feature/cycle-{cycle_id}\n"
                        f"2. Check the session report: "
                        f"dev_documents/CYCLE{cycle_id}/session_report.json\n"
                        "3. If satisfied, merge the PR (or use 'gh pr merge').\n"
                        "4. Proceed to the next cycle:\n"
                        f"   uv run manage.py run-cycle {next_cycle_id}"
                    )

                console.print(
                    Panel(msg, title="Next Action Guide", style="bold green", expand=False)
                )

        except Exception as e:
            console.print(f"[red]Error during execution:[/red] {e}")
            logger.exception("Graph execution failed")
            sys.exit(1)

    asyncio.run(_run())

@app.command()
def info() -> None:
    """Show configuration and status."""
    console.print(Panel(str(settings.model_dump()), title="Current Configuration"))
