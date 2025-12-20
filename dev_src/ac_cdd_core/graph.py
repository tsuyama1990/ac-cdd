from pathlib import Path
from typing import Any, Literal

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from .agents import auditor_agent, qa_analyst_agent
from .config import settings
from .domain_models import AuditResult, UatAnalysis
from .process_runner import ProcessRunner
from .service_container import ServiceContainer
from .services.git_ops import GitManager
from .services.jules_client import JulesClient
from .state import CycleState
from .utils import logger

MAX_AUDIT_RETRIES = 2


class GraphBuilder:
    def __init__(self, services: ServiceContainer):
        self.services = services
        self.jules_client = JulesClient()
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
                completion_signal_file=signal_file
            )
        except Exception as e:
            logger.error(f"Architect session failed: {e}")
            return {"error": str(e), "current_phase": "architect_failed"}

        return {
            "current_phase": "architect_complete",
            "planned_cycles": result.get("cycles", []),
            "error": None
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
        return {"current_phase": "branch_ready", "active_branch": branch}

    async def coder_session_node(self, state: CycleState) -> dict[str, Any]:
        """Coder Session: Implement and Test Creation."""
        cycle_id = state["cycle_id"]
        logger.info(f"Phase: Coder Session (Cycle {cycle_id})")

        template_path = Path(settings.paths.templates) / "CODER_INSTRUCTION.md"
        cycle_dir = Path(settings.paths.documents_dir) / f"CYCLE{cycle_id}"
        spec_file = cycle_dir / "SPEC.md"
        uat_file = cycle_dir / "UAT.md"
        arch_file = Path(settings.paths.documents_dir) / "SYSTEM_ARCHITECTURE.md"

        audit_feedback = state.get("audit_feedback")

        if audit_feedback:
            logger.info("Applying Audit Feedback to Coder Instructions.")
            feedback_text = "\n".join(f"- {issue}" for issue in audit_feedback)
            instruction = (
                f"Your previous implementation FAILED the strict audit.\n"
                f"You must fix the following CRITICAL ISSUES immediately:\n\n"
                f"{feedback_text}\n\n"
                f"Check the existing code, apply fixes, and verify with tests."
            )
        else:
            # Prepare standard instruction
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
                session_id=f"coder-{cycle_id}",
                prompt=instruction,
                files=files,
                completion_signal_file=signal_file
            )
            return {"coder_report": result, "current_phase": "coder_complete"}
        except Exception as e:
            return {"error": str(e), "current_phase": "coder_failed"}

    async def run_tests_node(self, state: CycleState) -> dict[str, Any]:
        """Run tests to capture logs for UAT analysis."""
        logger.info("Phase: Run Tests")

        runner = ProcessRunner()

        # Try running tests
        cmd = ["uv", "run", "pytest", "tests/"]
        stdout, stderr, code = await runner.run_command(cmd, check=False)

        logs = f"STDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"
        return {"test_logs": logs, "test_exit_code": code, "current_phase": "tests_run"}

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
        """Committee of Auditors Node (Sequential Multi-Audit)."""
        logger.info("Phase: Committee Auditor")

        auditor_idx = state.get("current_auditor_index", 1)
        review_count = state.get("current_auditor_review_count", 1)

        logger.info(
            f"Auditor #{auditor_idx} (Review {review_count}/{settings.REVIEWS_PER_AUDITOR})"
        )

        # 1. Gather Context
        runner = ProcessRunner()
        tree_cmd = [
            "tree", "-L", "3", "-I",
            "__pycache__|.git|.venv|node_modules|site-packages|*.egg-info"
        ]
        tree_out, _, _ = await runner.run_command(tree_cmd, check=False)
        diff_out = await self.git.get_diff("main")

        # Load Strict Persona Prompt
        template_path = Path(settings.paths.templates) / "AUDITOR_INSTRUCTION.md"
        if template_path.exists():
            strict_persona = template_path.read_text(encoding="utf-8")
        else:
            strict_persona = "Act as a strict code auditor. Reject if any issues found."

        # Inject Auditor Identity
        identity_prompt = (
            f"You are Auditor #{auditor_idx} of {settings.NUM_AUDITORS} in the review committee."
        )

        prompt = (
            f"{identity_prompt}\n{strict_persona}\n\n"
            "=== DIRECTORY STRUCTURE ===\n"
            f"{tree_out}\n\n"
            "=== CHANGES (DIFF) ===\n"
            f"{diff_out}\n\n"
        )

        # 2. Run Audit
        result = await auditor_agent.run(prompt)
        audit_result: AuditResult = result.output

        if audit_result.is_approved:
            logger.info(f"Auditor #{auditor_idx} APPROVED")

            # Check if committee is finished
            if auditor_idx >= settings.NUM_AUDITORS:
                return {
                    "audit_result": audit_result,
                    "current_phase": "audit_passed",
                    "audit_feedback": None
                }
            else:
                # Move to next auditor
                return {
                    "audit_result": audit_result,
                    "current_auditor_index": auditor_idx + 1,
                    "current_auditor_review_count": 1,
                    "current_phase": "audit_next_round",
                    "audit_feedback": None
                }
        else:
            logger.warning(f"Auditor #{auditor_idx} REJECTED")
            # Stay on same auditor, increment review count
            # Logic handled in conditional edge to decide loop vs fail
            return {
                "audit_result": audit_result,
                "current_auditor_review_count": review_count + 1,
                "audit_feedback": audit_result.critical_issues,
                "current_phase": "audit_failed"
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

        def check_audit(state: CycleState) -> Literal["commit", "auditor", "coder_session", "end"]:
            phase = state.get("current_phase")
            # We use the review_count stored in state,
            # which was already incremented in node if failed
            review_count = state.get("current_auditor_review_count", 1)
            # But the node returns the *next* count value.
            # If rejected, review_count is now (prev + 1).
            # Max retries means REVIEWS_PER_AUDITOR.
            # E.g. limit 2.
            # 1st try (count=1) -> Reject -> returns count=2 -> (2 <= 2) -> coder_session.
            # 2nd try (count=2) -> Reject -> returns count=3 -> (3 > 2) -> end.

            if phase == "audit_passed":
                # All auditors approved
                return "commit"

            if phase == "audit_next_round":
                # Passed current auditor, loop to next
                return "auditor"

            if phase == "audit_failed":
                # Check retries (note: review_count is already incremented)
                # If review_count is 2, it means we are about to try for the 2nd time?
                # No, review_count tracks "how many times have we TRIED".
                # If node returns count=2, it means we failed the 1st time, and next will be 2nd.
                # So if count <= LIMIT, we can retry.
                if review_count <= settings.REVIEWS_PER_AUDITOR:
                     return "coder_session"
                else:
                     logger.error("Audit Failed: Max retries exceeded for this auditor.")
                     return "end"

            return "end"

        workflow.add_conditional_edges(
            "auditor",
            check_audit,
            {
                "commit": "commit",
                "auditor": "auditor",
                "coder_session": "coder_session",
                "end": END,
            },
        )

        workflow.add_edge("commit", END)

        return workflow.compile()


def build_architect_graph(services: ServiceContainer) -> CompiledStateGraph:
    return GraphBuilder(services).build_architect_graph()


def build_coder_graph(services: ServiceContainer) -> CompiledStateGraph:
    return GraphBuilder(services).build_coder_graph()
