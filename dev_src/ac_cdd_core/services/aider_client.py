
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

        # Prepare Environment Variables for Aider (API Keys)
        # STRICT PASS-THROUGH: We pass only specific keys if they exist in host environment.
        # This allows the user to control exactly what keys Aider has access to via their .env
        allowed_keys = [
            "OPENROUTER_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "DEEPSEEK_API_KEY",
        ]
        env_vars = {k: os.environ[k] for k in allowed_keys if k in os.environ}

        try:
            if runner:
                # Run in Sandbox with ENV
                stdout, stderr, code = await runner.run_command(cmd, env=env_vars, check=False)
                
                if code != 0:
                    logger.error(f"Aider audit failed (Exit {code}). Stderr: {stderr}")
                    return f"SYSTEM_ERROR: Aider failed to run (Exit Code {code}). Stderr: {stderr}"
                
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
                    logger.error(f"Aider audit failed (Exit {result.returncode}). Stderr: {result.stderr}")
                    return f"SYSTEM_ERROR: Aider failed to run (Exit Code {result.returncode}). Stderr: {result.stderr}"
                
                return result.stdout

        except Exception as e:
            logger.error(f"Aider audit failed: {e}")
            return f"SYSTEM_ERROR: Aider audit failed due to internal error: {e}"

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

        # STRICT PASS-THROUGH (Same as audit)
        allowed_keys = [
            "OPENROUTER_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "DEEPSEEK_API_KEY",
        ]
        env_vars = {k: os.environ[k] for k in allowed_keys if k in os.environ}

        try:
            if runner:
                # Run in Sandbox
                stdout, stderr, code = await runner.run_command(cmd, env=env_vars, check=False)

                if code != 0:
                    logger.error(f"Aider fix failed (Exit {code}). Stderr: {stderr}")
                    return f"SYSTEM_ERROR: Aider failed to run (Exit Code {code}). Stderr: {stderr}"

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
                    logger.error(f"Aider fix failed (Exit {result.returncode}). Stderr: {result.stderr}")
                    return f"SYSTEM_ERROR: Aider failed to run (Exit Code {result.returncode}). Stderr: {result.stderr}"

                return result.stdout

        except Exception as e:
            logger.error(f"Aider fix failed: {e}")
            return f"SYSTEM_ERROR: Aider fix failed due to internal error: {e}"

    def parse_audit_report(self, output: str) -> str:
        """
        Parses the raw Aider output to extract the clean 'Audit Report'.
        Removes internal logs, token stats, and diff blocks if markers exist.
        Otherwise filters specific Aider lines.
        """
        marker_start = "=== AUDIT REPORT START ==="
        marker_end = "=== AUDIT REPORT END ==="
        
        # 1. Try to extract content between markers
        if marker_start in output:
             content_after_start = output.split(marker_start, 1)[1]
             if marker_end in content_after_start:
                 report_body = content_after_start.split(marker_end, 1)[0]
                 return report_body.strip()
             else:
                 # Start found but no end (maybe crashed or truncated?)
                 return content_after_start.strip()
                 
        # 2. Fallback: Filter obvious noise lines
        clean_lines = []
        lines = output.splitlines()
        for line in lines:
            # Skip Aider/System logs
            if any(x in line for x in ["Defined run_cmd", "Tokens:", "Git repo:", "Repo-map:", "Model:", "Aider v", "Added "]):
                continue
            if line.strip().startswith("<<<<<<< SEARCH"):
                # If code edit block appears in audit (shouldn't happen but user report showed it), skip it?
                # User report showed "LLM did not conform...".
                # If we want JUST the report, and no markers found, we return what's left.
                pass
            
            clean_lines.append(line)
            
        return "\n".join(clean_lines).strip()
