import shutil
import typer
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
import os
from dotenv import load_dotenv

# Import Orchestrator from the new package location
from ac_cdd.orchestrator import CycleOrchestrator

load_dotenv()

app = typer.Typer(help="AC-CDD Development Environment Manager")
console = Console()

@app.command()
def init():
    """プロジェクトの初期化と依存関係チェック"""
    console.print(Panel("Initializing AC-CDD Environment...", style="bold blue"))

    checks = [
        ("uv", "uv is required for package management."),
        ("gh", "GitHub CLI (gh) is required for PR management."),
        ("jules", "Jules CLI is required for AI coding."),
        ("gemini", "Gemini CLI is required for auditing."), # External gemini tool check
    ]

    all_pass = True
    for cmd, msg in checks:
        if not shutil.which(cmd):
            console.print(f"[red]✖ {cmd} not found.[/red] {msg}")
            all_pass = False
        else:
            console.print(f"[green]✔ {cmd} found.[/green]")

    if not Path(".env").exists():
        console.print("[yellow]⚠ .env file not found. Creating from .env.example...[/yellow]")
        if Path(".env.example").exists():
            shutil.copy(".env.example", ".env")
            console.print("[green]✔ .env created. Please fill in your secrets.[/green]")
        else:
            console.print("[red]✖ .env.example missing.[/red]")
            all_pass = False

    if all_pass:
        console.print(Panel("Initialization Complete! You are ready to start.", style="bold green"))
    else:
        console.print(Panel("Initialization Failed. Please fix errors above.", style="bold red"))
        raise typer.Exit(code=1)

@app.command(name="new-cycle")
def new_cycle(cycle_id: str):
    """新しい開発サイクルを作成します (例: 01, 02)"""
    base_path = Path(f"documents/CYCLE{cycle_id}")
    if base_path.exists():
        console.print(f"[red]Cycle {cycle_id} already exists![/red]")
        raise typer.Exit(code=1)

    base_path.mkdir(parents=True)
    templates_dir = Path("documents/templates")

    # Copy templates
    shutil.copy(templates_dir / "SPEC_TEMPLATE.md", base_path / "SPEC.md")
    shutil.copy(templates_dir / "UAT_TEMPLATE.md", base_path / "UAT.md")
    shutil.copy(templates_dir / "schema_template.py", base_path / "schema.py")

    console.print(f"[green]Created new cycle: CYCLE{cycle_id}[/green]")
    console.print(f"Please edit files in [bold]{base_path}[/bold]")

@app.command(name="start-cycle")
def start_cycle(cycle_id: str, dry_run: bool = False):
    """サイクルの自動実装・監査ループを開始します"""
    console.print(Panel(f"Starting Cycle {cycle_id} Automation", style="bold magenta"))
    if dry_run:
        console.print(
            "[yellow][DRY-RUN MODE] No actual API calls or commits will be made.[/yellow]"
        )

    orchestrator = CycleOrchestrator(cycle_id, dry_run=dry_run)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]Orchestrating...", total=None)

        try:
            orchestrator.execute_all(progress_task=task, progress_obj=progress)
            console.print(Panel(f"Cycle {cycle_id} Completed Successfully!", style="bold green"))
        except Exception as e:
            console.print(Panel(f"Cycle Failed: {str(e)}", style="bold red"))
            raise typer.Exit(code=1)

@app.command()
def doctor():
    """環境の健全性を診断します"""
    console.print("Diagnosing environment...")

    # 1. Check Gemini API Key
    if not os.getenv("GEMINI_API_KEY"):
        console.print("[red]✖ GEMINI_API_KEY is missing in .env[/red]")
    else:
        console.print("[green]✔ GEMINI_API_KEY found[/green]")

    # 2. Check GitHub Auth
    if shutil.which("gh"):
        import subprocess

        res = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
        if res.returncode == 0:
            console.print("[green]✔ GitHub CLI authenticated[/green]")
        else:
            console.print("[red]✖ GitHub CLI not logged in[/red]")
    else:
        console.print("[red]✖ gh command not found[/red]")

    # 3. Check External Gemini Tool
    if shutil.which("gemini"):
        console.print("[green]✔ External 'gemini' CLI tool found[/green]")
    else:
        console.print(
            "[yellow]⚠ External 'gemini' CLI tool not found (Strict Audit will fail "
            "if not mocked)[/yellow]"
        )

if __name__ == "__main__":
    app()
