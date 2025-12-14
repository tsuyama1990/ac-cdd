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
from ac_cdd.config import settings

load_dotenv()

app = typer.Typer(help="AC-CDD Development Environment Manager")
console = Console()

@app.command()
def init():
    """プロジェクトの初期化と依存関係チェック"""
    console.print(Panel("AC-CDD環境の初期化中...", style="bold blue"))

    # Use tools from config
    checks = [
        (settings.tools.uv_cmd, "パッケージ管理には uv が必要です。"),
        (settings.tools.gh_cmd, "PR管理には GitHub CLI (gh) が必要です。"),
        (settings.tools.jules_cmd, "AIコーディングには Jules CLI が必要です。"),
        (settings.tools.gemini_cmd, "監査には Gemini CLI が必要です。"),
    ]

    all_pass = True
    for cmd, msg in checks:
        if not shutil.which(cmd):
            console.print(f"[red]✖ {cmd} が見つかりません。[/red] {msg}")
            all_pass = False
        else:
            console.print(f"[green]✔ {cmd} が見つかりました。[/green]")

    if not Path(".env").exists():
        console.print("[yellow]⚠ .env ファイルが見つかりません。.env.example から作成します...[/yellow]")
        if Path(".env.example").exists():
            shutil.copy(".env.example", ".env")
            console.print("[green]✔ .env を作成しました。APIキーなどを入力してください。[/green]")
        else:
            console.print("[red]✖ .env.example が見つかりません。[/red]")
            all_pass = False
    else:
        console.print("[green]✔ .env ファイルを確認しました。[/green]")

    if all_pass:
        console.print(Panel("初期化完了！開発を開始できます。", style="bold green"))
    else:
        console.print(Panel("初期化に失敗しました。上記のエラーを確認してください。", style="bold red"))
        raise typer.Exit(code=1)

@app.command(name="new-cycle")
def new_cycle(cycle_id: str):
    """新しい開発サイクルを作成します (例: 01, 02)"""
    base_path = Path(settings.paths.documents_dir) / f"CYCLE{cycle_id}"
    if base_path.exists():
        console.print(f"[red]サイクル {cycle_id} は既に存在します！[/red]")
        raise typer.Exit(code=1)

    base_path.mkdir(parents=True)
    templates_dir = Path(settings.paths.documents_dir) / "templates"

    # Copy templates
    shutil.copy(templates_dir / "SPEC_TEMPLATE.md", base_path / "SPEC.md")
    shutil.copy(templates_dir / "UAT_TEMPLATE.md", base_path / "UAT.md")
    shutil.copy(templates_dir / "schema_template.py", base_path / "schema.py")

    console.print(f"[green]新しいサイクルを作成しました: CYCLE{cycle_id}[/green]")
    console.print(f"[bold]{base_path}[/bold] 内のファイルを編集してください。")

@app.command(name="start-cycle")
def start_cycle(cycle_id: str, dry_run: bool = False):
    """サイクルの自動実装・監査ループを開始します"""
    console.print(Panel(f"サイクル {cycle_id} の自動化を開始します", style="bold magenta"))
    if dry_run:
        console.print(
            "[yellow][DRY-RUN MODE] 実際のAPI呼び出しやコミットは行われません。[/yellow]"
        )

    orchestrator = CycleOrchestrator(cycle_id, dry_run=dry_run)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]実行中...", total=None)

        try:
            orchestrator.execute_all(progress_task=task, progress_obj=progress)
            console.print(Panel(f"サイクル {cycle_id} が正常に完了しました！", style="bold green"))
        except Exception as e:
            console.print(Panel(f"サイクル失敗: {str(e)}", style="bold red"))
            raise typer.Exit(code=1)

@app.command()
def doctor():
    """環境の健全性を診断します"""
    console.print("環境診断中...")

    # 1. Tools Check
    tools_to_check = [
        settings.tools.jules_cmd,
        settings.tools.gh_cmd,
        settings.tools.uv_cmd,
        settings.tools.audit_cmd
    ]

    missing_tools = []
    for tool in tools_to_check:
        if shutil.which(tool):
            console.print(f"[green]✔ {tool} が見つかりました[/green]")
        else:
            console.print(f"[red]✖ {tool} が見つかりません[/red]")
            missing_tools.append(tool)

    # 2. Env Check
    env_ok = True
    if Path(".env").exists():
        console.print("[green]✔ .env が見つかりました[/green]")
        if not os.getenv("GEMINI_API_KEY"):
             console.print("[yellow]⚠ .env に GEMINI_API_KEY が設定されていません[/yellow]")
    else:
        console.print("[red]✖ .env が見つかりません[/red]")
        env_ok = False

    if not missing_tools and env_ok:
        console.print(Panel("システム準備完了 (System Ready)", style="bold green"))
    else:
        missing_str = ", ".join(missing_tools)
        msg = "システム準備未完了 (System Not Ready)"
        if missing_tools:
            msg += f"\n不足ツール: {missing_str}"
        if not env_ok:
            msg += "\n.env 設定不足"
        console.print(Panel(msg, style="bold red"))

if __name__ == "__main__":
    app()
