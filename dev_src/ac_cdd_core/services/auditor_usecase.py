from pathlib import Path
from typing import Any

from rich.console import Console

from ac_cdd_core.config import settings
from ac_cdd_core.domain_models import AuditResult
from ac_cdd_core.enums import FlowStatus
from ac_cdd_core.services.git_ops import GitManager
from ac_cdd_core.services.jules_client import JulesClient
from ac_cdd_core.services.llm_reviewer import LLMReviewer
from ac_cdd_core.state import CycleState
from ac_cdd_core.state_manager import StateManager

console = Console()

class AuditorUseCase:
    """
    Encapsulates the logic and interactions for the Auditor AI (LLM / Aider).
    """

    def __init__(self, jules_client: JulesClient, git_manager: GitManager, llm_reviewer: LLMReviewer) -> None:
        self.jules = jules_client
        self.git = git_manager
        self.llm_reviewer = llm_reviewer

    async def _read_files(self, file_paths: list[str]) -> dict[str, str]:
        """Helper to read files from the local filesystem."""
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

    async def _run_static_analysis(self, target_files: list[str] | None = None) -> tuple[bool, str]:
        """Runs local static analysis (mypy, ruff) and returns (success, output)."""
        console.print("[bold cyan]Running Static Analysis (mypy, ruff)...[/bold cyan]")
        output = []
        success = True

        def truncate_output(text: str, max_lines: int = 50, max_chars: int = 2000) -> str:
            lines = text.splitlines()
            original_line_count = len(lines)
            if original_line_count > max_lines:
                text = (
                    "\n".join(lines[:max_lines])
                    + f"\n... (truncated {original_line_count - max_lines} more lines)"
                )
            if len(text) > max_chars:
                text = text[:max_chars] + f"\n... (truncated {len(text) - max_chars} more chars)"
            return text

        targets = target_files if target_files is not None else ["."]

        if target_files is not None and not target_files:
            console.print("[dim]No files to analyze.[/dim]")
            return True, "No files to analyze."

        try:
            mypy_targets = [f for f in targets if f == "." or f.endswith(".py")]
            if mypy_targets:
                mypy_cmd = ["uv", "run", "mypy", "--no-error-summary", *mypy_targets]
                stdout, stderr, code = await self.git.runner.run_command(mypy_cmd, check=False)
                if code != 0:
                    success = False
                    details = truncate_output(stdout + stderr)
                    output.append("### mypy Errors")
                    output.append(f"```\n{details}\n```")
                else:
                    console.print("[green]mypy passed[/green]")
        except Exception as e:
            output.append(f"Failed to run mypy: {e}")

        try:
            ruff_cmd = ["uv", "run", "ruff", "check", *targets]
            stdout, stderr, code = await self.git.runner.run_command(ruff_cmd, check=False)
            if code != 0:
                success = False
                details = truncate_output(stdout + stderr)
                output.append("### ruff Errors")
                output.append(f"```\n{details}\n```")
            else:
                console.print("[green]ruff passed[/green]")
        except Exception as e:
            output.append(f"Failed to run ruff: {e}")

        return success, "\n\n".join(output)

    async def execute(self, state: CycleState) -> dict[str, Any]:
        """Runs the auditor logic, static analysis, and prepares LLM reviewer feedback."""
        console.print("[bold magenta]Starting Auditor...[/bold magenta]")
        instruction = settings.get_template("AUDITOR_INSTRUCTION.md").read_text()

        context_paths = settings.get_context_files()
        architect_instruction = settings.get_template("ARCHITECT_INSTRUCTION.md")
        if architect_instruction.exists():
            context_paths.append(str(architect_instruction))
        context_docs = await self._read_files(context_paths)

        try:
            new_last_audited_commit = state.last_audited_commit
            pr_url = state.pr_url
            
            if pr_url:
                console.print(f"[dim]Checking out PR: {pr_url}[/dim]")
                try:
                    await self.git.checkout_pr(pr_url)
                    console.print("[dim]Successfully checked out PR branch[/dim]")

                    current_commit = await self.git.get_current_commit()
                    last_audited = state.last_audited_commit

                    if current_commit and current_commit == last_audited:
                        console.print(
                            f"[bold yellow]Robustness Check: Commit {current_commit[:7]} already audited.[/bold yellow]"
                        )
                        console.print("[dim]Checking if Jules is still running...[/dim]")

                        jules_session_id = state.jules_session_name
                        if not jules_session_id:
                            mgr = StateManager()
                            cycle_manifest = mgr.get_cycle(state.cycle_id)
                            if cycle_manifest:
                                jules_session_id = cycle_manifest.jules_session_id

                        if jules_session_id:
                            try:
                                jules_status = await self.jules.get_session_state(jules_session_id)
                                if jules_status not in ["COMPLETED", "SUCCEEDED", "FAILED"]:
                                    console.print(
                                        "[bold yellow]Jules session still active. Delegating wait logic to graph router.[/bold yellow]"
                                    )
                                    return {
                                        "status": FlowStatus.WAITING_FOR_JULES,
                                        "audit_result": state.audit_result,
                                        "last_audited_commit": last_audited,
                                    }
                            except Exception:
                                pass

                        console.print(
                            "[bold yellow]Jules session complete. Proceeding with audit on same commit.[/bold yellow]"
                        )

                    new_last_audited_commit = current_commit
                except Exception as e:
                    console.print(f"[yellow]Warning: Could not checkout PR: {e}[/yellow]")
            else:
                console.print(
                    "[yellow]Warning: No PR URL provided, reviewing current branch[/yellow]"
                )

            base_branch = state.feature_branch or state.integration_branch or "main"
            if pr_url:
                try:
                    pr_base = await self.git.get_pr_base_branch(pr_url)
                    if pr_base:
                        console.print(f"[dim]Detected PR base branch: {pr_base}[/dim]")
                        base_branch = pr_base
                except Exception as e:
                    console.print(f"[yellow]Warning: Could not get PR base branch: {e}[/yellow]")

            changed_file_paths = await self.git.get_changed_files(base_branch=base_branch)
            reviewable_extensions = {".py", ".md", ".toml", ".json", ".yaml", ".yml", ".txt", ".sh"}
            reviewable_files = [
                f for f in changed_file_paths if Path(f).suffix in reviewable_extensions
            ]

            excluded_patterns = [
                "dev_src/", "dev_documents/", "tests/ac_cdd/", ".github/", "pyproject.toml",
                "setup.py", "setup.cfg", "README.md", "LICENSE", ".gitignore", "Dockerfile",
                "docker-compose", ".env",
            ]

            reviewable_files = [
                f for f in reviewable_files
                if (f.endswith(".py") or f.startswith("tests/"))
                and not any(f.startswith(pattern) or pattern in f for pattern in excluded_patterns)
            ]

            build_artifact_patterns = [
                ".egg-info/", "__pycache__/", ".pyc", ".pyo", ".pyd",
                "dist/", "build/", ".pytest_cache/", ".mypy_cache/", ".ruff_cache/",
            ]

            reviewable_files = [
                f for f in reviewable_files
                if not any(pattern in f for pattern in build_artifact_patterns)
            ]

            if reviewable_files:
                try:
                    filtered_files = []
                    for file_path in reviewable_files:
                        _, _, code = await self.git.runner.run_command(
                            ["git", "check-ignore", "-q", file_path], check=False
                        )
                        if code != 0:
                            filtered_files.append(file_path)
                    reviewable_files = filtered_files
                except Exception as e:
                    console.print(f"[yellow]Warning: Could not filter gitignored files: {e}[/yellow]")

            if not reviewable_files:
                console.print(
                    "[yellow]Warning: No reviewable application files found. Using fallback.[/yellow]"
                )
                all_target_files = settings.get_target_files()
                excluded_prefixes_fallback = ("tests/ac_cdd/",)
                reviewable_files = [
                    f for f in all_target_files
                    if not any(f.startswith(prefix) for prefix in excluded_prefixes_fallback)
                ]
            
            context_file_names = {str(p) for p in context_paths}
            reviewable_files = [f for f in reviewable_files if f not in context_file_names]

            target_files = await self._read_files(reviewable_files)
        except Exception as e:
            console.print(f"[yellow]Warning: Could not get changed files from git: {e}[/yellow]")
            target_paths = settings.get_target_files()
            reviewable_files = target_paths
            target_files = await self._read_files(target_paths)

        model = (
            settings.reviewer.smart_model
            if settings.AUDITOR_MODEL_MODE == "smart"
            else settings.reviewer.fast_model
        )

        static_ok, static_log = await self._run_static_analysis(target_files=reviewable_files)

        audit_feedback = await self.llm_reviewer.review_code(
            target_files=target_files,
            context_docs=context_docs,
            instruction=instruction,
            model=model,
        )

        if "-> APPROVE" in audit_feedback:
            status = "approved"
        elif "-> REJECT" in audit_feedback:
            status = "rejected"
        else:
            status = "approved" if "NO ISSUES FOUND" in audit_feedback.upper() else "rejected"

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

        feature_branch = state.feature_branch
        if feature_branch:
            try:
                await self.git.checkout_branch(feature_branch)
            except Exception as e:
                console.print(f"[yellow]Warning: Could not return to feature branch: {e}[/yellow]")

        status_enum = FlowStatus.APPROVED if status == "approved" else FlowStatus.REJECTED

        return {
            "audit_result": result,
            "status": status_enum,
            "last_audited_commit": new_last_audited_commit,
        }
