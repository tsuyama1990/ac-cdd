import json
import shutil
import subprocess
import time
from pathlib import Path

# Relative import because utils is in the same package
from .utils import logger, run_command
from .config import settings

class CycleOrchestrator:
    """
    AC-CDD サイクルの自動化を管理するクラス。
    実装、テスト、監査、UATの各フェーズをオーケストレーションする。
    """

    def __init__(self, cycle_id: str, dry_run: bool = False):
        self.cycle_id = cycle_id
        self.dry_run = dry_run
        self.cycle_dir = Path(f"documents/CYCLE{cycle_id}")
        self.contracts_dir = Path("src/ac_cdd/contracts")
        self.audit_log_path = self.cycle_dir / "AUDIT_LOG.md"

        if not self.cycle_dir.exists():
            raise ValueError(f"Cycle directory {self.cycle_dir} does not exist.")

    def execute_all(self, progress_task=None, progress_obj=None):
        """全フェーズを実行"""
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
        """
        Phase 3.1: 契約の整合確認とマージ
        documents/CYCLE{id}/schema.py を src/ac_cdd/contracts/ にマージする。
        """
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
                    f.write(f"\n{import_line}\n")
        else:
            with open(init_file, "w") as f:
                f.write(f"{import_line}\n")

    def generate_property_tests(self):
        """
        Phase 3.2: プロパティベーステストの生成
        Julesに契約のみを見せてテストを書かせる。
        """
        prompt = settings.PROPERTY_TEST_PROMPT_TEMPLATE.format(cycle_id=self.cycle_id)

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
        """
        Phase 3.3 & 3.4: 実装・CI・監査ループ
        """
        max_retries = settings.MAX_RETRIES
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
            "schema in src/ac_cdd/contracts/",
        ]
        run_command(cmd)

    def _wait_for_ci(self) -> bool:
        """GitHub Actionsの完了を待つ"""
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
        """
        Phase 3.4: 世界一厳格な監査
        1. Bandit (Security)
        2. Mypy (Type Check)
        3. LLM Audit (if checks pass)
        """
        if self.dry_run:
            logger.info("[DRY-RUN] Static Analysis & Gemini Auditing... (Mocking approval)")
            return True

        logger.info("Running Static Analysis (Bandit & Mypy)...")

        # 1. Bandit
        try:
            # -r for recursive, -f custom or plain
            # We target src/ directory
            run_command(["bandit", "-r", "src/", "-ll"])
        except subprocess.CalledProcessError:
            msg = "Security Check (Bandit) Failed."
            logger.warning(msg)
            self._log_audit_failure([msg])
            return False

        # 2. Mypy
        try:
            run_command(["mypy", "src/"])
        except subprocess.CalledProcessError:
            msg = "Type Check (Mypy) Failed."
            logger.warning(msg)
            self._log_audit_failure([msg])
            return False

        # 3. LLM Audit
        logger.info("Static checks passed. Proceeding to LLM Audit...")

        prompt = settings.AUDITOR_PROMPT

        # Filter sensitive files if we were to read them here.
        # But since we pass "src/" to gemini, we rely on it or need to be careful.
        # The prompt instruction says: "Add filtering processing when orchestrator reads code and sends to AI"
        # Since 'gemini' CLI is used and we pass a directory, we can't easily filter *inside* the python code
        # unless we pass file contents explicitly or the CLI supports exclusion.
        # Assuming we need to implement exclusion logic if we were reading files manually.
        # However, for now, we will assume 'gemini' CLI handles the directory.
        # To strictly follow "Add filtering processing", we should probably manually
        # collect files excluding sensitive ones if 'gemini' CLI supports receiving file content via stdin or list.
        # Given the mock nature of external tools here, I will stick to the previous implementation
        # but add a comment that filtering is applied (conceptually) or if 'gemini' supports it.
        #
        # Re-reading: "Task 5: Security Filter... implement exclusion list... when reading code and sending to AI"
        # Since I'm using an external 'gemini' command, I can't filter what it reads unless I list files for it.
        # Let's assume 'gemini' accepts a list of files.

        # Implementation of File Filtering:
        files_to_audit = self._get_filtered_files("src/")

        # We pass the list of filtered files to the gemini command.
        # This assumes the gemini CLI accepts multiple file paths as arguments.
        cmd = [
            "gemini",
            "--json",
            prompt,
            *files_to_audit
        ]

        try:
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
            return False
        except FileNotFoundError:
            logger.warning("Gemini CLI not found. Skipping audit.")
            return False

    def _get_filtered_files(self, directory: str) -> list[str]:
        """
        Recursively list files in directory, excluding sensitive/ignored ones.
        """
        ignored_patterns = [
            "__pycache__", ".git", ".env", ".DS_Store", "*.pyc"
        ]
        # This is a simple implementation. In reality, use pathspec with .gitignore

        files = []
        path = Path(directory)
        for p in path.rglob("*"):
            if p.is_file():
                # Check exclusions
                if any(ignored in str(p) for ignored in ignored_patterns):
                    continue
                files.append(str(p))
        return files

    def _log_audit_failure(self, comments: list):
        with open(self.audit_log_path, "a") as f:
            f.write(f"\n## Audit Failed at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            for c in comments:
                f.write(f"- {c}\n")

    def run_uat_phase(self):
        """
        Phase 3.5: UATの生成と実行
        """
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
        """
        Phase 4: 自動マージ
        """
        if self.dry_run:
            logger.info("[DRY-RUN] Merging PR via gh CLI...")
            return

        cmd = ["gh", "pr", "merge", "--squash", "--delete-branch", "--admin"]
        run_command(cmd)
