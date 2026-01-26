from ac_cdd_core.utils import logger

from .base import BaseGitManager


class GitBranchingMixin(BaseGitManager):
    """Mixin for Git branching logic."""

    async def get_current_branch(self) -> str:
        try:
            return await self._run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        except RuntimeError:
            return "main"

    async def get_remote_url(self) -> str:
        """Returns the URL of the 'origin' remote."""
        return await self._run_git(["config", "--get", "remote.origin.url"])

    async def create_working_branch(self, prefix: str, branch_id: str) -> str:
        """
        Creates and checks out a feature branch: feature/{prefix}-{branch_id}.
        """
        branch_name = f"feature/{prefix}-{branch_id}"
        logger.info(f"Switching to branch {branch_name}...")

        # Check if branch exists
        _, _, code = await self.runner.run_command(
            [self.git_cmd, "rev-parse", "--verify", branch_name], check=False
        )

        if code == 0:
            logger.info(f"Branch {branch_name} exists. Checking out...")
            await self._run_git(["checkout", branch_name])
        else:
            logger.info(f"Branch does not exist. Creating {branch_name}...")
            await self._run_git(["checkout", "-b", branch_name])

        return branch_name

    async def create_integration_branch(
        self, session_id: str, prefix: str = "dev", branch_name: str | None = None
    ) -> str:
        """Creates integration branch from main for the session."""
        integration_branch = branch_name if branch_name else f"{prefix}/{session_id}/integration"
        logger.info(f"Creating integration branch: {integration_branch}")

        await self._run_git(["checkout", "main"])
        await self._run_git(["pull"])

        _, _, code = await self.runner.run_command(
            [self.git_cmd, "rev-parse", "--verify", integration_branch], check=False
        )

        if code == 0:
            logger.info(f"Integration branch {integration_branch} exists. Checking out...")
            await self._run_git(["checkout", integration_branch])
            await self._run_git(["pull"])
        else:
            logger.info(f"Creating new integration branch: {integration_branch}")
            await self._run_git(["checkout", "-b", integration_branch])
            await self._run_git(["push", "-u", "origin", integration_branch])

        return integration_branch

    async def create_feature_branch(self, branch_name: str, from_branch: str = "main") -> str:
        """Creates and checks out a new feature branch from the specified base branch."""
        logger.info(f"Creating feature branch: {branch_name} from {from_branch}")

        # Ensure we're on the base branch and it's up to date
        await self._run_git(["checkout", from_branch])
        await self._run_git(["pull"])

        # Create or checkout the new branch
        # Check if exists first
        _, _, code = await self.runner.run_command(
            [self.git_cmd, "rev-parse", "--verify", branch_name], check=False
        )
        if code == 0:
            logger.info(f"Feature branch {branch_name} already exists. Checking out...")
            await self._run_git(["checkout", branch_name])
            # Optional: Pull if it tracks remote
            import contextlib
            with contextlib.suppress(Exception):
                await self._run_git(["pull"])
        else:
            await self._run_git(["checkout", "-b", branch_name])
            # Push the branch to origin
            await self._run_git(["push", "-u", "origin", branch_name])

        logger.info(f"Created and pushed feature branch: {branch_name}")
        return branch_name

    async def create_session_branch(
        self, session_id: str, branch_type: str, branch_id: str, integration_branch: str
    ) -> str:
        """Creates a session-scoped branch from integration branch."""
        branch_name = f"dev/{session_id}/{branch_type}{branch_id}"
        logger.info(f"Creating session branch: {branch_name} from {integration_branch}")

        await self._run_git(["checkout", integration_branch])
        await self._run_git(["pull"])

        _, _, code = await self.runner.run_command(
            [self.git_cmd, "rev-parse", "--verify", branch_name], check=False
        )

        if code == 0:
            logger.info(f"Session branch {branch_name} exists. Checking out...")
            await self._run_git(["checkout", branch_name])
        else:
            logger.info(f"Creating new session branch: {branch_name}")
            await self._run_git(["checkout", "-b", branch_name])

        return branch_name

    async def validate_remote_branch(self, branch: str) -> tuple[bool, str]:
        """Validate that branch exists on remote and is up-to-date."""
        stdout, _, code = await self.runner.run_command(
            ["git", "ls-remote", "--heads", "origin", branch],
            check=False,
        )

        if code != 0 or not stdout.strip():
            return False, f"Branch '{branch}' does not exist on remote 'origin'"

        try:
            await self._run_git(["fetch", "origin", branch])
            local_hash = await self._run_git(["rev-parse", branch])
            remote_hash = await self._run_git(["rev-parse", f"origin/{branch}"])

            if local_hash != remote_hash:
                merge_base = await self._run_git(["merge-base", branch, f"origin/{branch}"])
                if merge_base == local_hash:
                    return False, (
                        f"Branch '{branch}' is behind remote.\n"
                        f"Pull latest changes: git pull origin {branch}"
                    )
                if merge_base == remote_hash:
                    logger.warning(f"Branch '{branch}' is ahead of remote (unpushed commits)")
                else:
                    return False, (
                        f"Branch '{branch}' has diverged from remote.\n"
                        f"Resolve divergence before proceeding."
                    )
        except Exception as e:
            logger.warning(f"Could not validate remote branch state: {e}")

        return True, ""
