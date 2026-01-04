"""Centralized error messages with recovery instructions."""

import sys

from ac_cdd_core.utils import check_api_key
from rich.console import Console
from rich.panel import Panel


class RecoveryMessages:
    """Provides consistent error messages with actionable recovery steps."""

    @staticmethod
    def session_not_found() -> str:
        """Error message when no session can be found."""
        return (
            "No session found.\n\n"
            "Recovery options:\n"
            "1. Start a new session:\n"
            "   uv run manage.py gen-cycles\n"
            "2. If you have an existing session, specify it:\n"
            "   uv run manage.py run-cycle --session <session-id>"
        )

    @staticmethod
    def merge_failed(pr_url: str, next_step: str) -> str:
        """Error message when auto-merge fails."""
        return (
            f"Auto-merge failed.\n\n"
            f"The PR was created but could not be merged automatically.\n"
            f"Please merge manually: {pr_url}\n\n"
            f"After merging, proceed with:\n"
            f"  {next_step}"
        )

    @staticmethod
    def architect_merge_failed(pr_url: str) -> str:
        """Error message when architect PR merge fails."""
        return RecoveryMessages.merge_failed(pr_url, "uv run manage.py run-cycle --id 01")

    @staticmethod
    def cycle_merge_failed(pr_url: str) -> str:
        """Error message when cycle PR merge fails."""
        return RecoveryMessages.merge_failed(pr_url, "the next cycle")

    @staticmethod
    def branch_not_found(branch: str, session_file: str = ".ac_cdd_session.json") -> str:
        """Error message when integration branch doesn't exist."""
        return (
            f"Integration branch '{branch}' does not exist.\n\n"
            f"Recovery options:\n"
            f"1. If you deleted the branch, clear the session file:\n"
            f"   rm {session_file}\n"
            f"2. If you want to recreate the session, run:\n"
            f"   uv run manage.py gen-cycles\n"
            f"3. If the branch exists remotely, fetch it:\n"
            f"   git fetch origin {branch}:{branch}"
        )

    @staticmethod
    def remote_branch_missing(branch: str) -> str:
        """Warning when branch exists locally but not on remote."""
        return (
            f"Integration branch '{branch}' exists locally but not on remote.\n\n"
            f"This may cause issues when creating PRs. Consider pushing the branch:\n"
            f"   git push -u origin {branch}"
        )

    @staticmethod
    def merge_conflict(source: str, target: str, original_branch: str) -> str:
        """Error message with merge conflict recovery steps."""
        return (
            f"Merge conflict between {source} and {target}.\n\n"
            f"Recovery steps:\n"
            f"1. Manually resolve conflicts:\n"
            f"   git checkout {target}\n"
            f"   git merge {source}\n"
            f"   # Resolve conflicts, then:\n"
            f"   git add .\n"
            f"   git commit\n"
            f"2. Or abandon the merge and investigate:\n"
            f"   git checkout {original_branch}"
        )


class SuccessMessages:
    """Centralized success messages with next steps."""

    @staticmethod
    def architect_complete(session_id: str, integration_branch: str) -> str:
        """Success message for architect phase completion."""
        return (
            f"✅ Architect Phase Complete! Session: {session_id}\n\n"
            f"Integration Branch: {integration_branch}\n"
            "Architecture PR has been merged to integration branch.\n\n"
            "Next Steps:\n"
            "1. Start implementing cycles:\n"
            f"   uv run manage.py run-cycle --id 01 --session {session_id}\n"
            "2. After all cycles complete, finalize the session:\n"
            f"   uv run manage.py finalize-session --session {session_id}"
        )

    @staticmethod
    def cycle_complete(cycle_id: str, next_cycle_id: str) -> str:
        """Success message for cycle completion."""
        return (
            f"✅ Cycle {cycle_id} Implementation Request Sent!\n\n"
            "Jules has created a Pull Request with the implementation.\n\n"
            "Next Steps:\n"
            "1. Review the Pull Request on GitHub.\n"
            "2. Merge the PR if the implementation and tests pass.\n"
            "3. Pull the changes locally:\n"
            "   git checkout main && git pull\n"
            "4. Proceed to the next cycle:\n"
            f"   uv run manage.py run-cycle --id {next_cycle_id}"
        )

    @staticmethod
    def all_cycles_complete() -> str:
        """Success message for all cycles completion."""
        return (
            "✅ All Cycles Completed!\n\n"
            "Next Steps:\n"
            "1. Perform a final system-wide audit.\n"
            "2. Deploy your application!"
        )

    @staticmethod
    def session_finalized(pr_url: str) -> str:
        """Success message for session finalization."""
        return (
            f"✅ Final PR Created!\n\n"
            f"PR URL: {pr_url}\n\n"
            "Next Steps:\n"
            "1. Review the PR on GitHub\n"
            "2. Merge to main when ready\n"
            "3. The integration branch will be automatically deleted\n\n"
            "To start a new session, run: uv run manage.py gen-cycles"
        )

    @staticmethod
    def show_panel(message: str, title: str = "Next Action Guide") -> None:
        """Display message in a styled panel."""
        cons = Console()
        cons.print(Panel(message, title=title, style="bold green", expand=False))


def ensure_api_key() -> None:
    """Check API key availability and exit if missing."""
    cons = Console()
    try:
        check_api_key()
    except ValueError as e:
        cons.print(f"[red]Configuration Error:[/red] {e}")
        sys.exit(1)
