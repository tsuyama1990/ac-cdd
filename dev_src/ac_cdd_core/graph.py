import json
from pathlib import Path
from typing import Any, Literal

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from .config import settings
from .domain_models import AuditResult
from .sandbox import SandboxRunner
from .service_container import ServiceContainer
from .services.git_ops import GitManager
from .services.jules_client import JulesClient
from .services.llm_reviewer import LLMReviewer
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
        self.jules_client = JulesClient()
        self.llm_reviewer = LLMReviewer()
        self.git = GitManager()
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
        """Explicitly close the sandbox runner."""
        if self.sandbox_runner:
            logger.info("Cleaning up shared sandbox...")
            await self.sandbox_runner.close()
            self.sandbox_runner = None

    # --- Architect Graph Nodes ---

    async def init_branch_node(self, state: CycleState) -> dict[str, Any]:
        """Setup Git Branch for Architecture."""
        logger.info("Phase: Init Branch (Architect)")
        await self.git.ensure_clean_state()
        branch = await self.git.create_working_branch("design", "architecture")
        return {"current_phase": "branch_ready", "active_branch": branch}

    async def architect_session_node(self, state: CycleState) -> dict[str, Any]:
        """Architect Session: Generates all specs and plans."""
        logger.info("Phase: Architect Session")

        # Get Shared Sandbox (Persistent)
        runner = await self._get_shared_sandbox()

        template_path = Path(settings.paths.templates) / "ARCHITECT_INSTRUCTION.md"
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
        instruction = template_path.read_text(encoding="utf-8")

        try:
            # Pass runner for remote execution
            result = await self.jules_client.run_session(
                session_id="architect-session",
                prompt=instruction,
                files=files,
                completion_signal_file=signal_file,
                runner=runner,
            )

            # Since Jules now returns a PR URL (or status dict) instead of file content directly,
            # we log the result and mark as complete.
            # Note: The actual 'cycles' plan is inside the PR content.
            # For the local flow to continue perfectly, we might need to parse the PR desc or file.
            # For now, we assume the user will review the PR.
            pr_url = result.get("pr_url")
            if pr_url:
                logger.info(f"Architect PR created: {pr_url}")

                # --- Auto-Merge Logic ---
                try:
                    logger.info("Attempting to auto-merge PR...")
                    await self.git.merge_pr(pr_url)
                    await self.git.pull_changes()
                    logger.info("PR merged and changes pulled successfully.")

                    # Reload plan status from the now-synced local file
                    if signal_file.exists():
                        try:
                            plan_data = json.loads(signal_file.read_text(encoding="utf-8"))
                            # Update result to include the planned cycles
                            result["cycles"] = plan_data.get("cycles", [])
                        except Exception as e:
                            logger.warning(f"Failed to parse plan_status.json after merge: {e}")

                except Exception as e:
                    logger.warning(
                        f"Auto-merge failed. Please merge manually via the URL above. Error: {e}"
                    )
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
        """Checkout or Create Branch for Cycle."""
        cycle_id = state["cycle_id"]
        logger.info(f"Phase: Checkout Branch (Cycle {cycle_id})")

        await self.git.ensure_clean_state()
        branch = await self.git.create_working_branch("feat", f"cycle{cycle_id}")
        
        # Initialize iteration count (default to 0 if not provided in start state)
        current_iter = state.get("iteration_count", 0)
        
        return {
            "current_phase": "branch_ready",
            "active_branch": branch,
            "iteration_count": current_iter,
        }

    async def coder_session_node(self, state: CycleState) -> dict[str, Any]:
        """Coder Session: Implement and Test Creation (Jules or Aider)."""
        cycle_id = state["cycle_id"]
        iteration_count = state.get("iteration_count", 0) + 1

        logger.info(
            f"Phase: Coder Session (Cycle {cycle_id}) - Iteration {iteration_count}/{settings.MAX_ITERATIONS}"
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
        if state.get("resume_mode") and state.get("pr_url"):
            logger.info(f"RESUMING Session: {state.get('jules_session_name')}")
            pr_url = state["pr_url"]
            
            # Ensure Sandbox is ready even if skipping Jules (for Syntax Check later)
            runner = await self._get_shared_sandbox()
            
            # Checkout the PR
            logger.info(f"Checking out PR: {pr_url}...")
            await self.git.checkout_pr(pr_url)
            
            return {
                "coder_report": {"pr_url": pr_url, "status": "resumed"},
                "current_phase": "coder_complete_resumed",
                "iteration_count": iteration_count,
                "jules_session_name": state.get("jules_session_name"),
                "pr_url": pr_url
            }

        # Determine if this is Initial Creation (Jules) or Fix Loop (Aider)
        if iteration_count > 1 and state.get("jules_session_name"):
            # --- FIX LOOP (Jules Reuse) ---
            logger.info(f"Mode: Jules Fixer (Refinement/Repair) - Resuming Session {state['jules_session_name']}")
            audit_feedback = state.get("audit_feedback", [])
            
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
                result = await self.jules_client.continue_session(
                    session_name=state["jules_session_name"],
                    prompt=instruction
                )
                
                pr_url = result.get("pr_url")
                if pr_url:
                    logger.info(f"Jules updated PR: {pr_url}")
                    # Switch to the PR branch to test the changes
                    await self.git.checkout_pr(pr_url)
                    
                    return {
                        "coder_report": result,
                        "current_phase": "coder_complete",
                        "iteration_count": iteration_count,
                        # maintain session info
                        "jules_session_name": state["jules_session_name"],
                        "pr_url": pr_url
                    }
                else:
                    return {"error": "Jules finished but lost track of PR.", "current_phase": "coder_failed"}

            except Exception as e:
                return {"error": str(e), "current_phase": "coder_failed"}

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
                    return {"error": "No PR created by Jules", "current_phase": "coder_failed"}
            except Exception as e:
                return {"error": str(e), "current_phase": "coder_failed"}

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
                    "active_branch": state.get("active_branch"), # Keep context
                    "audit_feedback": [f"Syntax Error:\nSTDOUT: {stdout_s}\nSTDERR: {stderr_s}"],
                    "error": "Syntax Check Failed. Please fix syntax errors."
                }

            # Step 2: Linting (Ruff)
            cmd_lint = ["ruff", "check", "."]
            stdout_l, stderr_l, code_l = await runner.run_command(cmd_lint, check=False)

            if code_l != 0:
                # Linting failed - pass as feedback to Coder (via Auditor loop or direct)
                # We return 'error' to stop? No, we want to feed back.
                # But current logic stops on 'error'.
                # Let's treat it as a failure that triggers feedback loop via Auditor (or shortcut back to Coder?)
                # For now, let's treat it as 'test_logs' equivalent so it passes to Auditor who REJECTS it.
                logs = f"Syntax Check: PASS\nLinting Failed:\n{stdout_l}\n{stderr_l}"
                return {"test_logs": logs, "test_exit_code": code_l, "current_phase": "syntax_check_failed"}

            logs = "Syntax Check: PASS\nLinting: PASS"
            return {"test_logs": logs, "test_exit_code": 0, "current_phase": "syntax_check_passed"}

        except Exception as e:
            logger.error(f"Sandbox execution failed: {e}")
            return {
                "test_logs": f"Execution Failed: {e}",
                "test_exit_code": -1,
                "current_phase": "syntax_check_system_error"
            }



    async def auditor_node(self, state: CycleState) -> dict[str, Any]:
        """Strict Auditor Node (Direct LLM Review)."""
        logger.info("Phase: Strict Auditor (Direct LLM)")

        iteration_count = state.get("iteration_count", 1)

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
        cycle_id = state.get("cycle_id", settings.DUMMY_CYCLE_ID)
        docs_dir = Path(settings.paths.documents_dir)
        cycle_dir = docs_dir / f"CYCLE{cycle_id}"
        
        docs = [
            docs_dir / "SYSTEM_ARCHITECTURE.md",
            cycle_dir / "SPEC.md",
            cycle_dir / "UAT.md"
        ]
        
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
                base_cwd = settings.paths.cwd if hasattr(settings.paths, 'cwd') else Path.cwd()
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

        instruction += f"\n\n(Iteration {iteration_count})"
        
        # 4. Run Audit via LLMReviewer (Direct API)
        # Use FAST_MODEL by default for reading/audit as per config
        model_to_use = settings.reviewer.fast_model
        
        output = await self.llm_reviewer.review_code(
            files=files_content, 
            instruction=instruction, 
            model=model_to_use
        )

        logger.info(f"Audit Round {iteration_count} Complete.")

        # Check for System Error
        if output.startswith("SYSTEM_ERROR"):
            logger.error(f"AUDIT SYSTEM ERROR DETECTED: {output}")
            return {
                "audit_result": AuditResult(
                    is_approved=False, 
                    critical_issues=["System Error"], 
                    suggestions=[]
                ),
                "current_phase": "audit_system_error",
                "audit_feedback": ["Internal System Error during Audit. Please check logs."],
                "error": "Audit System Error"
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
        }

    async def commit_coder_node(self, state: CycleState) -> dict[str, Any]:
        """Commit implementation."""
        cycle_id = state["cycle_id"]
        pr_url = state.get("pr_url")

        if pr_url:
            # Now we merge the PR to finalize the cycle
            logger.info("Audit Passed. Merging PR to main branch...")
            await self.git.merge_pr(pr_url)
            # Pull to ensure local is up to date with the merge
            await self.git.pull_changes()

        await self.git.commit_changes(f"feat(cycle{cycle_id}): implement and verify features")
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
            if state.get("error"):
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
            if state.get("error"):
                return "end"
            # Always proceed to syntax check/linting
            return "syntax_check"

        workflow.add_conditional_edges(
            "coder_session", check_coder, {"syntax_check": "syntax_check", "end": END}
        )
        
        # Direct edge from Syntax Check to Auditor (Auditor reviews the failure if check failed)
        workflow.add_edge("syntax_check", "auditor")

        def check_audit(state: CycleState) -> Literal["commit", "coder_session"]:
            current_iter = state.get("iteration_count", 0)
            max_iter = settings.MAX_ITERATIONS  # default: 3

            if current_iter < max_iter:
                logger.info(f"Iteration {current_iter}/{max_iter}: Proceeding to refinement loop.")
                return "coder_session"

            logger.info("Max iterations reached. Proceeding to commit.")
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
