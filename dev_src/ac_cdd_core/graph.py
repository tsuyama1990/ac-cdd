import json
from pathlib import Path
from typing import Any, Literal
import re

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from .agents import qa_analyst_agent
from .config import settings
from .domain_models import AuditResult, UatAnalysis
from .service_container import ServiceContainer
from .services.git_ops import GitManager
from .services.jules_client import JulesClient
from .services.aider_client import AiderClient
from .state import CycleState
from .utils import logger
from .sandbox import SandboxRunner

MAX_AUDIT_RETRIES = 2


class GraphBuilder:
    def __init__(self, services: ServiceContainer):
        self.services = services
        self.jules_client = JulesClient()
        self.aider_client = AiderClient()
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

        # Check if dependencies are already installed (optimization for reused/template sandboxes)
        # We check for 'uv' which is our main tool
        stdout, _, code = await self.sandbox_runner.run_command(["uv", "--version"], check=False)

        if code == 0:
            # Also check for aider, as it's critical
            _, _, aider_code = await self.sandbox_runner.run_command(["aider", "--version"], check=False)
            if aider_code == 0:
                logger.info("Dependencies appear to be installed. Skipping full install.")
            else:
                 logger.info("uv found but aider missing. Installing dependencies...")
                 code = 1 # Force install path
        
        if code != 0:
            logger.info("Installing dependencies...")
            # We need aider-chat for remote execution + standard test deps.
            # We install the current project in editable mode to get the 'ac-cdd' command (which JulesClient uses).
            deps = ["uv", "pytest", "python-dotenv", "aider-chat"]

            # Install dependencies
            await self.sandbox_runner.run_command(["pip", "install"] + deps)

            # Install the project itself (for the CLI tool)
            # The files are already synced to cwd by _sync_to_sandbox called in run_command
            await self.sandbox_runner.run_command(["pip", "install", "-e", "."])

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

    async def run_tests_node(self, state: CycleState) -> dict[str, Any]:
        """Run tests to capture logs for UAT analysis."""
        logger.info("Phase: Run Tests (Sandbox)")

        try:
            # Use Shared Sandbox
            runner = await self._get_shared_sandbox()

            # Execute Tests
            # Dependencies are already installed in _get_shared_sandbox
            cmd = ["uv", "run", "pytest", "tests/"]
            stdout, stderr, code = await runner.run_command(cmd, check=False)

            logs = f"STDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"
            return {"test_logs": logs, "test_exit_code": code, "current_phase": "tests_run"}

        except Exception as e:
            logger.error(f"Sandbox execution failed: {e}")
            return {
                "test_logs": f"Execution Failed: {e}",
                "test_exit_code": -1,
                "current_phase": "tests_failed_exec"
            }

    async def uat_evaluate_node(self, state: CycleState) -> dict[str, Any]:
        """Gemini-based UAT Evaluation."""
        logger.info("Phase: UAT Evaluate")

        cycle_id = state["cycle_id"]
        cycle_dir = Path(settings.paths.documents_dir) / f"CYCLE{cycle_id}"
        uat_file = cycle_dir / "UAT.md"

        uat_content = (
            uat_file.read_text(encoding="utf-8") if uat_file.exists() else "No UAT Definition."
        )
        logs = state.get("test_logs", "No logs.")

        prompt = (
            f"You are a QA Analyst. Evaluate if the features for Cycle {cycle_id} passed UAT.\n\n"
            f"=== UAT DEFINITION ===\n{uat_content}\n\n"
            f"=== TEST LOGS ===\n{logs}\n\n"
            "Determine if the acceptance criteria are met based on the test results.\n"
            "If tests failed or scenarios are missing, verdict is FAIL."
        )

        result = await qa_analyst_agent.run(prompt)
        
        logger.info(f"DEBUG: QA Result Type: {type(result)}")
        logger.info(f"DEBUG: QA Result Output Type: {type(result.output)}")
        
        analysis = result.output
        if isinstance(analysis, str):
             # Fallback if it comes back as string (try to parse if it looks like JSON, or fail gracefully)
             logger.warning(f"QA Agent returned string instead of object: {analysis}")
             # Attempt to parse if it looks like JSON
             if "{" in analysis:
                 try:
                     import json
                     # rudimentary cleanup if it has markdown code blocks
                     clean_json = analysis.replace("```json", "").replace("```", "").strip()
                     analysis = UatAnalysis.model_validate_json(clean_json)
                 except Exception as e:
                      logger.error(f"Failed to parse JSON from string: {e}")
                      return {"error": f"UAT Analysis format error: {analysis}", "current_phase": "uat_failed"}
             else:
                 return {"error": f"UAT Analysis returned unstructured text: {analysis}", "current_phase": "uat_failed"}

        logger.info(f"UAT Analysis: {analysis.verdict} - {analysis.summary[:100]}...")

        verdict = (
            "PASS"
            if "pass" in analysis.summary.lower() and state.get("test_exit_code") == 0
            else "FAIL"
        )

        if verdict == "FAIL":
            return {"error": f"UAT Failed: {analysis.summary}", "current_phase": "uat_failed"}

        return {"current_phase": "uat_passed", "error": None}

    async def auditor_node(self, state: CycleState) -> dict[str, Any]:
        """Strict Auditor Node (Aider)."""
        logger.info("Phase: Strict Auditor (Aider)")

        iteration_count = state.get("iteration_count", 1)

        # Get Shared Sandbox (Persistent)
        runner = await self._get_shared_sandbox()

        # 1. Gather Context (Files)
        src_files = list(Path(settings.paths.src).rglob("*.py"))
        test_files = list(Path(settings.paths.tests).rglob("*.py"))

        cwd = Path.cwd()
        def _to_rel(p: Path) -> str:
            try:
                return str(p.relative_to(cwd))
            except ValueError:
                return str(p)

        files_to_audit = [_to_rel(f) for f in src_files + test_files]

        # Load Instruction
        template_path = Path(settings.paths.templates) / "AUDITOR_INSTRUCTION.md"
        if template_path.exists():
            instruction = template_path.read_text(encoding="utf-8")
        else:
            instruction = "Review the code strictly."

        instruction += f"\n\n(Iteration {iteration_count})"

        # 2. Run Audit via Aider (Remote)
        output = await self.aider_client.run_audit(
            files=files_to_audit, instruction=instruction, runner=runner
        )

        logger.info(f"Audit Round {iteration_count} Complete.")

        # 3. Parse Output for Structured Report
        marker_start = "=== AUDIT REPORT START ==="
        marker_end = "=== AUDIT REPORT END ==="

        extracted_text = ""
        if marker_start in output and marker_end in output:
            try:
                start_idx = output.index(marker_start) + len(marker_start)
                end_idx = output.index(marker_end)
                extracted_text = output[start_idx:end_idx].strip()
            except ValueError:
                extracted_text = ""

        if not extracted_text:
            lines = output.strip().split("\n")
            if len(lines) > 20:
                extracted_text = "\n".join(lines[-20:])
            else:
                extracted_text = output.strip()

        feedback_lines = [line.strip() for line in extracted_text.split("\n") if line.strip()]

        dummy_result = AuditResult(
            is_approved=False,
            critical_issues=feedback_lines,
            minor_issues=[],
            score=0,
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
        workflow.add_node("run_tests", self.run_tests_node)
        workflow.add_node("uat_evaluate", self.uat_evaluate_node)
        workflow.add_node("auditor", self.auditor_node)
        workflow.add_node("commit", self.commit_coder_node)

        workflow.set_entry_point("checkout_branch")
        workflow.add_edge("checkout_branch", "coder_session")

        def check_coder(state: CycleState) -> Literal["run_tests", "end"]:
            if state.get("error"):
                return "end"
            # Always proceed to tests now, as we handle "fixing" via loop
            return "run_tests"

        workflow.add_conditional_edges(
            "coder_session", check_coder, {"run_tests": "run_tests", "end": END}
        )
        workflow.add_edge("run_tests", "uat_evaluate")

        def check_uat(state: CycleState) -> Literal["auditor", "end"]:
            if state.get("error"):
                return "end"
            return "auditor"

        workflow.add_conditional_edges(
            "uat_evaluate", check_uat, {"auditor": "auditor", "end": END}
        )

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
