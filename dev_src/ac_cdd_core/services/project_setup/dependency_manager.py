from pathlib import Path

from ac_cdd_core.process_runner import ProcessRunner
from ac_cdd_core.services.git_ops import GitManager
from ac_cdd_core.utils import logger


class DependencyManager:
    """Manages project dependencies and git initialization."""

    def __init__(self) -> None:
        self.runner = ProcessRunner()
        self.git = GitManager()

    async def initialize_dependencies_and_git(self) -> None:
        if not (Path.cwd() / "pyproject.toml").exists():
            logger.info("Initializing pyproject.toml...")
            await self.runner.run_command(["uv", "init", "--no-workspace"], check=False)

        logger.info("Installing development dependencies (ruff, mypy, pytest)...")
        try:
            await self.runner.run_command(
                ["uv", "add", "--dev", "ruff", "mypy", "pytest", "pytest-cov"], check=True
            )
            logger.info("✓ Dependencies installed successfully.")
        except Exception as e:
            logger.warning(f"Failed to install dependencies: {e}")

        if not (Path.cwd() / ".git").exists():
            logger.info("Initializing Git repository...")
            await self.runner.run_command(["git", "init"], check=True)

        try:
            await self.git._run_git(["add", "."])

            if await self.git.commit_changes(
                "Initialize project with AC-CDD structure and dev dependencies"
            ):
                logger.info("✓ Changes committed.")

                try:
                    remote_url = await self.git.get_remote_url()
                    if remote_url:
                        current_branch = await self.git.get_current_branch()
                        logger.info(f"Pushing {current_branch} to origin...")
                        await self.git.push_branch(current_branch)
                        logger.info("✓ Successfully pushed to remote.")
                    else:
                        logger.info("No remote 'origin' configured. Skipping push.")
                except Exception as e:
                    logger.warning(f"Failed to push to remote: {e}")
            else:
                logger.info("No changes to commit.")

        except Exception as e:
            logger.warning(f"Git operations failed: {e}")

    async def sync_dependencies(self) -> None:
        """Syncs dependencies using uv."""
        logger.info("[ProjectManager] Syncing dependencies...")
        try:
            await self.runner.run_command(["uv", "sync", "--dev"], check=True)

            _, _, code_ruff = await self.runner.run_command(
                ["uv", "run", "ruff", "--version"], check=False
            )
            _, _, code_mypy = await self.runner.run_command(
                ["uv", "run", "mypy", "--version"], check=False
            )

            if code_ruff != 0 or code_mypy != 0:
                logger.info("[ProjectManager] Installing missing linters...")
                await self.runner.run_command(["uv", "add", "--dev", "ruff", "mypy"], check=True)

            logger.info("[ProjectManager] Environment prepared.")
        except Exception as e:
            logger.warning(f"[ProjectManager] Dependency sync failed: {e}")
