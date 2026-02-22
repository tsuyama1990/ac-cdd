import asyncio
import os
import sys
import unittest.mock
from typing import Any

try:
    import select
except ImportError:
    select = None  # type: ignore[assignment]

import google.auth
import httpx
from ac_cdd_core.agents import get_manager_agent
from ac_cdd_core.config import settings
from ac_cdd_core.services.git_ops import GitManager
from ac_cdd_core.utils import logger
from google.auth.transport.requests import Request as GoogleAuthRequest
from rich.console import Console

from .jules.api import JulesApiClient
from .jules.context_builder import JulesContextBuilder
from .jules.git_context import JulesGitContext
from .jules.inquiry_handler import JulesInquiryHandler

console = Console()


# --- Exception Classes ---
class JulesSessionError(Exception):
    pass


class JulesTimeoutError(JulesSessionError):
    pass


class JulesApiError(Exception):
    pass


# --- API Client Implementation ---
# Moved to services/jules/api.py


# --- Service Client Implementation ---
class JulesClient:
    """
    Client for interacting with the Google Cloud Code Agents API (Jules API).
    """

    def __init__(self) -> None:
        self.project_id = settings.GCP_PROJECT_ID
        self.base_url = "https://jules.googleapis.com/v1alpha"
        self.timeout = settings.jules.timeout_seconds
        self.poll_interval = settings.jules.polling_interval_seconds
        self.console = Console()
        self.git = GitManager()

        try:
            self.credentials, self.project_id_from_auth = google.auth.default()  # type: ignore[no-untyped-call]
            if not self.project_id:
                self.project_id = self.project_id_from_auth
        except Exception as e:
            logger.warning(
                f"Could not load Google Credentials: {e}. Falling back to API Key if available."
            )
            self.credentials = None

        self.manager_agent = get_manager_agent()

        # Import PlanAuditor for plan approval (separate from manager_agent for questions)
        from ac_cdd_core.services.plan_auditor import PlanAuditor

        self.plan_auditor = PlanAuditor()

        api_key_to_use = settings.JULES_API_KEY
        if not api_key_to_use and self.credentials:
            api_key_to_use = self.credentials.token

        self.api_client = JulesApiClient(api_key=api_key_to_use)
        self.context_builder = JulesContextBuilder(self.git)
        self.git_context = JulesGitContext(self.git)
        self.inquiry_handler = JulesInquiryHandler(
            manager_agent=self.manager_agent, context_builder=self.context_builder, client_ref=self
        )

    async def _sleep(self, seconds: float) -> None:
        """Async sleep wrapper for easier mocking in tests."""
        await asyncio.sleep(seconds)

    def list_activities(self, session_id_path: str) -> list[dict[str, Any]]:
        """Delegates activity listing to the API Client."""
        return self.api_client.list_activities(session_id_path)

    def _get_headers(self) -> dict[str, str]:
        # Reuse headers from api_client + auth if needed
        headers = self.api_client.headers.copy()

        if self.credentials:
            if not self.credentials.valid:
                self.credentials.refresh(GoogleAuthRequest())  # type: ignore[no-untyped-call]
            headers["Authorization"] = f"Bearer {self.credentials.token or ''}"
        return headers

    def _is_httpx_mocked(self) -> bool:
        """Check if httpx.AsyncClient is mocked."""
        is_mock = isinstance(httpx.AsyncClient, (unittest.mock.MagicMock, unittest.mock.AsyncMock))
        if is_mock:
            return True
        return hasattr(httpx.AsyncClient, "return_value")

    async def run_session(
        self,
        session_id: str,
        prompt: str,
        files: list[str] | None = None,
        require_plan_approval: bool = False,
        **extra: Any,
    ) -> dict[str, Any]:
        """Orchestrates the Jules session."""
        if self.api_client.api_key == "dummy_jules_key" and not self._is_httpx_mocked():
            logger.info("Test Mode: Simulating Jules Session run.")
            return {
                "session_name": f"sessions/dummy-{session_id}",
                "pr_url": "https://github.com/dummy/repo/pull/1",
                "status": "success",
                "cycles": ["01", "02"],
            }

        if not self.api_client.api_key and "PYTEST_CURRENT_TEST" not in os.environ:
            errmsg = "Missing JULES_API_KEY or ADC credentials."
            raise JulesSessionError(errmsg)

        owner, repo_name, branch = await self.git_context.prepare_git_context()
        full_prompt = self.context_builder.construct_run_prompt(
            prompt, files, extra.get("target_files"), extra.get("context_files")
        )

        payload = {
            "prompt": full_prompt,
            "sourceContext": {
                "source": f"sources/github/{owner}/{repo_name}",
                "githubRepoContext": {"startingBranch": branch},
            },
            "automationMode": "AUTO_CREATE_PR",
            "requirePlanApproval": require_plan_approval,
        }
        if "title" in extra:
            payload["title"] = str(extra["title"])

        session_name = await self._create_jules_session(payload)

        # Session persistence is handled by the caller (graph_nodes.py)

        if require_plan_approval:
            return {"session_name": session_name, "status": "running"}

        logger.info(f"Session created: {session_name}. Waiting for PR creation...")
        result = await self.wait_for_completion(session_name, require_plan_approval=False)
        result["session_name"] = session_name
        return result

    async def _create_jules_session(self, payload: dict[str, Any]) -> str:
        """Wrapper to call create_session via api_client."""
        prompt = str(payload.get("prompt", ""))
        source_context = payload.get("sourceContext", {})
        source = str(source_context.get("source", ""))

        repo_context = source_context.get("githubRepoContext", {})
        branch = str(repo_context.get("startingBranch", "main"))

        require_approval = bool(payload.get("requirePlanApproval", False))
        title = payload.get("title")
        automation_mode = str(payload.get("automationMode", "AUTO_CREATE_PR"))

        resp = self.api_client.create_session(
            source,
            prompt,
            require_approval,
            branch=branch,
            title=str(title) if title else None,
            automation_mode=automation_mode,
        )
        return str(resp.get("name", ""))

    async def continue_session(self, session_name: str, prompt: str) -> dict[str, Any]:
        """Continues an existing session."""
        if self.api_client.api_key == "dummy_jules_key" and not self._is_httpx_mocked():
            return {
                "session_name": session_name,
                "pr_url": "https://github.com/dummy/repo/pull/2",
                "status": "success",
            }

        logger.info(f"Continuing Session {session_name} with info...")
        await self._send_message(session_name, prompt)
        logger.info(f"Waiting for Jules to process feedback for {session_name}...")
        result = await self.wait_for_completion(session_name)
        result["session_name"] = session_name
        return result

    async def wait_for_completion(
        self, session_name: str, require_plan_approval: bool = False
    ) -> dict[str, Any]:
        """Wait for Jules session completion using LangGraph state management.
        This method uses LangGraph to manage the complex state transitions of:
        - Monitoring session progress
        - Handling inquiries (questions from Jules)
        - Validating completion state
        - Checking for PR creation
        - Requesting manual PR creation if needed
        - Waiting for PR with state re-validation
        """
        if self.api_client.api_key == "dummy_jules_key" and not self._is_httpx_mocked():
            return {"status": "success", "pr_url": "https://github.com/dummy/pr/1"}

        from ac_cdd_core.jules_session_graph import build_jules_session_graph
        from ac_cdd_core.jules_session_state import JulesSessionState
        from langchain_core.runnables import RunnableConfig

        self.console.print(
            f"[bold green]Jules is working... (Session: {session_name})[/bold green]"
        )
        self.console.print(
            "[dim]Type your message and press Enter at any time to chat with Jules.[/dim]"
        )

        session_url = self._get_session_url(session_name)

        # Initialize processed IDs
        processed_ids: set[str] = set()
        processed_completion_ids: set[str] = set()
        await self._initialize_processed_ids(
            session_url, processed_ids, processed_completion_ids=processed_completion_ids
        )

        # Build graph
        graph = build_jules_session_graph(self)

        # Create initial state
        initial_state = JulesSessionState(
            session_url=session_url,
            session_name=session_name,
            start_time=asyncio.get_event_loop().time(),
            timeout_seconds=self.timeout,
            poll_interval=self.poll_interval,
            require_plan_approval=require_plan_approval,
            fallback_max_wait=settings.jules.wait_for_pr_timeout_seconds,
            processed_activity_ids=processed_ids,
            processed_completion_ids=processed_completion_ids,
        )

        # Run graph
        config = RunnableConfig(
            configurable={"thread_id": f"jules-{session_name}"},
            recursion_limit=settings.GRAPH_RECURSION_LIMIT,
        )

        final_state = await graph.ainvoke(initial_state, config)

        # Handle final state
        # LangGraph may return dict or object
        def _get(obj: Any, key: str) -> Any:
            return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)

        status = _get(final_state, "status")

        if status == "success":
            return {
                "status": "success",
                "pr_url": _get(final_state, "pr_url"),
                "raw": _get(final_state, "raw_data"),
            }

        error_msg = _get(final_state, "error") or "Session failed"

        if status == "failed":
            raise JulesSessionError(error_msg)
        if status == "timeout":
            msg = f"Session timed out. Last error: {error_msg}"
            raise JulesTimeoutError(msg)

        msg = f"Session ended in unexpected state: {status}"
        raise JulesSessionError(msg)

    async def wait_for_completion_legacy(
        self, session_name: str, require_plan_approval: bool = False
    ) -> dict[str, Any]:
        """Legacy polling-based implementation (kept for reference/fallback)."""
        if self.api_client.api_key == "dummy_jules_key" and not self._is_httpx_mocked():
            return {"status": "success", "pr_url": "https://github.com/dummy/pr/1"}

        processed_activity_ids: set[str] = set()
        start_time = asyncio.get_event_loop().time()

        self.console.print(
            f"[bold green]Jules is working... (Session: {session_name})[/bold green]"
        )
        self.console.print(
            "[dim]Type your message and press Enter at any time to chat with Jules.[/dim]"
        )

        session_url = self._get_session_url(session_name)
        await self._initialize_processed_ids(session_url, processed_activity_ids)

        last_activity_count = 0
        plan_rejection_count = [0]  # Use list to persist across iterations
        max_plan_rejections = 2  # Limit plan approval iterations
        async with httpx.AsyncClient() as client:
            while True:
                if asyncio.get_event_loop().time() - start_time > self.timeout:
                    tmsg = "Timed out waiting for Jules to complete."
                    raise JulesTimeoutError(tmsg)

                try:
                    response = await client.get(session_url, headers=self._get_headers())
                    response.raise_for_status()
                    data = response.json()

                    if data:
                        state = data.get("state")
                        logger.info(f"Jules session state: {state}")
                        await self.inquiry_handler.process_inquiries(
                            client,
                            session_url,
                            state,
                            processed_activity_ids,
                            plan_rejection_count,
                            max_plan_rejections,
                            require_plan_approval,
                        )
                        success_result = await self._check_success_state(
                            client, session_url, data, state
                        )
                        if success_result:
                            return success_result
                        self._check_failure_state(data, state)

                    last_activity_count = await self._log_activities_count(
                        client, session_url, last_activity_count
                    )
                    await self._handle_manual_input(session_url)

                except httpx.RequestError as e:
                    logger.warning(f"Polling loop network error (transient): {e}")
                except JulesSessionError:
                    raise
                except JulesApiError as e:
                    logger.warning(f"Poll check failed (transient): {e}")
                except Exception as e:
                    logger.warning(f"Polling loop unexpected error: {e}")

                await self._sleep(self.poll_interval)

    def _get_session_url(self, session_name: str) -> str:
        if session_name.startswith("sessions/"):
            return f"{self.base_url}/{session_name}"
        return f"{self.base_url}/sessions/{session_name}"

    async def get_session_state(self, session_id: str) -> str:
        """Get current state of Jules session.

        Args:
            session_id: Session ID (with or without "sessions/" prefix)

        Returns:
            Official Jules API Session state:
              - QUEUED: Session is queued
              - PLANNING: Jules is planning
              - AWAITING_PLAN_APPROVAL: Waiting for plan approval
              - AWAITING_USER_FEEDBACK: Jules has a question
              - IN_PROGRESS: Jules is actively working
              - PAUSED: Session is paused
              - FAILED: Session failed
              - COMPLETED: Session completed (may or may not have PR)
              - STATE_UNSPECIFIED: Unknown state
              - UNKNOWN: Could not retrieve state (network error etc.)
        """
        session_url = self._get_session_url(session_id)

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(session_url, headers=self._get_headers(), timeout=10.0)
                resp.raise_for_status()
                data = resp.json()
                return str(data.get("state", "UNKNOWN"))
            except Exception as e:
                logger.warning(f"Failed to get session state for {session_id}: {e}")
                return "UNKNOWN"

    async def _initialize_processed_ids(  # noqa: C901
        self,
        session_url: str,
        processed_ids: set[str],
        processed_completion_ids: set[str] | None = None,
    ) -> None:
        try:
            state = "UNKNOWN"
            initial_acts = []

            # Fetch session state and early activities via httpx to respect test mocks
            try:
                async with httpx.AsyncClient() as client:
                    session_resp = await client.get(
                        session_url, headers=self._get_headers(), timeout=10.0
                    )
                    if session_resp.status_code == httpx.codes.OK:
                        state = session_resp.json().get("state", "UNKNOWN")

                    act_url = f"{session_url}/activities?pageSize=100"
                    act_resp = await client.get(act_url, headers=self._get_headers(), timeout=10.0)
                    if act_resp.status_code == httpx.codes.OK:
                        initial_acts = act_resp.json().get("activities", [])
            except Exception as e:
                logger.warning(f"Failed to fetch initial session data: {e}")

            latest_inquiry_id = None
            latest_ts = ""

            for act in initial_acts:
                act_id = act.get("name")
                if not act_id:
                    continue

                processed_ids.add(act_id)

                if processed_completion_ids is not None and "sessionCompleted" in act:
                    processed_completion_ids.add(act_id)

                # If awaiting feedback, track the latest inquiry
                if state == "AWAITING_USER_FEEDBACK":
                    msg = self.inquiry_handler.extract_activity_message(act)
                    if msg:
                        ts = act.get("createTime", "")
                        if ts >= latest_ts:
                            latest_ts = ts
                            latest_inquiry_id = act_id

            # If we are waiting for feedback, ensure the latest inquiry is NOT ignored
            if latest_inquiry_id:
                processed_ids.discard(latest_inquiry_id)
                logger.info(
                    f"Session is {state}: Re-enabling latest inquiry {latest_inquiry_id} for processing."
                )

            logger.info(f"Initialized with {len(processed_ids)} existing activities to ignore.")
        except Exception as e:
            logger.warning(f"Failed to fetch initial activities: {e}")

    async def _check_success_state(  # noqa: C901
        self, client: httpx.AsyncClient, session_url: str, data: dict[str, Any], state: str
    ) -> dict[str, Any] | None:
        # Only COMPLETED state exists in Jules API (not SUCCEEDED)
        if state != "COMPLETED":
            return None

        # First check session outputs
        for output in data.get("outputs", []):
            if "pullRequest" in output:
                pr_url = output["pullRequest"].get("url")
                if pr_url:
                    self.console.print(f"\n[bold green]PR Created: {pr_url}[/bold green]")
                    return {"pr_url": pr_url, "status": "success", "raw": data}

        # Fallback: check activities for PR (sometimes PR is in activities but not outputs)
        try:
            act_url = f"{session_url}/activities"
            act_resp = await client.get(act_url, headers=self._get_headers(), timeout=10.0)
            if act_resp.status_code == httpx.codes.OK:
                activities = act_resp.json().get("activities", [])
                for activity in activities:
                    if "pullRequest" in activity:
                        pr_data = activity.get("pullRequest", {})
                        pr_url = pr_data.get("url")
                        if pr_url:
                            self.console.print(f"\n[bold green]PR Created: {pr_url}[/bold green]")
                            logger.info(
                                f"Found PR in activities (not in session outputs): {pr_url}"
                            )
                            return {"pr_url": pr_url, "status": "success", "raw": data}
        except Exception as e:
            logger.debug(f"Failed to check activities for PR: {e}")

        # If session is COMPLETED but no PR found, try to create PR manually
        if state == "COMPLETED":
            self.console.print("[yellow]Session Completed but NO PR found.[/yellow]")
            self.console.print("[cyan]Attempting to create PR manually...[/cyan]")

            try:
                pr_url = await self._create_manual_pr(session_url)
                if pr_url:
                    self.console.print(
                        f"\n[bold green]✓ PR Created Manually: {pr_url}[/bold green]"
                    )
                    return {"pr_url": pr_url, "status": "success", "raw": data}
            except Exception as e:
                logger.warning(f"Failed to create manual PR: {e}")
                self.console.print(f"[yellow]Could not create PR automatically: {e}[/yellow]")

            return {"status": "success", "raw": data}
        return None

    def _check_failure_state(self, data: dict[str, Any], state: str) -> None:
        if state != "FAILED":
            return

        for output in data.get("outputs", []):
            if "pullRequest" in output:
                pr_url = output["pullRequest"].get("url")
                if pr_url:
                    self.console.print(
                        f"\n[bold green]PR Created (Despite FAILED state): {pr_url}[/bold green]"
                    )

        error_msg = data.get("error", {}).get("message", "Unknown error")
        logger.error(f"Jules Session Failed: {error_msg}")
        emsg = f"Jules Session Failed: {error_msg}"
        raise JulesSessionError(emsg)

    async def _log_activities_count(
        self, client: httpx.AsyncClient, session_url: str, last_count: int
    ) -> int:
        act_url = f"{session_url}/activities"
        try:
            resp = await client.get(act_url, headers=self._get_headers(), timeout=10.0)
            if resp.status_code == httpx.codes.OK:
                activities = resp.json().get("activities", [])
                if len(activities) > last_count:
                    self.console.print(f"[dim]Activity Count: {len(activities)}[/dim]")
                    return len(activities)
        except Exception:  # noqa: S110
            pass
        return last_count

    async def _handle_manual_input(self, session_url: str) -> None:
        if not select:
            return
        try:
            if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                line = sys.stdin.readline()
                if line:
                    user_msg = line.strip()
                    if user_msg:
                        self.console.print(f"[dim]Sending: {user_msg}[/dim]")
                        await self._send_message(session_url, user_msg)
        except Exception:
            logger.debug("Non-blocking input check failed.")

    async def send_message(self, session_url: str, content: str) -> None:
        """Sends a message to the active session."""
        await self._send_message(session_url, content)

    async def _send_message(self, session_url: str, content: str) -> None:
        """Internal implementation for sending messages."""
        if self.api_client.api_key == "dummy_jules_key" and not self._is_httpx_mocked():
            logger.info("Test Mode: Dummy Message Sent.")
            return

        if not session_url.startswith("http"):
            session_url = self._get_session_url(session_url)

        url = f"{session_url}:sendMessage"
        payload = {"prompt": content}

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(url, json=payload, headers=self._get_headers())
                if resp.status_code == httpx.codes.OK:
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
        """Fetches the latest 'planGenerated' activity."""
        session_id_path = (
            session_id if session_id.startswith("sessions/") else f"sessions/{session_id}"
        )
        activities = self.list_activities(session_id_path)
        for activity in activities:
            if "planGenerated" in activity:
                return dict(activity.get("planGenerated", {}))
        return None

    async def wait_for_activity_type(
        self, session_id: str, target_type: str, timeout_seconds: int = 600, interval: int = 10
    ) -> dict[str, Any] | None:
        """Polls for a specific activity type with timeout."""
        session_id_path = (
            session_id if session_id.startswith("sessions/") else f"sessions/{session_id}"
        )
        try:
            async with asyncio.timeout(timeout_seconds):
                while True:
                    activities = self.list_activities(session_id_path)
                    for activity in activities:
                        if target_type in activity:
                            return activity
                    await self._sleep(interval)
        except TimeoutError:
            return None

    async def approve_plan(self, session_id: str, plan_id: str) -> dict[str, Any]:
        """Approves the specific plan."""
        session_id_path = (
            session_id if session_id.startswith("sessions/") else f"sessions/{session_id}"
        )
        return self.api_client.approve_plan(session_id_path, plan_id)

    async def _create_manual_pr(self, session_url: str) -> str | None:  # noqa: C901
        """
        Ask Jules to commit changes and create PR when auto-PR creation fails.

        Returns PR URL if successful, None otherwise.
        """
        try:
            self.console.print("[cyan]Sending message to Jules to commit and create PR...[/cyan]")

            message = (
                "The session has completed successfully, but no Pull Request was created.\n\n"
                "Please commit all your changes and create a Pull Request now.\n\n"
                "**Action Required:**\n"
                "1. Review all the files you've created/modified\n"
                "2. Commit all changes with a descriptive commit message\n"
                "3. Create a Pull Request to the main branch\n\n"
                "Do not wait for further instructions. Proceed immediately."
            )

            await self._send_message(session_url, message)

            # Wait for Jules to process and create PR
            self.console.print("[dim]Waiting for Jules to create PR...[/dim]")

            # Poll for PR creation (max 5 minutes)
            import asyncio

            max_wait = settings.jules.wait_for_pr_timeout_seconds
            poll_interval = 10
            elapsed = 0
            processed_fallback_ids: set[str] = set()

            async with httpx.AsyncClient() as client:
                while elapsed < max_wait:
                    await asyncio.sleep(poll_interval)
                    elapsed += poll_interval

                    # Check for PR and new activities
                    act_url = f"{session_url}/activities"
                    try:
                        act_resp = await client.get(
                            act_url, headers=self._get_headers(), timeout=10.0
                        )
                        if act_resp.status_code == httpx.codes.OK:
                            activities = act_resp.json().get("activities", [])
                            for activity in activities:
                                # Check for PR
                                if "pullRequest" in activity:
                                    pr_url: str | None = activity["pullRequest"].get("url")
                                    if pr_url:
                                        self.console.print(
                                            f"[bold green]PR Created: {pr_url}[/bold green]"
                                        )
                                        return pr_url

                                # Log new activities to show progress
                                act_id = activity.get("name", activity.get("id"))
                                if act_id and act_id not in processed_fallback_ids:
                                    msg = self.inquiry_handler.extract_activity_message(activity)
                                    if msg:
                                        self.console.print(f"[dim]Jules: {msg}[/dim]")
                                    processed_fallback_ids.add(act_id)

                    except Exception as e:
                        logger.debug(f"Error checking for PR/activities: {e}")

                    if elapsed % 30 == 0:  # Progress update every 30 seconds
                        self.console.print(
                            f"[dim]Still waiting for PR... ({elapsed}/{max_wait}s elapsed)[/dim]"
                        )

                logger.warning(f"Timeout ({max_wait}s) waiting for Jules to create PR")
                return None

        except Exception as e:
            logger.error(f"Error requesting Jules to create PR: {e}")
            return None
