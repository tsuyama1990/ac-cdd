import asyncio
import contextlib
import os
import tempfile
from pathlib import Path

from ac_cdd_core.config import settings
from ac_cdd_core.messages import RecoveryMessages
from ac_cdd_core.process_runner import ProcessRunner
from ac_cdd_core.utils import logger


class GitManager:
    """
    Manages Git operations for the AC-CDD workflow.
    Uses 'git' and 'gh' CLI commands.
    """

    STATE_BRANCH = "ac-cdd/state"

    def __init__(self) -> None:
        self.runner = ProcessRunner()
        self.git_cmd = "git"
        self.gh_cmd = settings.tools.gh_cmd

    async def _run_git(self, args: list[str], check: bool = True) -> str:
        cmd = [self.git_cmd, *args]
        stdout, stderr, code = await self.runner.run_command(cmd, check=check)
        if code != 0 and check:
            msg = f"Git command failed: {' '.join(cmd)}\nStderr: {stderr}"
            raise RuntimeError(msg)
        return str(stdout.strip())

    async def ensure_clean_state(self, force_stash: bool = False) -> None:
        """Ensures the working directory is clean."""
        status = await self._run_git(["status", "--porcelain"])
        if status:
            if not force_stash:
                logger.warning(
                    "Working directory has uncommitted changes.\n"
                    "These changes will be stashed before proceeding.\n"
                    "To recover them later, use: git stash pop"
                )

            logger.info("Stashing uncommitted changes...")
            await self._run_git(["stash", "push", "-u", "-m", "Auto-stash before workflow run"])
            logger.info("Changes stashed. Use 'git stash pop' to recover them.")

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

    async def commit_changes(self, message: str) -> bool:
        """
        Stages and commits all changes.
        Returns True if something was committed, False if empty.
        """
        await self._run_git(["add", "."])

        status = await self._run_git(["status", "--porcelain"])
        if not status:
            logger.info("No changes to commit.")
            return False

        await self._run_git(["commit", "-m", message])
        logger.info(f"Committed: {message}")
        return True

    async def merge_branch(self, target: str, source: str) -> None:
        """Merges source into target."""
        logger.info(f"Merging {source} into {target}...")
        original_branch = await self.get_current_branch()

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

    async def get_current_branch(self) -> str:
        try:
            return await self._run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        except RuntimeError:
            return "main"

    async def get_remote_url(self) -> str:
        """Returns the URL of the 'origin' remote."""
        return await self._run_git(["config", "--get", "remote.origin.url"])

    async def get_diff(self, target_branch: str = "main") -> str:
        """Returns the diff between HEAD and target branch."""
        return await self._run_git(["diff", f"{target_branch}...HEAD"])

    async def get_changed_files(self, base_branch: str = "main") -> list[str]:
        """Returns a list of unique file paths that have changed."""
        files = set()

        try:
            out = await self._run_git(["diff", "--name-only", f"{base_branch}...HEAD"], check=False)
            if out:
                files.update(out.splitlines())
        except Exception:
            logger.debug("Diff check failed (likely no base branch yet).")

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
            logger.info(".ac_cdd_session.json resolved.")

            status = await self._run_git(["status", "--porcelain"])
            if "UU" in status:
                logger.warning(
                    "Other conflicts exist. Please resolve them manually.\n"
                    "Local changes have been applied but conflicted."
                )
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

        # CRITICAL: Pull latest commits after checkout
        # Jules may have updated the PR with new commits
        logger.info("Pulling latest commits from PR...")
        try:
            await self._run_git(["pull"])
            logger.info("Successfully pulled latest commits")
        except Exception as e:
            logger.warning(f"Could not pull latest commits: {e}")

        logger.info(f"Checked out PR {pr_url} successfully.")

    async def checkout_branch(self, branch_name: str, force: bool = False) -> None:
        """Checks out an existing branch."""
        with contextlib.suppress(Exception):
            await self._run_git(["fetch"])

        logger.info(f"Checking out branch: {branch_name}...")
        await self.smart_checkout(branch_name, is_pr=False, force=force)

    async def pull_changes(self) -> None:
        """Pulls changes from the remote repository."""
        logger.info("Pulling latest changes...")
        await self._run_git(["pull"])
        logger.info("Changes pulled successfully.")

    async def push_branch(self, branch: str) -> None:
        """Pushes the specified branch to origin."""
        # Ensure authentication is set up if using GITHUB_TOKEN
        if os.environ.get("GITHUB_TOKEN"):
            try:
                # This configures git to use 'gh' as the credential helper
                await self.runner.run_command([self.gh_cmd, "auth", "setup-git"], check=False)
            except Exception as e:
                logger.debug(f"Failed to setup gh auth: {e}")

        logger.info(f"Pushing branch {branch} to origin...")
        await self._run_git(["push", "-u", "origin", branch])

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

        # Create and checkout the new branch
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

    async def merge_pr(self, pr_number: int | str, method: str = "squash") -> None:
        """
        Merge PR using gh CLI with auto-merge capability.
        Automatically converts Draft PRs to Ready before merging.

        Args:
            pr_number: PR number or URL
            method: Merge method ('squash', 'merge', or 'rebase')
        """
        pr = str(pr_number)

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
            # Continue to merge attempt anyway

        # 2. Merge
        logger.info(f"Merging PR {pr} using method={method}")

        # Strategy: Try Immediate Merge first (no --auto)
        # If it fails due to branch protection rules (CI/Reviews pending), fallback to --auto.

        cmd_immediate = [
            self.gh_cmd,
            "pr",
            "merge",
            pr,
            f"--{method}",
            "--delete-branch",
        ]

        # Use check=False to handle errors manually
        stdout, stderr, code = await self.runner.run_command(cmd_immediate, check=False)

        if code == 0:
            logger.info(f"Successfully merged PR {pr} immediately")
            return

        # Check if failure allows for auto-merge fallback
        # Typical errors: "status checks have not passed", "review is required"
        fallback_keywords = [
            "status check",
            "review",
            "protected",
            "requirement",
            "blocking",
            "wait",
        ]

        # Determine if we should try auto-merge
        should_fallback = any(keyword in stderr.lower() for keyword in fallback_keywords)

        if should_fallback:
            logger.info(f"Immediate merge failed ({stderr.strip()}). Attempting auto-merge...")
            cmd_auto = [
                self.gh_cmd,
                "pr",
                "merge",
                pr,
                f"--{method}",
                "--auto",
                "--delete-branch",
            ]
            _, stderr_auto, code_auto = await self.runner.run_command(cmd_auto, check=True)

            if code_auto == 0:
                logger.info(f"Successfully enabled auto-merge for PR {pr}")
                return

            # If auto-merge also fails
            msg = f"Failed to auto-merge PR {pr}: {stderr_auto}"
            raise RuntimeError(msg)

        # Fatal error (Conflict, Permission, etc.)
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

    async def ensure_state_branch(self) -> None:
        """
        Ensures the orphan branch 'ac-cdd/state' exists.
        It first checks locally, then tries to fetch from remote.
        If neither exists, it creates it cleanly without affecting the current worktree.
        """
        # 1. Check if local branch exists
        _, _, code = await self.runner.run_command(
            [self.git_cmd, "rev-parse", "--verify", self.STATE_BRANCH], check=False
        )
        if code == 0:
            return  # Exists locally

        # 2. Try to fetch from origin
        logger.info(f"Checking remote for {self.STATE_BRANCH}...")
        await self._run_git(
            ["fetch", "origin", f"{self.STATE_BRANCH}:{self.STATE_BRANCH}"], check=False
        )

        # Check again after fetch
        _, _, code = await self.runner.run_command(
            [self.git_cmd, "rev-parse", "--verify", self.STATE_BRANCH], check=False
        )
        if code == 0:
            logger.info(f"Fetched {self.STATE_BRANCH} from remote.")
            return

        # 3. Create orphan branch if not found anywhere
        logger.info(f"Creating orphan branch: {self.STATE_BRANCH}")

        with tempfile.TemporaryDirectory():
            # Create an empty tree object using asyncio directly (ProcessRunner doesn't support stdin)
            process = await asyncio.create_subprocess_exec(
                self.git_cmd,
                "mktree",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate(input=b"")
            if process.returncode != 0:
                error_msg = f"git mktree failed: {stderr.decode()}"
                raise RuntimeError(error_msg)
            empty_tree = stdout.decode().strip()

            # Create a commit object from the empty tree
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
                error_msg = f"git commit-tree failed: {stderr.decode()}"
                raise RuntimeError(error_msg)
            commit_hash = stdout.decode().strip()

            # Update the ref for the new branch
            await self._run_git(
                ["update-ref", f"refs/heads/{self.STATE_BRANCH}", commit_hash], check=True
            )
            logger.info(f"Created {self.STATE_BRANCH} at {commit_hash}")

    async def read_state_file(self, filename: str) -> str | None:
        """Reads a file from the state branch."""
        try:
            content, _, code = await self.runner.run_command(
                [self.git_cmd, "show", f"{self.STATE_BRANCH}:{filename}"], check=False
            )
            if code != 0:
                return None
            return str(content)
        except Exception as e:
            logger.warning(f"Failed to read state file {filename}: {e}")
            return None

    async def save_state_file(self, filename: str, content: str, message: str) -> None:
        """
        Saves a file to the state branch using a temporary worktree.
        This avoids touching the user's main working directory.
        """
        await self.ensure_state_branch()

        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create a worktree for the state branch
            try:
                await self._run_git(["worktree", "add", tmp_dir, self.STATE_BRANCH], check=True)
            except RuntimeError as e:
                # Check if it's already checked out in another worktree
                logger.warning(f"Could not add worktree (maybe locked?): {e}. Retrying with force.")
                # Try to prune/force if needed, or just fail safely
                await self._run_git(["worktree", "prune"], check=False)
                await self._run_git(
                    ["worktree", "add", "-f", tmp_dir, self.STATE_BRANCH], check=True
                )

            try:
                # Write file
                file_path = Path(tmp_dir) / filename
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding="utf-8")

                # Git add & commit inside worktree
                await self._run_git(["-C", tmp_dir, "add", filename], check=True)

                # Check for changes
                status, _, _ = await self.runner.run_command(
                    [self.git_cmd, "-C", tmp_dir, "status", "--porcelain"], check=False
                )
                if status.strip():
                    await self._run_git(["-C", tmp_dir, "commit", "-m", message], check=True)
                    await self._run_git(
                        ["-C", tmp_dir, "push", "origin", self.STATE_BRANCH], check=False
                    )
            finally:
                # Clean up worktree
                await self._run_git(["worktree", "remove", "--force", tmp_dir], check=False)
