import json
import shutil
import time
from pathlib import Path
from typing import Optional

from .utils import logger
from .config import settings
from .tools import ToolWrapper, ToolNotFoundError

class CycleOrchestrator:
    """
    AC-CDD サイクルの自動化を管理するクラス。
    実装、テスト、監査、UATの各フェーズをオーケストレーションする。
    """

    def __init__(self, cycle_id: str, dry_run: bool = False):
        self.cycle_id = cycle_id
        self.dry_run = dry_run

        # Use paths from config
        self.documents_dir = Path(settings.paths.documents_dir)
        self.contracts_dir = Path(settings.paths.contracts_dir)

        self.cycle_dir = self.documents_dir / f"CYCLE{cycle_id}"
        self.audit_log_path = self.cycle_dir / "AUDIT_LOG.md"

        if not self.cycle_dir.exists():
            raise ValueError(f"Cycle directory {self.cycle_dir} does not exist.")

        # Initialize tools
        try:
            self.jules = ToolWrapper(settings.tools.jules_cmd)
            self.gh = ToolWrapper(settings.tools.gh_cmd)
            self.audit_tool = ToolWrapper(settings.tools.audit_cmd) # bandit
            self.uv = ToolWrapper(settings.tools.uv_cmd)
            self.mypy = ToolWrapper(settings.tools.mypy_cmd)
            self.gemini = ToolWrapper(settings.tools.gemini_cmd)
        except ToolNotFoundError as e:
            if not self.dry_run:
                raise
            logger.warning(f"[DRY-RUN] Tool missing: {e}. Proceeding anyway.")

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
        prompt = settings.prompts.property_test_template.format(cycle_id=self.cycle_id)

        if self.dry_run:
            logger.info(f"[DRY-RUN] calling jules with prompt: {prompt}")
            return

        # cmd = ["jules", "remote", "new", ...]
        # Using ToolWrapper
        args = [
            "remote", "new",
            "--title", f"Generate Property Tests for Cycle {self.cycle_id}",
            "--description", prompt
        ]
        self.jules.run(args)

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
                self._trigger_fix(f"Audit failed. See {self.audit_log_path} for details.")

        raise Exception("Max retries reached in Implementation Loop.")

    def _trigger_implementation(self):
        description = (
            f"Implement requirements in {settings.paths.documents_dir}/CYCLE{self.cycle_id}/SPEC.md "
            f"following schema in {settings.paths.contracts_dir}/"
        )

        if self.dry_run:
            logger.info(f"[DRY-RUN] Jules implementing feature: {description}")
            return

        args = [
            "remote",
            "new",
            "--title",
            f"Implement Cycle {self.cycle_id}",
            "--description",
            description,
        ]
        self.jules.run(args)

    def _wait_for_ci(self) -> bool:
        """GitHub Actionsの完了を待つ"""
        if self.dry_run:
            logger.info("[DRY-RUN] Waiting for CI... (Mocking success)")
            return True

        logger.info("Watching CI status...")
        try:
            # gh run watch
            self.gh.run(["run", "watch", "--exit-status"])
            return True
        except Exception:
            return False

    def _trigger_fix(self, instructions: str):
        if self.dry_run:
            logger.info(f"[DRY-RUN] Jules fixing code: {instructions}")
            return

        # jules reply
        args = ["remote", "reply", "--message", instructions]
        self.jules.run(args)

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
            self.audit_tool.run(["-r", "src/", "-ll"])
        except Exception:
            msg = "Security Check (Bandit) Failed."
            logger.warning(msg)
            self._log_audit_failure([msg])
            return False

        # 2. Mypy
        try:
            self.mypy.run(["src/"])
        except Exception:
            msg = "Type Check (Mypy) Failed."
            logger.warning(msg)
            self._log_audit_failure([msg])
            return False

        # 3. LLM Audit
        logger.info("Static checks passed. Proceeding to LLM Audit...")

        prompt = settings.prompts.auditor_system
        files_to_audit = self._get_filtered_files("src/")

        # We pass the list of filtered files to the gemini command.
        args = [
            "--json",
            prompt,
            *files_to_audit
        ]

        try:
            res = self.gemini.run(args, capture_output=True)
            output = json.loads(res.stdout)

            if output.get("approved"):
                return True
            else:
                comments = output.get("comments", [])
                self._log_audit_failure(comments)
                return False
        except (Exception, json.JSONDecodeError) as e:
            logger.error(f"Audit tool execution failed: {e}")
            return False

    def _get_filtered_files(self, directory: str) -> list[str]:
        """
        Recursively list files in directory, excluding sensitive/ignored ones.
        """
        ignored_patterns = [
            "__pycache__", ".git", ".env", ".DS_Store", "*.pyc"
        ]

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
        gen_args = [
            "remote",
            "new",
            "--title",
            f"Generate UAT for Cycle {self.cycle_id}",
            "--description",
            f"Create Playwright tests in tests/e2e/ based on {settings.paths.documents_dir}/CYCLE{self.cycle_id}/UAT.md",
        ]
        self.jules.run(gen_args)

        # 2. Run Tests
        test_args = ["run", "pytest", "tests/e2e/"]
        try:
            self.uv.run(test_args)
        except Exception:
            self._trigger_fix("UAT Tests Failed. Please fix implementation or tests.")
            raise Exception("UAT Phase Failed")

    def finalize_cycle(self):
        """
        Phase 4: 自動マージ
        """
        if self.dry_run:
            logger.info("[DRY-RUN] Merging PR via gh CLI...")
            return

        # gh pr merge
        args = ["pr", "merge", "--squash", "--delete-branch", "--admin"]
        self.gh.run(args)
