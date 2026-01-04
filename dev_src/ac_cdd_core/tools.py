import shutil
import subprocess
from typing import Any

from .process_runner import ProcessRunner


class ToolNotFoundError(Exception):
    pass


class ToolWrapper:
    def __init__(self, command: str) -> None:
        self.command = command
        if not shutil.which(command):
            msg = f"Command '{command}' not found in PATH."
            raise ToolNotFoundError(msg)
        self.runner = ProcessRunner()

    async def run(
        self,
        args: list[str],
        _capture_output: bool = True,
        check: bool = True,
        _text: bool = True,
    ) -> subprocess.CompletedProcess[Any]:
        full_cmd = [self.command, *args]

        stdout, stderr, returncode = await self.runner.run_command(full_cmd, check=check)

        if check and returncode != 0:
            raise subprocess.CalledProcessError(returncode, full_cmd, output=stdout, stderr=stderr)

        return subprocess.CompletedProcess(
            args=full_cmd,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )


def semantic_code_search(query: str) -> str:
    """
    Search the codebase for relevant functions or classes using semantic search.
    Useful for finding definitions, understanding logic, or checking dependencies.
    """
    # NOTE: CodeRetriever is not yet implemented in the current structure.
    return f"Semantic search for '{query}' is not yet available."
