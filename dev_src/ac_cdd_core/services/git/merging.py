import contextlib
from pathlib import Path

from ac_cdd_core.messages import RecoveryMessages
from ac_cdd_core.utils import logger

from .base import BaseGitManager


class GitMergingMixin(BaseGitManager):
    """Mixin for Git merging and PR operations."""

    async def _ensure_no_pending_merge(self) -> None:
        """Aborts any pending merge to ensure clean index."""
        # Check if MERGE_HEAD exists (indicates merge in progress)
        merge_head = Path.cwd() / ".git" / "MERGE_HEAD"
        if merge_head.exists():
            logger.warning("Pending merge detected. Aborting to clean index...")
            try:
                await self._run_git(["merge", "--abort"], check=False)
            except Exception as e:
                logger.warning(f"Failed to abort merge: {e}")
                # Try hard reset if abort fails? No, too dangerous.
                # Just removing the file might leave index dirty.

        # Also ensure no cherry-pick or revert in progress
        for fname in ["CHERRY_PICK_HEAD", "REVERT_HEAD"]:
            fpath = Path.cwd() / ".git" / fname
            if fpath.exists():
                logger.warning(f"Pending {fname} detected. Aborting...")
                await self._run_git(["quit"], check=False)  # 'quit' works for cherry-pick/revert

    async def merge_branch(self, target: str, source: str) -> None:
        """Merges source into target."""
        logger.info(f"Merging {source} into {target}...")
        original_branch = await self.get_current_branch()  # type: ignore

        await self._run_git(["checkout", target])

        try:
            await self._run_git(["merge", source])
        except RuntimeError as e:
            logger.error(f"Merge conflict detected: {e}")
            await self._run_git(["merge", "--abort"], check=False)

            with contextlib.suppress(Exception):
                await self._run_git(["checkout", original_branch])

            error_msg = RecoveryMessages.merge_conflict(source, target, original_branch)
            raise RuntimeError(error_msg) from e

    async def merge_pr(self, pr_number: int | str, method: str = "squash") -> None:
        """
        Merge PR using gh CLI with auto-merge capability.
        Automatically converts Draft PRs to Ready before merging.
        """
        pr = str(pr_number)

        # 0. Ensure no pending merge conflict state exists
        await self._ensure_no_pending_merge()

        # 1. Check if Draft and mark ready if needed
        try:
            stdout, _, code = await self.runner.run_command(
                [self.gh_cmd, "pr", "view", pr, "--json", "isDraft", "--jq", ".isDraft"],
                check=False,
            )
            if code == 0 and stdout.strip() == "true":
                logger.info(f"PR {pr} is a draft. Marking as ready for review...")
                await self.runner.run_command([self.gh_cmd, "pr", "ready", pr], check=True)
        except Exception as e:
            logger.warning(f"Failed to check/update PR draft status: {e}")

        # 2. Merge
        logger.info(f"Merging PR {pr} using method={method}")

        cmd_immediate = [
            self.gh_cmd,
            "pr",
            "merge",
            pr,
            f"--{method}",
            "--delete-branch",
        ]

        stdout, stderr, code = await self.runner.run_command(cmd_immediate, check=False)

        if code == 0:
            logger.info(f"Successfully merged PR {pr} immediately")
            return

        fallback_keywords = [
            "status check",
            "review",
            "protected",
            "requirement",
            "blocking",
            "wait",
        ]

        if any(keyword in stderr.lower() for keyword in fallback_keywords):
            logger.info(f"Immediate merge failed ({stderr.strip()}). Attempting auto-merge...")
            cmd_auto = [self.gh_cmd, "pr", "merge", pr, f"--{method}", "--auto", "--delete-branch"]
            _, stderr_auto, code_auto = await self.runner.run_command(cmd_auto, check=True)

            if code_auto == 0:
                logger.info(f"Successfully enabled auto-merge for PR {pr}")
                return

            msg = f"Failed to auto-merge PR {pr}: {stderr_auto}"
            raise RuntimeError(msg)

        msg = f"Failed to merge PR {pr}: {stderr}"
        raise RuntimeError(msg)

    async def create_final_pr(self, integration_branch: str, title: str, body: str) -> str:
        """Creates final PR from integration branch to main."""
        logger.info(f"Creating final PR: {integration_branch} → main")

        stdout, _, code = await self.runner.run_command(
            [
                self.gh_cmd,
                "pr",
                "list",
                "--head",
                integration_branch,
                "--base",
                "main",
                "--json",
                "url",
                "--jq",
                ".[0].url",
            ],
            check=False,
        )

        if code == 0 and stdout.strip():
            existing_pr_url = str(stdout.strip())
            logger.info(f"PR already exists: {existing_pr_url}")
            return existing_pr_url

        await self._run_git(["checkout", integration_branch])

        try:
            await self._run_git(["pull"])
        except RuntimeError as e:
            logger.warning(f"Pull failed before push (proceeding anyway): {e}")

        await self._run_git(["push"])

        stdout, _, code = await self.runner.run_command(
            [
                self.gh_cmd,
                "pr",
                "create",
                "--base",
                "main",
                "--head",
                integration_branch,
                "--title",
                title,
                "--body",
                body,
            ],
            check=True,
        )

        if code != 0:
            errmsg = f"Failed to create PR: {stdout or 'Unknown error'}"
            raise RuntimeError(errmsg)

        pr_url = str(stdout.strip())
        logger.info(f"Final PR created: {pr_url}")
        return pr_url
