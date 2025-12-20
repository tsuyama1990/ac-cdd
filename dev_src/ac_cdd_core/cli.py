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
        console.print("[green]Project initialized successfully![/green]")
        console.print(
            "Please follow these steps to start:\n"
            "1. Edit [bold].env[/bold] (Add API keys and select Models)\n"
            f"2. Edit [bold]{settings.paths.documents_dir}/ALL_SPEC.md[/bold] "
            "(Define your requirements)\n"
            "3. Run [bold]uv run manage.py gen-cycles[/bold]"
        )
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

        services = ServiceContainer()
        from .graph import build_architect_graph
        graph = build_architect_graph(services)

        # Initialize state
        initial_state = CycleState(cycle_id=settings.DUMMY_CYCLE_ID)

        # Run the graph
        try:
            # We use aconfig={"recursion_limit": 50} for safety if needed
            final_state = await graph.invoke(initial_state)

            if final_state.get("error"):
                console.print(f"[red]Architect Phase Failed:[/red] {final_state['error']}")
                sys.exit(1)
            else:
                console.print("[green]Architect Phase Complete![/green]")
                console.print(
                    "Review [bold]ALL_SPEC.md[/bold] and [bold]SYSTEM_ARCHITECTURE.md[/bold]."
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

        services = ServiceContainer()
        from .graph import build_coder_graph
        graph = build_coder_graph(services)

        # Initialize state
        initial_state = CycleState(cycle_id=cycle_id)

        try:
            # We iterate through events to show progress if needed, or just invoke
            # invoke returns the final state
            final_state = await graph.invoke(initial_state, {"recursion_limit": 50})

            if final_state.get("error"):
                console.print(f"[red]Cycle {cycle_id} Failed:[/red] {final_state['error']}")
                # Check specific phase failures
                phase = final_state.get("current_phase")
                console.print(f"Failed at phase: [bold]{phase}[/bold]")
                sys.exit(1)
            else:
                console.print(f"[green]Cycle {cycle_id} Completed Successfully![/green]")

        except Exception as e:
            console.print(f"[red]Error during execution:[/red] {e}")
            logger.exception("Graph execution failed")
            sys.exit(1)

    asyncio.run(_run())

@app.command()
def info() -> None:
    """Show configuration and status."""
    console.print(Panel(str(settings.model_dump()), title="Current Configuration"))
