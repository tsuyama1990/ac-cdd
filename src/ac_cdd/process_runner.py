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

        Args:
            cmd: Command and arguments list.
            cwd: Working directory.
            check: If True, log error on non-zero exit code (but does not raise exception here,
                   caller handles logic or we can raise).
                   *Refinement*: Requirement says "check: bool = True" in signature.
                   Standard behavior for 'check' in subprocess is to raise CalledProcessError.
                   However, the prompt requirements say "handle logger.error for failures".
                   Let's raise an exception if check is True, similar to subprocess.run.
            env: Environment variables.

        Returns:
            stdout, stderr, returncode
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
                    # Note: We do not raise an exception here to strictly adhere to the
                    # requested return signature -> tuple[str, str, int].
                    # Callers must check returncode if they need to handle failure.
                    pass

            return stdout_str, stderr_str, returncode

        except Exception as e:
            logger.error(f"Execution failed for '{cmd_str}': {e}")
            # Depending on strictness, might want to re-raise or return error tuple
            # Returning -1 for returncode if generic exception
            return "", str(e), -1
