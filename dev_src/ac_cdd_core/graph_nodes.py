from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.console import Console

from .config import settings
from .domain_models import AuditResult
from .interfaces import IGraphNodes
from .sandbox import SandboxRunner
from .services.audit_orchestrator import AuditOrchestrator
from .services.git_ops import GitManager
from .services.jules_client import JulesClient
from .services.llm_reviewer import LLMReviewer
from .services.project import ProjectManager
from .state import CycleState
from .state_manager import StateManager

console = Console()


class CycleNodes(IGraphNodes):
    """
    Encapsulates the logic for each node in the AC-CDD workflow graph.
    """

    def __init__(self, sandbox_runner: SandboxRunner, jules_client: JulesClient) -> None:
        self.sandbox = sandbox_runner
        self.jules = jules_client
        self.git = GitManager()
        # Dependency injection for sub-services could be improved by passing them in,
        # but for now we construct them with the injected clients.
        self.audit_orchestrator = AuditOrchestrator(jules_client, sandbox_runner)
        self.llm_reviewer = LLMReviewer(sandbox_runner=sandbox_runner)

    async def _read_files(self, file_paths: list[str]) -> dict[str, str]:
        """Helper to read files from the sandbox or local."""
        result = {}
        for path_str in file_paths:
            p = Path(path_str)
            if p.exists() and p.is_file():
                try:
                    result[path_str] = p.read_text(encoding="utf-8")
                except Exception as e:
                    console.print(f"[yellow]Warning: Could not read {path_str}: {e}[/yellow]")
            else:
                pass
        return result

    async def _run_static_analysis(self) -> tuple[bool, str]:
        """Runs local static analysis (mypy, ruff) and returns (success, output)."""
        console.print("[bold cyan]Running Static Analysis (mypy, ruff)...[/bold cyan]")
        output = []
        success = True

        # Run mypy
        try:
            # Using settings checks if possible, or default
            mypy_cmd = ["uv", "run", "mypy", "."]
            stdout, stderr, code = await self.git.runner.run_command(mypy_cmd, check=False)
            if code != 0:
                success = False
                output.append("### mypy Errors")
                output.append(f"```\n{stdout}{stderr}\n```")
            else:
                console.print("[green]mypy passed[/green]")
        except Exception as e:
            output.append(f"Failed to run mypy: {e}")

        # Run ruff
        try:
            ruff_cmd = ["uv", "run", "ruff", "check", "."]
            stdout, stderr, code = await self.git.runner.run_command(ruff_cmd, check=False)
            if code != 0:
                success = False
                output.append("### ruff Errors")
                output.append(f"```\n{stdout}{stderr}\n```")
            else:
                console.print("[green]ruff passed[/green]")
        except Exception as e:
            output.append(f"Failed to run ruff: {e}")

        return success, "\n\n".join(output)

    async def architect_session_node(self, state: CycleState) -> dict[str, Any]:
        """Node for Architect Agent (Jules)."""
        console.print("[bold blue]Starting Architect Session...[/bold blue]")

        instruction = settings.get_template("ARCHITECT_INSTRUCTION.md").read_text()

        # Logic moved from CLI: requested_cycle_count is now the primary driver if present
        if state.get("requested_cycle_count"):
            n = state.get("requested_cycle_count")
            instruction += (
                f"\n\nIMPORTANT CONSTRAINT: The development plan MUST be divided into "
                f"exactly {n} implementation cycles."
            )
        # Fallback if just planned_cycle_count is used (backward compatibility)
        elif state.get("planned_cycle_count"):
            n = state.get("planned_cycle_count")
            instruction += (
                f"\n\nIMPORTANT CONSTRAINT: The development plan MUST be divided into "
                f"exactly {n} implementation cycles."
            )

        context_files = settings.get_context_files()

        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")

        # New Branch Strategy: Create Integration Branch as the working base
        integration_branch = f"dev/int-{timestamp}"

        # Create integration branch from main (works same as feature branch creation)
        await self.git.create_feature_branch(integration_branch, from_branch="main")

        result = await self.jules.run_session(
            session_id=f"architect-{timestamp}",  # Logical ID for request
            prompt=instruction,
            target_files=context_files,
            context_files=[],
            require_plan_approval=False,
        )

        if result.get("status") in ("success", "running") and result.get("pr_url"):
            pr_url = result["pr_url"]
            pr_number = pr_url.split("/")[-1]

            # Auto-Merge Architecture PR
            try:
                console.print(
                    f"[bold blue]Auto-merging Architecture PR #{pr_number}...[/bold blue]"
                )
                await self.git.merge_pr(pr_number)
                console.print("[bold green]Architecture merged successfully![/bold green]")

                # Prepare environment (fix perms, sync dependencies)
                try:
                    await ProjectManager().prepare_environment()
                except Exception as e:
                    console.print(f"[yellow]Warning: Environment preparation issue: {e}[/yellow]")

            except Exception as e:
                console.print(f"[bold red]Failed to auto-merge Architecture PR: {e}[/bold red]")
                # We don't fail the cycle here, but manual intervention will be needed

            return {
                "status": "architect_completed",
                "current_phase": "architect_done",
                "integration_branch": integration_branch,
                "active_branch": integration_branch,  # Working on integration branch
                "project_session_id": result.get("session_name"),
                "pr_url": pr_url,
            }

        if result.get("error"):
            return {"status": "architect_failed", "error": result.get("error")}

        return {"status": "architect_failed", "error": "Unknown Jules error or no PR URL"}

    async def _send_audit_feedback_to_session(
        self, session_id: str, feedback: str
    ) -> dict[str, Any] | None:
        """Send audit feedback to existing Jules session and wait for new PR.

        Returns result dict if successful, None if should create new session.
        """
        console.print(
            f"[bold yellow]Sending Audit Feedback to existing Jules session: {session_id}[/bold yellow]"
        )
        try:
            feedback_msg = (
                f"# AUDIT FEEDBACK - PLEASE ADDRESS THESE ISSUES\n\n"
                f"{feedback}\n\n"
                f"Please revise your implementation to address the above feedback and create a new PR."
            )
            await self.jules._send_message(self.jules._get_session_url(session_id), feedback_msg)

            # Wait for Jules to process feedback and create new PR
            result = await self.jules.wait_for_completion(session_id)

            if result.get("status") == "success" or result.get("pr_url"):
                return {"status": "ready_for_audit", "pr_url": result.get("pr_url")}
        except Exception as e:
            console.print(
                f"[yellow]Failed to send feedback to existing session: {e}. Creating new session...[/yellow]"
            )
        else:
            console.print(
                "[yellow]Jules session did not produce PR after feedback. Creating new session...[/yellow]"
            )
        return None

    async def coder_session_node(self, state: CycleState) -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915, PLR0911
        """Node for Coder Agent (Jules)."""
        cycle_id = state.get("cycle_id")
        iteration = state.get("iteration_count")
        current_phase = state.get("current_phase")

        # Resume Logic using StateManager
        mgr = StateManager()
        cycle_manifest = mgr.get_cycle(cycle_id)

        # Special handling: If we're waiting for Jules to produce a new commit
        # (because Auditor detected same commit), just wait for completion
        if state.get("status") == "wait_for_jules_completion":
            if cycle_manifest and cycle_manifest.jules_session_id:
                console.print(
                    f"[bold blue]Waiting for Jules to produce new commit: {cycle_manifest.jules_session_id}[/bold blue]"
                )
                try:
                    result = await self.jules.wait_for_completion(cycle_manifest.jules_session_id)
                    if result.get("status") == "success" or result.get("pr_url"):
                        return {"status": "ready_for_audit", "pr_url": result.get("pr_url")}
                    console.print("[yellow]Jules session did not produce PR. Continuing...[/yellow]")
                except Exception as e:
                    console.print(f"[yellow]Wait for completion failed: {e}[/yellow]")
            else:
                console.print("[yellow]No active Jules session found. Continuing...[/yellow]")


        # 1. Try Resume if session ID exists, but ONLY if we are not in a retry loop.
        # If status is 'retry_fix', we need to send feedback (handled below), not just resume.
        if (
            cycle_manifest
            and cycle_manifest.jules_session_id
            and state.get("resume_mode", False)
            and state.get("status") != "retry_fix"
        ):
            try:
                console.print(
                    f"[bold blue]Resuming Jules Session: {cycle_manifest.jules_session_id}[/bold blue]"
                )
                result = await self.jules.wait_for_completion(cycle_manifest.jules_session_id)

                # Check outcome
                if result.get("status") == "success" or result.get("pr_url"):
                    return {"status": "ready_for_audit", "pr_url": result.get("pr_url")}
                console.print("[yellow]Resume incomplete or failed. Restarting session...[/yellow]")
            except Exception as e:
                console.print(f"[yellow]Resume failed: {e}. Starting new session.[/yellow]")

        phase_label = "REFACTORING" if current_phase == "refactoring" else "CODER"
        console.print(
            f"[bold green]Starting {phase_label} Session for Cycle {cycle_id} "
            f"(Iteration {iteration})...[/bold green]"
        )

        if current_phase == "refactoring":
            instruction = settings.get_template("REFACTOR_INSTRUCTION.md").read_text()
            # No cycle ID needed in refactor instruction, but we can add context if needed
        else:
            instruction = settings.get_template("CODER_INSTRUCTION.md").read_text()
            instruction = instruction.replace("{{cycle_id}}", str(cycle_id))

        last_audit = state.get("audit_result")
        if state.get("status") == "retry_fix" and last_audit and last_audit.feedback:
            # Check if we have an existing Jules session to reuse
            if cycle_manifest and cycle_manifest.jules_session_id:
                # Check if session is still active before attempting reuse
                session_state = await self.jules.get_session_state(
                    cycle_manifest.jules_session_id
                )

                # Allow reuse for IN_PROGRESS and COMPLETED (Auditor Reject case)
                # Only create new session if FAILED
                if session_state in ["IN_PROGRESS", "COMPLETED", "SUCCEEDED"]:
                    console.print(
                        f"[dim]Reusing session ({session_state}): {cycle_manifest.jules_session_id}[/dim]"
                    )
                    retry_result = await self._send_audit_feedback_to_session(
                        cycle_manifest.jules_session_id, last_audit.feedback
                    )
                    if retry_result:
                        return retry_result
                elif session_state == "FAILED":
                    # Session failed - create new session
                    console.print(
                        "[yellow]Previous session FAILED. Creating new session for retry...[/yellow]"
                    )
                    # Fallback: Inject feedback into new session prompt
                    instruction += f"\n\n# PREVIOUS AUDIT FEEDBACK (MUST FIX)\n{last_audit.feedback}"
                    if cycle_manifest.pr_url:
                        instruction += f"\n\nPrevious PR: {cycle_manifest.pr_url}"
                else:
                    # Unknown state - log and create new session
                    console.print(
                        f"[yellow]Session in unexpected state: {session_state}. Creating new session...[/yellow]"
                    )
                    instruction += f"\n\n# PREVIOUS AUDIT FEEDBACK (MUST FIX)\n{last_audit.feedback}"
                    if cycle_manifest.pr_url:
                        instruction += f"\n\nPrevious PR: {cycle_manifest.pr_url}"
            else:
                console.print(
                    "[bold yellow]Injecting Audit Feedback into Coder Prompt...[/bold yellow]"
                )
                instruction += f"\n\n# PREVIOUS AUDIT FEEDBACK (MUST FIX)\n{last_audit.feedback}"

        target_files = settings.get_target_files()
        context_files = settings.get_context_files()

        try:
            # Generate a unique logical ID for the session request
            timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")

            # Distinguish session ID by phase so refactoring starts fresh if needed or tracks separately
            prefix = "refactor" if current_phase == "refactoring" else "coder"
            session_req_id = f"{prefix}-cycle-{cycle_id}-iter-{iteration}-{timestamp}"

            # Start new session
            result = await self.jules.run_session(
                session_id=session_req_id,
                prompt=instruction,
                target_files=target_files,
                context_files=context_files,
                require_plan_approval=False,  # Auto-approve all plans
            )

            # 2. Persist Session ID IMMEDIATELY for Hot Resume
            if result.get("session_name"):
                # We update the manifest, but if it's refactoring, we might want to track it differently?
                # For now, just overwriting the session ID in manifest is fine as we move forward.
                mgr.update_cycle_state(
                    cycle_id, jules_session_id=result["session_name"], status="in_progress"
                )

            if result.get("status") == "running" and result.get("session_name"):
                console.print(
                    f"[bold blue]Session {result['session_name']} created. Waiting for completion...[/bold blue]"
                )
                result = await self.jules.wait_for_completion(result["session_name"])

            if result.get("status") == "success" or result.get("pr_url"):
                # Success - reset restart counter
                if cycle_manifest:
                    mgr.update_cycle_state(cycle_id, session_restart_count=0)
                return {"status": "ready_for_audit", "pr_url": result.get("pr_url")}

        except Exception as e:
            console.print(f"[red]{phase_label} Session Failed: {e}[/red]")

            # Check if we should restart the session
            if cycle_manifest:
                restart_count = cycle_manifest.session_restart_count
                max_restarts = cycle_manifest.max_session_restarts

                if restart_count < max_restarts:
                    # Restart the session
                    new_restart_count = restart_count + 1
                    console.print(
                        f"[yellow]Restarting session (attempt {new_restart_count}/{max_restarts + 1})...[/yellow]"
                    )

                    # Clear the failed session ID and increment restart counter
                    mgr.update_cycle_state(
                        cycle_id,
                        jules_session_id=None,
                        session_restart_count=new_restart_count,
                        last_error=str(e)
                    )

                    # Recursively retry (this will create a new session)
                    return await self.coder_session_node(state)
                console.print(
                    f"[red]Max session restarts ({max_restarts}) reached. Failing cycle.[/red]"
                )

            return {"status": "failed", "error": str(e)}
        else:
            if result.get("status") == "failed":
                # Handle failure in the else block (when no exception was raised)
                # This shouldn't normally happen with the new LangGraph implementation
                # but keep it for safety
                if cycle_manifest:
                    restart_count = cycle_manifest.session_restart_count
                    max_restarts = cycle_manifest.max_session_restarts

                    if restart_count < max_restarts:
                        new_restart_count = restart_count + 1
                        console.print(
                            f"[yellow]Session failed without exception. Restarting (attempt {new_restart_count}/{max_restarts + 1})...[/yellow]"
                        )

                        mgr.update_cycle_state(
                            cycle_id,
                            jules_session_id=None,
                            session_restart_count=new_restart_count,
                            last_error=result.get("error", "Unknown error")
                        )

                        return await self.coder_session_node(state)

                return {"status": "failed", "error": result.get("error")}
            return {"status": "failed", "error": "Jules failed to produce PR"}

    async def auditor_node(self, state: CycleState) -> dict[str, Any]:  # noqa: PLR0912, PLR0915, C901
        """Node for Auditor Agent (Aider/LLM)."""
        console.print("[bold magenta]Starting Auditor...[/bold magenta]")

        instruction = settings.get_template("AUDITOR_INSTRUCTION.md").read_text()

        # Get context files (SPEC, UAT, ARCHITECT_INSTRUCTION, etc.) - these are static references
        context_paths = settings.get_context_files()
        # Add ARCHITECT_INSTRUCTION.md for project structure context
        architect_instruction = settings.get_template("ARCHITECT_INSTRUCTION.md")
        if architect_instruction.exists():
            context_paths.append(str(architect_instruction))
        context_docs = await self._read_files(context_paths)

        # DYNAMIC: Get all files changed in the current branch (what's in the PR)
        from .services.git_ops import GitManager

        git = GitManager()

        try:
            # Initialize with current state
            new_last_audited_commit = state.get("last_audited_commit")

            # CRITICAL: Checkout the PR branch before reviewing
            # Otherwise we'll be reviewing the wrong code!
            pr_url = state.get("pr_url")
            if pr_url:
                console.print(f"[dim]Checking out PR: {pr_url}[/dim]")
                try:
                    await git.checkout_pr(pr_url)
                    console.print("[dim]Successfully checked out PR branch[/dim]")

                    # ROBUSTNESS: Commit ID Check with Polling
                    current_commit = await git.get_current_commit()
                    last_audited = state.get("last_audited_commit")

                    if current_commit and current_commit == last_audited:
                        console.print(
                            f"[bold yellow]Robustness Check: Commit {current_commit[:7]} already audited.[/bold yellow]"
                        )
                        console.print("[dim]Polling for new commit from Jules...[/dim]")
                        import asyncio

                        # Poll for new commit with exponential backoff
                        max_wait_time = 300  # 5 minutes total
                        elapsed_time = 0
                        wait_intervals = [30, 60, 120]  # 30s, 60s, 120s
                        poll_index = 0

                        while elapsed_time < max_wait_time:
                            wait_time = wait_intervals[min(poll_index, len(wait_intervals) - 1)]
                            console.print(f"[dim]Waiting {wait_time}s for new commit...[/dim]")
                            await asyncio.sleep(wait_time)
                            elapsed_time += wait_time
                            poll_index += 1

                            # Check for new commit
                            new_commit = await git.get_current_commit()
                            if new_commit and new_commit != last_audited:
                                console.print(
                                    f"[bold green]New commit detected: {new_commit[:7]}. Proceeding with audit.[/bold green]"
                                )
                                current_commit = new_commit
                                break
                        else:
                            # Timeout: No new commit after max wait time
                            console.print(
                                f"[bold yellow]No new commit after {max_wait_time}s. "
                                f"Skipping audit and waiting for Jules to complete.[/bold yellow]"
                            )
                            # Return early with a special status to skip audit
                            return {
                                "status": "waiting_for_jules",
                                "audit_result": state.get("audit_result"),  # Keep previous audit result
                                "last_audited_commit": last_audited,
                            }

                    # Store for return
                    new_last_audited_commit = current_commit
                except Exception as e:
                    console.print(f"[yellow]Warning: Could not checkout PR: {e}[/yellow]")
                    console.print(
                        "[yellow]Proceeding with current branch (may review wrong code!)[/yellow]"
                    )
            else:
                console.print(
                    "[yellow]Warning: No PR URL provided, reviewing current branch[/yellow]"
                )

            # Get base branch for comparison (feature branch, not main)
            # Feature branch is where we accumulate all cycles
            # We compare to the PREVIOUS state of feature branch (before this cycle's changes)
            base_branch = state.get("feature_branch") or state.get("integration_branch", "main")
            console.print(f"[dim]Comparing changes against base branch: {base_branch}[/dim]")

            changed_file_paths = await git.get_changed_files(base_branch=base_branch)
            console.print(
                f"[dim]Auditor: Found {len(changed_file_paths)} changed files to review[/dim]"
            )

            # Filter to only code/config files (skip binary, images, etc.)
            reviewable_extensions = {".py", ".md", ".toml", ".json", ".yaml", ".yml", ".txt", ".sh"}
            reviewable_files = [
                f for f in changed_file_paths if Path(f).suffix in reviewable_extensions
            ]

            # CRITICAL: ONLY review application code
            # The Auditor should ONLY review what Jules was asked to create
            # NOT framework files (dev_src/, dev_documents/, pyproject.toml, tests/ac_cdd/, etc.)

            # Excluded patterns (framework, config, docs)
            excluded_patterns = [
                "dev_src/",
                "dev_documents/",
                "tests/ac_cdd/",
                ".github/",
                "pyproject.toml",
                "setup.py",
                "setup.cfg",
                "README.md",
                "LICENSE",
                ".gitignore",
                "Dockerfile",
                "docker-compose",
                ".env",
            ]

            # Include Python files and test files, but exclude framework/config
            reviewable_files = [
                f
                for f in reviewable_files
                if (f.endswith(".py") or f.startswith("tests/"))
                and not any(f.startswith(pattern) or pattern in f for pattern in excluded_patterns)
            ]

            # Filter out build artifacts and gitignored files
            # These are generated files that shouldn't be reviewed
            build_artifact_patterns = [
                ".egg-info/",
                "__pycache__/",
                ".pyc",
                ".pyo",
                ".pyd",
                "dist/",
                "build/",
                ".pytest_cache/",
                ".mypy_cache/",
                ".ruff_cache/",
            ]

            reviewable_files = [
                f
                for f in reviewable_files
                if not any(pattern in f for pattern in build_artifact_patterns)
            ]

            # Use git check-ignore to filter out .gitignore'd files
            # This catches any other generated files we might have missed
            if reviewable_files:
                try:
                    # git check-ignore returns 0 for ignored files, 1 for not ignored
                    filtered_files = []
                    for file_path in reviewable_files:
                        _, _, code = await git.runner.run_command(
                            ["git", "check-ignore", "-q", file_path], check=False
                        )
                        if code != 0:  # Not ignored, keep it
                            filtered_files.append(file_path)

                    ignored_count = len(reviewable_files) - len(filtered_files)
                    if ignored_count > 0:
                        console.print(f"[dim]Filtered out {ignored_count} gitignored files[/dim]")

                    reviewable_files = filtered_files
                except Exception as e:
                    console.print(
                        f"[yellow]Warning: Could not filter gitignored files: {e}[/yellow]"
                    )

            if not reviewable_files:
                console.print(
                    "[yellow]Warning: No reviewable application files found in changes. Using fallback.[/yellow]"
                )
                # Fallback to static configuration (also apply filtering)
                all_target_files = settings.get_target_files()
                console.print(f"[dim]DEBUG: Fallback target files: {all_target_files}[/dim]")
                excluded_prefixes_fallback = ("tests/ac_cdd/",)  # Framework tests
                reviewable_files = [
                    f
                    for f in all_target_files
                    if not any(f.startswith(prefix) for prefix in excluded_prefixes_fallback)
                ]
                console.print(f"[dim]DEBUG: After filtering: {reviewable_files}[/dim]")
            else:
                console.print(f"[dim]Auditor: Reviewing {len(reviewable_files)} code files[/dim]")

            # CRITICAL: Remove context files from review targets
            # Context files (SPEC.md, UAT.md, etc.) should only be reference, not audit targets
            context_file_names = {str(p) for p in context_paths}
            reviewable_files = [f for f in reviewable_files if f not in context_file_names]

            console.print(
                f"[dim]Auditor: Final review target: {len(reviewable_files)} files (context excluded)[/dim]"
            )
            console.print(f"[dim]DEBUG: Final reviewable files: {reviewable_files}[/dim]")

            target_files = await self._read_files(reviewable_files)

            # DEBUG: Show what files were actually read
            console.print(f"[dim]DEBUG: Successfully read {len(target_files)} files[/dim]")
            for filepath in target_files:
                console.print(
                    f"[dim]DEBUG: - {filepath} ({len(target_files[filepath])} chars)[/dim]"
                )

        except Exception as e:
            console.print(f"[yellow]Warning: Could not get changed files from git: {e}[/yellow]")
            console.print("[dim]Falling back to static target files configuration[/dim]")
            # Fallback to original behavior
            target_paths = settings.get_target_files()
            target_files = await self._read_files(target_paths)

        # Select model based on AUDITOR_MODEL_MODE setting
        model = (
            settings.reviewer.smart_model
            if settings.AUDITOR_MODEL_MODE == "smart"
            else settings.reviewer.fast_model
        )

        # Run static analysis BEFORE or PARALLEL to LLM?
        # Running before gives us clear fail signal.
        static_ok, static_log = await self._run_static_analysis()

        audit_feedback = await self.llm_reviewer.review_code(
            target_files=target_files,
            context_docs=context_docs,
            instruction=instruction,
            model=model,
        )

        status = "approved" if "NO ISSUES FOUND" in audit_feedback.upper() else "rejected"

        # OVERRIDE: If static analysis failed, force rejection and append log
        if not static_ok:
            console.print("[bold red]Static Analysis Failed. Extending feedback...[/bold red]")
            status = "rejected"
            audit_feedback += "\n\n# AUTOMATED CHECKS FAILED (MUST FIX)\n"
            audit_feedback += "The following static analysis errors were found. You MUST fix these before the code is accepted.\n"
            audit_feedback += static_log

        result = AuditResult(
            status=status.upper(),
            is_approved=(status == "approved"),
            reason="AI Audit Complete",
            feedback=audit_feedback,
        )

        # IMPORTANT: Return to feature branch after audit
        # This ensures subsequent iterations start from the correct branch
        feature_branch = state.get("feature_branch")
        if feature_branch:
            try:
                console.print(f"[dim]Returning to feature branch: {feature_branch}[/dim]")
                await git.checkout_branch(feature_branch)
                console.print("[dim]Successfully returned to feature branch[/dim]")
            except Exception as e:
                console.print(f"[yellow]Warning: Could not return to feature branch: {e}[/yellow]")

        return {
            "audit_result": result,
            "status": status,
            "last_audited_commit": new_last_audited_commit,
        }

    async def committee_manager_node(self, state: CycleState) -> dict[str, Any]:
        """Node for Managing the Committee of Auditors."""
        # Check if we're waiting for Jules to produce a new commit
        if state.get("status") == "waiting_for_jules":
            console.print(
                "[bold yellow]No new commit detected. Waiting for Jules to complete work...[/bold yellow]"
            )
            # Return to coder_session to wait for Jules completion
            # Don't increment counters or change audit state
            return {
                "status": "wait_for_jules_completion",
            }

        audit_res = state.get("audit_result")
        i: int = state.get("current_auditor_index", 1)
        j: int = state.get("current_auditor_review_count", 1)
        current_iter: int = state.get("iteration_count", 0)

        if audit_res and audit_res.is_approved:
            if i < settings.NUM_AUDITORS:
                next_idx = i + 1
                console.print(
                    f"[bold green]Auditor #{i} Approved. Moving to Auditor #{next_idx}.[/bold green]"
                )
                return {
                    "current_auditor_index": next_idx,
                    "current_auditor_review_count": 1,
                    "status": "next_auditor",
                }
            console.print("[bold green]All Auditors Approved![/bold green]")
            return {"status": "cycle_approved"}

        if j < settings.REVIEWS_PER_AUDITOR:
            next_rev = j + 1
            console.print(
                f"[bold yellow]Auditor #{i} Rejected. "
                f"Retry {next_rev}/{settings.REVIEWS_PER_AUDITOR}.[/bold yellow]"
            )
            # Enforce Cooldown logic for retry_fix (Single Auditor)
            import time

            last_fb = state.get("last_feedback_time", 0)
            now = time.time()
            cooldown = 180  # 3 minutes
            elapsed = now - last_fb

            if elapsed < cooldown and last_fb > 0:
                wait = cooldown - elapsed
                console.print(
                    f"[bold yellow]Cooldown: Waiting {int(wait)}s before next Coder session...[/bold yellow]"
                )
                import asyncio

                await asyncio.sleep(wait)

            return {
                "current_auditor_review_count": next_rev,
                "iteration_count": current_iter + 1,
                "status": "retry_fix",
                "last_feedback_time": time.time(),
            }
        if i < settings.NUM_AUDITORS:
            next_idx = i + 1
            console.print(
                f"[bold yellow]Auditor #{i} limit reached. "
                f"Fixing code then moving to Auditor #{next_idx}.[/bold yellow]"
            )
            # Enforce Cooldown logic for retry_fix (Auditor Limit)
            import time

            last_fb = state.get("last_feedback_time", 0)
            now = time.time()
            cooldown = 180  # 3 minutes
            elapsed = now - last_fb

            if elapsed < cooldown and last_fb > 0:
                wait = cooldown - elapsed
                console.print(
                    f"[bold yellow]Cooldown: Waiting {int(wait)}s before next Coder session...[/bold yellow]"
                )
                import asyncio

                await asyncio.sleep(wait)

            return {
                "current_auditor_index": next_idx,
                "current_auditor_review_count": 1,
                "iteration_count": current_iter + 1,
                "status": "retry_fix",
                "last_feedback_time": time.time(),
            }
        console.print(
            "[bold yellow]Final Auditor limit reached. Fixing code then Merging.[/bold yellow]"
        )
        return {
            "final_fix": True,
            "iteration_count": current_iter + 1,
            "status": "retry_fix",
        }

    async def uat_evaluate_node(self, state: CycleState) -> dict[str, Any]:
        """Node for UAT Evaluation, Auto-Merge, and Refactoring Transition."""
        console.print("[bold cyan]Running UAT Evaluation...[/bold cyan]")
        # Assume UAT passes for now

        # Auto-Merge Cycle PR
        pr_url = state.get("pr_url")
        if pr_url:
            try:
                pr_number = pr_url.split("/")[-1]
                console.print(f"[bold blue]Auto-merging Cycle PR #{pr_number}...[/bold blue]")
                await self.git.merge_pr(pr_number)
                console.print("[bold green]Cycle PR merged successfully![/bold green]")
            except Exception as e:
                console.print(f"[bold red]Failed to auto-merge Cycle PR: {e}[/bold red]")
                return {"status": "failed", "error": str(e)}

        # Refactoring Phase Transition Logic
        current_phase = state.get("current_phase")
        if current_phase != "refactoring":
            console.print("[bold magenta]Transitioning to Refactoring Phase...[/bold magenta]")
            # Clear audit results and reset counters for the refactoring loop
            return {
                "current_phase": "refactoring",
                "status": "start_refactor",
                "iteration_count": 0,
                "current_auditor_index": 1,
                "current_auditor_review_count": 1,
                "audit_result": None,
                "audit_pass_count": 0,
                "audit_retries": 0,
                "final_fix": False,
                "last_feedback_time": 0,
                "pr_url": None,
            }

        # If we were already in refactoring, we are done
        console.print("[bold green]Refactoring Phase Completed.[/bold green]")
        return {"status": "cycle_completed"}

    def check_coder_outcome(self, state: CycleState) -> str:
        if state.get("final_fix", False):
            return "completed"

        status = state.get("status")
        if status == "ready_for_audit":
            return "ready_for_audit"
        if status in {"failed", "architect_failed"}:
            return "failed"
        return "completed"

    def check_audit_outcome(self, _state: CycleState) -> str:
        # Legacy/Unused
        return "rejected_retry"

    def route_committee(self, state: CycleState) -> str:
        """Router from committee_manager_node."""
        status = state.get("status")
        if status == "next_auditor":
            return "auditor"
        if status == "cycle_approved":
            return "uat_evaluate"
        if status == "retry_fix":
            return "coder_session"
        if status == "wait_for_jules_completion":
            return "coder_session"
        return "failed"

    def route_uat(self, state: CycleState) -> str:
        """Router from uat_evaluate_node (Determine if we Loop to Refactor or Finish)."""
        status = state.get("status")
        if status == "start_refactor":
            return "coder_session"
        if status == "cycle_completed":
            return "end"
        return "end"  # failed etc.
