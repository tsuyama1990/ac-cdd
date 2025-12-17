from pathlib import Path
from typing import Any, Literal

from langgraph.graph import END, StateGraph

from .agents import (
    auditor_agent,
    coder_agent,
    planner_agent,
    qa_analyst_agent,
    structurer_agent,
)
from .config import settings
from .domain_models import (
    AuditResult,
    CyclePlan,
    SystemArchitecture,
    UatAnalysis,
)
from .process_runner import ProcessRunner
from .sandbox import SandboxRunner
from .service_container import ServiceContainer
from .state import CycleState
from .utils import logger


class GraphBuilder:
    def __init__(self, services: ServiceContainer):
        self.services = services

    async def structurer_node(self, state: CycleState) -> dict[str, Any]:
        """
        Phase -1: Structure Requirements
        Generates SYSTEM_ARCHITECTURE.md from ALL_SPEC.md.
        """
        logger.info("Phase: Structurer")

        docs_dir = Path(settings.paths.documents_dir)
        all_spec_path = docs_dir / "ALL_SPEC.md"

        if not all_spec_path.exists():
            logger.warning(f"{all_spec_path} not found. Skipping Structurer.")
            return {"current_phase": "structuring_skipped"}

        spec_content = all_spec_path.read_text(encoding="utf-8")

        user_task = (
            "Analyze the following raw requirements and create a comprehensive "
            "System Architecture Design.\n\n"
            f"RAW REQUIREMENTS:\n{spec_content}"
        )

        result = await structurer_agent.run(user_task)
        architecture: SystemArchitecture = result.output

        # Save artifacts
        out_md = docs_dir / "SYSTEM_ARCHITECTURE.md"
        out_json = docs_dir / "SYSTEM_ARCHITECTURE.json"

        # Simple Markdown rendering
        md_content = (
            f"# System Architecture: {settings.paths.package_dir}\n\n"
            f"## Background\n{architecture.background}\n\n"
            f"## Philosophy\n{architecture.philosophy}\n\n"
            f"## User Stories\n" + "\n".join(f"- {s}" for s in architecture.user_stories) + "\n\n"
            f"## System Design\n{architecture.system_design}\n\n"
            f"## Module Design\n{architecture.module_design}\n\n"
            f"## Tech Stack\n" + "\n".join(f"- {t}" for t in architecture.tech_stack) + "\n\n"
            "## Implementation Roadmap\n"
            + "\n".join(f"- {r}" for r in architecture.implementation_roadmap)
        )

        out_md.write_text(md_content, encoding="utf-8")
        out_json.write_text(architecture.model_dump_json(indent=2), encoding="utf-8")

        logger.info("SYSTEM_ARCHITECTURE generated.")
        return {"current_phase": "structuring_complete"}

    async def planner_node(self, state: CycleState) -> dict[str, Any]:
        """
        Phase 0: Planning Phase
        Generates SPEC, Schema, and UAT artifacts.
        """
        cycle_id = state["cycle_id"]
        logger.info(f"Phase: Planning (Cycle {cycle_id})")

        # Support Offline/Manual Planning: Check if artifacts already exist
        cycle_dir = Path(settings.paths.documents_dir) / f"CYCLE{cycle_id}"
        spec_path = cycle_dir / "SPEC.md"

        if spec_path.exists():
            logger.info(f"Plan artifacts found at {cycle_dir}. Skipping generation.")
            return {"current_phase": "planning_complete", "error": None}

        # Priority 1: Use System Architecture (Structured) if available
        # Modified to look for SYSTEM_ARCHITECTURE.json primarily
        sys_arch_json = Path(settings.paths.documents_dir) / "SYSTEM_ARCHITECTURE.json"

        # Fallback to older structured spec if needed
        structured_json_path = Path(settings.paths.documents_dir) / "ALL_SPEC_STRUCTURED.json"

        if sys_arch_json.exists():
            logger.info("Using System Architecture (JSON) for planning.")
            json_content = sys_arch_json.read_text(encoding="utf-8")
            user_task = (
                f"You are the Planner. The user has defined a strict System Architecture.\n\n"
                f"SYSTEM_ARCHITECTURE_JSON:\n{json_content}\n\n"
                "Based STRICTLY on this Architecture, generate the artifacts for "
                f"CYCLE{cycle_id}.\n"
                "Consult the 'implementation_roadmap' to see what belongs in this cycle.\n"
            )
        elif structured_json_path.exists():
            logger.info("Using Structured Spec (JSON) for planning.")
            json_content = structured_json_path.read_text(encoding="utf-8")
            user_task = (
                f"You are the Planner. The user has defined a strict Structured Specification.\n\n"
                f"STRUCTURED_SPEC_JSON:\n{json_content}\n\n"
                f"Based STRICTLY on this JSON, generate the artifacts for CYCLE{cycle_id}.\n"
                f"- SPEC.md: Must align with the 'features' list for this cycle.\n"
                f"- schema.py: Must implement the types defined in the 'architecture_overview'.\n"
                f"- UAT.md: Must derive scenarios from 'acceptance_criteria'."
            )
        else:
            # Priority 2: Use Markdown Template + Context
            planning_prompt_path = Path(settings.paths.templates) / "CYCLE_PLANNING_PROMPT.md"
            base_prompt = ""
            if planning_prompt_path.exists():
                base_prompt = planning_prompt_path.read_text(encoding="utf-8")

            user_task = (
                f"{base_prompt}\n\n"
                f"Focus specifically on generating artifacts for CYCLE{cycle_id}."
            )

        if state.get("goal"):
            user_task += f"\n\nUSER GOAL/INSTRUCTION: {state['goal']}"

        if state.get("error"):
            user_task += f"\n\nPREVIOUS ERROR/FEEDBACK: {state['error']}"

        result = await planner_agent.run(user_task)
        plan: CyclePlan = result.output

        self.services.artifact_manager.save_plan_artifacts(cycle_id, plan)

        return {"plan": plan, "current_phase": "planning_complete", "error": None}

    async def spec_writer_node(self, state: CycleState) -> dict[str, Any]:
        """
        Phase 3.1: Align Contracts (Sync Schema)
        """
        cycle_id = state["cycle_id"]
        logger.info(f"Phase: Spec Writer (Cycle {cycle_id})")

        self.services.contract_manager.align_contracts(cycle_id)

        return {"current_phase": "contracts_aligned"}

    async def test_generator_node(self, state: CycleState) -> dict[str, Any]:
        """
        Phase 3.2: Generate Property Tests
        """
        cycle_id = state["cycle_id"]
        logger.info(f"Phase: Test Generator (Cycle {cycle_id})")

        user_task = settings.prompts.property_test_template.format(cycle_id=cycle_id)

        target_path = Path(settings.paths.property_tests) / f"test_cycle{cycle_id}.py"

        user_task += f"\n\nReturn the code in a file named '{target_path}'."
        prompt_with_role = f"You are a QA Engineer.\n{user_task}"

        result = await coder_agent.run(prompt_with_role)

        # Return changes for review/application
        return {
            "code_changes": result.output,
            "current_phase": "tests_generated",
            "error": None,
        }

    async def apply_test_code_node(self, state: CycleState) -> dict[str, Any]:
        """Apply test code changes."""
        logger.info("Applying Test Code Changes")
        self.services.file_patcher.apply_changes(state["code_changes"], dry_run=False)
        return {"current_phase": "tests_applied"}

    async def coder_node(self, state: CycleState) -> dict[str, Any]:
        """
        Phase 3.3: Implementation (Generation Only)
        """
        cycle_id = state["cycle_id"]
        logger.info(f"Phase: Coder (Cycle {cycle_id})")

        # Increment loop count
        new_loop_count = state.get("loop_count", 0) + 1

        is_fix = state.get("error") is not None

        if is_fix:
            # Ensure feedback is a string
            feedback = state.get("error", "") or ""
            # Enhance prompt with structured audit result if available
            audit_res = state.get("audit_result")
            if audit_res and not audit_res.is_approved:
                feedback += "\n\nCRITICAL ISSUES:\n" + "\n".join(audit_res.critical_issues)
                feedback += "\n\nSUGGESTIONS:\n" + "\n".join(audit_res.suggestions)

            # Add correction history
            history = state.get("correction_history", [])
            if history:
                feedback += "\n\nPREVIOUS ATTEMPTS (Do not repeat these errors):\n"
                feedback += "\n".join(f"- {h}" for h in history[-3:])

            instructions = (
                f"Fix the implementation based on the following feedback:\n"
                f"{feedback}\n"
                "Analyze the stack trace or audit issues and fix the code in "
                f"{settings.paths.src}/."
            )
            prompt = instructions
        else:
            # Initial Implementation
            spec_path = Path(settings.paths.documents_dir) / f"CYCLE{cycle_id}/SPEC.md"
            schema_path = Path(settings.paths.contracts_dir) / f"schema_cycle{cycle_id}.py"

            spec_content = (
                spec_path.read_text(encoding="utf-8") if spec_path.exists() else "No SPEC found."
            )
            schema_content = (
                schema_path.read_text(encoding="utf-8")
                if schema_path.exists()
                else "No Schema found."
            )

            prompt = (
                f"Implement requirements based on the following SPEC and Schema:\n\n"
                f"=== SPEC ===\n{spec_content}\n\n"
                f"=== Schema ===\n{schema_content}\n\n"
                f"Implement the solution in {settings.paths.src}/."
            )

        result = await coder_agent.run(prompt)

        return {
            "code_changes": result.output,
            "error": None,
            "current_phase": "implementation_generated",
            "loop_count": new_loop_count,
        }

    async def apply_impl_code_node(self, state: CycleState) -> dict[str, Any]:
        """Apply implementation code changes."""
        logger.info("Applying Implementation Changes")
        self.services.file_patcher.apply_changes(state["code_changes"], dry_run=False)
        return {"current_phase": "implementation_applied"}

    async def tester_node(self, state: CycleState) -> dict[str, Any]:
        """
        Phase: Testing (Property + Unit)
        Runs in E2B Sandbox.
        """
        cycle_id = state["cycle_id"]
        logger.info(f"Phase: Tester (Cycle {cycle_id})")

        sandbox = SandboxRunner(sandbox_id=state.get("sandbox_id"))

        # Use configured test command
        cmd = settings.sandbox.test_cmd

        try:
            stdout, stderr, code = await sandbox.run_command(cmd, check=False)

            if sandbox.sandbox:
                new_sandbox_id = sandbox.sandbox.sandbox_id
            else:
                new_sandbox_id = state.get("sandbox_id")

            logs = stdout + "\n" + stderr

            if code != 0:
                logger.warning("Tests Failed.")
                err_msg = f"Tests Failed:\n{logs[-2000:]}"

                # Update history
                history = state.get("correction_history", [])
                history.append(f"Test failure at loop {state.get('loop_count', 0)}: {logs[-200:]}")

                return {
                    "test_logs": logs,
                    "error": err_msg,
                    "correction_history": history,
                    "current_phase": "testing_failed",
                    "sandbox_id": new_sandbox_id,
                }

            logger.info("Tests Passed.")
            return {
                "test_logs": logs,
                "error": None,
                "current_phase": "testing_passed",
                "sandbox_id": new_sandbox_id,
            }

        except Exception as e:
            return {"error": str(e), "current_phase": "testing_failed"}

    async def auditor_node(self, state: CycleState) -> dict[str, Any]:
        """
        Phase 3.4: Strict Audit
        Runs static analysis (Sandbox) and LLM Audit (Local).
        """
        logger.info("Phase: Auditor")
        sandbox = SandboxRunner(sandbox_id=state.get("sandbox_id"))

        # 1. Static Analysis in Sandbox
        errors = []

        # Lint Check (Ruff)
        out, err, code = await sandbox.run_command(settings.sandbox.lint_check_cmd, check=False)

        # Type Check (Mypy)
        out, err, code = await sandbox.run_command(settings.sandbox.type_check_cmd, check=False)
        if code != 0:
            errors.append(f"Mypy Failed:\n{out}\n{err}")

        # Security Check (Bandit)
        out, err, code = await sandbox.run_command(settings.sandbox.security_check_cmd, check=False)
        if code != 0:
            errors.append(f"Bandit Failed:\n{out}\n{err}")

        # 2. LLM Audit
        # We invoke the agent regardless of static analysis result to allow
        # "Smart Suppression" suggestions for static analysis errors.

        files_content = self.services.file_patcher.read_src_files(settings.paths.src)

        user_task = (
            f"Audit the code in {settings.paths.src}/ for Pydantic contracts and security."
        )

        if errors:
            user_task += (
                "\n\nSTATIC ANALYSIS FAILED:\n"
                + "\n".join(errors)
                + "\n\nIf these are false positives, suggest suppression comments."
            )

        prompt = f"{user_task}\n\n{files_content}"

        result = await auditor_agent.run(prompt)
        audit_res: AuditResult = result.output

        if not audit_res.is_approved:
            # Combine static errors with LLM feedback
            combined_issues = errors + audit_res.critical_issues
            err_msg = "Audit Failed:\n" + "\n".join(combined_issues)

            # Update history
            history = state.get("correction_history", [])
            history.append(
                f"Audit failure at loop {state.get('loop_count', 0)}: {combined_issues[:3]}"
            )

            return {
                "audit_logs": "\n".join(errors),
                "audit_result": audit_res,
                "error": err_msg,
                "correction_history": history,
                "current_phase": "audit_failed",
            }

        # If approved by LLM despite static errors, we might still fail if errors exist.
        # The LLM *should* have returned approved=False with suggestions to suppress.
        # If errors exist, we must return audit_failed so Coder can apply fixes/suppressions.

        if errors:
            history = state.get("correction_history", [])
            history.append(
                f"Static Analysis failure at loop {state.get('loop_count', 0)}: {errors[:3]}"
            )

            return {
                "audit_logs": "\n".join(errors),
                "audit_result": audit_res,
                "error": "Static Analysis Failed. See Audit Result for suppression advice.",
                "correction_history": history,
                "current_phase": "audit_failed",
            }

        return {"audit_result": audit_res, "error": None, "current_phase": "audit_passed"}

    async def uat_generator_node(self, state: CycleState) -> dict[str, Any]:
        """
        Phase 3.5a: UAT Generation
        """
        cycle_id = state["cycle_id"]
        logger.info(f"Phase: UAT Generator (Cycle {cycle_id})")

        # 1. Generate UAT Code
        uat_path = Path(settings.paths.documents_dir) / f"CYCLE{cycle_id}/UAT.md"
        uat_content = uat_path.read_text(encoding="utf-8") if uat_path.exists() else "No UAT found."

        description = (
            f"Create Playwright tests in {settings.paths.e2e_tests}/ "
            f"based on the following UAT plan:\n\n{uat_content}\n\n"
            "REQUIREMENTS:\n"
            "- Use `unittest.mock`, `pytest-mock`, or `vcrpy` to mock external connections.\n"
            "- Output valid Python code."
        )
        result = await coder_agent.run(description)

        return {
            "code_changes": result.output,
            "current_phase": "uat_generated",
            "error": None
        }

    async def apply_uat_code_node(self, state: CycleState) -> dict[str, Any]:
        """Apply UAT code changes."""
        logger.info("Applying UAT Code Changes")
        self.services.file_patcher.apply_changes(state["code_changes"], dry_run=False)
        return {"current_phase": "uat_applied"}

    async def uat_evaluator_node(self, state: CycleState) -> dict[str, Any]:
        """
        Phase 3.5b: UAT Execution & Analysis
        """
        cycle_id = state["cycle_id"]
        logger.info(f"Phase: UAT Evaluator (Cycle {cycle_id})")

        # 2. Run Tests in Sandbox
        sandbox = SandboxRunner(sandbox_id=state.get("sandbox_id"))
        # We want to run ONLY e2e tests here
        cmd = settings.sandbox.test_cmd + [settings.paths.e2e_tests]

        stdout, stderr, code = await sandbox.run_command(cmd, check=False)
        logs = stdout + "\n" + stderr
        success = code == 0

        # 3. Analyze
        verdict = "PASS" if success else "FAIL"
        analyze_prompt = f"Analyze UAT logs. Verdict: {verdict}\nLogs:\n{logs[-5000:]}"

        res = await qa_analyst_agent.run(analyze_prompt)
        analysis: UatAnalysis = res.output

        # Save report
        report_path = (
            Path(settings.paths.documents_dir) / f"CYCLE{cycle_id}" / "UAT_RESULT.md"
        )
        report_path.write_text(
            f"# UAT {verdict}\n\n{analysis.summary}\n{analysis.behavior_analysis}",
            encoding="utf-8",
        )

        if not success:
            return {
                "uat_analysis": analysis,
                "error": f"UAT Failed: {analysis.summary}",
                "current_phase": "uat_failed",
            }

        return {"uat_analysis": analysis, "error": None, "current_phase": "uat_passed"}

    async def diff_auditor_node(self, state: CycleState) -> dict[str, Any]:
        """
        Ad-hoc Phase: Diff Auditor
        Reviews git diff and provides feedback.
        """
        runner = ProcessRunner()
        # Get git diff
        stdout, stderr, code = await runner.run_command(["git", "diff", "HEAD"], check=False)
        diff = stdout

        if not diff:
            return {"current_phase": "no_changes", "error": "No changes to audit."}

        user_task = (
            "Review the following git diff focusing on Security, Performance, and Readability.\n"
            "Output ONLY specific, actionable instructions for an AI coder as a bulleted list.\n"
            f"Git Diff:\n{diff}"
        )

        result = await auditor_agent.run(user_task)
        audit_res: AuditResult = result.output

        if audit_res.is_approved:
            return {"audit_result": audit_res, "error": None, "current_phase": "audit_passed"}

        # Pass issues as error for coder to fix
        issues = "\n".join(audit_res.critical_issues + audit_res.suggestions)
        return {
            "audit_result": audit_res,
            "error": f"Audit Issues:\n{issues}",
            "current_phase": "audit_feedback",
        }

    # --- Graph Construction Methods ---

    def build_main_graph(self) -> StateGraph[CycleState]:
        workflow = StateGraph(CycleState)

        # Add Nodes
        workflow.add_node("structurer", self.structurer_node)
        workflow.add_node("planner", self.planner_node)
        workflow.add_node("spec_writer", self.spec_writer_node)
        
        workflow.add_node("test_generator", self.test_generator_node)
        workflow.add_node("apply_test", self.apply_test_code_node)
        
        workflow.add_node("coder", self.coder_node)
        workflow.add_node("apply_impl", self.apply_impl_code_node)
        
        workflow.add_node("tester", self.tester_node)
        workflow.add_node("auditor", self.auditor_node)
        
        workflow.add_node("uat_generator", self.uat_generator_node)
        workflow.add_node("apply_uat", self.apply_uat_code_node)
        workflow.add_node("uat_evaluator", self.uat_evaluator_node)

        # Define Edges
        # Conditional Entry Point
        def check_structure(state: CycleState) -> Literal["structurer", "planner"]:
            # If SYSTEM_ARCHITECTURE.json/md exists, skip to planner
            sys_arch = Path(settings.paths.documents_dir) / "SYSTEM_ARCHITECTURE.json"
            if sys_arch.exists():
                return "planner"
            return "structurer"

        workflow.set_conditional_entry_point(
            check_structure, {"structurer": "structurer", "planner": "planner"}
        )

        workflow.add_edge("structurer", "planner")
        workflow.add_edge("planner", "spec_writer")
        workflow.add_edge("spec_writer", "test_generator")
        
        # Test Gen -> Approval -> Apply
        def check_test_approval(state: CycleState) -> Literal["apply_test", "test_generator"]:
            if state.get("approved"):
                return "apply_test"
            return "test_generator" # Loop back on rejection with feedback in 'error'
        
        workflow.add_conditional_edges(
            "test_generator",
            check_test_approval,
            {"apply_test": "apply_test", "test_generator": "test_generator"},
        )
        workflow.add_edge("apply_test", "coder")

        # Coder -> Approval -> Apply
        def check_impl_approval(state: CycleState) -> Literal["apply_impl", "coder"]:
            if state.get("approved"):
                return "apply_impl"
            return "coder"
            
        workflow.add_conditional_edges(
            "coder", check_impl_approval, {"apply_impl": "apply_impl", "coder": "coder"}
        )
        workflow.add_edge("apply_impl", "tester")
        
        # Testing Loop
        def check_test_result(state: CycleState) -> Literal["auditor", "coder", "end"]:
            if state.get("error"):
                if state.get("loop_count", 0) > settings.MAX_RETRIES:
                    logger.error("Max retries reached in Testing Loop.")
                    return "end"
                # If tests failed, go back to coder
                return "coder"
            return "auditor"

        workflow.add_conditional_edges(
            "tester", check_test_result, {"auditor": "auditor", "coder": "coder", "end": END}
        )

        def check_audit_result(state: CycleState) -> Literal["uat_generator", "coder", "end"]:
            if state.get("error"):
                if state.get("loop_count", 0) > settings.MAX_RETRIES:
                    logger.error("Max retries reached in Audit Loop.")
                    return "end"
                return "coder"
            return "uat_generator"

        workflow.add_conditional_edges(
            "auditor",
            check_audit_result,
            {"uat_generator": "uat_generator", "coder": "coder", "end": END},
        )
        
        # UAT Flow
        def check_uat_approval(state: CycleState) -> Literal["apply_uat", "uat_generator"]:
            if state.get("approved"):
                return "apply_uat"
            return "uat_generator"
            
        workflow.add_conditional_edges(
            "uat_generator", check_uat_approval,
            {"apply_uat": "apply_uat", "uat_generator": "uat_generator"}
        )
        workflow.add_edge("apply_uat", "uat_evaluator")

        def check_uat_result(state: CycleState) -> Literal["end", "coder"]:
            if state.get("error"):
                if state.get("loop_count", 0) > settings.MAX_RETRIES:
                    logger.error("Max retries reached in UAT Loop.")
                    return "end"
                return "coder"
            return "end"

        workflow.add_conditional_edges(
            "uat_evaluator", check_uat_result, {"end": END, "coder": "coder"}
        )

        return workflow

    def build_audit_graph(self) -> StateGraph[CycleState]:
        """Graph for 'audit' command."""
        workflow = StateGraph(CycleState)
        workflow.add_node("diff_auditor", self.diff_auditor_node)
        workflow.add_node("coder", self.coder_node)

        workflow.set_entry_point("diff_auditor")

        def check_audit(state: CycleState) -> Literal["coder", "end"]:
            if state.get("error"):
                return "coder"
            return "end"

        workflow.add_conditional_edges(
            "diff_auditor", check_audit, {"coder": "coder", "end": END}
        )
        workflow.add_edge("coder", END)  # One-shot fix for audit
        return workflow

    def build_fix_graph(self) -> StateGraph[CycleState]:
        """Graph for 'fix' command."""
        workflow = StateGraph(CycleState)
        workflow.add_node("tester", self.tester_node)
        workflow.add_node("coder", self.coder_node)

        workflow.set_entry_point("tester")

        def check_test(state: CycleState) -> Literal["coder", "end"]:
            if state.get("error"):
                if state.get("loop_count", 0) > settings.MAX_RETRIES:
                    return "end"
                return "coder"
            return "end"

        workflow.add_conditional_edges("tester", check_test, {"coder": "coder", "end": END})
        workflow.add_edge("coder", "tester")
        return workflow


# For backward compatibility / easier import if needed, but CLI should use builder.
def build_graph(services: ServiceContainer) -> StateGraph[CycleState]:
    return GraphBuilder(services).build_main_graph()


def build_audit_graph(services: ServiceContainer) -> StateGraph[CycleState]:
    return GraphBuilder(services).build_audit_graph()


def build_fix_graph(services: ServiceContainer) -> StateGraph[CycleState]:
    return GraphBuilder(services).build_fix_graph()
