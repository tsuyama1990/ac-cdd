import asyncio
import difflib
import shutil
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from .config import settings
from .domain_models import AuditResult, CyclePlan, FileCreate, FileOperation, FilePatch, UatAnalysis
from .process_runner import ProcessRunner
from .tools import ToolNotFoundError, ToolWrapper
from .utils import logger


class CycleOrchestrator:
    """
    AC-CDD サイクルの自動化を管理するクラス (Refactored for Pydantic AI).
    """

    def __init__(
        self,
        cycle_id: str,
        dry_run: bool = False,
        auto_next: bool = False,
        auto_approve: bool = False,
        interactive: bool = True,
    ) -> None:
        self.cycle_id = cycle_id
        self.dry_run = dry_run
        self.auto_next = auto_next
        self.auto_approve = auto_approve
        self.interactive = interactive

        # Use paths from config
        self.documents_dir = Path(settings.paths.documents_dir)
        self.contracts_dir = Path(settings.paths.contracts_dir)

        self.cycle_dir = self.documents_dir / f"CYCLE{cycle_id}"
        self.audit_log_path = self.cycle_dir / "AUDIT_LOG.md"

        if not self.cycle_dir.exists():
            raise ValueError(f"Cycle directory {self.cycle_dir} does not exist.")

        self.process_runner = ProcessRunner()

        # Initialize tools
        try:
            self.gh = ToolWrapper(settings.tools.gh_cmd)
            self.audit_tool = ToolWrapper(settings.tools.audit_cmd)  # bandit
            self.uv = ToolWrapper(settings.tools.uv_cmd)
            self.mypy = ToolWrapper(settings.tools.mypy_cmd)
        except ToolNotFoundError as e:
            if not self.dry_run:
                raise
            logger.warning(f"[DRY-RUN] Tool missing: {e}. Proceeding anyway.")

    async def execute_all(
        self, progress_task: object | None = None, progress_obj: object | None = None
    ) -> None:
        """全フェーズを実行"""
        # Save progress context for agents to use if needed (simple hack)
        self._progress_obj = progress_obj
        self._progress_task = progress_task

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
                progress_obj.update(progress_task, description=f"[cyan]{name}...")  # type: ignore
            logger.info(f"Starting Phase: {name}")
            if asyncio.iscoroutinefunction(func):
                await func()
            else:
                func()
            logger.info(f"Completed Phase: {name}")

    async def _run_agent_with_ui(
        self, agent: object, prompt: str, task_name: str, result_type: object = str
    ) -> object:
        """
        Runs an agent with rich UI streaming (Spinner).
        """
        model_name = getattr(agent, "model", "Unknown Model")
        console = Console()

        with console.status(
            f"[bold green]Agent {model_name} is thinking about {task_name}...[/bold green]"
        ):
            # Fallback to standard run for now to ensure stability with structured outputs
            # but print token usage if possible.
            result = await agent.run(prompt, result_type=result_type)  # type: ignore

        # Mock usage display
        usage = getattr(result, "usage", None)
        if usage:
            logger.info(f"Token Usage: {usage}")

        return result

    async def plan_cycle(self) -> None:
        """
        Phase 0: 計画策定 (Planning Phase)
        """
        # Lazy import agents
        from .agents import planner_agent

        if self.dry_run:
            logger.info("[DRY-RUN] Planning Cycle... (Mocking plan generation)")
            return

        planning_prompt_path = Path(settings.paths.templates) / "CYCLE_PLANNING_PROMPT.md"
        if not planning_prompt_path.exists():
            raise FileNotFoundError(f"{planning_prompt_path} not found.")

        base_prompt = planning_prompt_path.read_text(encoding="utf-8")
        user_task = (
            f"{base_prompt}\n\nFocus specifically on generating artifacts for CYCLE{self.cycle_id}."
        )

        logger.info(f"Generating Plan for CYCLE{self.cycle_id}...")

        # Run Pydantic AI Agent (mocked for now for streaming replacement later)
        result = await self._run_agent_with_ui(
            planner_agent, user_task, "Planning Phase", result_type=CyclePlan
        )
        plan: CyclePlan = result.output  # type: ignore

        self._save_plan_artifacts(plan)

    def _save_plan_artifacts(self, plan: CyclePlan) -> None:
        """Saves the CyclePlan artifacts to disk."""
        self.cycle_dir.mkdir(parents=True, exist_ok=True)

        # Save artifacts
        for artifact in [plan.spec_file, plan.schema_file, plan.uat_file]:
            # The prompt asks for dev_documents/CYCLE{id}/filename,
            # so we respect that but ensure target dir
            p = Path(artifact.path)
            target_path = self.cycle_dir / p.name
            target_path.write_text(artifact.content, encoding="utf-8")
            logger.info(f"Saved {target_path}")

        # Save thought process
        (self.cycle_dir / "PLAN_THOUGHTS.md").write_text(plan.thought_process, encoding="utf-8")

    def align_contracts(self) -> None:
        """
        Phase 3.1: 契約の整合確認とマージ (Sync)
        """
        source_schema = self.cycle_dir / "schema.py"
        target_schema = self.contracts_dir / f"schema_cycle{self.cycle_id}.py"

        if not source_schema.exists():
            raise FileNotFoundError(f"{source_schema} not found.")

        if self.dry_run:
            logger.info(f"[DRY-RUN] Would copy {source_schema} to {target_schema}")
            return

        self.contracts_dir.mkdir(parents=True, exist_ok=True)

        if target_schema.exists():
            backup = target_schema.with_suffix(".py.bak")
            shutil.copy(target_schema, backup)
            logger.info(f"Backed up existing schema to {backup}")

        shutil.copy(source_schema, target_schema)

        init_file = self.contracts_dir / "__init__.py"
        import_line = f"from .schema_cycle{self.cycle_id} import *"

        if init_file.exists():
            content = init_file.read_text(encoding="utf-8")
            if import_line not in content:
                with open(init_file, "a", encoding="utf-8") as f:
                    f.write(f"\n{import_line}\n")
        else:
            with open(init_file, "w", encoding="utf-8") as f:
                f.write(f"{import_line}\n")

    async def generate_property_tests(self) -> None:
        """
        Phase 3.2: プロパティベーステストの生成
        """
        # Lazy import agents
        from .agents import coder_agent

        user_task = settings.prompts.property_test_template.format(cycle_id=self.cycle_id)

        # Add instruction to return correct path
        target_path_str = f"tests/property/test_cycle{self.cycle_id}.py"
        user_task += f"\n\nReturn the code in a file named '{target_path_str}'."

        if self.dry_run:
            logger.info(f"[DRY-RUN] generating property tests with prompt: {user_task}")
            return

        prompt_with_role = f"You are a QA Engineer.\n{user_task}"

        result = await self._run_agent_with_ui(
            coder_agent,
            prompt_with_role,
            "Generating Property Tests",
            result_type=list[FileOperation],
        )
        # Handle structured output
        self._apply_agent_changes(result.output)  # type: ignore

    async def run_implementation_loop(self) -> None:
        """
        Phase 3.3 & 3.4: 実装・CI・監査ループ
        """
        logger.info("Starting Implementation Phase")

        max_plan_retries = 3
        plan_attempt = 0

        while plan_attempt < max_plan_retries:
            plan_attempt += 1
            if plan_attempt > 1:
                logger.warning(
                    f"Self-Healing: Re-planning cycle ({plan_attempt}/{max_plan_retries})..."
                )
                await self._replan_cycle(
                    "Implementation loop failed repeatedly. "
                    "Please review SPEC/Schema/UAT and simplify or fix logic."
                )

            # 1. Initial Implementation
            await self._trigger_implementation()

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
                passed, logs = await self._run_tests()

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
                    await self._trigger_fix(fix_prompt)
                    continue

                # 2.2 Audit
                logger.info("Tests Passed. Proceeding to Strict Audit...")
                audit_result = await self.run_strict_audit()

                if audit_result is True:
                    logger.info("Audit Passed (Clean)!")
                    loop_success = True
                    break
                else:
                    logger.warning("Audit Failed. Triggering fix...")
                    await self._trigger_fix(f"Audit failed. See {self.audit_log_path} for details.")
                    continue

            if loop_success:
                return

            logger.error("Implementation Loop Failed.")

        raise Exception(
            f"Max retries reached in Self-Healing Plan Loop ({max_plan_retries} attempts)."
        )

    async def _replan_cycle(self, feedback: str) -> None:
        """
        Re-runs planning with feedback.
        """
        # Lazy import agents
        from .agents import planner_agent

        logger.info("Triggering Re-Planning with feedback...")

        planning_prompt_path = Path(settings.paths.templates) / "CYCLE_PLANNING_PROMPT.md"
        base_prompt = ""
        if planning_prompt_path.exists():
            base_prompt = planning_prompt_path.read_text(encoding="utf-8")

        user_task = (
            f"{base_prompt}\n\n"
            f"CRITICAL UPDATE: The previous plan failed during implementation.\n"
            f"Feedback: {feedback}\n\n"
            f"Please revise the SPEC, Schema, and UAT for CYCLE{self.cycle_id}."
        )

        result = await self._run_agent_with_ui(
            planner_agent, user_task, "Re-Planning Cycle", result_type=CyclePlan
        )
        self._save_plan_artifacts(result.output)  # type: ignore

    async def _trigger_implementation(self) -> None:
        # Lazy import agents
        from .agents import coder_agent

        spec_path = f"{settings.paths.documents_dir}/CYCLE{self.cycle_id}/SPEC.md"
        description = (
            f"Implement requirements in {spec_path} "
            f"following schema in {settings.paths.contracts_dir}/"
        )

        if self.dry_run:
            logger.info(f"[DRY-RUN] Implementing feature: {description}")
            return

        result = await self._run_agent_with_ui(
            coder_agent, description, "Implementing Features", result_type=list[FileOperation]
        )
        self._apply_agent_changes(result.output)  # type: ignore

    def _fuzzy_find(self, content: str, block: str) -> tuple[int, int]:
        """
        Finds the block in content with fuzzy matching (ignoring whitespace).
        Returns (start_index, end_index) or (-1, -1) if not found.
        """
        # 1. Exact match attempt
        idx = content.find(block)
        if idx != -1:
            return idx, idx + len(block)

        # 2. Normalized match attempt
        # We will split into lines and match sequences of stripped lines
        content_lines = content.splitlines(keepends=True)
        block_lines = block.splitlines(keepends=True)

        norm_content = [line.strip() for line in content_lines]
        norm_block = [line.strip() for line in block_lines]

        # Remove empty lines from search block for robustness?
        # Requirement says "exact block ... including all whitespace"
        # but fuzzy fallback implies looseness.
        # Let's match stripped non-empty lines sequence.

        # Simple sliding window on lines
        n_block = len(norm_block)
        n_content = len(norm_content)

        if n_block == 0:
            return -1, -1

        for i in range(n_content - n_block + 1):
            if norm_content[i : i + n_block] == norm_block:
                # Found match in lines i to i + n_block
                # Calculate char indices
                start_char = sum(len(line) for line in content_lines[:i])
                end_char = sum(len(line) for line in content_lines[: i + n_block])
                return start_char, end_char

        return -1, -1

    def _apply_agent_changes(self, changes: list[FileOperation]) -> None:
        """
        Applies a list of FileOperation objects to the file system with interactive review.
        """
        console = Console()
        is_tty = sys.stdout.isatty()

        for op in changes:
            p = Path(op.path)
            new_content = ""
            diff_text = ""

            # Prepare content based on operation type
            if isinstance(op, FileCreate):
                if p.exists():
                    # Although 'create', if it exists we might be overwriting or it's a mistake.
                    # Let's treat it as overwrite for 'FileCreate'.
                    # But usually agents should use Patch.
                    # But if the file is truly new, p.read_text fails.
                    old_content_lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
                else:
                    old_content_lines = []

                new_content = op.content
                new_content_lines = new_content.splitlines(keepends=True)

                diff = list(
                    difflib.unified_diff(
                        old_content_lines,
                        new_content_lines,
                        fromfile=str(p),
                        tofile=str(p),
                        lineterm="",
                    )
                )
                diff_text = "".join(diff)
                if not diff_text and p.exists():
                    logger.info(f"No changes for {p}")
                    continue

            elif isinstance(op, FilePatch):
                if not p.exists():
                    logger.error(f"Cannot patch non-existent file: {p}")
                    continue

                original_content = p.read_text(encoding="utf-8")

                # Use fuzzy finder
                start_idx, end_idx = self._fuzzy_find(original_content, op.search_block)

                if start_idx == -1:
                    logger.error(
                        f"Patch failed for {p}: search_block not found in file "
                        "(Exact match required)."
                    )
                    # Optionally we could try fuzzy match or just fail.
                    # Requirement says "fail error log and skip".
                    continue

                # Replace content
                new_content = (
                    original_content[:start_idx] + op.replace_block + original_content[end_idx:]
                )

                # Generate Diff for the whole file
                old_content_lines = original_content.splitlines(keepends=True)
                new_content_lines = new_content.splitlines(keepends=True)

                diff = list(
                    difflib.unified_diff(
                        old_content_lines,
                        new_content_lines,
                        fromfile=str(p),
                        tofile=str(p),
                        lineterm="",
                    )
                )
                diff_text = "".join(diff)

            # Interactive Review
            if self.interactive and is_tty and not self.auto_approve and not self.dry_run:
                console.print(
                    Panel(f"Proposed changes for [bold]{p}[/bold] ({op.operation})", style="blue")
                )
                if diff_text:
                    syntax = Syntax(diff_text, "diff", theme="monokai", line_numbers=True)
                    console.print(syntax)
                else:
                    console.print(
                        f"[yellow]New File (Full Content):[/yellow]\n{new_content[:500]}..."
                    )

                should_apply = typer.confirm(f"Apply changes to {p}?", default=True)
                if not should_apply:
                    logger.warning(f"Skipped changes for {p}")
                    continue

            # Apply
            if not self.dry_run:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(new_content, encoding="utf-8")
                logger.info(f"Applied {op.operation} to {p}")

    async def _trigger_fix(self, instructions: str) -> None:
        # Lazy import agents
        from .agents import coder_agent

        if self.dry_run:
            logger.info(f"[DRY-RUN] Fixing code: {instructions}")
            return

        result = await self._run_agent_with_ui(
            coder_agent, instructions, "Fixing Code", result_type=list[FileOperation]
        )
        self._apply_agent_changes(result.output)  # type: ignore

    async def _run_tests(self) -> tuple[bool, str]:
        """
        Runs tests locally using uv run pytest and captures logs.
        """
        if self.dry_run:
            return True, ""

        uv_path = shutil.which("uv")
        if not uv_path:
            raise ToolNotFoundError("uv not found")

        cmd = [uv_path, "run", "pytest"]
        try:
            # Use ProcessRunner to run tests
            stdout, stderr, returncode = await self.process_runner.run_command(cmd, check=False)
            logs = stdout + "\n" + stderr

            if returncode == 0:
                return True, ""

            if len(logs) > 2000:
                logs = "...(truncated)...\n" + logs[-2000:]
            return False, logs

        except Exception as e:
            logger.error(f"Failed to run tests: {e}")
            return False, str(e)

    async def run_strict_audit(self) -> bool:
        """
        Phase 3.4: 世界一厳格な監査
        """
        # Lazy import agents
        from .agents import auditor_agent

        if self.dry_run:
            logger.info("[DRY-RUN] Mocking audit approval")
            return True

        logger.info("Running Static Analysis (Ruff, Mypy, Bandit)...")

        # 1. Ruff
        ruff_path = shutil.which("ruff")
        if ruff_path:
            # check --fix
            await self.process_runner.run_command(
                [ruff_path, "check", "--fix", "src/", "tests/"], check=False
            )
            # format
            await self.process_runner.run_command(
                [ruff_path, "format", "src/", "tests/"], check=False
            )

        # 2. Mypy
        try:
            await self.mypy.run(["src/"])
        except Exception as e:
            msg = f"Type Check (Mypy) Failed: {e}"
            logger.warning(msg)
            self._log_audit_failure([msg])
            return False

        # 3. Bandit
        try:
            await self.audit_tool.run(["-r", "src/", "-ll"])
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
                content = Path(fpath).read_text(encoding="utf-8")
                files_content += f"\n\n=== File: {fpath} ===\n{content}"
            except Exception as e:
                logger.warning(f"Failed to read {fpath}: {e}")

        user_task = (
            f"Audit the following code files:\n{files_content}\n\n"
            "Evaluate if the code follows Pydantic contracts, "
            "security best practices, and clean code principles."
        )

        # Run Auditor Agent
        result = await self._run_agent_with_ui(
            auditor_agent, user_task, "Auditing Code", result_type=AuditResult
        )
        audit_result: AuditResult = result.output  # type: ignore

        if audit_result.is_approved:
            return True
        else:
            self._log_audit_failure(audit_result.critical_issues + audit_result.suggestions)
            return False

    def _get_filtered_files(self, directory: str) -> list[str]:
        import fnmatch

        ignored_patterns = {"__pycache__", ".git", ".env", ".DS_Store", "*.pyc"}

        auditignore_path = Path(".auditignore")
        if auditignore_path.exists():
            try:
                lines = auditignore_path.read_text(encoding="utf-8").splitlines()
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
                is_ignored = False
                for pattern in ignored_patterns:
                    if fnmatch.fnmatch(p.name, pattern) or fnmatch.fnmatch(str(p), pattern):
                        is_ignored = True
                        break
                    if pattern in str(p):  # strict substring check
                        is_ignored = True
                        break

                if not is_ignored:
                    files.append(str(p))
        return files

    def _log_audit_failure(self, comments: list[str]) -> None:
        import time

        with open(self.audit_log_path, "a", encoding="utf-8") as f:
            f.write(f"\n## Audit Failed at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            for c in comments:
                f.write(f"- {c}\n")

    async def run_uat_phase(self) -> None:
        """
        Phase 3.5: UATの生成と実行
        """
        # Lazy import agents
        from .agents import coder_agent

        if self.dry_run:
            logger.info("[DRY-RUN] UAT Phase")
            return

        # 1. Generate UAT Code
        uat_path = f"{settings.paths.documents_dir}/CYCLE{self.cycle_id}/UAT.md"
        description = (
            f"Create Playwright tests in tests/e2e/ based on {uat_path}.\n"
            "REQUIREMENTS:\n"
            "- Use `unittest.mock`, `pytest-mock`, or `vcrpy` "
            "to mock ALL external connections.\n"
            "- Focus purely on logic and UI behavior verification.\n"
            "- Output valid Python code."
        )

        # coder_agent is typed to return list[FileChange]
        result = await self._run_agent_with_ui(
            coder_agent, description, "Generating UAT", result_type=list[FileOperation]
        )
        self._apply_agent_changes(result.output)  # type: ignore

        # 2. Run Tests
        uv_path = shutil.which("uv")
        if not uv_path:
            raise ToolNotFoundError("uv not found")

        cmd = [uv_path, "run", "pytest", "tests/e2e/"]

        success = False
        logs = ""

        try:
            # Use ProcessRunner to run UAT tests
            stdout, stderr, returncode = await self.process_runner.run_command(cmd, check=False)
            logs = stdout + "\n" + stderr

            if returncode == 0:
                success = True
                logger.info("UAT Tests Passed.")
            else:
                logger.warning("UAT Tests Failed.")
        except Exception as e:
            logs = str(e)
            logger.error(f"UAT Execution Error: {e}")

        # 3. Analyze Results
        await self._analyze_uat_results(logs, success)

        if not success:
            await self._trigger_fix(f"UAT Tests Failed. Logs:\n{logs[-2000:]}")
            raise Exception("UAT Phase Failed")

    async def _analyze_uat_results(self, logs: str, success: bool) -> None:
        # Lazy import agents
        from .agents import qa_analyst_agent

        logger.info("Analyzing UAT Results...")
        verdict = "PASS" if success else "FAIL"

        user_task = (
            f"Analyze the following pytest logs for UAT.\n"
            f"Verdict: {verdict}\n\n"
            f"Logs:\n{logs[-10000:]}\n\n"
        )

        result = await self._run_agent_with_ui(
            qa_analyst_agent, user_task, "Analyzing UAT Results", result_type=UatAnalysis
        )
        analysis: UatAnalysis = result.output  # type: ignore

        report_path = self.cycle_dir / "UAT_RESULT.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"# UAT Result: {analysis.verdict}\n\n")
            f.write(f"## Summary\n{analysis.summary}\n\n")
            f.write(f"## Analysis\n{analysis.behavior_analysis}\n")

        logger.info(f"UAT Report saved to {report_path}")

    async def finalize_cycle(self) -> None:
        """
        Phase 4: 自動マージ
        """
        if self.dry_run:
            logger.info("[DRY-RUN] Merging PR via gh CLI...")
        else:
            args = ["pr", "merge", "--squash", "--delete-branch", "--admin"]
            await self.gh.run(args)

        if self.auto_next:
            # Note: prepare_next_cycle should be scheduled or handled by caller if async
            # But currently finalize_cycle is synchronous in loop.
            pass

    async def prepare_next_cycle(self) -> None:
        logger.info(f"Auto-Next enabled: Preparing next cycle after CYCLE{self.cycle_id}...")
        try:
            current_int = int(self.cycle_id)
            next_id = f"{current_int + 1:02d}"
        except ValueError:
            return

        next_cycle_dir = self.documents_dir / f"CYCLE{next_id}"
        if not next_cycle_dir.exists():
            next_cycle_dir.mkdir(parents=True)
            templates_dir = Path(settings.paths.templates) / "cycle"
            for item in ["SPEC.md", "UAT.md", "schema.py"]:
                src = templates_dir / item
                dst = next_cycle_dir / item
                if src.exists():
                    shutil.copy(src, dst)

        next_orchestrator = CycleOrchestrator(
            next_id, dry_run=self.dry_run, auto_next=self.auto_next, interactive=self.interactive
        )
        await next_orchestrator.plan_cycle()
