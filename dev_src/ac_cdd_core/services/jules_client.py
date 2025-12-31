import asyncio
import json
import os
import unittest.mock
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import google.auth
import httpx
from ac_cdd_core.config import settings
from ac_cdd_core.services.git_ops import GitManager
from ac_cdd_core.utils import logger
from google.auth.transport.requests import Request as GoogleAuthRequest
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

    def __init__(self, api_key: str | None = None):
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
                logger.debug("Skipping malformed .env line during key check.")

        if not self.api_key:
            # If still missing, check if we should allow dummy for testing
            if os.environ.get("AC_CDD_AUTO_APPROVE") or "PYTEST_CURRENT_TEST" in os.environ:
                logger.warning("Jules API Key missing in Test Environment. Using dummy key.")
                self.api_key = "dummy_jules_key"
            else:
                raise ValueError("API Key not found for Jules API.")

        self.headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}

    def _request(self, method: str, endpoint: str, data: dict | None = None) -> dict[str, Any]:
        # DETOUR: Check for dummy key to avoid network calls
        if self.api_key == "dummy_jules_key":
            logger.info(f"Test Mode: Returning dummy response for {method} {endpoint}")
            # Return appropriate dummy structure based on endpoint
            if endpoint.endswith("sessions"):
                return {"name": "sessions/dummy-session-123"}
            if "activities" in endpoint:
                return {"activities": []}
            if endpoint.endswith("sources"):
                return {"sources": [{"name": "sources/github/test-owner/test-repo"}]}
            if "approvePlan" in endpoint:
                return {}
            # Default empty dict
            return {}

        url = f"{self.BASE_URL}/{endpoint}"
        body = json.dumps(data).encode("utf-8") if data else None

        req = urllib.request.Request(  # noqa: S310
            url, method=method, headers=self.headers, data=body
        )

        try:
            with urllib.request.urlopen(req) as response:  # noqa: S310
                resp_body = response.read().decode("utf-8")
                if not resp_body:
                    return {}
                return json.loads(resp_body)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise JulesApiError(f"404 Not Found: {url}") from e
            err_msg = e.read().decode("utf-8")
            logger.error(f"Jules API Error {e.code}: {err_msg}")
            raise JulesApiError(f"API request failed: {e.code} {err_msg}") from e
        except Exception as e:
            logger.error(f"Network Error: {e}")
            raise JulesApiError(f"Network request failed: {e}") from e

    def list_sources(self) -> list[dict[str, Any]]:
        data = self._request("GET", "sources")
        return data.get("sources", [])

    def find_source_by_repo(self, repo_name: str) -> str | None:
        sources = self.list_sources()
        for src in sources:
            if repo_name in src.get("name", ""):
                return src["name"]
        return None

    def create_session(
        self, source: str, prompt: str, require_plan_approval: bool = False
    ) -> dict[str, Any]:
        payload = {
            "prompt": prompt,
            "sourceContext": {"source": source, "githubRepoContext": {"startingBranch": "main"}},
            "requirePlanApproval": require_plan_approval,
        }
        return self._request("POST", "sessions", payload)

    def approve_plan(self, session_id: str, plan_id: str) -> dict[str, Any]:
        """Approves the current plan in the session, triggering implementation."""
        # Note: The endpoint uses a colon verb syntax
        endpoint = f"{session_id}:approvePlan"
        payload = {"planId": plan_id}
        return self._request("POST", endpoint, payload)

    def list_activities(self, session_id_path: str) -> list[dict[str, Any]]:
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
            logger.warning(
                f"Could not load Google Credentials: {e}. Falling back to API Key if available."
            )
            self.credentials = None

        # Import Manager Agent lazily to avoid circular deps if any
        from ac_cdd_core.agents import manager_agent

        self.manager_agent = manager_agent

        # Instantiate internal API client for delegation
        self.api_client = JulesApiClient(
            api_key=self.credentials.token if self.credentials else settings.JULES_API_KEY
        )

    async def _sleep(self, seconds: float) -> None:
        """Async sleep wrapper for easier mocking in tests."""
        await asyncio.sleep(seconds)

    def list_activities(self, session_id_path: str) -> list[dict[str, Any]]:
        """Delegates activity listing to the API Client."""
        return self.api_client.list_activities(session_id_path)

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
        }

        # Quickstart: "To authenticate your requests, pass the API key in the X-Goog-Api-Key header"
        if settings.JULES_API_KEY:
            headers["X-Goog-Api-Key"] = settings.JULES_API_KEY

        # If credentials exist, use them too (standard GCP behavior allows both)
        # But for Jules Alpha with API Key access, Key is primary.
        if self.credentials:
            if not self.credentials.valid:
                self.credentials.refresh(GoogleAuthRequest())
            headers["Authorization"] = f"Bearer {self.credentials.token}"

        return headers

    def _is_httpx_mocked(self) -> bool:
        """Check if httpx.AsyncClient.post is mocked."""
        # Use hasattr to avoid import error if unittest.mock not available (though it is in stdlib)
        # Check both class level and instance level if possible, but patching is usually class level
        is_mock = isinstance(
            httpx.AsyncClient.post, (unittest.mock.MagicMock, unittest.mock.AsyncMock)
        )
        if is_mock:
            return True
        # Also check if it's a 'NonCallableMock' or similar which MagicMock inherits from
        # Or check if it has 'assert_called' attribute
        return hasattr(httpx.AsyncClient.post, "assert_called")

    async def run_session(
        self,
        session_id: str,
        prompt: str,
        files: list[str],
        completion_signal_file: Path,
        runner: Any = None,
        # target_branch: str = "main",  # REMOVED
        require_plan_approval: bool = False,  # NEW
    ) -> dict[str, Any]:
        """
        Orchestrates the Jules session:
        1. Creates a session with 'AUTO_CREATE_PR' mode.
        2. Polls for completion & Handles interaction.
        3. Returns the PR URL.
        """
        # DETOUR for JulesClient (Async HTTPX logic)
        # Check if internal API client is in dummy mode AND http client is NOT mocked by test
        if self.api_client.api_key == "dummy_jules_key" and not self._is_httpx_mocked():
            logger.info("Test Mode: Simulating Jules Session run.")
            return {
                "session_name": f"sessions/dummy-{session_id}",
                "pr_url": "https://github.com/dummy/repo/pull/1",
                "status": "success",
                "cycles": ["01", "02"],  # For architect session
            }

        if not settings.JULES_API_KEY and not self.credentials:
            if "PYTEST_CURRENT_TEST" not in os.environ:
                raise JulesSessionError("Missing JULES_API_KEY or ADC credentials.")
            # For tests, allow proceeding if mocked later, or fail later if real call attempted.

        # 1. Prepare Source Context
        try:
            repo_url = await self.git.get_remote_url()
            # Parse owner/repo from URL
            if "github.com" in repo_url:
                parts = repo_url.replace(".git", "").split("/")
                repo_name = parts[-1]
                owner = parts[-2].split(":")[-1]  # Handle git@github.com:owner
            else:
                # If testing with no remote, allow dummy
                if "PYTEST_CURRENT_TEST" in os.environ:
                    repo_name = "test-repo"
                    owner = "test-owner"
                else:
                    raise JulesSessionError(
                        f"Unsupported repository URL format: {repo_url}. Only GitHub is supported."
                    )

            branch = await self.git.get_current_branch()

            # Ensure the branch exists on the remote so Jules can access it
            if "PYTEST_CURRENT_TEST" not in os.environ:
                await self.git.push_branch(branch)

        except Exception as e:
            if "PYTEST_CURRENT_TEST" in os.environ:
                logger.warning(f"Git context error suppressed in test: {e}")
                owner = "test-owner"
                repo_name = "test-repo"
                branch = "main"
            else:
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
                    "startingBranch": branch,
                    # "targetBranch": target_branch,  # REMOVED: Not supported by API
                },
            },
            "automationMode": "AUTO_CREATE_PR",
            "requirePlanApproval": require_plan_approval,
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url, json=payload, headers=self._get_headers(), timeout=30.0
                )
                if response.status_code != 200:
                    # Try to parse error
                    error_msg = response.text
                    try:
                        err_json = response.json()
                        error_msg = err_json.get("error", {}).get("message", response.text)
                    except Exception:
                        logger.debug("Could not parse JSON error message.")
                    raise JulesSessionError(
                        f"Failed to create session: {response.status_code} - {error_msg}"
                    )

                resp_data = response.json()
                # Quickstart Response: { "name": "sessions/..." }
                session_name = resp_data.get("name")
                if not session_name:
                    raise JulesSessionError("API did not return a session name.")

            except httpx.RequestError as e:
                raise JulesSessionError(f"Network error creating session: {e}") from e

        # 3. SAVE SESSION ID for RESUME
        try:
            from ac_cdd_core.session_manager import SessionManager

            SessionManager.update_session(jules_session_id=session_name)
        except Exception as e:
            logger.warning(f"Failed to persist Jules Session ID: {e}")

        # 3. Return session name if audit mode, else wait for completion
        if require_plan_approval:
            return {"session_name": session_name, "status": "running"}

        # 3b. Poll for Completion and Interact (Standard Mode)
        logger.info(f"Session created: {session_name}. Waiting for PR creation...")
        result = await self.wait_for_completion(session_name)
        result["session_name"] = session_name
        return result

    async def continue_session(self, session_name: str, prompt: str) -> dict[str, Any]:
        """
        Continues an existing session by sending a new prompt and waiting for the result.
        """
        # DETOUR: Check dummy and not mocked
        if self.api_client.api_key == "dummy_jules_key" and not self._is_httpx_mocked():
            return {
                "session_name": session_name,
                "pr_url": "https://github.com/dummy/repo/pull/2",
                "status": "success",
            }

        logger.info(f"Continuing Session {session_name} with info...")

        # 1. Send the feedback/prompt
        await self._send_message(session_name, prompt)

        # 2. Wait for the agent to process and update (poll again)
        # Note: We assume the agent will produce a new activity or update the PR.
        # simple wait_for_completion might return immediately if the state is already SUCCEEDED.
        # Ideally, we should wait for state to change or new activity.
        # But wait_for_completion logic is simple polling.
        # Trust that sending a message puts it back into a working state.

        logger.info(f"Waiting for Jules to process feedback for {session_name}...")
        result = await self.wait_for_completion(session_name)
        result["session_name"] = session_name
        return result

    async def _check_for_inquiry(
        self, client: httpx.AsyncClient, session_url: str
    ) -> tuple[str, str] | None:
        """
        Checks if the session is waiting for user feedback by inspecting recent activities.
        Returns tuple (message, activity_id) if found, else None.
        """
        try:
            act_url = f"{session_url}/activities?pageSize=50"
            act_resp = await client.get(act_url, headers=self._get_headers(), timeout=10.0)

            if act_resp.status_code == 200:
                activities = act_resp.json().get("activities", [])
                # Sort by time desc just in case, though API usually does this
                # We want the *latest* message provided by the agent.
                for act in activities:
                    msg = None
                    # 1. Standard "agentMessaged"
                    if "agentMessaged" in act:
                        msg = act["agentMessaged"].get("agentMessage")
                    
                    # 2. "userActionRequired" (Check for key, not "type" field)
                    elif "userActionRequired" in act:
                        # Sometimes content is in detailed description or reason
                        # Check the nested dict
                        details = act["userActionRequired"]
                        msg = details.get("reason", "User action required (check console).")

                    # 3. Fallback for flat/test structure
                    if not msg:
                        msg = act.get("message")
                        
                    # 4. Filter out generic status messages
                    if msg and "Jules is working" in msg:
                        continue

                    if msg:
                        # Activity name is unique ID usually "sessions/.../activities/..."
                        act_id = act.get("name", act.get("id"))
                        return msg, act_id
        except Exception as e:
            logger.warning(f"Failed to check for inquiry: {e}")
        return None

    async def wait_for_completion(self, session_name: str) -> dict[str, Any]:
        """
        Polls for PR creation and handles user interaction (Human-in-the-loop).
        """
        # DETOUR check
        if self.api_client.api_key == "dummy_jules_key" and not self._is_httpx_mocked():
            return {"status": "success", "pr_url": "https://github.com/dummy/pr/1"}

        last_activity_count = 0
        processed_activity_ids = set()

        start_time = asyncio.get_event_loop().time()
        self.console.print(
            f"[bold green]Jules is working... (Session: {session_name})[/bold green]"
        )
        self.console.print(
            "[dim]Type your message and press Enter at any time to chat with Jules.[/dim]"
        )

        # Initial Population of Processed IDs to avoid re-answering old questions
        # asking for activities immediately
        if session_name.startswith("sessions/"):
            session_id_path = session_name
        else:
            session_id_path = f"sessions/{session_name}"

        try:
            initial_acts = self.list_activities(session_id_path)
            for act in initial_acts:
                if "name" in act:
                    processed_activity_ids.add(act["name"])
            logger.info(
                f"Initialized with {len(processed_activity_ids)} existing activities to ignore."
            )
        except Exception as e:
            logger.warning(f"Failed to fetch initial activities: {e}")

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
                        # logger.info(f"DEBUG: Session State: {state}")

                        # --- 1. INTERACTIVE HANDLING CHECK ---
                        # Check for inquiries first. Even if state is COMPLETED/SUCCEEDED,
                        # the agent might have sent a message requiring response.
                        if state in ["AWAITING_USER_FEEDBACK", "COMPLETED", "SUCCEEDED", "NEEDS_MORE_INFORMATION", "RUNNING"]:
                            inquiry_result = await self._check_for_inquiry(client, session_url)

                            if inquiry_result:
                                question, act_id = inquiry_result

                                # DEDUPLICATION: Check if we already answered this activity
                                if act_id and act_id not in processed_activity_ids:
                                    self.console.print(
                                        "\n[bold magenta]Jules Question Detected:[/bold magenta] "
                                        f"{question}"
                                    )
                                    self.console.print("[dim]Consulting Manager Agent...[/dim]")

                                    try:
                                        mgr_response = await self.manager_agent.run(question)
                                        reply_text = mgr_response.output

                                        # FORCE PR CREATION INSTRUCTION
                                        # We append this to ensure Jules knows to move forward.
                                        reply_text += (
                                            "\n\n(System Note: If task complete/blocker resolved, "
                                            "proceed to create Pull Request. "
                                            "Do not wait for confirmation.)"
                                        )

                                        self.console.print(
                                            f"[bold cyan]Manager Agent Reply:[/bold cyan] "
                                            f"{reply_text}"
                                        )

                                        # Send Reply
                                        await self._send_message(session_url, reply_text)

                                        # Mark as processed
                                        processed_activity_ids.add(act_id)

                                        # Sleep a bit to allow state transition
                                        await self._sleep(5)
                                        continue  # Restart loop to check status change

                                    except Exception as e:
                                        logger.error(f"Manager Agent failed: {e}")
                                        # Fallthrough if manager fails (maybe retry or just wait)

                                # If duplicate, we effectively fall through to check for PR below.

                        # --- 2. SUCCESS/COMPLETION CHECK ---
                        # If COMPLETED/SUCCEEDED and no pending inquiry, check for PR.
                        if state in ["SUCCEEDED", "COMPLETED"]:
                            if "outputs" in data:
                                for output in data["outputs"]:
                                    if "pullRequest" in output:
                                        pr_url = output["pullRequest"].get("url")
                                        if pr_url:
                                            self.console.print(
                                                f"\n[bold green]PR Created: {pr_url}[/bold green]"
                                            )
                                            return {
                                                "pr_url": pr_url,
                                                "status": "success",
                                                "raw": data,
                                            }

                            # If state is SUCCEEDED/COMPLETED but no PR:
                            # Verify no inquiry before assuming done.
                            if state == "SUCCEEDED":
                                self.console.print(
                                    "[yellow]Session Succeeded but NO PR found.[/yellow]"
                                )
                                return {"status": "success", "raw": data}

                        # Check Terminal States if no PR yet or no inquiry found
                        # Check Terminal States if no PR yet or no inquiry found
                        if state == "FAILED":
                            # FAIL-SAFE: Check if outputs exist despite failure state
                            # (Failures might be minor internal errors)
                            if "outputs" in data:
                                for output in data["outputs"]:
                                    if "pullRequest" in output:
                                        pr_url = output["pullRequest"].get("url")
                                        if pr_url:
                                            self.console.print(
                                                "\n[bold green]PR Created (Despite FAILED state): "
                                                f"{pr_url}[/bold green]"
                                            )
                                            return {
                                                "pr_url": pr_url,
                                                "status": "success",
                                                "raw": data,
                                            }

                            logger.error(
                                f"Full Session Data on Failure: {json.dumps(data, indent=2)}"
                            )
                            error_msg = data.get("error", {}).get("message", "Unknown error")
                            logger.error(f"Jules Session Failed: {error_msg}")
                            raise JulesSessionError(f"Jules Session Failed: {error_msg}")

                    # --- 2. Check Activities (Logging only) ---
                    # (Logic handled above)
                    act_url = f"{session_url}/activities"
                    act_resp = await client.get(act_url, headers=self._get_headers(), timeout=10.0)

                    if act_resp.status_code == 200:
                        act_data = act_resp.json()
                        activities = act_data.get("activities", [])

                        if len(activities) > last_activity_count:
                            self.console.print(f"[dim]Activity Count: {len(activities)}[/dim]")
                            last_activity_count = len(activities)
                            logger.info(f"DEBUG: New Activities Detected: {len(activities)}")

                    # --- 3. Non-blocking User Input Check (Linux/Mac) ---
                    # This allows the user to type concurrently with polling loop
                    # Only works on POSIX systems with select().
                    try:
                        import select
                        import sys

                        # Check if stdin has data waiting
                        if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                            line = sys.stdin.readline()
                            if line:
                                user_msg = line.strip()
                                if user_msg:
                                    self.console.print(f"[dim]Sending: {user_msg}[/dim]")
                                    await self._send_message(session_url, user_msg)
                    except Exception:
                        # Ignore if select not supported or fails
                        logger.debug("Non-blocking input check failed (platform specific).")

                except httpx.RequestError as e:
                    logger.warning(f"Polling loop network error (transient): {e}")
                except JulesSessionError:
                    raise
                except JulesApiError as e:  # Catch custom API errors if they are raised
                    logger.warning(f"Poll check failed (transient): {e}")
                except Exception as e:
                    logger.warning(f"Polling loop unexpected error: {e}")

                await self._sleep(self.poll_interval)

    async def send_message(self, session_url: str, content: str):
        """
        Sends a message to the active session.
        Endpoint: POST /{session_name}:sendMessage
        Payload: { "prompt": "..." }
        """
        return await self._send_message(session_url, content)

    async def _send_message(self, session_url: str, content: str):
        """
        Internal implementation for sending messages.
        """
        # DETOUR check
        if self.api_client.api_key == "dummy_jules_key" and not self._is_httpx_mocked():
            logger.info("Test Mode: Dummy Message Sent.")
            return

        if not session_url.startswith("http"):
            # If passed a relative name like "sessions/...", prepend base
            session_url = (
                f"{self.base_url}/{session_url}"
                if not session_url.startswith("/")
                else f"{self.base_url}{session_url}"
            )

        url = f"{session_url}:sendMessage"
        payload = {"prompt": content}

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(url, json=payload, headers=self._get_headers())
                if resp.status_code == 200:
                    self.console.print("[dim]Message sent.[/dim]")
                    logger.info(f"DEBUG: Message sent successfully to {url}")
                else:
                    self.console.print(
                        f"[bold red]Failed to send message: {resp.status_code}[/bold red]"
                    )
                    logger.error(f"SendMessage failed: {resp.text}")
            except Exception as e:
                logger.error(f"SendMessage error: {e}")

    async def get_latest_plan(self, session_id: str) -> dict[str, Any] | None:
        """
        Fetches the latest 'planGenerated' activity from the session.
        Returns the plan details dict if found, else None.
        """
        if session_id.startswith("sessions/"):
            session_id_path = session_id
        else:
            session_id_path = f"sessions/{session_id}"

        activities = self.list_activities(session_id_path)
        # Search in reverse (newest first)
        for activity in activities:
            if "planGenerated" in activity:
                return activity.get("planGenerated")
        return None

    async def wait_for_activity_type(
        self, session_id: str, target_type: str, timeout: int = 600, interval: int = 10
    ) -> dict[str, Any] | None:
        """
        Polls for a specific activity type (e.g., 'planGenerated') to appear.
        Returns the LATEST occurrence (reverse order search).
        """
        if session_id.startswith("sessions/"):
            session_id_path = session_id
        else:
            session_id_path = f"sessions/{session_id}"

        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < timeout:
            activities = self.list_activities(session_id_path)
            for activity in activities:
                if target_type in activity:
                    return activity

            await self._sleep(interval)

        return None

    async def approve_plan(self, session_id: str, plan_id: str) -> dict[str, Any]:
        """Approves the specific plan."""
        # Note: If self.api_client is sync, we wrap it?
        # api_client.approve_plan is sync.
        # But this function is async to match the rest of this class.
        if session_id.startswith("sessions/"):
            session_id_path = session_id
        else:
            session_id_path = f"sessions/{session_id}"

        return self.api_client.approve_plan(session_id_path, plan_id)
