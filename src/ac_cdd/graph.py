from pathlib import Path
from typing import Literal

from langgraph.graph import END, StateGraph

from .agents import (
    auditor_agent,
    coder_agent,
    planner_agent,
    qa_analyst_agent,
)
from .config import settings
from .domain_models import (
    AuditResult,
    CyclePlan,
    UatAnalysis,
)
from .presentation import ConsolePresenter
from .sandbox import SandboxRunner
from .services import ArtifactManager, ContractManager, FilePatcher
from .state import CycleState
from .utils import logger

# --- Services ---
file_patcher = FilePatcher()
contract_manager = ContractManager()
artifact_manager = ArtifactManager()
presenter = ConsolePresenter()


async def planner_node(state: CycleState) -> dict:
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

    # Priority 1: Use Structured JSON if available
    structured_json_path = Path(settings.paths.documents_dir) / "ALL_SPEC_STRUCTURED.json"
    if structured_json_path.exists():
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

        user_task = f"{base_prompt}\n\nFocus specifically on generating artifacts for CYCLE{cycle_id}."

    if state.get("goal"):
        user_task += f"\n\nUSER GOAL/INSTRUCTION: {state['goal']}"

    if state.get("error"):
        user_task += f"\n\nPREVIOUS ERROR/FEEDBACK: {state['error']}"

    result = await planner_agent.run(user_task)
    plan: CyclePlan = result.output

    artifact_manager.save_plan_artifacts(cycle_id, plan)

    return {"plan": plan, "current_phase": "planning_complete", "error": None}


async def spec_writer_node(state: CycleState) -> dict:
    """
    Phase 3.1: Align Contracts (Sync Schema)
    """
    cycle_id = state["cycle_id"]
    logger.info(f"Phase: Spec Writer (Cycle {cycle_id})")

    contract_manager.align_contracts(cycle_id)

    return {"current_phase": "contracts_aligned"}


async def test_generator_node(state: CycleState) -> dict:
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

    # Logic for interaction
    preview_results = file_patcher.apply_changes(result.output, dry_run=True)

    should_apply = True
    if state.get("interactive", False):
        should_apply = presenter.review_and_confirm(preview_results)
    else:
        presenter.print_patch_results(preview_results)

    if should_apply and not state.get("dry_run", False):
        file_patcher.apply_changes(result.output, dry_run=False)

    return {"current_phase": "tests_generated"}


async def coder_node(state: CycleState) -> dict:
    """
    Phase 3.3: Implementation
    """
    cycle_id = state["cycle_id"]
    logger.info(f"Phase: Coder (Cycle {cycle_id})")

    # Increment loop count
    new_loop_count = state.get("loop_count", 0) + 1

    is_fix = state.get("error") is not None

    if is_fix:
        feedback = state["error"]
        # Enhance prompt with structured audit result if available
        audit_res = state.get("audit_result")
        if audit_res and not audit_res.is_approved:
             feedback += "\n\nCRITICAL ISSUES:\n" + "\n".join(audit_res.critical_issues)
             feedback += "\n\nSUGGESTIONS:\n" + "\n".join(audit_res.suggestions)

        instructions = (
            f"Fix the implementation based on the following feedback:\n"
            f"{feedback}\n"
            f"Analyze the stack trace or audit issues and fix the code in {settings.paths.src}/."
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
            schema_path.read_text(encoding="utf-8") if schema_path.exists() else "No Schema found."
        )

        prompt = (
            f"Implement requirements based on the following SPEC and Schema:\n\n"
            f"=== SPEC ===\n{spec_content}\n\n"
            f"=== Schema ===\n{schema_content}\n\n"
            f"Implement the solution in {settings.paths.src}/."
        )

    result = await coder_agent.run(prompt)

    # Logic for interaction
    preview_results = file_patcher.apply_changes(result.output, dry_run=True)

    should_apply = True
    if state.get("interactive", False):
        should_apply = presenter.review_and_confirm(preview_results)
    else:
        presenter.print_patch_results(preview_results)

    if should_apply and not state.get("dry_run", False):
        file_patcher.apply_changes(result.output, dry_run=False)

    return {
        "code_changes": result.output,
        "error": None,
        "current_phase": "implementation_done",
        "loop_count": new_loop_count,
    }


async def tester_node(state: CycleState) -> dict:
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
            return {
                "test_logs": logs,
                "error": f"Tests Failed:\n{logs[-2000:]}",
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


async def auditor_node(state: CycleState) -> dict:
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

    files_content = file_patcher.read_src_files(settings.paths.src)

    user_task = f"Audit the code in {settings.paths.src}/ for Pydantic contracts and security."

    if errors:
        user_task += (
            "\n\nSTATIC ANALYSIS FAILED:\n" + "\n".join(errors) +
            "\n\nIf these are false positives, suggest suppression comments."
        )

    prompt = f"{user_task}\n\n{files_content}"

    result = await auditor_agent.run(prompt)
    audit_res: AuditResult = result.output

    if not audit_res.is_approved:
        # Combine static errors with LLM feedback
        combined_issues = errors + audit_res.critical_issues
        err_msg = "Audit Failed:\n" + "\n".join(combined_issues)

        return {
            "audit_logs": "\n".join(errors),
            "audit_result": audit_res,
            "error": err_msg,
            "current_phase": "audit_failed",
        }

    # If approved by LLM despite static errors, we might still fail if errors exist.
    # The LLM *should* have returned approved=False with suggestions to suppress.
    # If errors exist, we must return audit_failed so Coder can apply fixes/suppressions.

    if errors:
         return {
            "audit_logs": "\n".join(errors),
            "audit_result": audit_res,
            "error": "Static Analysis Failed. See Audit Result for suppression advice.",
            "current_phase": "audit_failed",
        }

    return {"audit_result": audit_res, "error": None, "current_phase": "audit_passed"}


async def uat_node(state: CycleState) -> dict:
    """
    Phase 3.5: UAT
    Generate UAT tests, run them in Sandbox, Analyze results.
    """
    cycle_id = state["cycle_id"]
    logger.info(f"Phase: UAT (Cycle {cycle_id})")

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

    # Logic for interaction
    preview_results = file_patcher.apply_changes(result.output, dry_run=True)

    should_apply = True
    if state.get("interactive", False):
        should_apply = presenter.review_and_confirm(preview_results)
    else:
        presenter.print_patch_results(preview_results)

    if should_apply and not state.get("dry_run", False):
        file_patcher.apply_changes(result.output, dry_run=False)

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
    report_path = Path(settings.paths.documents_dir) / f"CYCLE{cycle_id}" / "UAT_RESULT.md"
    report_path.write_text(
        f"# UAT {verdict}\n\n{analysis.summary}\n{analysis.behavior_analysis}", encoding="utf-8"
    )

    if not success:
        return {
            "uat_analysis": analysis,
            "error": f"UAT Failed: {analysis.summary}",
            "current_phase": "uat_failed",
        }

    return {"uat_analysis": analysis, "error": None, "current_phase": "uat_passed"}


# --- Graph Definition ---


def build_graph() -> StateGraph[CycleState]:
    workflow = StateGraph(CycleState)

    # Add Nodes
    workflow.add_node("planner", planner_node)
    workflow.add_node("spec_writer", spec_writer_node)
    workflow.add_node("test_generator", test_generator_node)
    workflow.add_node("coder", coder_node)
    workflow.add_node("tester", tester_node)
    workflow.add_node("auditor", auditor_node)
    workflow.add_node("uat", uat_node)

    # Define Edges
    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "spec_writer")
    workflow.add_edge("spec_writer", "test_generator")
    workflow.add_edge("test_generator", "coder")
    workflow.add_edge("coder", "tester")

    # Conditional Edges

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

    def check_audit_result(state: CycleState) -> Literal["uat", "coder", "end"]:
        if state.get("error"):
            if state.get("loop_count", 0) > settings.MAX_RETRIES:
                logger.error("Max retries reached in Audit Loop.")
                return "end"
            return "coder"
        return "uat"

    workflow.add_conditional_edges(
        "auditor", check_audit_result, {"uat": "uat", "coder": "coder", "end": END}
    )

    def check_uat_result(state: CycleState) -> Literal["end", "coder"]:
        if state.get("error"):
            if state.get("loop_count", 0) > settings.MAX_RETRIES:
                logger.error("Max retries reached in UAT Loop.")
                return "end"
            return "coder"
        return "end"

    workflow.add_conditional_edges("uat", check_uat_result, {"end": END, "coder": "coder"})

    return workflow


async def diff_auditor_node(state: CycleState) -> dict:
    """
    Ad-hoc Phase: Diff Auditor
    Reviews git diff and provides feedback.
    """
    from .process_runner import ProcessRunner

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

    result = await auditor_agent.run(user_task, result_type=AuditResult)
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


def build_audit_graph() -> StateGraph[CycleState]:
    """Graph for 'audit' command."""
    workflow = StateGraph(CycleState)
    workflow.add_node("diff_auditor", diff_auditor_node)
    workflow.add_node("coder", coder_node)

    workflow.set_entry_point("diff_auditor")

    def check_audit(state: CycleState) -> Literal["coder", "end"]:
        if state.get("error"):
            return "coder"
        return "end"

    workflow.add_conditional_edges("diff_auditor", check_audit, {"coder": "coder", "end": END})
    workflow.add_edge("coder", END)  # One-shot fix for audit
    return workflow


def build_fix_graph() -> StateGraph[CycleState]:
    """Graph for 'fix' command."""
    workflow = StateGraph(CycleState)
    workflow.add_node("tester", tester_node)
    workflow.add_node("coder", coder_node)

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
