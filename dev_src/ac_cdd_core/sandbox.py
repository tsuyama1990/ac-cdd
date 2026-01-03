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
                self.sandbox = Sandbox.connect(self.sandbox_id, api_key=self.api_key)
                return self.sandbox
            except Exception as e:
                logger.warning(
                    f"Failed to connect to sandbox {self.sandbox_id}: {e}. Creating new."
                )

        logger.info("Creating new E2B Sandbox...")
        self.sandbox = Sandbox.create(
            api_key=self.api_key,
            template=settings.sandbox.template,
            timeout=settings.sandbox.timeout,  # Pass explicit timeout for keep-alive
        )

        # Ensure CWD exists
        self.sandbox.commands.run(f"mkdir -p {self.cwd}")

        # Initial setup: Sync files FIRST, then install dependencies
        # (Crucial for lightweight setup where we might rely on local configs,
        # though here we just install ruff)
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
        Runs a shell command in the sandbox.
        """
        # --- 修正: リトライロジックの追加 ---
        max_retries = 1
        for attempt in range(max_retries + 1):
            try:
                # Sandboxを取得 (初回または再作成)
                sandbox = await self._get_sandbox()

                # ファイル同期 (最新コードを反映)
                # Note: self._sync_to_sandbox needs to accept sandbox arg or use self.sandbox
                # The provided code snippet uses 'sandbox' var which is correct.
                await self._sync_to_sandbox(sandbox)

                # Save join for logging, but use shlex for safety if we were passing string
                # e2b runs string via /bin/bash -c "cmd" usually.
                import shlex

                command_str = shlex.join(cmd)
                logger.info(f"[Sandbox] Running (Attempt {attempt + 1}): {command_str}")

                exec_result = sandbox.commands.run(
                    command_str, cwd=self.cwd, envs=env or {}, timeout=settings.sandbox.timeout
                )
                stdout = exec_result.stdout
                stderr = exec_result.stderr
                exit_code = exec_result.exit_code or 0

                # 成功したらループ終了
                break

            except Exception as e:
                # タイムアウトやSandbox消失のエラーか判定
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

                    # 既存のインスタンスを破棄
                    if self.sandbox:
                        try:
                            self.sandbox.kill()
                        except Exception as sandbox_kill_err:
                            logger.debug(f"Failed to kill sandbox: {sandbox_kill_err}")
                        self.sandbox = None
                        self._last_sync_hash = None  # Force re-sync on new sandbox definition

                    # 次のループで _get_sandbox() が呼ばれ、新規作成＆install_cmdが実行される
                    continue
                # コマンド自体の失敗(exit_code)は例外にならない場合もあるが、
                # e2bのエラーオブジェクトの場合は中身を取り出してbreak
                if hasattr(e, "exit_code") and hasattr(e, "stdout") and hasattr(e, "stderr"):
                    stdout = e.stdout
                    stderr = e.stderr
                    exit_code = e.exit_code
                    break

                # 解決不能なエラーはそのまま投げる
                raise e
        # ----------------------------------

        if check and exit_code != 0:
            raise RuntimeError(
                f"Command failed with code {exit_code}:\nSTDOUT: {stdout}\nSTDERR: {stderr}"
            )

        return stdout, stderr, exit_code

    def _compute_sync_hash(self) -> str:
        """Computes hash of directories to sync."""
        root = Path.cwd()
        return calculate_directory_hash(
            root, settings.sandbox.files_to_sync, settings.sandbox.dirs_to_sync
        )

    def _create_sync_tarball(self) -> io.BytesIO:
        """Creates a tarball of files to sync."""
        root = Path.cwd()
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
        return tar_buffer

    async def _sync_to_sandbox(self, sandbox: Sandbox | None = None) -> None:
        """
        Uploads configured directories and files to the sandbox using a tarball for performance.
        Skips if content hasn't changed.
        """
        if sandbox is None:
            sandbox = self.sandbox
            if sandbox is None:
                # If we still don't have a sandbox, we can't sync.
                # However, this method is usually called after _get_sandbox.
                # Or it might be called in tests with mocked sandbox.
                # If self.sandbox is also None, we should probably raise or return.
                if settings.sandbox.template:  # Just a check to ensure settings loaded
                    pass
                return

        current_hash = self._compute_sync_hash()

        if self._last_sync_hash == current_hash:
            logger.info("Sandbox files up-to-date. Skipping sync.")
            return

        tar_buffer = self._create_sync_tarball()

        # Upload the tarball
        remote_tar_path = f"{self.cwd}/bundle.tar.gz"
        sandbox.files.write(remote_tar_path, tar_buffer)

        # Extract
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
