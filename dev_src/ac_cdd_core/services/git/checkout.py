import contextlib
import os

from ac_cdd_core.utils import logger

from .base import BaseGitManager


class GitCheckoutMixin(BaseGitManager):
    """Mixin for Git checkout and stash operations."""

    async def smart_checkout(self, target: str, is_pr: bool = False, force: bool = False) -> None:
        """Robust checkout that handles local changes by auto-committing."""
        await self._auto_commit_if_dirty()

        try:
            if is_pr:
                cmd = [self.gh_cmd, "pr", "checkout", target]
                if force:
                    cmd.append("--force")
                await self.runner.run_command(cmd, check=True)
            else:
                cmd = ["checkout", target]
                if force:
                    cmd.append("-f")
                await self._run_git(cmd)

        except Exception:
            logger.error(f"Failed to checkout '{target}'. Please check git status.")
            raise

    async def _auto_commit_if_dirty(self, message: str = "Auto-save before checkout") -> None:
        """Automatically commits changes if the working directory is dirty."""
        # Check for uncommitted changes
        stdout, _, _ = await self.runner.run_command(["git", "status", "--porcelain"], check=False)
        if stdout.strip():
            # CRITICAL: Check for unmerged files (conflicts) before committing
            # Codes: DD, AU, UD, UA, DU, AA, UU
            lines = stdout.splitlines()
            conflict_codes = {"DD", "AU", "UD", "UA", "DU", "AA", "UU"}
            for line in lines:
                # Porcelain v1: XY PATH (X=index, Y=worktree)
                if line[:2] in conflict_codes:
                    error_msg = f"Cannot auto-commit due to unresolved conflicts: {line[3:]}. Please resolve specific conflicts before proceeding."
                    raise RuntimeError(error_msg)

            logger.info("Uncommitted changes detected. Auto-committing...")
            await self._run_git(["add", "."])
            await self._run_git(["commit", "-m", message])
            logger.info("✓ Auto-committed changes.")

    async def checkout_pr(self, pr_url: str) -> None:
        """Checks out the Pull Request branch using GitHub CLI."""
        logger.info(f"Checking out PR: {pr_url}...")
        # Use force=True to overwrite any local divergence (e.g. from auto-commits)
        await self.smart_checkout(pr_url, is_pr=True, force=True)

        logger.info("Pulling latest commits from PR...")
        try:
            await self._run_git(["pull"])
        except Exception as e:
            logger.warning(f"Could not pull latest commits: {e}")
        logger.info(f"Checked out PR {pr_url} successfully.")

    async def get_pr_base_branch(self, pr_url: str) -> str:
        """
        Gets the base branch name for a given PR URL.
        Useful for determining the correct diff target.
        """
        try:
            # gh pr view <url> --json baseRefName -q .baseRefName
            stdout, _, _ = await self.runner.run_command(
                [self.gh_cmd, "pr", "view", pr_url, "--json", "baseRefName", "-q", ".baseRefName"],
                check=True,
            )
            base_branch = str(stdout).strip()
            if base_branch:
                return base_branch
            logger.warning(f"Could not determine base branch for PR {pr_url}, defaulting to main")
            return "main"  # noqa: TRY300
        except Exception as e:
            logger.warning(f"Failed to get PR base branch: {e}")
            return "main"

    async def checkout_branch(self, branch_name: str, force: bool = False) -> None:
        """Checks out an existing branch."""
        with contextlib.suppress(Exception):
            await self._run_git(["fetch"])

        logger.info(f"Checking out branch: {branch_name}...")
        await self.smart_checkout(branch_name, is_pr=False, force=force)

    async def ensure_clean_state(self, force_stash: bool = False) -> None:
        """Ensures the working directory is clean."""
        await self._auto_commit_if_dirty("Auto-save before workflow run")

    async def commit_changes(self, message: str) -> bool:
        """Stages and commits all changes."""
        await self._run_git(["add", "."])
        status = await self._run_git(["status", "--porcelain"])
        if not status:
            return False
        await self._run_git(["commit", "-m", message])
        return True

    async def pull_changes(self) -> None:
        """Pulls changes from the remote repository using rebase."""
        logger.info("Pulling latest changes (rebase)...")
        await self._run_git(["pull", "--rebase"])
        logger.info("Changes pulled successfully.")

    async def push_branch(self, branch: str) -> None:
        """Pushes the specified branch to origin."""
        if os.environ.get("GITHUB_TOKEN"):
            with contextlib.suppress(Exception):
                await self.runner.run_command([self.gh_cmd, "auth", "setup-git"], check=False)

        logger.info(f"Pushing branch {branch} to origin...")
        await self._run_git(["push", "-u", "origin", branch])

    async def get_diff(self, target_branch: str = "main") -> str:
        """Returns the diff between HEAD and target branch."""
        return await self._run_git(["diff", f"{target_branch}...HEAD"])

    async def get_changed_files(self, base_branch: str = "main") -> list[str]:
        """Returns a list of unique file paths that have changed."""
        files = set()
        with contextlib.suppress(Exception):
            out = await self._run_git(["diff", "--name-only", f"{base_branch}...HEAD"], check=False)
            if out:
                files.update(out.splitlines())

        out = await self._run_git(["diff", "--name-only", "--cached"], check=False)
        if out:
            files.update(out.splitlines())

        out = await self._run_git(["diff", "--name-only"], check=False)
        if out:
            files.update(out.splitlines())

        out = await self._run_git(["ls-files", "--others", "--exclude-standard"], check=False)
        if out:
            files.update(out.splitlines())

        return sorted(files)
