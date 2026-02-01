from pathlib import Path

from ac_cdd_core.config import settings
from ac_cdd_core.process_runner import ProcessRunner
from ac_cdd_core.utils import logger


class BaseGitManager:
    """Base class for Git operations."""

    def __init__(self) -> None:
        self.runner = ProcessRunner()
        self.git_cmd = "git"
        self.gh_cmd = settings.tools.gh_cmd

    async def _ensure_no_lock(self) -> None:
        """Removes stale index.lock file if it exists."""
        lock_file = Path.cwd() / ".git" / "index.lock"
        if lock_file.exists():
            try:
                # We assume single-threaded git access in this agent context.
                lock_file.unlink()
                logger.warning("Removed stale .git/index.lock file")
            except OSError as e:
                logger.warning(f"Could not remove .git/index.lock: {e}")

    async def _run_git(self, args: list[str], check: bool = True) -> str:
        # Check for lock before running any command
        await self._ensure_no_lock()

        cmd = [self.git_cmd, *args]
        stdout, stderr, code = await self.runner.run_command(cmd, check=check)
        if code != 0 and check:
            msg = f"Git command failed: {' '.join(cmd)}\nStderr: {stderr}"
            raise RuntimeError(msg)
        return str(stdout.strip())

    async def get_current_commit(self) -> str:
        """Returns the current commit hash (HEAD)."""
        stdout, _, _ = await self.runner.run_command(
            [self.git_cmd, "rev-parse", "HEAD"], check=True
        )
        return str(stdout).strip()
