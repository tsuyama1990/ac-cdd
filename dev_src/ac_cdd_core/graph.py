import json
from pathlib import Path
from typing import Any, Literal

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from .config import settings
from .domain_models import AuditResult
from .sandbox import SandboxRunner
from .service_container import ServiceContainer
from .state import CycleState
from .utils import logger

MAX_AUDIT_RETRIES = 2


def _to_relative_path(p: Path) -> str:
    """Helper to convert path to relative path from CWD."""
    try:
        return str(p.relative_to(Path.cwd()))
    except ValueError:
        return str(p)


class GraphBuilder:
    def __init__(self, services: ServiceContainer):
        self.services = services
        self.jules_client = services.jules
        self.llm_reviewer = services.reviewer
        self.git = services.git
        # Shared sandbox for the lifecycle of the graph execution (approx. one cycle)
        self.sandbox_runner: SandboxRunner | None = None

    async def _get_shared_sandbox(self) -> SandboxRunner:
        """
        Get or initialize the shared sandbox runner.
        Ensures dependencies are installed once.
        """
        if self.sandbox_runner:
            return self.sandbox_runner

        logger.info("Initializing Shared Sandbox...")

        # Use template ID from settings if available (e.g., prebuilt image)
        # self.sandbox_runner = SandboxRunner(sandbox_id=None, cwd=settings.sandbox.cwd)
        # Note: SandboxRunner init doesn't create the sandbox immediately, run_command does.
        # But we want to ensure deps are installed now.
        self.sandbox_runner = SandboxRunner()

        # We trigger a simple command to ensure connection/creation
        await self.sandbox_runner.run_command(["echo", "Sandbox Ready"], check=False)

        # Check if dependencies (ruff) are installed
        _, _, ruff_code = await self.sandbox_runner.run_command(["ruff", "--version"], check=False)

        if ruff_code != 0:
            logger.info("Installing dependencies (ruff)...")
            await self.sandbox_runner.run_command(["pip", "install", "ruff"])

        # Init Git Repo for tracking (still useful for some ops, but not for Aider anymore)
        await self.sandbox_runner.run_command(["git", "init"], check=False)
        await self.sandbox_runner.run_command(
            ["git", "config", "user.email", "bot@ac-cdd.com"], check=False
        )
        await self.sandbox_runner.run_command(
            ["git", "config", "user.name", "AC-CDD Bot"], check=False
        )
        await self.sandbox_runner.run_command(["git", "add", "."], check=False)
        await self.sandbox_runner.run_command(["git", "commit", "-m", "init"], check=False)

        return self.sandbox_runner

    async def cleanup(self) -> None:
        """Explicitly close the sandbox runner with retry logic."""
        if self.sandbox_runner:
            logger.info("Cleaning up shared sandbox...")

            # Retry logic with exponential backoff
            max_retries = 3
            retry_delay = 1  # seconds

            for attempt in range(max_retries):
                try:
                    # Add timeout to prevent hanging
                    import asyncio

                    await asyncio.wait_for(
                        self.sandbox_runner.close(),
                        timeout=30.0,  # 30 second timeout
                    )
                    logger.info("Sandbox cleanup successful.")
                    self.sandbox_runner = None
                    return
                except TimeoutError:
                    logger.warning(
                        f"Sandbox cleanup timed out (attempt {attempt + 1}/{max_retries})"
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                except Exception as e:
                    logger.warning(
                        f"Sandbox cleanup failed (attempt {attempt + 1}/{max_retries}): {e}"
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2

            # If all retries failed, log error but don't crash
            logger.error(
                "Failed to cleanup sandbox after multiple retries. "
                "The sandbox may still be running. Check your E2B dashboard."
            )
            self.sandbox_runner = None

    # --- Architect Graph Nodes ---

    async def init_branch_node(self, state: CycleState) -> dict[str, Any]:
        """Setup Integration Branch and Architecture Branch for Session."""
        logger.info("Phase: Init Session & Branch (Architect)")

        # Generate or use existing session ID
        session_id = state.session_id or settings.current_session_id

        # Create integration branch from main
        integration_branch = await self.git.create_integration_branch(
            session_id=session_id, prefix=settings.session.integration_branch_prefix
        )

        # Simplified: We run DIRECTLY on the integration branch.
        # Jules will create its own ephemeral agent-branch from here.
        active_branch = integration_branch

        return {
            "current_phase": "branch_ready",
            "active_branch": active_branch,
            "session_id": session_id,
            "integration_branch": integration_branch,
        }

    async def architect_session_node(self, state: CycleState) -> dict[str, Any]:
        """Architect Session: Generates all specs and plans."""
        logger.info("Phase: Architect Session")

        # Get Shared Sandbox (Persistent)
        runner = await self._get_shared_sandbox()

        # Prioritize custom instruction in dev_documents
        custom_instruction_path = Path(settings.paths.documents_dir) / "ARCHITECT_INSTRUCTION.md"
        if custom_instruction_path.exists():
            instruction_path = custom_instruction_path
            logger.info(f"Using custom Architect instruction from: {instruction_path}")
        else:
            instruction_path = Path(settings.paths.templates) / "ARCHITECT_INSTRUCTION.md"
            logger.info(f"Using default Architect instruction from: {instruction_path}")

        spec_path = Path(settings.paths.documents_dir) / "ALL_SPEC.md"
        signal_file = Path(settings.paths.documents_dir) / "plan_status.json"

        if not spec_path.exists():
            return {"error": "ALL_SPEC.md not found.", "current_phase": "architect_failed"}

        # Input: user requirements (ALL_SPEC.md)
        cwd = Path.cwd()

        def _to_rel(p: Path) -> str:
            try:
                return str(p.relative_to(cwd))
            except ValueError:
                return str(p)

        files = [_to_rel(spec_path)]

        # System Instruction: ARCHITECT_INSTRUCTION.md
        instruction = instruction_path.read_text(encoding="utf-8")

        try:
            # Pass runner for remote execution
            result = await self.jules_client.run_session(
                session_id="architect-session",
                prompt=instruction,
                files=files,
                completion_signal_file=signal_file,
                runner=runner,
                # target_branch=state.integration_branch, # REMOVED
            )

            # Since Jules now returns a PR URL (or status dict) instead of file content directly,
            # we log the result and mark as complete.
            # Note: The actual 'cycles' plan is inside the PR content.
            # For the local flow to continue perfectly, we might need to parse the PR desc or file.
            # For now, we assume the user will review the PR.
            pr_url = result.get("pr_url")
            if pr_url:
                logger.info(f"Architect PR created: {pr_url}")

                # --- Auto-Merge Logic to Integration Branch ---
                try:
                    logger.info(
                        f"Attempting to auto-merge PR to integration branch: "
                        f"{state.integration_branch}..."
                    )
                    await self.git.merge_to_integration(pr_url, state.integration_branch)
                    logger.info("PR merged to integration branch successfully.")

                    # Reload plan status from the now-synced local file
                    if signal_file.exists():
                        try:
                            plan_data = json.loads(signal_file.read_text(encoding="utf-8"))
                            # Update result to include the planned cycles
                            result["cycles"] = plan_data.get("cycles", [])
                        except Exception as e:
                            logger.warning(f"Failed to parse plan_status.json after merge: {e}")

                except Exception:
                    # CRITICAL: Merge failure should stop the workflow
                    from ac_cdd_core.error_messages import RecoveryMessages

                    error_msg = RecoveryMessages.architect_merge_failed(pr_url)
                    logger.error(error_msg)
                    return {"error": error_msg, "current_phase": "architect_merge_failed"}
                # ------------------------

            else:
                msg = (
                    "Jules session finished but NO Pull Request was created.\n"
                    "Possible causes:\n"
                    "1. The prompt instructed to output text instead of creating files.\n"
                    "2. The agent decided no changes were necessary.\n"
                    "Check the GCP Console for the session logs."
                )
                logger.error(msg)
                return {"error": "No PR created by Jules", "current_phase": "architect_failed"}

        except Exception as e:
            logger.error(f"Architect session failed: {e}")
            return {"error": str(e), "current_phase": "architect_failed"}

        return {
            "current_phase": "architect_complete",
            "planned_cycles": result.get("cycles", []),
            "error": None,
        }

    async def commit_architect_node(self, state: CycleState) -> dict[str, Any]:
        """Commit architecture artifacts."""
        await self.git.commit_changes("docs: generate system architecture and specs")
        return {"current_phase": "complete"}

    # --- Coder Graph Nodes ---

    async def checkout_branch_node(self, state: CycleState) -> dict[str, Any]:
        """Checkout or Create Branch for Cycle from Integration Branch."""
        cycle_id = state.cycle_id
        logger.info(f"Phase: Checkout Branch (Cycle {cycle_id})")

        # Ensure we have session context
        if not state.session_id or not state.integration_branch:
            raise ValueError("Session not initialized. Run gen-cycles first to create a session.")

        # Simplified: We use the integration branch directly.
        # We ensure we are on it.
        await self.git.checkout_branch(state.integration_branch)
        active_branch = state.integration_branch

        return {
            "current_phase": "branch_ready",
            "active_branch": active_branch,
            "iteration_count": state.iteration_count,
            "current_auditor_index": 1,
            "current_auditor_review_count": 1,
        }

    async def coder_session_node(self, state: CycleState) -> dict[str, Any]:
        """Coder Session: Implement and Test Creation (Jules or Aider)."""
        cycle_id = state.cycle_id
        iteration_count = state.iteration_count + 1

        logger.info(
            f"Phase: Coder Session (Cycle {cycle_id}) - "
            f"Iteration {iteration_count}/{settings.MAX_ITERATIONS}"
        )

        template_path = Path(settings.paths.templates) / "CODER_INSTRUCTION.md"
        cycle_dir = Path(settings.paths.documents_dir) / f"CYCLE{cycle_id}"
        spec_file = cycle_dir / "SPEC.md"
        uat_file = cycle_dir / "UAT.md"
        arch_file = Path(settings.paths.documents_dir) / "SYSTEM_ARCHITECTURE.md"

        cwd = Path.cwd()

        def _to_rel(p: Path) -> str:
            try:
                return str(p.relative_to(cwd))
            except ValueError:
                return str(p)

        # RESUME BYPASS CHECK
        if state.resume_mode and state.pr_url:
            logger.info(f"RESUMING Session: {state.jules_session_name}")
            pr_url = state.pr_url

            # Ensure Sandbox is ready even if skipping Jules (for Syntax Check later)
            runner = await self._get_shared_sandbox()

            # Checkout the PR
            logger.info(f"Checking out PR: {pr_url}...")
            await self.git.checkout_pr(pr_url)

            # Sync with main to ensure latest system fixes are applied
            try:
                current_branch = await self.git.get_current_branch()
                if current_branch != "main":
                    logger.info(f"Syncing main into {current_branch}...")
                    # We use merge_branch which checks out target again, but that's fine
                    await self.git.merge_branch(current_branch, "main")
            except Exception as e:
                logger.warning(f"Failed to sync main into feature branch: {e}")

            return {
                "coder_report": {"pr_url": pr_url, "status": "resumed"},
                "current_phase": "coder_complete_resumed",
                "iteration_count": iteration_count,
                "jules_session_name": state.jules_session_name,
                "pr_url": pr_url,
                "resume_mode": False,
                # FIX: Preserve committee state
                "current_auditor_index": state.current_auditor_index,
                "current_auditor_review_count": state.current_auditor_review_count,
            }

        # Determine if this is Initial Creation (Jules) or Fix Loop (Aider)
        if iteration_count > 1 and state.jules_session_name:
            # --- FIX LOOP (Jules Reuse) ---
            logger.info(
                f"Mode: Jules Fixer (Refinement/Repair) - "
                f"Resuming Session {state.jules_session_name}"
            )
            audit_feedback = state.audit_feedback

            # Get Shared Sandbox (Persistent)
            runner = await self._get_shared_sandbox()

            # Instruction
            if audit_feedback:
                feedback_text = "\n".join(f"- {issue}" for issue in audit_feedback)
                instruction = (
                    f"The previous implementation failed the audit.\n"
                    f"Please fix the following issues strictly:\n\n{feedback_text}\n\n"
                    f"Update the code and the PR."
                )
            else:
                instruction = (
                    "The previous audit passed contextually, but we are doing another iteration.\n"
                    "Please review and optimize the code further."
                )

            try:
                # Continue Jules Session
                logger.info(
                    f"Sending Audit Feedback to Jules ({len(instruction)} chars): "
                    f"{instruction[:200]}..."
                )
                result = await self.jules_client.continue_session(
                    session_name=state.jules_session_name, prompt=instruction
                )

                pr_url = result.get("pr_url")
                if pr_url:
                    logger.info(f"Jules updated PR: {pr_url}")
                    # Switch to the PR branch to test the changes
                    await self.git.checkout_pr(pr_url)

                    # Advance committee state after fix
                    next_review_count = state.current_auditor_review_count + 1
                    next_auditor_idx = state.current_auditor_index

                    # If current auditor finished all reviews, move to next auditor
                    if next_review_count > settings.REVIEWS_PER_AUDITOR:
                        next_review_count = 1
                        next_auditor_idx += 1

                    return {
                        "coder_report": result,
                        "current_phase": "coder_complete",
                        "iteration_count": iteration_count,
                        # maintain session info
                        "jules_session_name": state["jules_session_name"],
                        "pr_url": pr_url,
                        # advance committee state
                        "current_auditor_index": next_auditor_idx,
                        "current_auditor_review_count": next_review_count,
                    }
                else:
                    return {
                        "error": "Jules finished but lost track of PR.",
                        "current_phase": "coder_failed",
                        # FIX: Preserve committee state for potential resume
                        "current_auditor_index": state.current_auditor_index,
                        "current_auditor_review_count": state.current_auditor_review_count,
                        "jules_session_name": state.jules_session_name,
                    }

            except Exception as e:
                return {
                    "error": str(e),
                    "current_phase": "coder_failed",
                    # FIX: Preserve committee state
                    "current_auditor_index": state.current_auditor_index,
                    "current_auditor_review_count": state.current_auditor_review_count,
                    "jules_session_name": state.jules_session_name,
                }

        else:
            # --- INITIAL CREATION (Jules New Session) ---
            logger.info("Mode: Jules Creator (Initial Impl)")

            # Get Shared Sandbox
            runner = await self._get_shared_sandbox()

            base_instruction = template_path.read_text(encoding="utf-8")
            instruction = base_instruction.replace("{{cycle_id}}", cycle_id)

            files = [_to_rel(template_path), _to_rel(arch_file)]
            if spec_file.exists():
                files.append(_to_rel(spec_file))
            if uat_file.exists():
                files.append(_to_rel(uat_file))

            signal_file = cycle_dir / "session_report.json"

            try:
                # Execute Remote Jules
                result = await self.jules_client.run_session(
                    session_id=f"coder-{cycle_id}-iter{iteration_count}",
                    prompt=instruction,
                    files=files,
                    completion_signal_file=signal_file,
                    runner=runner,
                    # target_branch=state.integration_branch, # REMOVED
                )

                pr_url = result.get("pr_url")
                session_name = result.get("session_name")

                if pr_url:
                    logger.info(f"Coder PR created: {pr_url}")

                    # Switch to the PR branch to test the changes
                    # DO NOT MERGE YET (as per user request)
                    await self.git.checkout_pr(pr_url)

                    return {
                        "coder_report": result,
                        "current_phase": "coder_complete",
                        "iteration_count": iteration_count,
                        "jules_session_name": session_name,
                        "pr_url": pr_url,
                        # FIX: Preserve committee state
                        "current_auditor_index": state.current_auditor_index,
                        "current_auditor_review_count": state.current_auditor_review_count,
                    }
                else:
                    msg = (
                        "Jules session finished but NO Pull Request was created.\n"
                        "Possible causes:\n"
                        "1. The prompt instructed to output text instead of creating files.\n"
                        "2. The agent decided no changes were necessary.\n"
                        "Check the GCP Console for the session logs."
                    )
                    logger.error(msg)
                    return {
                        "error": "No PR created by Jules",
                        "current_phase": "coder_failed",
                        # FIX: Preserve committee state
                        "current_auditor_index": state.current_auditor_index,
                        "current_auditor_review_count": state.current_auditor_review_count,
                    }
            except Exception as e:
                return {
                    "error": str(e),
                    "current_phase": "coder_failed",
                    # FIX: Preserve committee state
                    "current_auditor_index": state.current_auditor_index,
                    "current_auditor_review_count": state.current_auditor_review_count,
                }

    async def syntax_check_node(self, state: CycleState) -> dict[str, Any]:
        """Run syntax check and linting (Static Analysis) instead of heavy tests."""
        logger.info("Phase: Syntax Check & Linting (Sandbox)")

        try:
            runner = await self._get_shared_sandbox()

            # Step 1: Syntax Check (compileall)
            cmd_syntax = ["python3", "-m", "compileall", "-q", "."]
            stdout_s, stderr_s, code_s = await runner.run_command(cmd_syntax, check=False)

            if code_s != 0:
                logger.error("Syntax Check Failed")
                return {
                    "active_branch": state.active_branch,  # Keep context
                    "audit_feedback": [f"Syntax Error:\nSTDOUT: {stdout_s}\nSTDERR: {stderr_s}"],
                    "error": "Syntax Check Failed. Please fix syntax errors.",
                }

            # Step 2: Linting (Ruff)
            cmd_lint = ["ruff", "check", "."]
            stdout_l, stderr_l, code_l = await runner.run_command(cmd_lint, check=False)

            if code_l != 0:
                # Linting failed - pass as feedback to Coder (via Auditor loop or direct)
                # We return 'error' to stop? No, we want to feed back.
                # But current logic stops on 'error'.
                # Let's treat it as a failure that triggers feedback loop via Auditor
                # For now, treat as 'test_logs' equivalent so it passes to Auditor who REJECTS it.
                logs = f"Syntax Check: PASS\nLinting Failed:\n{stdout_l}\n{stderr_l}"
                return {
                    "test_logs": logs,
                    "test_exit_code": code_l,
                    "current_phase": "syntax_check_failed",
                }

            logs = "Syntax Check: PASS\nLinting: PASS"
            return {"test_logs": logs, "test_exit_code": 0, "current_phase": "syntax_check_passed"}

        except Exception as e:
            logger.error(f"Sandbox execution failed: {e}")
            return {
                "test_logs": f"Execution Failed: {e}",
                "test_exit_code": -1,
                "current_phase": "syntax_check_system_error",
            }

    async def auditor_node(self, state: CycleState) -> dict[str, Any]:
        """Strict Auditor Node (Direct LLM Review)."""

        # Get committee state (Pydantic provides defaults)
        auditor_idx = state.current_auditor_index
        review_count = state.current_auditor_review_count
        iteration_count = state.iteration_count

        logger.info(
            f"Phase: Auditor #{auditor_idx} - Review {review_count}/{settings.REVIEWS_PER_AUDITOR} "
            f"(Iteration {iteration_count})"
        )

        # Get Shared Sandbox (Persistent)
        _ = await self._get_shared_sandbox()

        # 1. Gather Context (Smart Audit: Changed Files + Configs)
        try:
            # Detect changed files (PR content)
            changed_files = await self.git.get_changed_files()
            logger.info(f"Smart Audit: Detected {len(changed_files)} changed files.")
        except Exception as e:
            logger.warning(f"Failed to detect changed files: {e}. Falling back to full scan.")
            changed_files = []

        # Helper to check extension
        def is_py(f: str) -> bool:
            return f.endswith(".py")

        files_to_audit = set()

        # Always include root Configs
        root_configs = ["ac_cdd_config.py", "pyproject.toml"]
        for rc in root_configs:
            if Path(rc).exists():
                files_to_audit.add(rc)

        if changed_files:
            # Smart Mode: Only changed files + Configs
            for f in changed_files:
                if is_py(f) or f in root_configs:
                    if Path(f).exists():
                        files_to_audit.add(f)
        else:
            # Fallback Mode: Full Scan
            logger.info("No changes detected (or fallback). Performing FULL SCAN.")
            src_files = list(Path(settings.paths.src).rglob("*.py"))
            test_files = list(Path(settings.paths.tests).rglob("*.py"))
            contract_files = (
                list(Path(settings.paths.contracts_dir).rglob("*.py"))
                if settings.paths.contracts_dir
                else []
            )

            for f in src_files + test_files + contract_files:
                files_to_audit.add(_to_relative_path(f))

        files_to_audit = sorted(list(files_to_audit))

        # Add Documentation (Spec, UAT, Arch) to ensure Auditor understands the objective
        cycle_id = state.cycle_id
        docs_dir = Path(settings.paths.documents_dir)
        cycle_dir = docs_dir / f"CYCLE{cycle_id}"

        docs = [docs_dir / "SYSTEM_ARCHITECTURE.md", cycle_dir / "SPEC.md", cycle_dir / "UAT.md"]

        for d in docs:
            if d.exists():
                files_to_audit.append(_to_relative_path(d))

        files_to_audit = sorted(list(set(files_to_audit)))

        # 2. Read File Contents
        # Since we are sending to LLM, we need the actual content.
        # We can try reading from local disk (since we are synced) or from sandbox if needed.
        # We assume local is up to date because we did sync/checkout operations.
        files_content: dict[str, str] = {}
        for f_path in files_to_audit:
            try:
                # Try reading from local first
                base_cwd = settings.paths.cwd if hasattr(settings.paths, "cwd") else Path.cwd()
                p = Path(base_cwd) / f_path
                # Fallback to simple Path(f_path) if relative to cwd
                if not p.exists():
                    p = Path(f_path)

                if p.exists():
                    files_content[f_path] = p.read_text(encoding="utf-8", errors="replace")
                else:
                    logger.warning(f"File {f_path} not found locally for audit.")
            except Exception as e:
                logger.warning(f"Failed to read {f_path}: {e}")

        # 3. Load Instruction
        template_path = Path(settings.paths.templates) / "AUDITOR_INSTRUCTION.md"
        if template_path.exists():
            instruction = template_path.read_text(encoding="utf-8")
        else:
            instruction = "Review the code strictly."

        instruction += (
            f"\n\n(Auditor #{auditor_idx}, Review {review_count}/{settings.REVIEWS_PER_AUDITOR}, "
            f"Iteration {iteration_count})"
        )

        # 4. Run Audit via LLMReviewer (Direct API)
        # Use FAST_MODEL by default for reading/audit as per config
        model_to_use = settings.reviewer.fast_model

        output = await self.llm_reviewer.review_code(
            files=files_content, instruction=instruction, model=model_to_use
        )
        logger.info(f"LLM Response received (Length: {len(output)})")

        logger.info(
            f"Auditor #{auditor_idx} Review {review_count}/{settings.REVIEWS_PER_AUDITOR} Complete."
        )

        # Check for System Error
        if output.startswith("SYSTEM_ERROR"):
            logger.error(f"AUDIT SYSTEM ERROR DETECTED: {output}")
            return {
                "audit_result": AuditResult(
                    is_approved=False, critical_issues=["System Error"], suggestions=[]
                ),
                "current_phase": "audit_system_error",
                "audit_feedback": ["Internal System Error during Audit. Please check logs."],
                "error": "Audit System Error",
            }

        # 5. Parse Output (Direct from LLM Response)
        # We expect the LLM to follow the format in AUDITOR_INSTRUCTION.md
        # Basic parsing: look for lines starting with "- " or structured blocks if requested.
        # But wait, existing logic used `aider_client.parse_audit_report`.
        # The prompt asks for:
        # === AUDIT REPORT START ===
        # ...
        # === AUDIT REPORT END ===

        marker_start = "=== AUDIT REPORT START ==="
        marker_end = "=== AUDIT REPORT END ==="

        report_body = output
        if marker_start in output:
            report_body = output.split(marker_start, 1)[1]
            if marker_end in report_body:
                report_body = report_body.split(marker_end, 1)[0]

        report_body = report_body.strip()

        # Simple line splitting for "issues" list context
        feedback_lines = [line.strip() for line in report_body.split("\n") if line.strip()]

        dummy_result = AuditResult(
            is_approved=False,
            critical_issues=feedback_lines,
            suggestions=[],
        )

        return {
            "audit_result": dummy_result,
            "current_phase": "audit_complete",
            "audit_feedback": feedback_lines,
            "current_auditor_index": auditor_idx,
            "current_auditor_review_count": review_count,
        }

    async def commit_coder_node(self, state: CycleState) -> dict[str, Any]:
        """Commit implementation and merge to integration branch."""
        cycle_id = state.cycle_id
        pr_url = state.pr_url

        if pr_url:
            # Merge to INTEGRATION branch (not main)
            logger.info(
                f"Audit passed. Merging PR to integration branch: {state.integration_branch}"
            )
            try:
                await self.git.merge_to_integration(pr_url, state.integration_branch)
                logger.info(f"Successfully merged cycle {cycle_id} to integration branch.")
            except Exception:
                # CRITICAL: Merge failure should stop the workflow
                from ac_cdd_core.error_messages import RecoveryMessages

                error_msg = RecoveryMessages.cycle_merge_failed(pr_url)
                logger.error(error_msg)
                return {"error": error_msg, "current_phase": "merge_failed"}

        # No additional commit needed - PR merge handles it
        # We're now on integration branch, ready for next cycle
        return {"current_phase": "complete"}

    # --- Graph Construction ---

    def build_architect_graph(self) -> CompiledStateGraph:
        workflow = StateGraph(CycleState)
        workflow.add_node("init_branch", self.init_branch_node)
        workflow.add_node("architect_session", self.architect_session_node)
        workflow.add_node("commit", self.commit_architect_node)

        workflow.set_entry_point("init_branch")
        workflow.add_edge("init_branch", "architect_session")

        def check_architect(state: CycleState) -> Literal["commit", "end"]:
            if state.error:
                return "end"
            return "commit"

        workflow.add_conditional_edges(
            "architect_session", check_architect, {"commit": "commit", "end": END}
        )
        workflow.add_edge("commit", END)

        return workflow.compile()

    def build_coder_graph(self) -> CompiledStateGraph:
        workflow = StateGraph(CycleState)
        workflow.add_node("checkout_branch", self.checkout_branch_node)
        workflow.add_node("coder_session", self.coder_session_node)
        workflow.add_node("syntax_check", self.syntax_check_node)
        workflow.add_node("auditor", self.auditor_node)
        workflow.add_node("commit", self.commit_coder_node)

        workflow.set_entry_point("checkout_branch")
        workflow.add_edge("checkout_branch", "coder_session")

        def check_coder(state: CycleState) -> Literal["syntax_check", "end"]:
            if state.error:
                return "end"
            # Always proceed to syntax check/linting
            return "syntax_check"

        workflow.add_conditional_edges(
            "coder_session", check_coder, {"syntax_check": "syntax_check", "end": END}
        )

        # Direct edge from Syntax Check to Auditor (Auditor reviews the failure if check failed)
        workflow.add_edge("syntax_check", "auditor")

        def check_audit(state: CycleState) -> Literal["commit", "coder_session"]:
            # Pydantic provides defaults, use direct access
            auditor_idx = state.current_auditor_index
            review_count = state.current_auditor_review_count

            # Check if current auditor has more reviews to do
            if review_count < settings.REVIEWS_PER_AUDITOR:
                # Same auditor, next review
                logger.info(
                    f"Auditor #{auditor_idx}: Review {review_count}/{settings.REVIEWS_PER_AUDITOR} "
                    "complete. Proceeding to fix and next review."
                )
                return "coder_session"

            # Current auditor finished all reviews, check if more auditors
            if auditor_idx < settings.NUM_AUDITORS:
                # Move to next auditor
                logger.info(
                    f"Auditor #{auditor_idx} complete ({settings.REVIEWS_PER_AUDITOR} reviews). "
                    f"Moving to Auditor #{auditor_idx + 1}."
                )
                return "coder_session"

            # All auditors finished all reviews
            logger.info(
                f"All {settings.NUM_AUDITORS} auditors completed {settings.REVIEWS_PER_AUDITOR} "
                "reviews each. "
                f"Total: {settings.NUM_AUDITORS * settings.REVIEWS_PER_AUDITOR} audit-fix cycles. "
                "Proceeding to commit."
            )
            return "commit"

        workflow.add_conditional_edges(
            "auditor",
            check_audit,
            {
                "commit": "commit",
                "coder_session": "coder_session",
            },
        )

        workflow.add_edge("commit", END)

        return workflow.compile()


def build_architect_graph(services: ServiceContainer) -> CompiledStateGraph:
    # Deprecated legacy helper, preferably use GraphBuilder directly in CLI to access cleanup
    return GraphBuilder(services).build_architect_graph()


def build_coder_graph(services: ServiceContainer) -> CompiledStateGraph:
    return GraphBuilder(services).build_coder_graph()
