import asyncio
import subprocess
from pathlib import Path

from .utils import logger


class ProcessRunner:
    """
    Handles asynchronous process execution with logging and output capture.
    """

    async def run_command(
        self,
        cmd: list[str],
        cwd: Path | None = None,
        check: bool = True,
        env: dict[str, str] | None = None,
    ) -> tuple[str, str, int]:
        """
        Executes a command asynchronously.
        """
        cmd_str = " ".join(cmd)
        logger.debug(f"Running command: {cmd_str}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )
            stdout, stderr = await process.communicate()

            stdout_str = stdout.decode().strip() if stdout else ""
            stderr_str = stderr.decode().strip() if stderr else ""
            returncode = process.returncode or 0

            if returncode != 0:
                if check:
                    logger.error(f"Command failed [{returncode}]: {cmd_str}")
                    if stderr_str:
                        logger.error(f"Stderr: {stderr_str}")

                    # DEBUG: Diagnose git permissions issues
                    if cmd[0] == "git":
                        try:
                            import os

                            logger.error(f"DEBUG: Process UID={os.getuid()}, GID={os.getgid()}")
                            git_index = Path(".git/index")
                            if git_index.exists():
                                st = git_index.stat()
                                logger.error(
                                    f"DEBUG: .git/index: mode={oct(st.st_mode)}, uid={st.st_uid}, gid={st.st_gid}"
                                )
                            else:
                                logger.error("DEBUG: .git/index not found")

                            lock_file = Path(".git/index.lock")
                            if lock_file.exists():
                                logger.error("DEBUG: .git/index.lock EXISTS (Lock contention)")
                        except Exception as e:
                            logger.error(f"DEBUG failed: {e}")
                    raise subprocess.CalledProcessError(
                        returncode, cmd, output=stdout_str, stderr=stderr_str
                    )  # noqa: TRY301
                logger.debug(f"Command failed (expected) [{returncode}]: {cmd_str}")
        except Exception as e:
            logger.error(f"Execution failed for '{cmd_str}': {e}")
            return "", str(e), -1
        else:
            return stdout_str, stderr_str, returncode
