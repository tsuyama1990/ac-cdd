import asyncio
import os
import shutil
from pathlib import Path

import logfire
import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from ac_cdd.agents import auditor_agent, coder_agent
from ac_cdd.config import settings
from ac_cdd.domain_models import AuditResult, FileOperation
from ac_cdd.orchestrator import CycleOrchestrator
from ac_cdd.process_runner import ProcessRunner

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


# --- Cycle Workflow ---


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
    """サイクルの自動実装・監査ループを開始します (複数ID指定可)"""
    asyncio.run(_start_cycle_async(names, dry_run, auto_next, yes, interactive))


async def _start_cycle_async(
    names: list[str], dry_run: bool, auto_next: bool, auto_approve: bool, interactive: bool
) -> None:
    if not names:
        console.print("[red]少なくとも1つのサイクルIDを指定してください (例: 01)[/red]")
        raise typer.Exit(code=1)

    for cycle_id in names:
        console.print(Panel(f"サイクル {cycle_id} の自動化を開始します", style="bold magenta"))
        if dry_run:
            console.print(
                "[yellow][DRY-RUN MODE] 実際のAPI呼び出しやコミットは行われません。[/yellow]"
            )

        orchestrator = CycleOrchestrator(
            cycle_id,
            dry_run=dry_run,
            auto_next=auto_next,
            auto_approve=auto_approve,
            interactive=interactive,
        )

        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
        ) as progress:
            task = progress.add_task(f"[cyan]Cycle {cycle_id} 実行中...", total=None)

            try:
                await orchestrator.execute_all(progress_task=task, progress_obj=progress)
                console.print(
                    Panel(f"サイクル {cycle_id} が正常に完了しました！", style="bold green")
                )
            except Exception as e:
                console.print(Panel(f"サイクル {cycle_id} 失敗: {str(e)}", style="bold red"))
                raise typer.Exit(code=1) from e


# --- Ad-hoc Workflow ---


@app.command()
def audit(repo: str = typer.Option(None, help="Target repository")) -> None:
    """
    [Strict Review] Gitの差分をAuditorに激辛レビューさせ、Coderに修正指示を出します。
    """
    asyncio.run(_audit_async(repo))


async def _audit_async(repo: str) -> None:
    typer.echo("🔍 Fetching git diff...")
    runner = ProcessRunner()

    try:
        stdout, stderr, returncode = await runner.run_command(["git", "diff", "HEAD"], check=False)

        if returncode != 0:
            # If stderr is present, it might be an error.
            if stderr:
                typer.secho(f"Git Error: {stderr}", fg=typer.colors.RED)
                raise typer.Exit(1)

        diff_output = stdout

        if not diff_output:
            typer.secho("No changes detected to audit.", fg=typer.colors.YELLOW)
            return

        typer.echo("🧠 Auditor is thinking (Strict Review Mode)...")
        prompt = (
            "Review the following git diff focusing on Security, "
            "Performance, and Readability.\n"
            "Output ONLY specific, actionable instructions for an AI coder "
            "as a bulleted list.\n\n"
            f"Git Diff:\n{diff_output}"
        )

        # We enforce structured output even for ad-hoc audit
        result_typed = await auditor_agent.run(prompt, result_type=AuditResult)

        data: AuditResult = result_typed.output
        review_instruction = data.critical_issues + data.suggestions

        review_text = "\n".join(review_instruction)

        typer.echo("🤖 Coder is taking over...")

        coder_prompt = f"Here are the audit findings. Please fix the code.\n\n{review_text}"
        coder_result = await coder_agent.run(coder_prompt)

        typer.secho("✅ Audit complete. Fix task assigned to Coder!", fg=typer.colors.GREEN)

        # Changes are now list[FileOperation]
        changes: list[FileOperation] = coder_result.output

        # Instantiate orchestrator for file application logic (reuse reuse!)
        orchestrator = CycleOrchestrator("00", dry_run=False)  # Dummy cycle ID
        orchestrator._apply_agent_changes(changes)

    except Exception as e:
        typer.secho(str(e), fg=typer.colors.RED)
        raise typer.Exit(1) from e


@app.command()
def fix() -> None:
    """
    [Auto Fix] テストを実行し、失敗した場合にCoderに修正させます。
    Smart Fix: pytest --last-failed -> pytest full -> Coder
    """
    asyncio.run(_fix_async())


async def _fix_async() -> None:
    uv_path = shutil.which("uv")
    if not uv_path:
        typer.secho("Error: 'uv' not found.", fg=typer.colors.RED)
        raise typer.Exit(1)

    runner = ProcessRunner()

    # 1. Try running only failed tests first
    typer.echo("🧪 Running failed tests (pytest --last-failed)...")

    stdout, stderr, returncode = await runner.run_command(
        [uv_path, "run", "pytest", "--last-failed"], check=False
    )
    logs = stdout + "\n" + stderr

    if returncode == 0:
        # 2. If no failures (or no history), run full suite
        typer.echo("✨ Last failed tests passed (or none). Running full suite...")
        stdout_full, stderr_full, returncode_full = await runner.run_command(
            [uv_path, "run", "pytest"], check=False
        )
        logs_full = stdout_full + "\n" + stderr_full

        if returncode_full == 0:
            typer.secho("✨ All tests passed! Nothing to fix.", fg=typer.colors.GREEN)
            return

        # Capture failure logs from full run
        logs = logs_full

    # 3. Failures detected
    typer.secho("💥 Tests failed! Invoking Coder for repairs...", fg=typer.colors.RED)

    try:
        prompt = (
            f"Tests failed. Analyze the logs and fix the code in src/.\n\nLogs:\n{logs[-2000:]}"
        )
        result = await coder_agent.run(prompt)
        typer.secho("✅ Fix task assigned to Coder.", fg=typer.colors.GREEN)

        changes: list[FileOperation] = result.output

        # Reuse logic
        orchestrator = CycleOrchestrator("00", dry_run=False)
        orchestrator._apply_agent_changes(changes)

    except Exception as e:
        typer.secho(str(e), fg=typer.colors.RED)
        raise typer.Exit(1) from e


@app.command()
def doctor() -> None:
    """環境チェック"""

    # ツールとインストールガイドの辞書
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
        if settings.debug:  # Assuming Settings has debug or check env
            console.print_exception()
        elif os.getenv("DEBUG"):
            console.print_exception()
        else:
            console.print("Run with DEBUG=1 environment variable to see full traceback.")
        raise typer.Exit(code=1) from e


if __name__ == "__main__":
    friendly_error_handler()
