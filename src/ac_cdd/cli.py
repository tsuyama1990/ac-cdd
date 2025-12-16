import asyncio
import os
import shutil
from pathlib import Path

import logfire
import typer
from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from ac_cdd.config import settings
from ac_cdd.graph import build_audit_graph, build_fix_graph, build_graph

load_dotenv()

# Initialize Logfire
if os.getenv("LOGFIRE_TOKEN"):
    logfire.configure()

app = typer.Typer(help="AC-CDD: AI-Native Cycle-Based Development Orchestrator")
console = Console()


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
    cycle_id = name
    base_path = Path(settings.paths.documents_dir) / f"CYCLE{cycle_id}"
    if base_path.exists():
        console.print(f"[red]サイクル {cycle_id} は既に存在します！[/red]")
        raise typer.Exit(code=1)

    base_path.mkdir(parents=True)
    templates_dir = Path(settings.paths.templates) / "cycle"

    for item in ["SPEC.md", "UAT.md", "schema.py"]:
        src = templates_dir / item
        if src.exists():
            shutil.copy(src, base_path / item)
        else:
            console.print(f"[yellow]⚠ Template {item} missing.[/yellow]")

    console.print(f"[green]新しいサイクルを作成しました: CYCLE{cycle_id}[/green]")
    console.print(f"[bold]{base_path}[/bold] 内のファイルを編集してください。")


@app.command(name="start-cycle")
def start_cycle(
    names: list[str],
    dry_run: bool = False,
    auto_next: bool = False,
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompts"),
    interactive: bool = typer.Option(True, help="Enable interactive approval of file changes"),
) -> None:
    """サイクルの自動実装・監査ループを開始します (LangGraph使用)"""
    asyncio.run(_start_cycle_async(names, dry_run, auto_next, yes, interactive))


async def _run_graph(graph_builder, initial_state: dict, title: str) -> None:
    """Generic graph runner with progress UI."""
    memory = MemorySaver()
    graph = graph_builder.compile(checkpointer=memory)

    config = {"configurable": {"thread_id": f"session-{initial_state.get('cycle_id', 'adhoc')}"}}

    console.print(Panel(f"Running: {title}", style="bold magenta"))

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
    ) as progress:
        task_id = progress.add_task("[cyan]Executing...[/cyan]", total=None)

        try:
            async for event in graph.astream(initial_state, config=config):
                for node_name, state_update in event.items():
                    phase = state_update.get("current_phase", node_name)
                    progress.update(
                        task_id, description=f"[cyan]Node: {node_name} ({phase})..."
                    )
                    if state_update.get("error"):
                        err_msg = state_update["error"][:200]
                        console.print(f"[red]Error in {node_name}:[/red] {err_msg}...")

            console.print(Panel("完了しました！", style="bold green"))
        except Exception as e:
            console.print(Panel(f"失敗: {str(e)}", style="bold red"))
            # raise typer.Exit(code=1) from e


async def _start_cycle_async(
    names: list[str], dry_run: bool, auto_next: bool, auto_approve: bool, interactive: bool
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

    for cycle_id in names:
        initial_state = {
            "cycle_id": cycle_id,
            "loop_count": 0,
            "current_phase": "start",
            "error": None,
            "sandbox_id": None,
            "dry_run": dry_run,
            "interactive": interactive,
        }
        await _run_graph(build_graph(), initial_state, f"Cycle {cycle_id}")


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
    }
    await _run_graph(build_audit_graph(), initial_state, "Ad-hoc Audit")


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
    }
    await _run_graph(build_fix_graph(), initial_state, "Ad-hoc Fix")


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
        if settings.debug or os.getenv("DEBUG"):
            console.print_exception()
        else:
            console.print("Run with DEBUG=1 environment variable to see full traceback.")
        raise typer.Exit(code=1) from e


if __name__ == "__main__":
    friendly_error_handler()
