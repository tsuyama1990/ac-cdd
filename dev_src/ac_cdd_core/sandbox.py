import io
import os
import tarfile
from pathlib import Path

from e2b_code_interpreter import Sandbox

from .config import settings
from .hash_utils import calculate_directory_hash
from .utils import logger


class SandboxRunner:
    """
    Executes code and commands in an E2B Sandbox for safety and isolation.
    """

    def __init__(self, sandbox_id: str | None = None, cwd: str | None = None):
        self.api_key = os.getenv("E2B_API_KEY")
        if not self.api_key:
            logger.warning("E2B_API_KEY not found. Sandbox execution will fail.")

        # Use settings for defaults if not provided
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
                self.sandbox = await Sandbox.connect(self.sandbox_id, api_key=self.api_key)
                return self.sandbox
            except Exception as e:
                logger.warning(
                    f"Failed to connect to sandbox {self.sandbox_id}: {e}. Creating new."
                )

        logger.info("Creating new E2B Sandbox...")
        self.sandbox = await Sandbox.create(
            api_key=self.api_key, template=settings.sandbox.template
        )

        # Initial setup: install UV and sync files
        if settings.sandbox.install_cmd:
            await self.sandbox.commands.run(
                settings.sandbox.install_cmd, timeout=settings.sandbox.timeout
            )

        await self._sync_to_sandbox(self.sandbox)

        return self.sandbox

    async def run_command(
        self, cmd: list[str], check: bool = False, env: dict[str, str] | None = None
    ) -> tuple[str, str, int]:
        """
        Runs a shell command in the sandbox.
        """
        sandbox = await self._get_sandbox()

        # Ensure latest files are there before running
        await self._sync_to_sandbox(sandbox)

        command_str = " ".join(cmd)
        logger.info(f"[Sandbox] Running: {command_str}")

        exec_result = await sandbox.commands.run(
            command_str, cwd=self.cwd, envs=env or {}, timeout=settings.sandbox.timeout
        )

        stdout = exec_result.stdout
        stderr = exec_result.stderr
        exit_code = exec_result.exit_code or 0

        if check and exit_code != 0:
            raise RuntimeError(
                f"Command failed with code {exit_code}:\nSTDOUT: {stdout}\nSTDERR: {stderr}"
            )

        return stdout, stderr, exit_code

    async def _sync_to_sandbox(self, sandbox: Sandbox) -> None:
        """
        Uploads configured directories and files to the sandbox using a tarball for performance.
        Skips if content hasn't changed.
        """
        root = Path.cwd()
        current_hash = calculate_directory_hash(
            root, settings.sandbox.files_to_sync, settings.sandbox.dirs_to_sync
        )

        if self._last_sync_hash == current_hash:
            logger.info("Sandbox files up-to-date. Skipping sync.")
            return

        tar_buffer = io.BytesIO()

        with tarfile.open(fileobj=tar_buffer, mode="w:gz") as tar:
            # Sync individual files
            for filename in settings.sandbox.files_to_sync:
                file_path = root / filename
                if file_path.exists():
                    tar.add(file_path, arcname=filename)

            # Sync directories
            for folder in settings.sandbox.dirs_to_sync:
                local_folder = root / folder
                if not local_folder.exists():
                    continue

                for file_path in local_folder.rglob("*"):
                    if file_path.is_file():
                        # Filter generic ignored
                        if "__pycache__" in str(file_path) or ".git" in str(file_path):
                            continue

                        rel_path = file_path.relative_to(root)
                        tar.add(file_path, arcname=str(rel_path))

        tar_buffer.seek(0)

        # Upload the tarball
        remote_tar_path = f"{self.cwd}/bundle.tar.gz"
        await sandbox.files.write(remote_tar_path, tar_buffer)

        # Extract
        await sandbox.commands.run(
            f"tar -xzf bundle.tar.gz -C {self.cwd}", timeout=settings.sandbox.timeout
        )
        logger.info("Synced files to sandbox via tarball.")
        self._last_sync_hash = current_hash

    async def sync_from_sandbox(self) -> None:
        """
        Downloads changes from the sandbox back to the local file system.
        Useful when remote tools (like Aider) modify code.
        """
        if not self.sandbox:
            return

        logger.info("Syncing files from sandbox to local...")

        # We only sync back configured directories/files
        dirs = settings.sandbox.dirs_to_sync
        files = settings.sandbox.files_to_sync

        # Create a tar of these on the remote
        # We use a broad ignore to avoid syncing back huge artifacts if possible,
        # but here we trust the specified dirs.
        paths_str = " ".join([d for d in dirs] + [f for f in files])
        remote_tar = f"download_bundle.tar.gz" # relative to cwd in run command

        # Tar on remote
        # We ignore errors (|| true) in case some files don't exist yet
        cmd = f"tar -czf {remote_tar} {paths_str} || true"
        await self.sandbox.commands.run(cmd, cwd=self.cwd, timeout=settings.sandbox.timeout)

        # Download
        try:
            # sandbox.files.read returns bytes
            content = await self.sandbox.files.read(f"{self.cwd}/{remote_tar}")

            tar_buffer = io.BytesIO(content)

            with tarfile.open(fileobj=tar_buffer, mode="r:gz") as tar:
                # We extract to current working directory, overwriting local files.
                # Filter to ensure we don't extract absolute paths or '..'

                def is_safe_member(member):
                    return not (member.name.startswith("/") or ".." in member.name)

                safe_members = [m for m in tar.getmembers() if is_safe_member(m)]
                tar.extractall(path=Path.cwd(), members=safe_members)

            logger.info("Synced files from sandbox to local.")

            # Update hash so we don't re-upload immediately if we run another command
            self._last_sync_hash = calculate_directory_hash(
                Path.cwd(), settings.sandbox.files_to_sync, settings.sandbox.dirs_to_sync
            )

        except Exception as e:
            logger.error(f"Failed to sync from sandbox: {e}")

    async def close(self) -> None:
        if self.sandbox:
            await self.sandbox.close()
            self.sandbox = None
