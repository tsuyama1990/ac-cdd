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

MAX_AUDIT_RETRIES = 2


class GraphBuilder:
    def __init__(self, services: ServiceContainer):
        self.services = services
        self.jules_client = JulesClient()
        self.aider_client = AiderClient()
        self.git = GitManager()

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

        template_path = Path(settings.paths.templates) / "ARCHITECT_INSTRUCTION.md"
        spec_path = Path(settings.paths.documents_dir) / "ALL_SPEC.md"
        signal_file = Path(settings.paths.documents_dir) / "plan_status.json"

        if not spec_path.exists():
            return {"error": "ALL_SPEC.md not found.", "current_phase": "architect_failed"}

        # Input: user requirements (ALL_SPEC.md)
        files = [str(spec_path)]
        # System Instruction: ARCHITECT_INSTRUCTION.md
        instruction = template_path.read_text(encoding="utf-8")

        try:
            result = await self.jules_client.run_session(
                session_id="architect-session",
                prompt=instruction,
                files=files,
                completion_signal_file=signal_file,
            )
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
        # Initialize iteration count for the new cycle
        return {
            "current_phase": "branch_ready",
            "active_branch": branch,
            "iteration_count": 0,
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

        # Determine if this is Initial Creation (Jules) or Fix Loop (Aider)
        if iteration_count > 1:
            # --- FIX LOOP (Aider) ---
            logger.info("Mode: Aider Fixer (Refinement/Repair)")
            audit_feedback = state.get("audit_feedback")

            # Gather files to fix
            # TODO: In the future, use git status or Aider's repo map to narrow down context.
            src_files = list(Path(settings.paths.src).rglob("*.py"))
            test_files = list(Path(settings.paths.tests).rglob("*.py"))
            files_to_edit = [str(f) for f in src_files + test_files]

            # Instruction
            if audit_feedback:
                # feedback is a list of strings
                feedback_text = "\n".join(f"- {issue}" for issue in audit_feedback)
                instruction = (
                    f"You are the Lead Engineer fixing issues found during audit.\n"
                    f"Fix the following issues strictly:\n\n{feedback_text}\n\n"
                    f"Verify your changes with tests."
                )
            else:
                instruction = (
                    "You are the Lead Engineer. The previous audit passed, "
                    "but you must now OPTIMIZE the code.\n"
                    "Refactor for performance, readability, and better typing."
                )

            try:
                result = await self.aider_client.run_fix(
                    files=files_to_edit, instruction=instruction
                )
                return {
                    "coder_report": {"tool": "aider", "output": result},
                    "current_phase": "coder_complete",
                    "iteration_count": iteration_count,
                }
            except Exception as e:
                return {"error": str(e), "current_phase": "coder_failed"}

        else:
            # --- INITIAL CREATION (Jules) ---
            logger.info("Mode: Jules Creator (Initial Impl)")

            base_instruction = template_path.read_text(encoding="utf-8")
            instruction = base_instruction.replace("{{cycle_id}}", cycle_id)

            files = [str(template_path), str(arch_file)]
            if spec_file.exists():
                files.append(str(spec_file))
            if uat_file.exists():
                files.append(str(uat_file))

            signal_file = cycle_dir / "session_report.json"

            try:
                result = await self.jules_client.run_session(
                    session_id=f"coder-{cycle_id}-iter{iteration_count}",
                    prompt=instruction,
                    files=files,
                    completion_signal_file=signal_file,
                )
                return {
                    "coder_report": result,
                    "current_phase": "coder_complete",
                    "iteration_count": iteration_count,
                }
            except Exception as e:
                return {"error": str(e), "current_phase": "coder_failed"}

    async def run_tests_node(self, state: CycleState) -> dict[str, Any]:
        """Run tests to capture logs for UAT analysis."""
        logger.info("Phase: Run Tests (Sandbox)")

        # Initialize: Create a new SandboxRunner instance for isolation as requested
        from .sandbox import SandboxRunner

        # Create a fresh runner to ensure clean state and safe disposal
        runner = SandboxRunner(cwd="/home/user")

        try:
            # Setup Environment: Explicitly ensure dependencies
            # Although SandboxRunner runs install_cmd on init, we strictly follow instructions
            # to setup the environment.
            logger.info("Setting up Sandbox Environment...")
            await runner.run_command(["pip", "install", "uv", "pytest", "python-dotenv"])

            # Execute Tests
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
        finally:
            # Cleanup: Ensure sandbox resources are released
            await runner.close()

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
        analysis: UatAnalysis = result.output

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

        # 1. Gather Context (Files)
        # Include both src and tests for context
        # TODO: In the future, use git status or Aider's repo map to narrow down context.
        src_files = list(Path(settings.paths.src).rglob("*.py"))
        test_files = list(Path(settings.paths.tests).rglob("*.py"))
        files_to_audit = [str(f) for f in src_files + test_files]

        # Load Instruction
        template_path = Path(settings.paths.templates) / "AUDITOR_INSTRUCTION.md"
        if template_path.exists():
            instruction = template_path.read_text(encoding="utf-8")
        else:
            instruction = "Review the code strictly."

        instruction += f"\n\n(Iteration {iteration_count})"

        # 2. Run Audit via Aider
        output = await self.aider_client.run_audit(files=files_to_audit, instruction=instruction)

        logger.info(f"Audit Round {iteration_count} Complete.")

        # 3. Parse Output for Structured Report
        # Look for content between markers
        marker_start = "=== AUDIT REPORT START ==="
        marker_end = "=== AUDIT REPORT END ==="

        extracted_text = ""
        if marker_start in output and marker_end in output:
            try:
                start_idx = output.index(marker_start) + len(marker_start)
                end_idx = output.index(marker_end)
                extracted_text = output[start_idx:end_idx].strip()
            except ValueError:
                # Should not happen given the check, but safe fallback
                extracted_text = ""

        if not extracted_text:
            # Fallback: take the last 20 lines or full output if short
            lines = output.strip().split("\n")
            if len(lines) > 20:
                extracted_text = "\n".join(lines[-20:])
            else:
                extracted_text = output.strip()

        # Split into lines for feedback
        feedback_lines = [line.strip() for line in extracted_text.split("\n") if line.strip()]

        # Dummy result to satisfy type hints if strictly checked elsewhere
        dummy_result = AuditResult(
            is_approved=False,  # Always assume false/improve in fixed loop
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
    return GraphBuilder(services).build_architect_graph()


def build_coder_graph(services: ServiceContainer) -> CompiledStateGraph:
    return GraphBuilder(services).build_coder_graph()
