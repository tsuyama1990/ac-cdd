import io
import os
import shlex

from e2b_code_interpreter import Sandbox

from .config import settings
from .services.sandbox.sync import SandboxSyncManager
from .utils import logger


class SandboxRunner:
    """
    Executes code and commands in an E2B Sandbox for safety and isolation.
    """

    def __init__(self, sandbox_id: str | None = None, cwd: str | None = None) -> None:
        self.api_key = os.getenv("E2B_API_KEY")
        if not self.api_key:
            logger.warning("E2B_API_KEY not found. Sandbox execution will fail.")

        self.cwd = cwd or settings.sandbox.cwd
        self.sandbox_id = sandbox_id
        self.sandbox: Sandbox | None = None
        self._last_sync_hash: str | None = None

    async def _get_sandbox(self) -> Sandbox:
        """Get or create a sandbox instance."""
        if self.sandbox:
            return self.sandbox

        if self.sandbox_id:
            try:
                logger.info(f"Connecting to existing sandbox: {self.sandbox_id}")
                self.sandbox = Sandbox.connect(self.sandbox_id, api_key=self.api_key)
            except Exception as e:
                logger.warning(
                    f"Failed to connect to sandbox {self.sandbox_id}: {e}. Creating new."
                )
            else:
                return self.sandbox

        logger.info("Creating new E2B Sandbox...")
        self.sandbox = Sandbox.create(
            api_key=self.api_key,
            template=settings.sandbox.template,
            timeout=settings.sandbox.timeout,
        )

        self.sandbox.commands.run(f"mkdir -p {self.cwd}")
        await self._sync_to_sandbox(self.sandbox)

        if settings.sandbox.install_cmd:
            self.sandbox.commands.run(
                settings.sandbox.install_cmd, timeout=settings.sandbox.timeout
            )

        return self.sandbox

    async def run_command(
        self, cmd: list[str], check: bool = False, env: dict[str, str] | None = None
    ) -> tuple[str, str, int]:
        """
        Runs a shell command in the sandbox with retry logic.
        """
        max_retries = 1
        stdout = ""
        stderr = ""
        exit_code = 0

        for attempt in range(max_retries + 1):
            try:
                sandbox = await self._get_sandbox()
                await self._sync_to_sandbox(sandbox)

                command_str = shlex.join(cmd)
                logger.info(f"[Sandbox] Running (Attempt {attempt + 1}): {command_str}")

                # Build sandbox environment: start from caller-supplied env vars,
                # then explicitly clear Docker-host-specific variables that must not
                # leak into the E2B sandbox.
                # UV_PROJECT_ENVIRONMENT is set to /opt/ac_cdd_project_venv in the
                # Docker container (to avoid host-venv path leakage), but /opt/ is
                # not writable inside E2B, so ruff/mypy fail with "Permission denied".
                sandbox_env: dict[str, str] = dict(env or {})
                sandbox_env.setdefault("UV_PROJECT_ENVIRONMENT", "")  # clear if not overridden

                exec_result = sandbox.commands.run(
                    command_str, cwd=self.cwd, envs=sandbox_env, timeout=settings.sandbox.timeout
                )
                stdout = exec_result.stdout
                stderr = exec_result.stderr
                exit_code = exec_result.exit_code or 0
                break

            except Exception as e:
                err_msg = str(e).lower()
                is_sandbox_error = (
                    "sandbox was not found" in err_msg
                    or "timeout" in err_msg
                    or "sandbox error" in err_msg
                )

                if is_sandbox_error and attempt < max_retries:
                    logger.warning(
                        f"Sandbox disconnection detected: {e}. Re-initializing sandbox..."
                    )
                    if self.sandbox:
                        try:
                            self.sandbox.kill()
                        except Exception as sandbox_kill_err:
                            logger.debug(f"Failed to kill sandbox: {sandbox_kill_err}")
                        self.sandbox = None
                        self._last_sync_hash = None
                    continue

                if hasattr(e, "exit_code") and hasattr(e, "stdout") and hasattr(e, "stderr"):
                    stdout = e.stdout
                    stderr = e.stderr
                    exit_code = e.exit_code
                    break
                raise

        if check and exit_code != 0:
            msg = f"Command failed with code {exit_code}:\nSTDOUT: {stdout}\nSTDERR: {stderr}"
            raise RuntimeError(msg)

        return stdout, stderr, exit_code

    def _compute_sync_hash(self) -> str:
        """Computes hash of directories to sync."""
        return SandboxSyncManager.compute_sync_hash()

    def _create_sync_tarball(self) -> io.BytesIO:
        """Creates a tarball of files to sync."""
        return SandboxSyncManager.create_sync_tarball()

    async def _sync_to_sandbox(self, sandbox: Sandbox | None = None) -> None:
        """
        Uploads configured directories and files to the sandbox using a tarball for performance.
        Skips if content hasn't changed.
        """
        if sandbox is None:
            sandbox = self.sandbox
            if sandbox is None:
                return

        current_hash = self._compute_sync_hash()

        if self._last_sync_hash == current_hash:
            logger.info("Sandbox files up-to-date. Skipping sync.")
            return

        tar_buffer = self._create_sync_tarball()

        remote_tar_path = f"{self.cwd}/bundle.tar.gz"
        sandbox.files.write(remote_tar_path, tar_buffer)

        sandbox.commands.run(
            f"tar -xzf {remote_tar_path} -C {self.cwd}", timeout=settings.sandbox.timeout
        )
        logger.info("Synced files to sandbox via tarball.")
        self._last_sync_hash = current_hash

    async def cleanup(self) -> None:
        """alias for close, matching test expectations"""
        await self.close()

    async def close(self) -> None:
        if self.sandbox:
            self.sandbox.kill()
            self.sandbox = None
