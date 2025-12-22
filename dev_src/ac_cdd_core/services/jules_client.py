import asyncio
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

from ac_cdd_core.config import settings
from ac_cdd_core.process_runner import ProcessRunner
from ac_cdd_core.utils import logger
from rich.console import Console

if TYPE_CHECKING:
    from ac_cdd_core.sandbox import SandboxRunner

console = Console()


class JulesSessionError(Exception):
    pass


class JulesTimeoutError(JulesSessionError):
    pass


@dataclass
class JulesActivity:
    type: str
    content: str | None = None
    tool_name: str | None = None
    requires_response: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JulesActivity":
        return cls(
            type=data.get("type", "unknown"),
            content=data.get("content"),
            tool_name=data.get("tool_name"),
            requires_response=data.get("requires_response", False),
        )


class JulesClient:
    """
    Client for interacting with the Jules Autonomous Agent via CLI.
    Manages session execution, processing output, and supervisor loop.
    Implements an Event-Driven Supervisor model.
    """

    def __init__(self) -> None:
        self.runner = ProcessRunner()
        self.executable = settings.jules.executable
        self.timeout = settings.jules.timeout_seconds
        self.max_loops = 100  # Increased for event loop
        self.console = Console()
        self.poll_interval = 5  # Seconds between polls

    async def run_session(
        self,
        session_id: str,
        prompt: str,
        files: list[str],
        completion_signal_file: Path,
        timeout_override: int | None = None,
        runner: Optional["SandboxRunner"] = None,
    ) -> dict[str, Any]:
        """
        Starts a Jules session and enters an event loop to monitor progress.
        Handles:
        - Polling for activities
        - Processing tool outputs (files)
        - Proxying user input for agent questions
        - Detecting completion

        Args:
            session_id: The unique session identifier.
            prompt: The instruction prompt for the agent.
            files: List of file paths to load into context.
            completion_signal_file: The file path that signals completion (e.g., plan_status.json).
            runner: Optional SandboxRunner for remote execution.

        Returns:
            The content of the completion signal file (parsed JSON).
        """
        # 1. Clean up previous signal file
        if completion_signal_file.exists():
            try:
                completion_signal_file.unlink()
            except Exception as e:
                logger.warning(f"Could not delete old signal file {completion_signal_file}: {e}")

        # 2. Initial Kick-off (Send the prompt)
        logger.info(f"Starting Jules Session {session_id}...")
        await self._send_user_response(session_id, prompt, files, runner)

        loop_count = 0
        max_loops = self.max_loops

        # UI Status
        status_context = self.console.status("[bold green]Jules is working...", spinner="dots")
        status_context.start()

        try:
            while loop_count < max_loops:
                loop_count += 1

                # 3. Check for Completion (File Signal)
                if completion_signal_file.exists():
                    try:
                        content = completion_signal_file.read_text(encoding="utf-8")
                        if content.strip():
                            status_context.stop()
                            logger.info("Completion signal detected.")
                            return json.loads(content)
                    except Exception as e:
                        logger.warning(f"Error reading signal file: {e}")

                # 4. Poll Activities
                try:
                    activities = await self._fetch_activities(session_id, runner)
                except Exception as e:
                    logger.warning(f"Failed to fetch activities: {e}")
                    activities = []

                if not activities:
                    await asyncio.sleep(self.poll_interval)
                    continue

                latest = activities[-1]

                # 5. Handle States
                if latest.type == "agent_message" and latest.requires_response:
                    status_context.stop()

                    # Ensure we process any files in the message content before asking
                    if latest.content:
                        self._parse_and_save(latest.content)
                        self.console.print(
                            f"\n[bold magenta]Jules asks:[/bold magenta] {latest.content}"
                        )

                    # Get User Input
                    user_response = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: self.console.input("[bold green]Your Answer > [/bold green]")
                    )

                    # Resume working status
                    status_context.start()
                    await self._send_user_response(session_id, user_response, runner=runner)

                elif latest.type in ("tool_use", "agent_thought", "agent_plan"):
                    # Just log/update status
                    # Parse any files that might be in the output/thought
                    if latest.content:
                        self._parse_and_save(latest.content)

                    # Update status message if tool name is available
                    if latest.tool_name:
                        status_context.update(f"[bold green]Jules is using {latest.tool_name}...")

                    await asyncio.sleep(self.poll_interval)

                elif latest.type in ("session_completed", "pr_created"):
                    # Status check logic modified for robustness
                    status_context.stop()
                    logger.info(f"Session completed via activity: {latest.type}")

                    # Give it a moment for file to appear/sync
                    await asyncio.sleep(5)

                    if completion_signal_file.exists():
                        status_context.start()  # Restart status if we loop back (though unlikely if file exists)
                        continue
                    else:
                        # Fallback: API says done, but file is missing.
                        # Auto-reply to force file generation.
                        logger.warning(
                            "API reports completion but signal file missing. Sending auto-reply."
                        )

                        auto_msg = (
                            "API says completed, but completion_signal_file is missing. "
                            "Please output the json file in the FILENAME format immediately."
                        )
                        await self._send_user_response(session_id, auto_msg, runner=runner)

                        # Resume status and continue loop to wait for the file
                        status_context.start()
                        await asyncio.sleep(self.poll_interval)
                        continue

                else:
                    # Unknown or generic activity
                    if latest.content:
                        self._parse_and_save(latest.content)
                    await asyncio.sleep(self.poll_interval)

        finally:
            status_context.stop()

        raise JulesTimeoutError(
            f"Jules session reached max loops ({max_loops}) "
            f"without generating {completion_signal_file}"
        )

    async def _fetch_activities(
        self, session_id: str, runner: Optional["SandboxRunner"] = None
    ) -> list[JulesActivity]:
        """
        Polls the Jules API (via CLI) for the latest activities.
        """
        cmd_exe = self.executable
        # Assuming CLI command: jules activities --session <id> --json
        # NOTE: If running remotely, we assume 'jules' is in path
        cmd = ["jules" if runner else cmd_exe, "activities", "--session", session_id, "--output", "json"]

        try:
            if runner:
                # Remote execution
                stdout, stderr, code = await runner.run_command(cmd, check=True)
                result_stdout = stdout
            else:
                # Local execution
                result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: subprocess.run(cmd, check=True, capture_output=True, text=True),
                )
                result_stdout = result.stdout

            data = json.loads(result_stdout)
            # transform to objects
            return [JulesActivity.from_dict(item) for item in data]

        except (subprocess.CalledProcessError, RuntimeError) as e:
            # RuntimeError comes from SandboxRunner.run_command if check=True
            # logger.debug(f"Fetch activities failed: {e}")
            return []
        except json.JSONDecodeError:
            return []
        except FileNotFoundError:
            return []

    async def _send_user_response(
        self,
        session_id: str,
        message: str,
        files: list[str] = None,
        runner: Optional["SandboxRunner"] = None,
    ) -> None:
        """
        Sends a message (or prompt) to the agent.
        """
        cmd_exe = self.executable
        # If remote, assume 'jules' is in path.
        cmd = ["jules" if runner else cmd_exe, "chat", "--session", session_id]

        if files:
            for file_path in files:
                # For remote, we assume files are synced.
                # For local, we check existence.
                if runner:
                    # Just append the path, assume it exists on remote relative to cwd
                    cmd.extend(["--file", str(file_path)])
                else:
                    if Path(file_path).exists():
                        cmd.extend(["--file", str(file_path)])

        cmd.append(message)

        try:
            if runner:
                await runner.run_command(cmd, check=True)
            else:
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: subprocess.run(cmd, check=True, capture_output=True, text=True),
                )
        except (subprocess.CalledProcessError, RuntimeError) as e:
            err_msg = str(e)
            if hasattr(e, "stderr"):
                err_msg += f": {e.stderr}"
            logger.error(f"Failed to send message: {err_msg}")
            raise JulesSessionError(f"Failed to send message: {err_msg}") from e

    def _parse_and_save(self, text: str) -> None:
        r"""
        Parses text for FILENAME blocks and writes them to disk.
        Robust Regex allows:
        - Spaces around filename
        - Any or no language identifier after ```
        """
        # Improved Regex
        pattern = re.compile(r"FILENAME:\s*([^\n]+)\s*\n\s*```[^\n]*\n(.*?)```", re.DOTALL)

        matches = pattern.findall(text)
        if not matches:
            return

        for filename, content in matches:
            filename = filename.strip()
            # Security check (optional but recommended)
            if ".." in filename or filename.startswith("/"):
                logger.warning(f"[Security] Skipped unsafe path: {filename}")
                continue

            file_path = Path(filename)

            # Ensure directory exists
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding="utf-8")
                logger.info(f"[System] Saved: {filename}")
            except Exception as e:
                logger.error(f"Failed to save {filename}: {e}")
