
import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from ac_cdd_core.config import settings
from ac_cdd_core.utils import logger

if TYPE_CHECKING:
    from ac_cdd_core.sandbox import SandboxRunner

class AiderClient:
    """
    Wrapper for the 'aider' CLI tool.
    Provides methods for auditing (read-only) and fixing (edit) code.
    """

    def __init__(self) -> None:
        self.smart_model = settings.aider.smart_model
        self.fast_model = settings.aider.fast_model
        # Resolve 'aider' executable path (fallback for local execution)
        self.executable = shutil.which("aider")
        if not self.executable:
            # If running remotely, this might not matter, but good to have for local fallback
            self.executable = "aider"

    async def run_audit(
        self, files: list[str], instruction: str, runner: Optional["SandboxRunner"] = None
    ) -> str:
        """
        Run Aider in read-only mode to audit files.
        Uses FAST_MODEL.
        """
        logger.info(f"Running Aider Audit on {len(files)} files...")

        # Construct command
        # Note: If running remotely, we assume 'aider' is in PATH or installed in sandbox
        cmd = [
            "aider",
            "--model", self.fast_model,
            "--read-only",
            "--no-auto-commits",
            "--message", instruction,
        ]

        # Append files
        # For remote execution, we assume files exist in sandbox (synced)
        # For local execution, we filter by existence
        if not runner:
            valid_files = [f for f in files if Path(f).exists()]
            if not valid_files:
                return "No valid files to audit."
            cmd.extend(valid_files)
            # Use local executable path
            cmd[0] = self.executable
        else:
            # Remote: assume files are synced
            cmd.extend(files)

        try:
            if runner:
                # Run in Sandbox
                stdout, stderr, code = await runner.run_command(cmd, check=False)
                if code != 0:
                     logger.warning(f"Remote Aider audit returned code {code}: {stderr}")
                return stdout
            else:
                # Local Execution (Fallback)
                result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: subprocess.run(  # noqa: S603
                        cmd, check=False, capture_output=True, text=True, env={**os.environ}
                    ),
                )
                if result.returncode != 0:
                    logger.warning(f"Aider audit returned non-zero exit code: {result.stderr}")
                return result.stdout

        except Exception as e:
            logger.error(f"Aider audit failed: {e}")
            return f"Audit failed due to internal error: {e}"

    async def run_fix(
        self, files: list[str], instruction: str, runner: Optional["SandboxRunner"] = None
    ) -> str:
        """
        Run Aider in edit mode to fix issues.
        Uses SMART_MODEL.
        """
        logger.info(f"Running Aider Fix on {len(files)} files...")

        cmd = [
            "aider",
            "--model", self.smart_model,
            "--yes",  # Auto-confirm edits
            "--no-auto-commits", # Let graph handle commits
            "--message", instruction,
        ]

        if not runner:
            valid_files = [f for f in files if Path(f).exists()]
            if not valid_files:
                return "No valid files to fix."
            cmd.extend(valid_files)
            cmd[0] = self.executable
        else:
            cmd.extend(files)

        try:
            if runner:
                # Run in Sandbox
                stdout, stderr, code = await runner.run_command(cmd, check=False)

                if code != 0:
                    logger.warning(f"Remote Aider fix returned code {code}: {stderr}")
                    return f"Fix failed: {stderr}"

                # Sync back changes from sandbox to local
                await runner.sync_from_sandbox()

                return stdout
            else:
                # Local Execution
                result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: subprocess.run(  # noqa: S603
                        cmd, check=False, capture_output=True, text=True, env={**os.environ}
                    ),
                )

                if result.returncode != 0:
                    logger.warning(f"Aider fix returned non-zero exit code: {result.stderr}")
                    return f"Fix failed: {result.stderr}"

                return result.stdout

        except Exception as e:
            logger.error(f"Aider fix failed: {e}")
            return f"Fix failed due to internal error: {e}"
