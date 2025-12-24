import asyncio
import json
import httpx
import google.auth
import sys
import select
from google.auth.transport.requests import Request as GoogleAuthRequest
from typing import Any, Optional, Dict
from pathlib import Path

from ac_cdd_core.config import settings
from ac_cdd_core.utils import logger
from ac_cdd_core.services.git_ops import GitManager
from rich.console import Console

console = Console()

class JulesSessionError(Exception):
    pass

class JulesTimeoutError(JulesSessionError):
    pass

class JulesClient:
    """
    Client for interacting with the Google Cloud Code Agents API (Jules API).
    Uses asynchronous HTTP requests to submit tasks and poll for Pull Request creation.
    """

    def __init__(self) -> None:
        self.project_id = settings.GCP_PROJECT_ID
        # Quickstart: Base URL is global, no region required in path
        self.base_url = "https://jules.googleapis.com/v1alpha"
        self.timeout = settings.jules.timeout_seconds
        self.poll_interval = settings.jules.polling_interval_seconds
        self.console = Console()
        self.git = GitManager()

        # Initialize Authentication (Prefer ADC)
        try:
            self.credentials, self.project_id_from_auth = google.auth.default()
            if not self.project_id:
                self.project_id = self.project_id_from_auth
        except Exception as e:
            logger.warning(f"Could not load Google Credentials: {e}. Falling back to API Key if available.")
            self.credentials = None

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
        }

        # Quickstart: "To authenticate your requests, pass the API key in the X-Goog-Api-Key header"
        if settings.JULES_API_KEY:
             headers["X-Goog-Api-Key"] = settings.JULES_API_KEY

        # If credentials exist, use them too (standard GCP behavior often allows both or requires token for some resources)
        # But for Jules Alpha with API Key access, Key is primary.
        if self.credentials:
            if not self.credentials.valid:
                self.credentials.refresh(GoogleAuthRequest())
            headers["Authorization"] = f"Bearer {self.credentials.token}"

        return headers

    async def run_session(
        self,
        session_id: str,
        prompt: str,
        files: list[str],
        completion_signal_file: Path,
        runner: Any = None,
    ) -> Dict[str, Any]:
        """
        Orchestrates the Jules session:
        1. Creates a session with 'AUTO_CREATE_PR' mode.
        2. Polls for completion & Handles interaction.
        3. Returns the PR URL.
        """
        if not settings.JULES_API_KEY and not self.credentials:
             raise JulesSessionError("Missing JULES_API_KEY or ADC credentials.")

        # 1. Prepare Source Context
        try:
            repo_url = await self.git.get_remote_url()
            # Parse owner/repo from URL
            if "github.com" in repo_url:
                parts = repo_url.replace(".git", "").split("/")
                repo_name = parts[-1]
                owner = parts[-2].split(":")[-1] # Handle git@github.com:owner
            else:
                raise JulesSessionError(f"Unsupported repository URL format: {repo_url}. Only GitHub is supported.")

            branch = await self.git.get_current_branch()
        except Exception as e:
            raise JulesSessionError(f"Failed to determine git context: {e}") from e

        # 2. Create Session
        logger.info(f"Creating Jules Session {session_id} on branch {branch}...")

        # Quickstart: POST https://jules.googleapis.com/v1alpha/sessions
        url = f"{self.base_url}/sessions"

        full_prompt = prompt
        if files:
            file_list_str = "\n".join(files)
            full_prompt += f"\n\nPlease focus on the following files:\n{file_list_str}"

        # Quickstart Payload Structure
        payload = {
            "prompt": full_prompt,
            "sourceContext": {
                "source": f"sources/github/{owner}/{repo_name}",
                "githubRepoContext": {
                    "startingBranch": branch
                }
            },
            "automationMode": "AUTO_CREATE_PR"
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json=payload, headers=self._get_headers(), timeout=30.0)
                if response.status_code != 200:
                    # Try to parse error
                    error_msg = response.text
                    try:
                        err_json = response.json()
                        error_msg = err_json.get("error", {}).get("message", response.text)
                    except:
                        pass
                    raise JulesSessionError(f"Failed to create session: {response.status_code} - {error_msg}")

                resp_data = response.json()
                # Quickstart Response: { "name": "sessions/..." }
                session_name = resp_data.get("name")
                if not session_name:
                    raise JulesSessionError("API did not return a session name.")

            except httpx.RequestError as e:
                raise JulesSessionError(f"Network error creating session: {e}") from e

        # 3. Poll for Completion and Interact
        logger.info(f"Session created: {session_name}. Waiting for PR creation...")
        return await self.wait_for_completion(session_name)

    async def wait_for_completion(self, session_name: str) -> Dict[str, Any]:
        """
        Polls for PR creation and handles user interaction (Human-in-the-loop).
        """
        last_activity_count = 0

        start_time = asyncio.get_event_loop().time()
        self.console.print(f"[bold green]Jules is working... (Session: {session_name})[/bold green]")
        self.console.print("[dim]Type your message and press Enter at any time to chat with Jules.[/dim]")

        async with httpx.AsyncClient() as client:
            while True:
                if asyncio.get_event_loop().time() - start_time > self.timeout:
                    raise JulesTimeoutError("Timed out waiting for Jules to complete.")

                try:
                    # --- 1. Check Session Status ---
                    if session_name.startswith("sessions/"):
                        session_url = f"{self.base_url}/{session_name}"
                    else:
                        session_url = f"{self.base_url}/sessions/{session_name}"

                    resp = await client.get(session_url, headers=self._get_headers(), timeout=10.0)

                    if resp.status_code != 200:
                        logger.warning(f"Polling error: {resp.status_code}")
                    else:
                        data = resp.json()
                        state = data.get("state")

                        # Check for PR
                        if "outputs" in data:
                            for output in data["outputs"]:
                                if "pullRequest" in output:
                                    pr_url = output["pullRequest"].get("url")
                                    if pr_url:
                                        self.console.print(f"\n[bold green]PR Created: {pr_url}[/bold green]")
                                        return {"pr_url": pr_url, "status": "success", "raw": data}

                        # Check Terminal States if no PR yet
                        if state == "SUCCEEDED":
                            self.console.print("[yellow]Session Succeeded but NO PR found.[/yellow]")
                            return {"status": "success", "raw": data}

                        if state == "FAILED":
                            error_msg = data.get("error", {}).get("message", "Unknown error")
                            logger.error(f"Jules Session Failed: {error_msg}")
                            raise JulesSessionError(f"Jules Session Failed: {error_msg}")

                    # --- 2. Check Activities ---
                    act_url = f"{session_url}/activities"
                    act_resp = await client.get(act_url, headers=self._get_headers(), timeout=10.0)

                    if act_resp.status_code == 200:
                        act_data = act_resp.json()
                        activities = act_data.get("activities", [])

                        if len(activities) > last_activity_count:
                            self.console.print(f"\n[bold blue]New Activity detected ({len(activities)} total)[/bold blue]")
                            # TODO: Log activity details if useful
                            last_activity_count = len(activities)

                    # --- 3. Non-blocking User Input Check (Linux/Mac) ---
                    # This allows the user to type concurrently with polling loop
                    # Only works on POSIX systems with select().
                    try:
                        import sys, select
                        # Check if stdin has data waiting
                        if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                            line = sys.stdin.readline()
                            if line:
                                user_msg = line.strip()
                                if user_msg:
                                    self.console.print(f"[dim]Sending: {user_msg}[/dim]")
                                    await self._send_message(session_url, user_msg)
                    except Exception:
                        pass # Ignore if select not supported or fails

                except Exception as e:
                    logger.warning(f"Polling loop error: {e}")

                await asyncio.sleep(self.poll_interval)

    async def _send_message(self, session_url: str, content: str):
        """
        Sends a message to the active session.
        Endpoint: POST /{session_name}:sendMessage
        Payload: { "prompt": "..." }
        """
        url = f"{session_url}:sendMessage"
        payload = {"prompt": content}

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(url, json=payload, headers=self._get_headers())
                if resp.status_code == 200:
                    self.console.print("[dim]Message sent.[/dim]")
                else:
                    self.console.print(f"[bold red]Failed to send message: {resp.status_code}[/bold red]")
                    logger.error(f"SendMessage failed: {resp.text}")
            except Exception as e:
                logger.error(f"SendMessage error: {e}")
