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
            await self._run_git(["stash", "push", "-m", "Auto-stash before Jules run"])

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

    async def get_diff(self, target_branch: str = "main") -> str:
        """Returns the diff between HEAD and target branch."""
        return await self._run_git(["diff", f"{target_branch}...HEAD"])
