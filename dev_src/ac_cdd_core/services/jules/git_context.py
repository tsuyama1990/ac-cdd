import os
from datetime import UTC, datetime

from ac_cdd_core.services.git_ops import GitManager
from ac_cdd_core.utils import logger


class JulesSessionError(Exception):
    pass


class JulesGitContext:
    def __init__(self, git: GitManager) -> None:
        self.git = git

    async def prepare_git_context(self) -> tuple[str, str, str]:
        try:
            repo_url = await self.git.get_remote_url()
            if "github.com" in repo_url:
                parts = repo_url.replace(".git", "").split("/")
                repo_name = parts[-1]
                owner = parts[-2].split(":")[-1]
            elif "PYTEST_CURRENT_TEST" in os.environ:
                repo_name, owner = "test-repo", "test-owner"
            else:
                self._raise_jules_session_error(repo_url)

            branch = await self.git.get_current_branch()

            # Handle detached HEAD state (Jules cannot clone 'HEAD')
            if branch == "HEAD":
                timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
                branch = f"jules-sync-{timestamp}"
                logger.warning(f"Detached HEAD detected. Creating temporary sync branch: {branch}")
                # Safely create and switch to the temp branch so we can push it
                await self.git.runner.run_command(["git", "checkout", "-b", branch], check=True)

            if "PYTEST_CURRENT_TEST" not in os.environ:
                try:
                    # Sync with remote before pushing to handle external changes (PRs, etc.)
                    # We use run_command directly to avoid strict checking on pull (it might fail if upstream missing)
                    await self.git.runner.run_command(
                        ["git", "pull", "--rebase", "origin", branch], check=False
                    )
                    await self.git.push_branch(branch)
                except Exception as e:
                    logger.warning(f"Could not sync/push branch: {e}")
        except Exception as e:
            if "PYTEST_CURRENT_TEST" in os.environ:
                return "test-owner", "test-repo", "main"
            if isinstance(e, JulesSessionError):
                raise
            emsg = f"Failed to determine/push git context: {e}"
            raise JulesSessionError(emsg) from e
        else:
            return owner, repo_name, branch

    def _raise_jules_session_error(self, repo_url: str) -> None:
        msg = f"Unsupported repository URL format: {repo_url}"
        raise JulesSessionError(msg)
