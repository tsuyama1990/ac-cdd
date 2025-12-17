import asyncio
import os
import shutil
import sqlite3
from pathlib import Path

import logfire
import typer
from dotenv import load_dotenv
from langgraph.checkpoint.sqlite import SqliteSaver
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from ac_cdd.config import settings
from ac_cdd.graph import GraphBuilder
from ac_cdd.service_container import ServiceContainer
from ac_cdd.services.project import ProjectManager

load_dotenv()

# Initialize Logfire
if os.getenv("LOGFIRE_TOKEN"):
    logfire.configure()

app = typer.Typer(help="AC-CDD: AI-Native Cycle-Based Development Orchestrator")
console = Console()

# Instantiate global services (CLI is the entry point)
services = ServiceContainer.default()
project_manager = ProjectManager()


@app.command()
def init() -> None:
    """プロジェクトの初期化と依存関係チェック"""
    console.print(Panel("AC-CDD環境の初期化中...", style="bold blue"))

    checks = [
        (settings.tools.uv_cmd, "パッケージ管理には uv が必要です。"),
        (settings.tools.gh_cmd, "PR管理には GitHub CLI (gh) が必要です。"),
        (settings.tools.audit_cmd, "監査には Bandit が必要です。"),
    ]

    all_pass = True
    for cmd, msg in checks:
        if not shutil.which(cmd):
            console.print(f"[red]✖ {cmd} が見つかりません。[/red] {msg}")
            all_pass = False
        else:
            console.print(f"[green]✔ {cmd} が見つかりました。[/green]")

    if not Path(".env").exists():
        console.print(
            "[yellow]⚠ .env ファイルが見つかりません。セットアップを開始します...[/yellow]"
        )

        env_content = ""
        env_template = Path(".env.example")
        if not env_template.exists():
            env_template = Path(settings.paths.templates) / ".env.example"

        if env_template.exists():
            with open(env_template, encoding="utf-8") as f:
                for line in f:
                    if line.strip() and not line.startswith("#"):
                        key = line.split("=")[0].strip()
                        default_val = line.split("=")[1].strip() if "=" in line else ""
                        value = typer.prompt(f"Enter value for {key}", default=default_val)
                        env_content += f"{key}={value}\n"
                    else:
                        env_content += line

            with open(".env", "w", encoding="utf-8") as f:
                f.write(env_content)
            console.print("[green]✔ .env を作成しました。[/green]")
        else:
            console.print("[red]✖ .env.example が見つかりません。[/red]")
            all_pass = False
    else:
        console.print("[green]✔ .env ファイルを確認しました。[/green]")

    if all_pass:
        console.print(Panel("初期化完了！開発を開始できます。", style="bold green"))
    else:
        console.print(
            Panel("初期化に失敗しました。上記のエラーを確認してください。", style="bold red")
        )
        raise typer.Exit(code=1)


# --- Cycle Workflow (Graph Based) ---


@app.command(name="new-cycle")
def new_cycle(name: str) -> None:
    """新しい開発サイクルを作成します (例: 01, 02)"""
    success, msg = project_manager.create_new_cycle(name)
    if success:
        console.print(f"[green]{msg}[/green]")
    else:
        console.print(f"[red]{msg}[/red]")
        raise typer.Exit(code=1)


@app.command(name="start-cycle")
def start_cycle(
    names: list[str],
    dry_run: bool = False,
    auto_next: bool = False,
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompts"),
    interactive: bool = typer.Option(True, help="Enable interactive approval of file changes"),
    goal: str = typer.Option(None, "--goal", help="Specific goal or instruction for this cycle"),
) -> None:
    """サイクルの自動実装・監査ループを開始します (LangGraph使用)"""
    asyncio.run(_start_cycle_async(names, dry_run, auto_next, yes, interactive, goal))


async def _get_checkpointer(cycle_id: str) -> SqliteSaver:
    """Get a configured SqliteSaver for the given cycle."""
    db_path = Path(".jules/checkpoints.sqlite")
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path, check_same_thread=False)
    return SqliteSaver(conn)


async def _run_graph(graph, initial_state: dict, title: str, thread_id: str) -> None:
    """Generic graph runner with progress UI and human-in-the-loop support."""
    checkpointer = await _get_checkpointer(thread_id)
    
    # Compile with interrupts for human review
    app = graph.compile(
        checkpointer=checkpointer,
        interrupt_before=["apply_test", "apply_impl", "apply_uat"]
    )

    config = {"configurable": {"thread_id": thread_id}}
    
    # State for the runner loop
    resume_input = initial_state
    
    console.print(Panel(f"Running: {title}", style="bold magenta"))

    while True:
        try:
            # We run the graph until it finishes or hits an interrupt
            # We use a progress bar for the active execution phase
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task_id = progress.add_task("[cyan]Executing...[/cyan]", total=None)
                
                # If we are resuming, passing None resumes from the checkpoint state.
                # However, if it's the *first* run, we pass initial_state.
                # After the first run, resume_input should be None (unless we are providing
                # new input, which update_state handles differently).
                # Actually, for resuming after interrupt, passing Command(resume=value)
                # or just None (if logic is in state) works.
                # Here we updated state via update_state, so we pass None to resume.
                
                input_to_stream = resume_input if resume_input == initial_state else None

                async for event in app.astream(input_to_stream, config=config):
                    for node_name, state_update in event.items():
                        phase = state_update.get("current_phase", node_name)
                        progress.update(
                            task_id, description=f"[cyan]Node: {node_name} ({phase})..."
                        )
                        if state_update.get("error"):
                            err_msg = state_update["error"][:200]
                            console.print(f"[red]Error in {node_name}:[/red] {err_msg}...")

            # Check execution status
            snapshot = app.get_state(config)
            
            if not snapshot.next:
                # Execution finished
                console.print(Panel("完了しました！", style="bold green"))
                break
                
            # If we are here, we are likely at an interruption point
            next_step = snapshot.next[0]
            
            if next_step in ["apply_test", "apply_impl", "apply_uat"]:
                # --- Human-in-the-loop Interaction ---
                state_values = snapshot.values
                code_changes = state_values.get("code_changes", [])
                interactive = state_values.get("interactive", False)
                
                if not interactive:
                    # Auto-approve in non-interactive mode
                    console.print(
                        f"[yellow]Auto-approving {next_step} (Non-interactive mode)[/yellow]"
                    )
                    app.update_state(config, {"approved": True, "error": None})
                else:
                    # Show diff and ask for approval
                    console.print(Panel(f"Review Required for {next_step}", style="bold yellow"))
                    
                    # Generate preview (dry-run)
                    preview = services.file_patcher.apply_changes(code_changes, dry_run=True)
                    
                    # Use Presenter to confirm
                    approved = services.presenter.review_and_confirm(preview)
                    
                    if approved:
                        console.print("[green]Approved. Applying changes...[/green]")
                        app.update_state(config, {"approved": True, "error": None})
                    else:
                        feedback = typing_prompt("Enter feedback/rejection reason:")
                        console.print("[red]Rejected. Looping back to agent...[/red]")
                        app.update_state(
                            config, {"approved": False, "error": f"User Rejected: {feedback}"}
                        )
                
                # Prepared to resume
                resume_input = None 
                # continue the loop to resume execution
                
            else:
                # Stopped for some other reason? Should not happen with current config.
                console.print(f"[yellow]Paused at {next_step}. Resuming...[/yellow]")
                resume_input = None

        except Exception as e:
            console.print(Panel(f"失敗: {str(e)}", style="bold red"))
            # Depending on severity, we might want to break or continue
            break

def typing_prompt(text: str) -> str:
    """Helper for typed input"""
    return typer.prompt(text)


async def _start_cycle_async(
    names: list[str],
    dry_run: bool,
    auto_next: bool,
    auto_approve: bool,
    interactive: bool,
    goal: str | None,
) -> None:
    if not names:
        console.print("[red]少なくとも1つのサイクルIDを指定してください (例: 01)[/red]")
        raise typer.Exit(code=1)

    if not dry_run:
        try:
            from ac_cdd.rag.indexer import CodeIndexer
            console.print("[cyan]Indexing codebase for RAG...[/cyan]")
            CodeIndexer().index()
            console.print("[green]Index updated.[/green]")
        except Exception as e:
            console.print(f"[yellow]Warning: Indexing failed: {e}[/yellow]")

    graph_builder = GraphBuilder(services)
    main_graph = graph_builder.build_main_graph()

    for cycle_id in names:
        initial_state = {
            "cycle_id": cycle_id,
            "loop_count": 0,
            "current_phase": "start",
            "error": None,
            "sandbox_id": None,
            "dry_run": dry_run,
            "interactive": interactive,
            "goal": goal,
        }
        await _run_graph(main_graph, initial_state, f"Cycle {cycle_id}", f"cycle-{cycle_id}")


# --- Ad-hoc Workflow (Graph Based) ---


@app.command()
def audit(repo: str = typer.Option(None, help="Target repository (ignored, uses current)")) -> None:
    """
    [Strict Review] Gitの差分をAuditorに激辛レビューさせ、Coderに修正指示を出します。
    """
    asyncio.run(_audit_async())


async def _audit_async() -> None:
    initial_state = {
        "cycle_id": "audit",
        "loop_count": 0,
        "current_phase": "audit_start",
        "error": None,
        "sandbox_id": None,
        "dry_run": False,
        "interactive": True,
        "goal": None,
    }
    graph_builder = GraphBuilder(services)
    audit_graph = graph_builder.build_audit_graph()
    await _run_graph(audit_graph, initial_state, "Ad-hoc Audit", "audit-session")


@app.command()
def fix() -> None:
    """
    [Auto Fix] テストを実行し、失敗した場合にCoderに修正させます。
    """
    asyncio.run(_fix_async())


async def _fix_async() -> None:
    initial_state = {
        "cycle_id": "fix",
        "loop_count": 0,
        "current_phase": "fix_start",
        "error": None,
        "sandbox_id": None,
        "dry_run": False,
        "interactive": True,
        "goal": None,
    }
    graph_builder = GraphBuilder(services)
    fix_graph = graph_builder.build_fix_graph()
    await _run_graph(fix_graph, initial_state, "Ad-hoc Fix", "fix-session")


@app.command()
def refine_spec() -> None:
    """
    [Architect] ALL_SPEC.md を読み込み、構造化された仕様書 (ALL_SPEC_STRUCTURED.md) を生成します。
    """
    asyncio.run(_refine_spec_async())


async def _refine_spec_async() -> None:
    from ac_cdd.agents import architect_agent
    
    spec_path = Path(settings.paths.documents_dir) / "ALL_SPEC.md"
    if not spec_path.exists():
        console.print(
            "[red]❌ ALL_SPEC.md not found. "
            "Run 'copy dev_documents/templates/ALL_SPEC.md dev_documents/' first.[/red]"
        )
        raise typer.Exit(1)
        
    console.print(Panel("Refining Specification into Structured Format...", style="bold blue"))
    
    raw_content = spec_path.read_text(encoding="utf-8")
    
    # Run Agent
    try:
        result = await architect_agent.run(f"Refine this specification:\n\n{raw_content}")
        structured_spec = result.output
        
        # Save output
        out_path = Path(settings.paths.documents_dir) / "ALL_SPEC_STRUCTURED.md"
        
        # Convert to rigorous Markdown using the Pydantic model
        md_content = f"""# Structured Project Specification

*Generated by AC-CDD Architect Agent*

## Overview
{structured_spec.overview}

## Goals
{chr(10).join(f"- {g}" for g in structured_spec.goals)}

## Architecture
{structured_spec.architecture_overview}

## Feature Backlog
"""
        for f in structured_spec.features:
            md_content += (
                f"### {f.name} ({f.priority})\n"
                f"{f.description}\n\n**Acceptance Criteria:**\n"
            )
            md_content += "\n".join(f"- {ac}" for ac in f.acceptance_criteria) + "\n\n"

        md_content += "## Technical Constraints\n"
        md_content += "\n".join(
            f"- **{c.category}**: {c.description}" for c in structured_spec.constraints
        )
        
        # Also save raw JSON for downstream tools
        (Path(settings.paths.documents_dir) / "ALL_SPEC_STRUCTURED.json").write_text(
            structured_spec.model_dump_json(indent=2), encoding="utf-8"
        )
        
        out_path.write_text(md_content, encoding="utf-8")
        
        console.print(f"[green]✔ Generated {out_path}[/green]")
        console.print(f"[green]✔ Generated {out_path.with_suffix('.json')}[/green]")
        console.print("Please review these files before starting a cycle.")
        
    except Exception as e:
        console.print(f"[red]Failed to refine spec: {e}[/red]")


@app.command()
def doctor() -> None:
    """環境チェック"""
    tools = {
        "git": "Install Git from https://git-scm.com/",
        "uv": "Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh",
        "gh": "Install GitHub CLI: https://cli.github.com/",
        "bandit": "Install bandit (via pip/uv)",
    }

    all_ok = True
    typer.echo("Checking development environment...\n")

    for tool, instruction in tools.items():
        path = shutil.which(tool)
        if path:
            typer.secho(f"✅ {tool:<10}: Found at {path}", fg=typer.colors.GREEN)
        else:
            typer.secho(f"❌ {tool:<10}: MISSING", fg=typer.colors.RED)
            typer.echo(f"   Action: {instruction}")
            all_ok = False

    if all_ok:
        typer.secho("\n✨ System is ready for AI-Native Development.", fg=typer.colors.GREEN)
    else:
        typer.secho("\n⚠️  Please install missing tools to proceed.", fg=typer.colors.YELLOW)
        raise typer.Exit(1)


def friendly_error_handler() -> None:
    try:
        app()
    except Exception as e:
        console.print(Panel(f"An unexpected error occurred: {str(e)}", style="bold red"))
        # Settings might not be loaded if env is broken, so check carefully
        is_debug = False
        try:
            is_debug = settings.debug or os.getenv("DEBUG")
        except Exception:
            is_debug = os.getenv("DEBUG")

        if is_debug:
            console.print_exception()
        else:
            console.print("Run with DEBUG=1 environment variable to see full traceback.")
        raise typer.Exit(code=1) from e


if __name__ == "__main__":
    friendly_error_handler()
