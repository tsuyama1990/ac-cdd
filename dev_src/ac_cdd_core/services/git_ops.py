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
        return str(stdout.strip())

    async def ensure_clean_state(self, force_stash: bool = False) -> None:
        """Ensures the working directory is clean.

        Args:
            force_stash: If True, auto-stash without prompting (for --auto mode)
        """
        status = await self._run_git(["status", "--porcelain"])
        if status:
            if not force_stash:
                logger.warning(
                    "Working directory has uncommitted changes.\n"
                    "These changes will be stashed before proceeding.\n"
                    "To recover them later, use: git stash pop"
                )
                # In non-interactive mode, we'll proceed with stash
                # In future, could add interactive prompt here

            logger.info("Stashing uncommitted changes...")
            await self._run_git(["stash", "push", "-u", "-m", "Auto-stash before workflow run"])
            logger.info("Changes stashed. Use 'git stash pop' to recover them.")

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

        # Remember original branch for recovery
        original_branch = await self.get_current_branch()

        # Checkout target
        await self._run_git(["checkout", target])

        # Merge
        try:
            await self._run_git(["merge", source])
        except RuntimeError as e:
            logger.error(f"Merge conflict detected: {e}")
            await self._run_git(["merge", "--abort"], check=False)

            # Return to original branch
            try:
                await self._run_git(["checkout", original_branch])
            except Exception:  # noqa: S110
                pass  # Best effort

            from ac_cdd_core.messages import RecoveryMessages

            error_msg = RecoveryMessages.merge_conflict(source, target, original_branch)
            raise RuntimeError(error_msg) from e

    async def get_current_branch(self) -> str:
        try:
            return await self._run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        except RuntimeError:
            # Likely empty repo with no commits yet. Default to 'main'
            return "main"

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

    async def smart_checkout(self, target: str, is_pr: bool = False, force: bool = False) -> None:
        """
        Robust checkout that handles local changes (e.g., .ac_cdd_session.json).

        Strategy:
        1. Check for dirty state.
        2. If dirty, stash (snapshot).
        3. Checkout target.
        4. Pop stash.
        5. If conflict on .ac_cdd_session.json, force resolve to local (stashed) version.
        """
        stashed = await self._stash_changes()

        try:
            if is_pr:
                # PR Checkout (using gh)
                cmd = [self.gh_cmd, "pr", "checkout", target]
                if force:
                    cmd.append("--force")
                await self.runner.run_command(cmd, check=True)
            else:
                # Normal Branch Checkout
                cmd = ["checkout", target]
                if force:
                    cmd.append("-f")
                await self._run_git(cmd)

        except Exception as e:
            # If checkout failed, try to pop stash to restore state
            if stashed:
                logger.warning("Checkout failed. Restoring local changes...")
                try:
                    await self._run_git(["stash", "pop"])
                except Exception:
                    logger.error("Failed to restore stash after failed checkout.")

            # Log specific advice
            logger.error(
                f"Failed to checkout '{target}'. Please stash/commit your changes or use --force."
            )
            raise e

        if stashed:
            await self._restore_stash()

    async def _stash_changes(self) -> bool:
        """Checks for uncommitted changes and stashes them if found."""
        status = await self._run_git(["status", "--porcelain"])
        if status:
            logger.info("Uncommitted changes detected. Performing smart checkout...")
            # Stash with specific message to identify it
            await self._run_git(["stash", "push", "-u", "-m", "AC-CDD Auto-stash for checkout"])
            return True
        return False

    async def _restore_stash(self) -> None:
        """Restores stashed changes, resolving session file conflicts."""
        logger.info("Restoring local changes...")
        try:
            await self._run_git(["stash", "pop"])
        except RuntimeError:
            # Conflict detected
            logger.warning("Conflict detected during stash restoration.")
            await self._resolve_session_conflict()

    async def _resolve_session_conflict(self) -> None:
        """
        Resolves conflicts specifically for .ac_cdd_session.json by preferring the stashed version.
        """
        # Check for .ac_cdd_session.json conflict specifically
        # Logic: We want the STASHED version.
        try:
            logger.info("Auto-resolving .ac_cdd_session.json to local version...")
            # We overwrite the file with the content from the stash
            # 'stash@{0}' is the one we just tried to pop
            await self._run_git(["checkout", "stash@{0}", "--", ".ac_cdd_session.json"])
            await self._run_git(["add", ".ac_cdd_session.json"])
            logger.info(".ac_cdd_session.json resolved.")

            # Check if other conflicts remain
            status = await self._run_git(["status", "--porcelain"])
            if "UU" in status:  # UU = Both modified (conflict)
                logger.warning(
                    "Other conflicts exist. Please resolve them manually.\n"
                    "Local changes have been applied but conflicted."
                )
            else:
                # If clear, drop the stash (since pop failed to drop it due to conflict)
                await self._run_git(["stash", "drop"])
                logger.info("Stash dropped after resolution.")

        except Exception as ex:
            logger.error(f"Failed to auto-resolve session file: {ex}")
            raise

    async def checkout_pr(self, pr_url: str) -> None:
        """
        Checks out the Pull Request branch using GitHub CLI.
        """
        logger.info(f"Checking out PR: {pr_url}...")
        await self.smart_checkout(pr_url, is_pr=True)
        logger.info(f"Checked out PR {pr_url} successfully.")

    async def checkout_branch(self, branch_name: str, force: bool = False) -> None:
        """
        Checks out an existing branch.
        """
        # Ensure we have the latest remote state before checkout
        try:
            await self._run_git(["fetch"])
        except Exception as e:
            logger.warning(f"Git fetch failed before checkout: {e}")

        logger.info(f"Checking out branch: {branch_name}...")
        await self.smart_checkout(branch_name, is_pr=False, force=force)

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

    async def validate_remote_branch(self, branch: str) -> tuple[bool, str]:
        """Validate that branch exists on remote and is up-to-date.

        Returns:
            (is_valid, error_message)
        """
        # Check if branch exists on remote
        stdout, _, code = await self.runner.run_command(
            ["git", "ls-remote", "--heads", "origin", branch],
            check=False,
        )

        if code != 0 or not stdout.strip():
            return False, f"Branch '{branch}' does not exist on remote 'origin'"

        # Check if local is behind remote
        try:
            await self._run_git(["fetch", "origin", branch])

            # Compare local and remote
            local_hash = await self._run_git(["rev-parse", branch])
            remote_hash = await self._run_git(["rev-parse", f"origin/{branch}"])

            if local_hash != remote_hash:
                # Check if local is behind
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

    # Session-Based Branch Operations

    async def create_integration_branch(
        self, session_id: str, prefix: str = "dev", branch_name: str | None = None
    ) -> str:
        """
        Creates integration branch from main for the session.
        Returns: integration branch name
        """
        integration_branch = branch_name if branch_name else f"{prefix}/{session_id}/integration"
        logger.info(f"Creating integration branch: {integration_branch}")

        # Ensure we're on main and up to date
        await self._run_git(["checkout", "main"])
        await self._run_git(["pull"])

        # Check if integration branch exists
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

    async def create_session_branch(
        self, session_id: str, branch_type: str, branch_id: str, integration_branch: str
    ) -> str:
        """
        Creates a session-scoped branch from integration branch.

        Args:
            session_id: Session identifier
            branch_type: Type of branch (arch, cycle)
            branch_id: Specific identifier (architecture, 01, 02, etc.)
            integration_branch: Parent integration branch

        Returns: branch name
        """
        branch_name = f"dev/{session_id}/{branch_type}{branch_id}"
        logger.info(f"Creating session branch: {branch_name} from {integration_branch}")

        # Checkout integration branch and pull latest
        await self._run_git(["checkout", integration_branch])
        await self._run_git(["pull"])

        # Check if session branch exists
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

    async def merge_to_integration(self, pr_url: str, integration_branch: str) -> None:
        """
        Merges PR to integration branch (not main).
        """
        logger.info(f"Merging PR to integration branch: {integration_branch}")

        # Try to mark as ready just in case it's a draft
        await self.runner.run_command([self.gh_cmd, "pr", "ready", pr_url], check=False)

        # Merge PR (this merges to the PR's target branch, which should be integration)
        _, stderr, code = await self.runner.run_command(
            [self.gh_cmd, "pr", "merge", pr_url, "--merge", "--delete-branch"], check=True
        )

        if code != 0:
            raise RuntimeError(f"Failed to merge PR {pr_url}: {stderr}")

        # Checkout integration branch and pull
        await self._run_git(["checkout", integration_branch])
        await self._run_git(["pull"])

        logger.info(f"Merged to {integration_branch} successfully.")

    async def create_final_pr(self, integration_branch: str, title: str, body: str) -> str:
        """
        Creates final PR from integration branch to main.
        Returns: PR URL (existing or newly created)
        """
        logger.info(f"Creating final PR: {integration_branch} → main")

        # Check for existing PR first
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

        # Ensure integration branch is pushed
        await self._run_git(["checkout", integration_branch])
        await self._run_git(["push"])

        # Create PR
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
                body,
            ],
            check=True,
        )

        if code != 0:
            # Try to get error message from stdout or infer
            raise RuntimeError(f"Failed to create PR: {stdout if stdout else 'Unknown error'}")

        pr_url = str(stdout.strip())
        logger.info(f"Final PR created: {pr_url}")
        return pr_url
