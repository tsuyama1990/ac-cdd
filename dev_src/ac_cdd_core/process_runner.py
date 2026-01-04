import asyncio
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
                logger.error(f"Command failed [{returncode}]: {cmd_str}")
                if stderr_str:
                    logger.error(f"Stderr: {stderr_str}")

                if check:
                    pass
        except Exception as e:  # noqa: BLE001
            logger.error(f"Execution failed for '{cmd_str}': {e}")
            return "", str(e), -1
        else:
            return stdout_str, stderr_str, returncode
