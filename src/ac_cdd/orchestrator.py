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

    def __init__(self, cycle_id: str, dry_run: bool = False, auto_next: bool = False) -> None:
        self.cycle_id = cycle_id
        self.dry_run = dry_run
        self.auto_next = auto_next

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
            ("Planning Phase", self.plan_cycle),
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

    def plan_cycle(self) -> None:
        """
        Phase 0: 計画策定 (Planning Phase)
        JulesがALL_SPEC.mdとCYCLE_PLANNING_PROMPT.mdを読み込み、
        自動的に実装計画 (SPEC.md, schema.py, UAT.md) を策定・配置する。
        """
        if self.dry_run:
            logger.info("[DRY-RUN] Planning Cycle... (Mocking plan generation)")
            return

        # 1. Read Inputs
        planning_prompt_path = Path(settings.paths.templates) / "CYCLE_PLANNING_PROMPT.md"
        all_spec_path = self.documents_dir / "ALL_SPEC.md"

        if not planning_prompt_path.exists():
            raise FileNotFoundError(f"{planning_prompt_path} not found.")

        # Note: ALL_SPEC.md might be missing if not initialized, but typically required for planning
        if not all_spec_path.exists():
            logger.warning(f"{all_spec_path} not found. Using default/empty context.")
            all_spec_content = "(No ALL_SPEC.md provided)"
        else:
            all_spec_content = all_spec_path.read_text()

        base_prompt = planning_prompt_path.read_text()

        # 2. Construct Prompt
        # Inject ALL_SPEC content into the placeholder or append it
        user_task = base_prompt.replace("[PASTE YOUR ALL_SPEC.MD CONTENT HERE]", all_spec_content)
        user_task += f"\n\nFocus specifically on generating artifacts for CYCLE{self.cycle_id}."

        # Use 'architect' role
        full_prompt = self._construct_prompt(settings.agents.architect, user_task)

        # 3. Call Jules API
        logger.info(f"Generating Plan for CYCLE{self.cycle_id}...")
        # We expect Jules to output Markdown code blocks.
        # Ideally, we should parse the output and save to files.
        # For now, we'll ask Jules to output the content and we rely on the user/Jules to ensure
        # the format is correct.
        # But wait, the task implies AUTOMATION. So we should parse the response and write to:
        # - dev_documents/CYCLE{id}/SPEC.md
        # - dev_documents/CYCLE{id}/schema.py
        # - dev_documents/CYCLE{id}/UAT.md

        response_text = self.jules_client.start_task(
            prompt=full_prompt,
            session_name=f"Cycle{self.cycle_id}_Planning"
        )

        # 4. Parse and Save Artifacts
        self._parse_and_save_plan(response_text)

    def _parse_and_save_plan(self, response_text: str) -> None:
        """
        Parses the LLM response for code blocks and saves them to the cycle directory.
        Expected format matches CYCLE_PLANNING_PROMPT.md output example.
        """
        self.cycle_dir.mkdir(parents=True, exist_ok=True)

        # Simple parsing strategy: look for filenames in headers or text followed by code blocks
        # or just regex for ```markdown ... ``` blocks?
        # Given the prompt template asks for specific headers like:
        # ### 1. `dev_documents/CYCLE01/SPEC.md`
        # ```markdown ... ```
        # We can try to regex extract based on file extensions or headers.

        import re

        # Pattern to find file path and content
        # Matches: ### <number>. `path` \n ```<lang> \n <content> \n ```
        # We'll be lenient with the path regex
        pattern = re.compile(r"###\s*\d+\.\s*`([^`]+)`\s*\n\s*```(\w*)\n(.*?)```", re.DOTALL)

        matches = pattern.findall(response_text)

        if not matches:
            logger.warning("No artifacts found. Saving full response to PLAN.md")
            (self.cycle_dir / "PLAN.md").write_text(response_text)
            return

        for fpath_str, _lang, content in matches:
            # Extract filename from path (ignoring directory provided by LLM if it differs)
            # The prompt asks for dev_documents/CYCLE{id}/filename
            # We want to force save to self.cycle_dir
            fname = Path(fpath_str).name
            target_path = self.cycle_dir / fname

            target_path.write_text(content)
            logger.info(f"Saved {target_path}")

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
        Self-Healing:
          If implementation fails after max retries, retry the Plan Phase.
        """
        logger.info("Starting Implementation Phase")

        # Outer loop for Self-Healing (Re-Planning)
        max_plan_retries = 3
        plan_attempt = 0

        while plan_attempt < max_plan_retries:
            plan_attempt += 1
            if plan_attempt > 1:
                logger.warning(
                    f"Self-Healing: Re-planning cycle ({plan_attempt}/{max_plan_retries})..."
                )
                # Feedback loop: Ask Jules to revise the plan based on failure
                # We use a specialized re-planning task with failure context.

                self._replan_cycle(
                    "Implementation loop failed repeatedly. "
                    "Please review SPEC/Schema/UAT and simplify or fix logic."
                )

            # 1. Initial Implementation
            self._trigger_implementation()

            # 2. Refinement Loop
            max_retries = settings.MAX_RETRIES
            attempt = 0

            logger.info("Entering Refinement Loop (Stable Audit Loop)")

            loop_success = False

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
                    continue  # Back to Test

                # 2.2 Audit
                logger.info("Tests Passed. Proceeding to Strict Audit...")
                audit_result = self.run_strict_audit()

                if audit_result is True:
                    logger.info("Audit Passed (Clean)!")
                    # Success: Test Pass AND Audit Pass sequentially
                    loop_success = True
                    break
                else:
                    logger.warning("Audit Failed. Triggering fix...")
                    # Note: Logic says "Fix -> Back to Test"
                    self._trigger_fix(f"Audit failed. See {self.audit_log_path} for details.")
                    continue  # Back to Test

            if loop_success:
                return

            # If we reach here, the inner loop failed (max retries)
            logger.error("Implementation Loop Failed.")
            # Continue to outer loop (Self-Healing)
            # We will use 'failure_reason' for the re-plan prompt.

        raise Exception(
            f"Max retries reached in Self-Healing Plan Loop ({max_plan_retries} attempts)."
        )

    def _replan_cycle(self, feedback: str) -> None:
        """
        Re-runs planning with feedback.
        """
        logger.info("Triggering Re-Planning with feedback...")

        # Similar to plan_cycle but with feedback
        planning_prompt_path = Path(settings.paths.templates) / "CYCLE_PLANNING_PROMPT.md"
        all_spec_path = self.documents_dir / "ALL_SPEC.md"

        base_prompt = planning_prompt_path.read_text() if planning_prompt_path.exists() else ""
        all_spec_content = all_spec_path.read_text() if all_spec_path.exists() else ""

        user_task = base_prompt.replace("[PASTE YOUR ALL_SPEC.MD CONTENT HERE]", all_spec_content)
        user_task += (
            f"\n\nCRITICAL UPDATE: The previous plan failed during implementation.\n"
            f"Feedback: {feedback}\n\n"
            f"Please revise the SPEC, Schema, and UAT for CYCLE{self.cycle_id} "
            "to be simpler or more robust."
        )

        full_prompt = self._construct_prompt(settings.agents.architect, user_task)

        response_text = self.jules_client.start_task(
            prompt=full_prompt,
            session_name=f"Cycle{self.cycle_id}_RePlanning"
        )
        self._parse_and_save_plan(response_text)

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
        1. Ruff (Lint & Fix)
        2. Mypy (Type Check)
        3. Bandit (Security)
        4. LLM Audit (if all static checks pass)
        """
        if self.dry_run:
            logger.info("[DRY-RUN] Static Analysis & Gemini Auditing... (Mocking approval)")
            return True

        logger.info("Running Static Analysis (Ruff, Mypy, Bandit)...")

        # 1. Ruff Check & Fix
        try:
            # S607: We need full path for ruff.
            # Assuming ruff is installed in the environment (uv should handle it)
            # We can use `uv run ruff` or just `ruff` if in venv.
            # Safe bet is using `uv run ruff` as configured in tools,
            # but settings doesn't have ruff_cmd. Let's use shutil.which("ruff")
            ruff_path = shutil.which("ruff")
            if ruff_path:
                # Run check with fix
                subprocess.run(  # noqa: S603
                    [ruff_path, "check", "--fix", "src/", "tests/"],
                    check=True,
                    capture_output=True,
                    text=True
                )
                # Run format
                subprocess.run(  # noqa: S603
                    [ruff_path, "format", "src/", "tests/"],
                    check=True,
                    capture_output=True,
                    text=True
                )
            else:
                logger.warning("Ruff not found. Skipping auto-fix.")
        except subprocess.CalledProcessError as e:
            msg = f"Linting (Ruff) Failed:\n{e.stdout}\n{e.stderr}"
            logger.warning(msg)
            self._log_audit_failure([msg])
            return False

        # 2. Mypy
        try:
            self.mypy.run(["src/"])
        except Exception as e:
            # Ensure we catch the specific tool error or general exception and log details
            msg = f"Type Check (Mypy) Failed: {e}"
            logger.warning(msg)
            self._log_audit_failure([msg])
            return False

        # 3. Bandit
        try:
            self.audit_tool.run(["-r", "src/", "-ll"])
        except Exception as e:
            msg = f"Security Check (Bandit) Failed: {e}"
            logger.warning(msg)
            self._log_audit_failure([msg])
            return False

        # 4. LLM Audit
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
        Includes Result Analysis and Reporting.
        """
        if self.dry_run:
            logger.info("[DRY-RUN] Generating UAT with Playwright and running pytest...")
            return

        # 1. Generate UAT Code
        uat_path = f"{settings.paths.documents_dir}/CYCLE{self.cycle_id}/UAT.md"
        description = (
            f"Create Playwright tests in tests/e2e/ based on {uat_path}.\n"
            "REQUIREMENTS:\n"
            "- Use `unittest.mock`, `pytest-mock`, or `vcrpy` to mock ALL external connections.\n"
            "- Focus purely on logic and UI behavior verification.\n"
            "- ELIMINATE FLAKINESS: Do not depend on live environments.\n"
            "- Output valid Python code."
        )

        full_prompt = self._construct_prompt(settings.agents.tester, description)

        self.jules_client.start_task(
            prompt=full_prompt,
            session_name=f"Cycle{self.cycle_id}_UAT"
        )

        # 2. Run Tests & Capture Output
        uv_path = shutil.which("uv")
        if not uv_path:
            raise ToolNotFoundError("uv not found")

        cmd = [uv_path, "run", "pytest", "tests/e2e/"]

        success = False
        logs = ""

        try:
            # Capture output instead of using ToolWrapper which might print to stdout
            result = subprocess.run( # noqa: S603
                cmd,
                capture_output=True,
                text=True,
                check=False
            )
            logs = result.stdout + "\n" + result.stderr
            if result.returncode == 0:
                success = True
                logger.info("UAT Tests Passed.")
            else:
                logger.warning("UAT Tests Failed.")

        except Exception as e:
            logs = str(e)
            logger.error(f"UAT Execution Error: {e}")

        # 3. Analyze Results & Generate Report
        self._analyze_uat_results(logs, success)

        if not success:
            self._trigger_fix(f"UAT Tests Failed. Logs:\n{logs[-2000:]}")
            raise Exception("UAT Phase Failed")

    def _analyze_uat_results(self, logs: str, success: bool) -> None:
        """
        Analyzes UAT logs using AI and generates a report.
        """
        logger.info("Analyzing UAT Results...")

        verdict = "PASS" if success else "FAIL"

        user_task = (
            f"Analyze the following pytest logs for UAT (User Acceptance Testing).\n"
            f"Verdict: {verdict}\n\n"
            f"Logs:\n{logs[-10000:]}\n\n" # Send last 10k chars
            "Task:\n"
            "1. Summarize executed tests.\n"
            "2. Provide insights on system behavior against requirements.\n"
            "3. If failed, explain why.\n"
            "4. Output strictly in Markdown format."
        )

        full_prompt = self._construct_prompt(settings.agents.qa_analyst, user_task)

        try:
            # Using Gemini for analysis as it is good at summarization
            response = self.gemini_client.start_task(prompt=full_prompt)

            report_path = self.cycle_dir / "UAT_RESULT.md"
            with open(report_path, "w") as f:
                f.write(f"# UAT Result: {verdict}\n\n")
                f.write(response)

            logger.info(f"UAT Report saved to {report_path}")

        except Exception as e:
            logger.warning(f"Failed to generate UAT Report: {e}")

    def finalize_cycle(self) -> None:
        """
        Phase 4: 自動マージ
        """
        if self.dry_run:
            logger.info("[DRY-RUN] Merging PR via gh CLI...")
        else:
            # gh pr merge
            args = ["pr", "merge", "--squash", "--delete-branch", "--admin"]
            self.gh.run(args)

        if self.auto_next:
            self.prepare_next_cycle()

    def prepare_next_cycle(self) -> None:
        """
        Auto-Next: Scaffolds and starts planning for the next cycle.
        """
        logger.info(f"Auto-Next enabled: Preparing next cycle after CYCLE{self.cycle_id}...")

        # 1. Calculate Next ID
        try:
            current_int = int(self.cycle_id)
            next_id = f"{current_int + 1:02d}"
        except ValueError:
            logger.warning(f"Could not parse cycle ID {self.cycle_id} as int. Skipping Auto-Next.")
            return

        # 2. Scaffold (Reusing logic similar to new-cycle CLI but programmatic)
        next_cycle_dir = self.documents_dir / f"CYCLE{next_id}"
        if next_cycle_dir.exists():
            logger.warning(
                f"Next cycle directory {next_cycle_dir} already exists. Skipping scaffolding."
            )
        else:
            logger.info(f"Scaffolding CYCLE{next_id}...")
            next_cycle_dir.mkdir(parents=True)
            templates_dir = Path(settings.paths.templates) / "cycle"

            # Copy templates
            for item in ["SPEC.md", "UAT.md", "schema.py"]:
                src = templates_dir / item
                dst = next_cycle_dir / item
                if src.exists():
                    shutil.copy(src, dst)
                else:
                    logger.warning(f"Template {src} not found.")

        # 3. Start Planning for Next Cycle
        logger.info(f"Triggering Planning Phase for CYCLE{next_id}...")

        # Create a new orchestrator instance for the next cycle
        # We don't chain auto_next recursively to prevent infinite loops, or we could.
        # Let's set auto_next=False for the next one for safety, or keep it?
        # User said "Continuous Cycle", implying it continues.
        # But infinite loop risk is high. Let's keep it True but user can stop via Ctrl+C.

        # However, calling execute_all() here would recurse.
        # The prompt says "prepare (scaffolding) OR start".
        # And "4. (if possible) ... auto start planning phase".
        # I will instantiate and call ONLY plan_cycle() to set it up.

        next_orchestrator = CycleOrchestrator(
            next_id, dry_run=self.dry_run, auto_next=self.auto_next
        )
        next_orchestrator.plan_cycle()

        logger.info(
            f"CYCLE{next_id} Planning Complete. Please review artifacts in {next_cycle_dir}"
        )
