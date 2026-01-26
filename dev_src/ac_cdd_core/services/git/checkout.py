import contextlib
import os

from ac_cdd_core.utils import logger

from .base import BaseGitManager


class GitCheckoutMixin(BaseGitManager):
    """Mixin for Git checkout and stash operations."""

    async def smart_checkout(self, target: str, is_pr: bool = False, force: bool = False) -> None:
        """Robust checkout that handles local changes."""
        stashed = await self._stash_changes()

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
            if stashed:
                logger.warning("Checkout failed. Restoring local changes...")
                with contextlib.suppress(Exception):
                    await self._run_git(["stash", "pop"])

                await self._ensure_no_lock()

            logger.error(
                f"Failed to checkout '{target}'. Please stash/commit your changes or use --force."
            )
            raise

        if stashed:
            await self._restore_stash()

    async def _stash_changes(self) -> bool:
        """Checks for uncommitted changes and stashes them if found."""
        status = await self._run_git(["status", "--porcelain"])
        if status:
            logger.info("Uncommitted changes detected. Performing smart checkout...")
            await self._run_git(["stash", "push", "-u", "-m", "AC-CDD Auto-stash for checkout"])
            return True
        return False

    async def _restore_stash(self) -> None:
        """Restores stashed changes, resolving session file conflicts."""
        logger.info("Restoring local changes...")
        try:
            await self._run_git(["stash", "pop"])
        except RuntimeError:
            logger.warning("Conflict detected during stash restoration.")
            await self._resolve_session_conflict()

    async def _resolve_session_conflict(self) -> None:
        """Resolves conflicts specifically for .ac_cdd_session.json."""
        try:
            logger.info("Auto-resolving .ac_cdd_session.json to local version...")
            await self._run_git(["checkout", "stash@{0}", "--", ".ac_cdd_session.json"])
            await self._run_git(["add", ".ac_cdd_session.json"])

            status = await self._run_git(["status", "--porcelain"])
            if "UU" in status:
                logger.warning("Other conflicts exist. Please resolve them manually.")
            else:
                await self._run_git(["stash", "drop"])
                logger.info("Stash dropped after resolution.")

        except Exception as ex:
            logger.error(f"Failed to auto-resolve session file: {ex}")
            raise

    async def checkout_pr(self, pr_url: str) -> None:
        """Checks out the Pull Request branch using GitHub CLI."""
        logger.info(f"Checking out PR: {pr_url}...")
        await self.smart_checkout(pr_url, is_pr=True)

        logger.info("Pulling latest commits from PR...")
        try:
            await self._run_git(["pull"])
        except Exception as e:
            logger.warning(f"Could not pull latest commits: {e}")
        logger.info(f"Checked out PR {pr_url} successfully.")

    async def checkout_branch(self, branch_name: str, force: bool = False) -> None:
        """Checks out an existing branch."""
        with contextlib.suppress(Exception):
            await self._run_git(["fetch"])

        logger.info(f"Checking out branch: {branch_name}...")
        await self.smart_checkout(branch_name, is_pr=False, force=force)

    async def ensure_clean_state(self, force_stash: bool = False) -> None:
        """Ensures the working directory is clean."""
        status = await self._run_git(["status", "--porcelain"])
        if status:
            if not force_stash:
                logger.warning(
                    "Working directory has uncommitted changes.\n"
                    "These changes will be stashed before proceeding."
                )
            logger.info("Stashing uncommitted changes...")
            await self._run_git(["stash", "push", "-u", "-m", "Auto-stash before workflow run"])

    async def commit_changes(self, message: str) -> bool:
        """Stages and commits all changes."""
        await self._run_git(["add", "."])
        status = await self._run_git(["status", "--porcelain"])
        if not status:
            return False
        await self._run_git(["commit", "-m", message])
        return True

    async def pull_changes(self) -> None:
        """Pulls changes from the remote repository."""
        logger.info("Pulling latest changes...")
        await self._run_git(["pull"])
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
