from ac_cdd_core.config import settings
from ac_cdd_core.process_runner import ProcessRunner
from ac_cdd_core.utils import logger


class GitManager:
    """
    Manages Git operations for the AC-CDD workflow.
    Uses 'git' and 'gh' CLI commands.
    """

    def __init__(self) -> None:
        self.runner = ProcessRunner()
        self.git_cmd = "git"
        self.gh_cmd = settings.tools.gh_cmd

    async def _run_git(self, args: list[str], check: bool = True) -> str:
        cmd = [self.git_cmd] + args
        stdout, stderr, code = await self.runner.run_command(cmd, check=check)
        if code != 0 and check:
            raise RuntimeError(f"Git command failed: {' '.join(cmd)}\nStderr: {stderr}")
        return stdout.strip()

    async def ensure_clean_state(self) -> None:
        """Ensures the working directory is clean."""
        status = await self._run_git(["status", "--porcelain"])
        if status:
            logger.warning("Working directory is not clean. Stashing changes...")
            await self._run_git(["stash", "push", "-u", "-m", "Auto-stash before Jules run"])

    async def create_working_branch(self, prefix: str, id: str) -> str:
        """
        Creates and checks out a feature branch: feature/{prefix}-{id}.
        """
        branch_name = f"feature/{prefix}-{id}"
        logger.info(f"Switching to branch {branch_name}...")

        # Check if branch exists
        _, _, code = await self.runner.run_command(
            [self.git_cmd, "rev-parse", "--verify", branch_name], check=False
        )

        if code == 0:
            logger.info(f"Branch {branch_name} exists. Checking out...")
            await self._run_git(["checkout", branch_name])
        else:
            # If not, create it
            logger.info(f"Branch does not exist. Creating {branch_name}...")
            await self._run_git(["checkout", "-b", branch_name])

        return branch_name

    async def commit_changes(self, message: str) -> bool:
        """
        Stages and commits all changes.
        Returns True if something was committed, False if empty.
        """
        # Stage all
        await self._run_git(["add", "."])

        # Check if anything to commit
        status = await self._run_git(["status", "--porcelain"])
        if not status:
            logger.info("No changes to commit.")
            return False

        await self._run_git(["commit", "-m", message])
        logger.info(f"Committed: {message}")
        return True

    async def merge_branch(self, target: str, source: str) -> None:
        """
        Merges source into target.
        """
        logger.info(f"Merging {source} into {target}...")

        # Checkout target
        await self._run_git(["checkout", target])

        # Merge
        try:
            await self._run_git(["merge", source])
        except RuntimeError as e:
            logger.error(f"Merge conflict detected: {e}")
            await self._run_git(["merge", "--abort"], check=False)
            raise RuntimeError(f"Merge conflict between {source} and {target}. Aborted.") from e

    async def get_current_branch(self) -> str:
        return await self._run_git(["rev-parse", "--abbrev-ref", "HEAD"])

    async def get_remote_url(self) -> str:
        """Returns the URL of the 'origin' remote."""
        return await self._run_git(["config", "--get", "remote.origin.url"])

    async def get_diff(self, target_branch: str = "main") -> str:
        """Returns the diff between HEAD and target branch."""
        return await self._run_git(["diff", f"{target_branch}...HEAD"])

    async def get_changed_files(self, base_branch: str = "main") -> list[str]:
        """
        Returns a list of unique file paths that have changed
        (Committed, Staged, Unstaged, Untracked).
        """
        files = set()

        # 1. Diff against base branch (Committed vs Base)
        try:
            out = await self._run_git(["diff", "--name-only", f"{base_branch}...HEAD"], check=False)
            if out:
                files.update(out.splitlines())
        except Exception:
            # Ignore errors if branch reference doesn't exist yet
            logger.debug("Diff check failed (likely no base branch yet).")

        # 2. Staged
        out = await self._run_git(["diff", "--name-only", "--cached"], check=False)
        if out:
            files.update(out.splitlines())

        # 3. Unstaged
        out = await self._run_git(["diff", "--name-only"], check=False)
        if out:
            files.update(out.splitlines())

        # 4. Untracked
        out = await self._run_git(["ls-files", "--others", "--exclude-standard"], check=False)
        if out:
            files.update(out.splitlines())

        return sorted(list(files))

    async def merge_pr(self, pr_url: str) -> None:
        """
        Merges a Pull Request using GitHub CLI.
        """
        logger.info(f"Merging PR: {pr_url}...")
        try:
            await self.runner.run_command(
                [self.gh_cmd, "pr", "merge", pr_url, "--merge", "--delete-branch"],
                check=True,
            )
            logger.info("PR merged successfully.")
        except Exception as e:
            logger.warning(f"Failed to auto-merge PR. Please merge manually. Error: {e}")

    async def checkout_pr(self, pr_url: str) -> None:
        """
        Checks out the Pull Request branch using GitHub CLI.
        """
        logger.info(f"Checking out PR: {pr_url}...")
        _, _, code = await self.runner.run_command(
            [self.gh_cmd, "pr", "checkout", pr_url, "--force"],
            check=True,
        )
        if code != 0:
            raise RuntimeError(f"Failed to checkout PR {pr_url}")
        logger.info(f"Checked out PR {pr_url} successfully.")

    async def pull_changes(self) -> None:
        """
        Pulls changes from the remote repository.
        """
        logger.info("Pulling latest changes...")
        await self._run_git(["pull"])
        logger.info("Changes pulled successfully.")

    async def push_branch(self, branch: str) -> None:
        """Pushes the specified branch to origin."""
        logger.info(f"Pushing branch {branch} to origin...")
        await self._run_git(["push", "-u", "origin", branch])
