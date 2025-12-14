import os
import shutil
import sys
from pathlib import Path
import subprocess

# 定数定義
BASE_DIR = Path(__file__).resolve().parent

# ファイル内容の定義

PYPROJECT_TOML = """[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "autonomous-dev-env"
version = "0.1.0"
description = "AI-Native Cycle-Based Contract-Driven Development Environment"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "fastapi",
    "uvicorn",
    "pydantic>=2.0",
    "python-dotenv",
]

[dependency-groups]
dev = [
    "typer",
    "rich",
    "shellingham",
    "pytest",
    "pytest-cov",
    "hypothesis",
    "playwright",
    "vcrpy",
    "ruff",
    "google-genai",
]

[tool.ruff]
line-length = 100
fix = true

[tool.ruff.lint]
select = ["E", "F", "I"]
ignore = []

[tool.pytest.ini_options]
addopts = "--cov=src --cov-report=term-missing"
testpaths = ["tests"]

[tool.hatch.build.targets.wheel]
packages = ["src/contracts", "src/core", "scripts"]
"""

MANAGE_PY = """#!/usr/bin/env python3
import sys
import shutil
import typer
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
import os
from dotenv import load_dotenv

# モジュールのインポート (セットアップ後を想定)
try:
    from scripts.ai_orchestrator import CycleOrchestrator
except ImportError:
    # 初期化前の場合、モジュールがない可能性がある
    pass

load_dotenv()

app = typer.Typer(help="AC-CDD Development Environment Manager")
console = Console()

@app.command()
def init():
    \"\"\"プロジェクトの初期化と依存関係チェック\"\"\"
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
    \"\"\"新しい開発サイクルを作成します (例: 01, 02)\"\"\"
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
    \"\"\"サイクルの自動実装・監査ループを開始します\"\"\"
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
    \"\"\"環境の健全性を診断します\"\"\"
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
"""

SCRIPTS_ORCHESTRATOR_PY = """import json
import shutil
import subprocess
import time
from pathlib import Path

from .utils import logger, run_command


class CycleOrchestrator:
    \"\"\"
    AC-CDD サイクルの自動化を管理するクラス。
    実装、テスト、監査、UATの各フェーズをオーケストレーションする。
    \"\"\"

    def __init__(self, cycle_id: str, dry_run: bool = False):
        self.cycle_id = cycle_id
        self.dry_run = dry_run
        self.cycle_dir = Path(f"documents/CYCLE{cycle_id}")
        self.contracts_dir = Path("src/contracts")
        self.audit_log_path = self.cycle_dir / "AUDIT_LOG.md"

        if not self.cycle_dir.exists():
            raise ValueError(f"Cycle directory {self.cycle_dir} does not exist.")

    def execute_all(self, progress_task=None, progress_obj=None):
        \"\"\"全フェーズを実行\"\"\"
        steps = [
            ("Aligning Contracts", self.align_contracts),
            ("Generating Property Tests", self.generate_property_tests),
            ("Implementation Loop", self.run_implementation_loop),
            ("UAT Phase", self.run_uat_phase),
            ("Finalizing Cycle", self.finalize_cycle),
        ]

        for name, func in steps:
            if progress_obj:
                progress_obj.update(progress_task, description=f"[cyan]{name}...")
            logger.info(f"Starting Phase: {name}")
            func()
            logger.info(f"Completed Phase: {name}")

    def align_contracts(self):
        \"\"\"
        Phase 3.1: 契約の整合確認とマージ
        documents/CYCLE{id}/schema.py を src/contracts/ にマージする。
        \"\"\"
        source_schema = self.cycle_dir / "schema.py"
        target_schema = self.contracts_dir / f"schema_cycle{self.cycle_id}.py"

        if not source_schema.exists():
            raise FileNotFoundError(f"{source_schema} not found.")

        # Pydanticモデルとして有効かチェック (Dry runでも行う)
        # 実際にはここで import してチェックしたいが、簡単のためファイルコピーとみなす

        if self.dry_run:
            logger.info(f"[DRY-RUN] Would copy {source_schema} to {target_schema}")
            return

        # ディレクトリ確認
        self.contracts_dir.mkdir(parents=True, exist_ok=True)

        # 既存ファイルがある場合、バックアップ
        if target_schema.exists():
            backup = target_schema.with_suffix(".py.bak")
            shutil.copy(target_schema, backup)
            logger.info(f"Backed up existing schema to {backup}")

        shutil.copy(source_schema, target_schema)

        # __init__.py の更新
        # 名前空間の衝突を避けるため、サイクルIDを含めたエイリアスでインポートするか、
        # あるいは「最新のサイクルが正義」として上書きを許容するか。
        # ここではシンプルに追記するが、実際の運用では古いサイクルのクラス名変更などを検討すべき。
        init_file = self.contracts_dir / "__init__.py"
        import_line = f"from .schema_cycle{self.cycle_id} import *"

        if init_file.exists():
            content = init_file.read_text()
            if import_line not in content:
                with open(init_file, "a") as f:
                    f.write(f"\\n{import_line}\\n")
        else:
            with open(init_file, "w") as f:
                f.write(f"{import_line}\\n")

    def generate_property_tests(self):
        \"\"\"
        Phase 3.2: プロパティベーステストの生成
        Julesに契約のみを見せてテストを書かせる。
        \"\"\"
        prompt = (
            "実装は見ず、このPydanticスキーマ (contracts/) の制約が正しく機能するかを検証する "
            "Hypothesisテストを作成せよ。出力先は tests/property/test_cycle{cycle_id}.py"
        )

        if self.dry_run:
            logger.info(f"[DRY-RUN] calling jules with prompt: {prompt}")
            return

        # contractsディレクトリの中身をコンテキストとして渡す
        # 注意: 実際のJules CLIの引数体系に合わせて調整が必要
        cmd = [
            "jules", "remote", "new",
            "--title", f"Generate Property Tests for Cycle {self.cycle_id}",
            "--description", prompt
            # コンテキスト指定が必要ならここに追加
        ]
        run_command(cmd)

    def run_implementation_loop(self):
        \"\"\"
        Phase 3.3 & 3.4: 実装・CI・監査ループ
        \"\"\"
        max_retries = 10
        attempt = 0

        while attempt < max_retries:
            attempt += 1
            logger.info(f"Implementation Loop: Attempt {attempt}/{max_retries}")

            # 1. Implement
            self._trigger_implementation()

            # 2. CI Check
            if not self._wait_for_ci():
                logger.warning("CI Failed. Triggering fix...")
                self._trigger_fix("CI Check failed. Please fix the implementation based on logs.")
                continue

            # 3. Strict Audit
            audit_result = self.run_strict_audit()
            if audit_result is True:
                logger.info("Audit Passed!")
                return
            else:
                logger.warning("Audit Failed. Triggering fix...")
                # Audit結果は AUDIT_LOG.md にある想定
                self._trigger_fix(f"Audit failed. See {self.audit_log_path} for details.")

        raise Exception("Max retries reached in Implementation Loop.")

    def _trigger_implementation(self):
        if self.dry_run:
            logger.info("[DRY-RUN] Jules implementing feature from SPEC.md and schema.py...")
            return

        cmd = [
            "jules",
            "remote",
            "new",
            "--title",
            f"Implement Cycle {self.cycle_id}",
            "--description",
            f"Implement requirements in documents/CYCLE{self.cycle_id}/SPEC.md following "
            "schema in src/contracts/",
        ]
        run_command(cmd)

    def _wait_for_ci(self) -> bool:
        \"\"\"GitHub Actionsの完了を待つ\"\"\"
        if self.dry_run:
            logger.info("[DRY-RUN] Waiting for CI... (Mocking success)")
            return True

        logger.info("Watching CI status...")
        # gh run watch を使う。失敗したら exit code が非0になる
        try:
            # 最新のRunを監視
            run_command(["gh", "run", "watch", "--exit-status"])
            return True
        except subprocess.CalledProcessError:
            return False

    def _trigger_fix(self, instructions: str):
        if self.dry_run:
            logger.info(f"[DRY-RUN] Jules fixing code: {instructions}")
            return

        # 既存の会話/PRへの返信として実装するのが理想だが、ここでは新規タスクとして単純化
        cmd = ["jules", "remote", "reply", "--message", instructions]
        # 注意: jules reply は対話コンテキストが必要。ここでは概念実装。
        run_command(cmd)

    def run_strict_audit(self) -> bool:
        \"\"\"
        Phase 3.4: 世界一厳格な監査
        Gemini CLI (JSON mode) を呼び出す。
        \"\"\"
        prompt = (
            "あなたは世界一厳格なコード監査人です。"
            "Pydantic契約違反、セキュリティ、設計原則の観点からコードをレビューしてください。"
            "合格なら `{\\"approved\\": true}`、"
            "不合格なら `{\\"approved\\": false, \\"comments\\": [...]}` をJSONで返してください。"
        )

        if self.dry_run:
            logger.info("[DRY-RUN] Gemini Auditing... (Mocking approval)")
            return True

        # srcディレクトリ全体を監査対象とする
        # gemini CLIの仕様に合わせて調整
        cmd = [
            "gemini", # 外部コマンド
            "--json", # JSON出力モード (仮定)
            prompt,
            "src/"    # 対象ディレクトリ
        ]

        try:
            # 実際には run_command で出力をキャプチャしてパースする
            # ここでは run_command はストリーミング出力用なので、subprocess.run を直接使う
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            output = json.loads(res.stdout)

            if output.get("approved"):
                return True
            else:
                comments = output.get("comments", [])
                self._log_audit_failure(comments)
                return False
        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            logger.error(f"Audit tool execution failed: {e}")
            # ツール自体の失敗は、とりあえずFalseとして扱うか、例外にするか
            return False
        except FileNotFoundError:
            logger.warning(
                "Gemini CLI not found. Skipping audit (assuming pass for dev environment if "
                "not strict)."
            )
            # 本来はFailさせるべきだが、開発環境構築中なのでWarningに留めるケースも
            return False

    def _log_audit_failure(self, comments: list):
        with open(self.audit_log_path, "a") as f:
            f.write(f"\\n## Audit Failed at {time.strftime('%Y-%m-%d %H:%M:%S')}\\n")
            for c in comments:
                f.write(f"- {c}\\n")

    def run_uat_phase(self):
        \"\"\"
        Phase 3.5: UATの生成と実行
        \"\"\"
        if self.dry_run:
            logger.info("[DRY-RUN] Generating UAT with Playwright and running pytest...")
            return

        # 1. Generate UAT Code
        gen_cmd = [
            "jules",
            "remote",
            "new",
            "--title",
            f"Generate UAT for Cycle {self.cycle_id}",
            "--description",
            f"Create Playwright tests in tests/e2e/ based on documents/CYCLE{self.cycle_id}/UAT.md",
        ]
        run_command(gen_cmd)

        # 2. Run Tests
        test_cmd = ["uv", "run", "pytest", "tests/e2e/"]
        try:
            run_command(test_cmd)
        except subprocess.CalledProcessError:
            self._trigger_fix("UAT Tests Failed. Please fix implementation or tests.")
            raise Exception("UAT Phase Failed")

    def finalize_cycle(self):
        \"\"\"
        Phase 4: 自動マージ
        \"\"\"
        if self.dry_run:
            logger.info("[DRY-RUN] Merging PR via gh CLI...")
            return

        cmd = ["gh", "pr", "merge", "--squash", "--delete-branch", "--admin"]
        run_command(cmd)
"""

SCRIPTS_UTILS_PY = """import subprocess
import logging
from rich.logging import RichHandler
from rich.console import Console

console = Console()

# ロガー設定
logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True)]
)

logger = logging.getLogger("AC-CDD")

def run_command(command: list[str], cwd=None, env=None):
    \"\"\"
    コマンドを実行し、出力をリアルタイムで表示する。
    エラー時は CalledProcessError を送出する。
    \"\"\"
    cmd_str = " ".join(command)
    logger.info(f"Running: {cmd_str}")

    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        for line in process.stdout:
            print(line, end="") # RichHandler経由でなく直接出力して生ログを見せる

        process.wait()

        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, command)

    except Exception as e:
        logger.error(f"Command failed: {e}")
        raise

def check_dependency(cmd: str) -> bool:
    import shutil
    return shutil.which(cmd) is not None
"""

TEMPLATE_SCHEMA = """from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any

# 契約（Contract）定義
# このファイルがこのサイクルの「正解」となります。
# 変更する場合は必ずこのファイルを更新し、再整合させてください。

class CycleInput(BaseModel):
    \"\"\"入力データの仕様\"\"\"
    model_config = ConfigDict(extra='forbid') # 厳格モード: 定義されていないフィールドは禁止

    request_id: str = Field(..., description="リクエストID")
    payload: Dict[str, Any] = Field(default_factory=dict, description="処理対象データ")

class CycleOutput(BaseModel):
    \"\"\"出力データの仕様\"\"\"
    success: bool = Field(..., description="処理成功フラグ")
    data: Optional[Dict[str, Any]] = Field(None, description="結果データ")
    error_message: Optional[str] = Field(None, description="エラー時のメッセージ")
"""

TEMPLATE_SPEC = """# 仕様書 (SPEC)

## 1. 概要
このサイクルの目的と概要を記述します。

## 2. 機能要件
- [ ] 要件1
- [ ] 要件2

## 3. 非機能要件
- パフォーマンス:
- セキュリティ:

## 4. エッジケース
- 入力が空の場合
- 異常系データ
"""

TEMPLATE_UAT = """# ユーザー受け入れテスト (UAT)

## シナリオ1: 正常系
User Action:
Expected Result:

## シナリオ2: エラー系
User Action:
Expected Result:
"""

GITHUB_WORKFLOW_CI = """name: AC-CDD CI Check

on:
  pull_request:
    branches: [ main ]
  push:
    branches: [ main ]
  workflow_dispatch:

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v1

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version-file: "pyproject.toml"

      - name: Install dependencies
        run: uv sync --all-extras --dev

      - name: Run Linting
        run: uv run ruff check src tests

      - name: Run Property Tests
        run: uv run pytest tests/property/

      - name: Install Playwright Browsers
        run: uv run playwright install --with-deps chromium

      - name: Run E2E Tests
        # E2Eテストが存在する場合のみ実行
        run: |
          if [ -d "tests/e2e" ] && [ "$(ls -A tests/e2e)" ]; then
            uv run pytest tests/e2e/
          else
            echo "No E2E tests found, skipping."
          fi
"""

ENV_EXAMPLE = """# API Keys
GEMINI_API_KEY=your_gemini_api_key_here
JULES_API_KEY=your_jules_api_key_here

# Settings
LOG_LEVEL=INFO
"""

MAIN_PY = """from fastapi import FastAPI

app = FastAPI(title="AC-CDD Application")

@app.get("/")
def read_root():
    return {"message": "Hello from AC-CDD Environment"}
"""

def create_structure():
    # 1. Directories
    dirs = [
        "src/contracts",
        "src/core",
        "tests/property",
        "tests/e2e",
        "documents/templates",
        "scripts",
        ".github/workflows",
    ]
    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)
        print(f"Created directory: {d}")

    # 2. Files
    files_map = {
        "pyproject.toml": PYPROJECT_TOML,
        "manage.py": MANAGE_PY,
        "scripts/ai_orchestrator.py": SCRIPTS_ORCHESTRATOR_PY,
        "scripts/utils.py": SCRIPTS_UTILS_PY,
        "documents/templates/schema_template.py": TEMPLATE_SCHEMA,
        "documents/templates/SPEC_TEMPLATE.md": TEMPLATE_SPEC,
        "documents/templates/UAT_TEMPLATE.md": TEMPLATE_UAT,
        ".github/workflows/ci.yml": GITHUB_WORKFLOW_CI,
        ".env.example": ENV_EXAMPLE,
        "src/main.py": MAIN_PY,
    }

    for path_str, content in files_map.items():
        path = Path(path_str)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Created file: {path_str}")

    # 3. Init files
    Path("src/contracts/__init__.py").touch()
    Path("scripts/__init__.py").touch()

    # 4. Make manage.py executable
    try:
        mode = os.stat("manage.py").st_mode
        os.chmod("manage.py", mode | 0o755)
    except Exception as e:
        print(f"Warning: Could not make manage.py executable: {e}")

if __name__ == "__main__":
    print("Setting up AC-CDD Environment...")
    create_structure()
    print("Setup Complete! Run 'uv sync' and then './manage.py init' to start.")
