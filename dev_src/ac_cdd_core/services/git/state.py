import asyncio
import tempfile
from pathlib import Path

from ac_cdd_core.utils import logger

from .base import BaseGitManager


class GitStateMixin(BaseGitManager):
    """Mixin for management of isolated state branch."""

    STATE_BRANCH = (
        "ac_cdd_core/state"  # Keeping consistent with previous name if possible, or using new one?
    )
    # Original was "ac-cdd/state". Let's duplicate it to be safe.
    STATE_BRANCH_NAME = "ac-cdd/state"

    async def ensure_state_branch(self) -> None:
        """Ensures the orphan branch exists."""
        _, _, code = await self.runner.run_command(
            [self.git_cmd, "rev-parse", "--verify", self.STATE_BRANCH_NAME], check=False
        )
        if code == 0:
            return

        logger.info(f"Checking remote for {self.STATE_BRANCH_NAME}...")
        await self._run_git(
            ["fetch", "origin", f"{self.STATE_BRANCH_NAME}:{self.STATE_BRANCH_NAME}"], check=False
        )

        _, _, code = await self.runner.run_command(
            [self.git_cmd, "rev-parse", "--verify", self.STATE_BRANCH_NAME], check=False
        )
        if code == 0:
            return

        logger.info(f"Creating orphan branch: {self.STATE_BRANCH_NAME}")
        with tempfile.TemporaryDirectory():
            process = await asyncio.create_subprocess_exec(
                self.git_cmd,
                "mktree",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate(input=b"")
            if process.returncode != 0:
                err_msg = f"git mktree failed: {stderr.decode()}"
                raise RuntimeError(err_msg)

            empty_tree = stdout.decode().strip()
            process = await asyncio.create_subprocess_exec(
                self.git_cmd,
                "commit-tree",
                empty_tree,
                "-m",
                "Initial state branch",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                err_msg = f"git commit-tree failed: {stderr.decode()}"
                raise RuntimeError(err_msg)

            commit_hash = stdout.decode().strip()
            await self._run_git(
                ["update-ref", f"refs/heads/{self.STATE_BRANCH_NAME}", commit_hash], check=True
            )

    async def read_state_file(self, filename: str) -> str | None:
        """Reads a file from the state branch."""
        try:
            content, _, code = await self.runner.run_command(
                [self.git_cmd, "show", f"{self.STATE_BRANCH_NAME}:{filename}"], check=False
            )
            return str(content) if code == 0 else None
        except Exception:
            return None

    async def save_state_file(self, filename: str, content: str, message: str) -> None:
        """Saves a file to the state branch using a temporary worktree."""
        await self.ensure_state_branch()
        with tempfile.TemporaryDirectory() as tmp_dir:
            try:
                await self._run_git(
                    ["worktree", "add", tmp_dir, self.STATE_BRANCH_NAME], check=True
                )
            except RuntimeError:
                await self._run_git(["worktree", "prune"], check=False)
                await self._run_git(
                    ["worktree", "add", "-f", tmp_dir, self.STATE_BRANCH_NAME], check=True
                )

            try:
                file_path = Path(tmp_dir) / filename
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding="utf-8")
                await self._run_git(["-C", tmp_dir, "add", filename], check=True)

                status, _, _ = await self.runner.run_command(
                    [self.git_cmd, "-C", tmp_dir, "status", "--porcelain"], check=False
                )
                if status.strip():
                    await self._run_git(["-C", tmp_dir, "commit", "-m", message], check=True)
                    await self._run_git(
                        ["-C", tmp_dir, "push", "origin", self.STATE_BRANCH_NAME], check=False
                    )
            finally:
                await self._run_git(["worktree", "remove", "--force", tmp_dir], check=False)
