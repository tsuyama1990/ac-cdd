import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from .config import settings
from .gemini_api_client import GeminiApiClient
from .jules_api_client import JulesApiClient
from .tools import ToolNotFoundError, ToolWrapper
from .utils import logger


class CycleOrchestrator:
    """
    AC-CDD サイクルの自動化を管理するクラス。
    実装、テスト、監査、UATの各フェーズをオーケストレーションする。
    """

    def __init__(self, cycle_id: str, dry_run: bool = False) -> None:
        self.cycle_id = cycle_id
        self.dry_run = dry_run

        # Use paths from config
        self.documents_dir = Path(settings.paths.documents_dir)
        self.contracts_dir = Path(settings.paths.contracts_dir)

        self.cycle_dir = self.documents_dir / f"CYCLE{cycle_id}"
        self.audit_log_path = self.cycle_dir / "AUDIT_LOG.md"

        if not self.cycle_dir.exists():
            raise ValueError(f"Cycle directory {self.cycle_dir} does not exist.")

        # Initialize API Clients
        # Need to handle missing keys gracefully or raise depending on policy
        # For now, we assume env vars are present or clients handle missing keys during call
        # if possible (though init usually needs them)
        # We will retrieve keys from env or empty string if dry_run
        jules_key = os.getenv("JULES_API_KEY", "")
        gemini_key = os.getenv("GEMINI_API_KEY", "")

        # Use configured base URL for Jules if present
        jules_base_url = settings.tools.jules_base_url

        self.jules_client = JulesApiClient(api_key=jules_key, base_url=jules_base_url)
        # We initialize Gemini client, but it might fail if key is missing and library validates
        # immediately. Assuming google-genai validates on call or we are in dry_run.
        self.gemini_client = GeminiApiClient(api_key=gemini_key)

        # Initialize tools
        try:
            # We no longer use ToolWrapper for Jules/Gemini for intelligence tasks
            self.gh = ToolWrapper(settings.tools.gh_cmd)
            self.audit_tool = ToolWrapper(settings.tools.audit_cmd) # bandit
            self.uv = ToolWrapper(settings.tools.uv_cmd)
            self.mypy = ToolWrapper(settings.tools.mypy_cmd)
        except ToolNotFoundError as e:
            if not self.dry_run:
                raise
            logger.warning(f"[DRY-RUN] Tool missing: {e}. Proceeding anyway.")

    def execute_all(self, progress_task=None, progress_obj=None) -> None:
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

    def _get_system_context(self) -> str:
        """
        Retrieves dynamic context (Spec + Conventions).
        """
        context = []

        # 1. Constitution (ALL_SPEC.md)
        all_spec_path = self.documents_dir / "ALL_SPEC.md"
        if all_spec_path.exists():
            content = all_spec_path.read_text()
            context.append(f"=== Project Constitution (ALL_SPEC.md) ===\n{content}")

        # 2. Conventions
        conventions_path = self.documents_dir / "conventions.md"
        if conventions_path.exists():
            context.append(f"=== Conventions ===\n{conventions_path.read_text()}")

        return "\n\n".join(context)

    def _construct_prompt(self, role_prompt: str, user_task: str) -> str:
        """
        Constructs the full prompt with System Role, Dynamic Context, and Task.
        """
        dynamic_context = self._get_system_context()

        full_prompt = (
            f"<system_role>\n{role_prompt}\n</system_role>\n\n"
            f"<context>\n{dynamic_context}\n</context>\n\n"
            f"<task>\n{user_task}\n</task>"
        )
        return full_prompt

    def align_contracts(self) -> None:
        """
        Phase 3.1: 契約の整合確認とマージ
        Phase 3.1: 契約の整合確認とマージ
        src/ac_cdd/contracts/ に Cycleのschema.pyをマージする。
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

    def generate_property_tests(self) -> None:
        """
        Phase 3.2: プロパティベーステストの生成
        Julesに契約のみを見せてテストを書かせる。
        """
        user_task = settings.prompts.property_test_template.format(cycle_id=self.cycle_id)

        # Use 'tester' role
        full_prompt = self._construct_prompt(settings.agents.tester, user_task)

        if self.dry_run:
            logger.info(f"[DRY-RUN] calling jules with prompt: {full_prompt}")
            return

        # Call Jules API
        self.jules_client.start_task(
            prompt=full_prompt,
            session_name=f"Cycle{self.cycle_id}_PropertyTests"
        )

    def run_implementation_loop(self) -> None:
        """
        Phase 3.3 & 3.4: 実装・CI・監査ループ
        Logic:
          1. Implement
          2. Refinement Loop (Test -> Audit -> Re-Audit)
        """
        logger.info("Starting Implementation Phase")

        # 1. Initial Implementation
        self._trigger_implementation()

        # 2. Refinement Loop
        max_retries = settings.MAX_RETRIES
        attempt = 0

        logger.info("Entering Refinement Loop (Stable Audit Loop)")

        while attempt < max_retries:
            attempt += 1
            logger.info(f"Refinement Loop: Iteration {attempt}/{max_retries}")

            # 2.1 Test
            logger.info("Running Tests...")
            passed, logs = self._run_tests()

            if not passed:
                logger.warning("Tests Failed. Triggering fix...")
                fix_prompt = (
                    "Test Failed.\n"
                    "Here is the captured log (last 2000 chars):\n"
                    "--------------------------------------------------\n"
                    f"{logs}\n"
                    "--------------------------------------------------\n"
                    "Please analyze the stack trace and fix the implementation in src/."
                )
                self._trigger_fix(fix_prompt)
                continue # Back to Test

            # 2.2 Audit
            logger.info("Tests Passed. Proceeding to Strict Audit...")
            audit_result = self.run_strict_audit()

            if audit_result is True:
                logger.info("Audit Passed (Clean)!")
                # Success: Test Pass AND Audit Pass sequentially
                return
            else:
                logger.warning("Audit Failed. Triggering fix...")
                # Note: Logic says "Fix -> Back to Test"
                self._trigger_fix(f"Audit failed. See {self.audit_log_path} for details.")
                continue # Back to Test

        raise Exception("Max retries reached in Implementation/Audit Loop.")

    def _trigger_implementation(self) -> None:
        spec_path = f"{settings.paths.documents_dir}/CYCLE{self.cycle_id}/SPEC.md"
        description = (
            f"Implement requirements in {spec_path} "
            f"following schema in {settings.paths.contracts_dir}/"
        )

        # Use 'coder' role
        full_prompt = self._construct_prompt(settings.agents.coder, description)

        if self.dry_run:
            logger.info(f"[DRY-RUN] Jules implementing feature: {full_prompt}")
            return

        self.jules_client.start_task(
            prompt=full_prompt,
            session_name=f"Cycle{self.cycle_id}_Implementation"
        )

    def _run_tests(self) -> tuple[bool, str]:
        """
        Runs tests locally using uv run pytest and captures logs.
        Returns (success: bool, logs: str)
        """
        if self.dry_run:
            logger.info("[DRY-RUN] Running tests locally... (Mocking success)")
            return True, ""

        uv_path = shutil.which("uv")
        if not uv_path:
            raise ToolNotFoundError("uv not found")

        cmd = [uv_path, "run", "pytest"]
        # Use simple subprocess run to capture output
        try:
            result = subprocess.run(  # noqa: S603
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                return True, ""

            # Combine stdout and stderr
            logs = result.stdout + "\n" + result.stderr
            # Keep last 2000 chars
            if len(logs) > 2000:
                logs = "...(truncated)...\n" + logs[-2000:]

            return False, logs

        except Exception as e:
            logger.error(f"Failed to run tests: {e}")
            return False, str(e)

    def _trigger_fix(self, instructions: str) -> None:
        if self.dry_run:
            logger.info(f"[DRY-RUN] Jules fixing code: {instructions}")
            return

        self.jules_client.send_message(prompt=instructions)

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

        files_to_audit = self._get_filtered_files("src/")

        files_content = ""
        for fpath in files_to_audit:
            try:
                content = Path(fpath).read_text()
                files_content += f"\n\n=== File: {fpath} ===\n{content}"
            except Exception as e:
                logger.warning(f"Failed to read {fpath} for audit: {e}")

        user_task = (
            f"Audit the following code files:\n{files_content}\n\n"
            "Respond in JSON format with 'approved' (boolean) and 'comments' "
            "(list of strings) if not approved."
        )

        full_prompt = self._construct_prompt(settings.agents.auditor, user_task)

        try:
            # We use gemini_client
            # Note: start_task/generate_content returns text (JSON string in this case)
            response_text = self.gemini_client.start_task(
                prompt=full_prompt,
                json_mode=True
            )

            # Remove Markdown code fences if present (Gemini often adds ```json ... ```)
            cleaned_text = response_text.replace("```json", "").replace("```", "").strip()

            output = json.loads(cleaned_text)

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
        Also reads .auditignore from project root.
        """
        # Default ignored patterns
        ignored_patterns = {
            "__pycache__", ".git", ".env", ".DS_Store", "*.pyc"
        }

        # Read .auditignore if exists
        auditignore_path = Path(".auditignore")
        if auditignore_path.exists():
            try:
                lines = auditignore_path.read_text().splitlines()
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        ignored_patterns.add(line)
            except Exception as e:
                logger.warning(f"Failed to read .auditignore: {e}")

        files = []
        path = Path(directory)
        for p in path.rglob("*"):
            if p.is_file():
                # Simple check: match file name or parts of path
                # Note: fnmatch would be better for glob patterns, but basic string check
                # covers most simple cases. For robust support, use fnmatch.
                # However, original code used 'in'. Let's upgrade to fnmatch if possible,
                # or stick to 'in' if patterns are simple substrings.
                # The .auditignore I created has "*.pyc". 'in' checks substring.
                # "*.pyc" in "foo.pyc" is False.
                # So we should use fnmatch.
                import fnmatch

                # Check if any pattern matches
                # We check both name and full relative path
                is_ignored = False
                for pattern in ignored_patterns:
                    if fnmatch.fnmatch(p.name, pattern) or fnmatch.fnmatch(str(p), pattern):
                        is_ignored = True
                        break
                    # Also check if it contains substring for strict patterns like '.git'
                    if pattern in str(p):
                        is_ignored = True
                        break

                if is_ignored:
                    continue

                files.append(str(p))
        return files

    def _log_audit_failure(self, comments: list[str]) -> None:
        with open(self.audit_log_path, "a") as f:
            f.write(f"\n## Audit Failed at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            for c in comments:
                f.write(f"- {c}\n")

    def run_uat_phase(self) -> None:
        """
        Phase 3.5: UATの生成と実行
        """
        if self.dry_run:
            logger.info("[DRY-RUN] Generating UAT with Playwright and running pytest...")
            return

        # 1. Generate UAT Code
        uat_path = f"{settings.paths.documents_dir}/CYCLE{self.cycle_id}/UAT.md"
        description = f"Create Playwright tests in tests/e2e/ based on {uat_path}"

        # Use 'tester' role? Or 'coder'? Usually UAT is written by Tester/QA.
        full_prompt = self._construct_prompt(settings.agents.tester, description)

        self.jules_client.start_task(
            prompt=full_prompt,
            session_name=f"Cycle{self.cycle_id}_UAT"
        )

        # 2. Run Tests
        test_args = ["run", "pytest", "tests/e2e/"]
        try:
            self.uv.run(test_args)
        except Exception:
            self._trigger_fix("UAT Tests Failed. Please fix implementation or tests.")
            raise Exception("UAT Phase Failed") from None

    def finalize_cycle(self) -> None:
        """
        Phase 4: 自動マージ
        """
        if self.dry_run:
            logger.info("[DRY-RUN] Merging PR via gh CLI...")
            return

        # gh pr merge
        args = ["pr", "merge", "--squash", "--delete-branch", "--admin"]
        self.gh.run(args)
