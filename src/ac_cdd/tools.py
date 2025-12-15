import shutil
import subprocess
from typing import Any

from .process_runner import ProcessRunner


class ToolNotFoundError(Exception):
    pass


class ToolWrapper:
    def __init__(self, command: str):
        self.command = command
        if not shutil.which(command):
            raise ToolNotFoundError(f"Command '{command}' not found in PATH.")
        self.runner = ProcessRunner()

    async def run(
        self,
        args: list[str],
        capture_output: bool = True,
        check: bool = True,
        text: bool = True,
    ) -> subprocess.CompletedProcess[Any]:
        full_cmd = [self.command] + args

        # Delegate to ProcessRunner
        # Note: ProcessRunner returns (stdout, stderr, returncode)
        # We need to map it back to CompletedProcess to maintain existing API contract for now.

        stdout, stderr, returncode = await self.runner.run_command(full_cmd, check=check)

        if check and returncode != 0:
            # Maintain the behavior of raising CalledProcessError if check=True
            # ProcessRunner logs it, but we raise it here to satisfy ToolWrapper contract
            raise subprocess.CalledProcessError(returncode, full_cmd, output=stdout, stderr=stderr)

        return subprocess.CompletedProcess(
            args=full_cmd,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )
