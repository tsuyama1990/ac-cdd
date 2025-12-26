import asyncio
import json
import httpx
import google.auth
import sys
import select
import os
import re
import time
from google.auth.transport.requests import Request as GoogleAuthRequest
from typing import Any, Optional, Dict, List
from pathlib import Path
import urllib.request
import urllib.error

from ac_cdd_core.config import settings
from ac_cdd_core.utils import logger
from ac_cdd_core.services.git_ops import GitManager
from rich.console import Console

console = Console()

# --- Exception Classes ---
class JulesSessionError(Exception):
    pass

class JulesTimeoutError(JulesSessionError):
    pass

class JulesApiError(Exception):
    pass

# --- API Client Implementation ---
class JulesApiClient:
    BASE_URL = "https://jules.googleapis.com/v1alpha"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.JULES_API_KEY
        if not self.api_key:
            from dotenv import load_dotenv
            load_dotenv()
            self.api_key = os.getenv("JULES_API_KEY") or os.getenv("GOOGLE_API_KEY")
        
        if not self.api_key:
            # Last ditch attempt
            try:
                if Path(".env").exists():
                    content = Path(".env").read_text()
                    for line in content.splitlines():
                        if line.startswith("JULES_API_KEY="):
                            self.api_key = line.split("=", 1)[1].strip().strip('"')
            except Exception:
                pass
            
        if not self.api_key:
             raise ValueError("API Key not found for Jules API.")

        self.headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json"
        }

    def _request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/{endpoint}"
        body = json.dumps(data).encode("utf-8") if data else None
        
        req = urllib.request.Request(url, method=method, headers=self.headers, data=body)
        
        try:
            with urllib.request.urlopen(req) as response:
                resp_body = response.read().decode("utf-8")
                if not resp_body:
                    return {}
                return json.loads(resp_body)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise JulesApiError(f"404 Not Found: {url}")
            err_msg = e.read().decode("utf-8")
            logger.error(f"Jules API Error {e.code}: {err_msg}")
            raise JulesApiError(f"API request failed: {e.code} {err_msg}") from e
        except Exception as e:
            logger.error(f"Network Error: {e}")
            raise JulesApiError(f"Network request failed: {e}") from e

    def list_sources(self) -> List[Dict[str, Any]]:
        data = self._request("GET", "sources")
        return data.get("sources", [])

    def find_source_by_repo(self, repo_name: str) -> Optional[str]:
        sources = self.list_sources()
        for src in sources:
            if repo_name in src.get("name", ""):
                 return src["name"]
        return None

    def create_session(self, source: str, prompt: str) -> Dict[str, Any]:
        payload = {
            "prompt": prompt,
            "sourceContext": {
                "source": source,
                "githubRepoContext": {
                    "startingBranch": "main"
                }
            }
        }
        return self._request("POST", "sessions", payload)

    def approve_plan(self, session_id: str) -> Dict[str, Any]:
        """Approves the current plan in the session, triggering PR creation."""
        # Note: The endpoint uses a colon verb syntax
        endpoint = f"{session_id}:approvePlan"
        # Endpoint takes an empty body or specific approval options if needed
        # Documentation implies simple POST is enough for default approval
        return self._request("POST", endpoint, {})

    def list_activities(self, session_id_path: str) -> List[Dict[str, Any]]:
        try:
            resp = self._request("GET", f"{session_id_path}/activities?pageSize=50")
            return resp.get("activities", [])
        except JulesApiError as e:
            if "404" in str(e):
                return []
            raise


# --- Service Client Implementation ---
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
        
        # Import Manager Agent lazily to avoid circular deps if any
        from ac_cdd_core.agents import manager_agent
        self.manager_agent = manager_agent

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

            # Ensure the branch exists on the remote so Jules can access it
            await self.git.push_branch(branch)

        except Exception as e:
            raise JulesSessionError(f"Failed to determine/push git context: {e}") from e

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
        result = await self.wait_for_completion(session_name)
        result["session_name"] = session_name
        return result

    async def continue_session(self, session_name: str, prompt: str) -> Dict[str, Any]:
        """
        Continues an existing session by sending a new prompt and waiting for the result.
        """
        logger.info(f"Continuing Session {session_name} with info...")
        
        # 1. Send the feedback/prompt
        await self._send_message(session_name, prompt)
        
        # 2. Wait for the agent to process and update (poll again)
        # Note: We assume the agent will produce a new activity or update the PR.
        # simple wait_for_completion might return immediately if the state is already SUCCEEDED.
        # Ideally, we should wait for state to change or new activity.
        # But wait_for_completion logic is simple polling.
        # Let's trust that sending a message puts it back into a working state or creates new activities.
        
        logger.info(f"Waiting for Jules to process feedback for {session_name}...")
        result = await self.wait_for_completion(session_name)
        result["session_name"] = session_name
        return result

    async def _check_for_inquiry(self, client: httpx.AsyncClient, session_url: str) -> Optional[str]:
        """
        Checks if the session is waiting for user feedback by inspecting recent activities.
        """
        try:
            act_url = f"{session_url}/activities?pageSize=50"
            act_resp = await client.get(act_url, headers=self._get_headers(), timeout=10.0)
            
            if act_resp.status_code == 200:
                activities = act_resp.json().get("activities", [])
                for act in activities:
                    if "agentMessaged" in act:
                        return act["agentMessaged"].get("agentMessage")
        except Exception as e:
            logger.warning(f"Failed to check for inquiry: {e}")
        return None

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


                        # --- INTERACTIVE HANDLING START ---
                        # Check for inquiries in both AWAITING_USER_FEEDBACK and COMPLETED states
                        # COMPLETED might be a "turn complete" state waiting for next input
                        if state in ["AWAITING_USER_FEEDBACK", "COMPLETED"]:
                             question = await self._check_for_inquiry(client, session_url)
                             
                             if question:
                                 self.console.print(f"\n[bold magenta]Jules Question Detected:[/bold magenta] {question}")
                                 self.console.print("[dim]Consulting Manager Agent...[/dim]")
                                 
                                 try:
                                     # Ask Manager Agent
                                     mgr_response = await self.manager_agent.run(question)
                                     reply_text = mgr_response.output
                                     
                                     self.console.print(f"[bold cyan]Manager Agent Reply:[/bold cyan] {reply_text}")
                                     
                                     # Send Reply
                                     await self._send_message(session_url, reply_text)
                                     
                                     # Sleep a bit to allow state transition
                                     await asyncio.sleep(5)
                                     continue # Restart loop to check status change
                                     
                                 except Exception as e:
                                     logger.error(f"Manager Agent failed: {e}")
                                     # Fallthrough if manager fails (maybe retry or just wait)

                        # --- INTERACTIVE HANDLING END ---

                        # Check Terminal States if no PR yet or no inquiry found
                        if state in ["SUCCEEDED", "COMPLETED"]:
                            # If we are here in COMPLETED state, it means no question was found/handled above
                            if "outputs" in data:
                                for output in data["outputs"]:
                                    if "pullRequest" in output:
                                        pr_url = output["pullRequest"].get("url")
                                        if pr_url:
                                            self.console.print(f"\n[bold green]PR Created: {pr_url}[/bold green]")
                                            return {"pr_url": pr_url, "status": "success", "raw": data}

                            self.console.print("[yellow]Session Succeeded/Completed but NO PR found.[/yellow]")
                            return {"status": "success", "raw": data}

                        if state == "FAILED":
                            logger.error(f"Full Session Data on Failure: {json.dumps(data, indent=2)}")
                            error_msg = data.get("error", {}).get("message", "Unknown error")
                            logger.error(f"Jules Session Failed: {error_msg}")
                            raise JulesSessionError(f"Jules Session Failed: {error_msg}")


                    # --- 2. Check Activities (Logging only) ---
                    # (Code below remains for logging purposes, but logic handled above for interaction)
                    act_url = f"{session_url}/activities"
                    act_resp = await client.get(act_url, headers=self._get_headers(), timeout=10.0)

                    if act_resp.status_code == 200:
                        act_data = act_resp.json()
                        activities = act_data.get("activities", [])

                        if len(activities) > last_activity_count:
                             # Just log new activity count for now to avoid duplicate prints with above logic
                             self.console.print(f"[dim]Activity Count: {len(activities)}[/dim]")
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

                except httpx.RequestError as e:
                    logger.warning(f"Polling loop network error (transient): {e}")
                except JulesSessionError:
                    raise
                except JulesApiError as e: # Catch custom API errors if they are raised
                    logger.warning(f"Poll check failed (transient): {e}")
                except Exception as e:
                    logger.warning(f"Polling loop unexpected error: {e}")

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
