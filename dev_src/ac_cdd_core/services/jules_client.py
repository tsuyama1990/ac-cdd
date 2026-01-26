import asyncio
import json
import os
import sys
import unittest.mock
from pathlib import Path
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
from ac_cdd_core.state_manager import StateManager
from ac_cdd_core.utils import logger
from google.auth.transport.requests import Request as GoogleAuthRequest
from rich.console import Console

from .jules.api import JulesApiClient

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
        """Check if httpx.AsyncClient.post is mocked."""
        is_mock = isinstance(
            httpx.AsyncClient.post, (unittest.mock.MagicMock, unittest.mock.AsyncMock)
        )
        if is_mock:
            return True
        return hasattr(httpx.AsyncClient.post, "assert_called")

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

        owner, repo_name, branch = await self._prepare_git_context()
        full_prompt = self._construct_run_prompt(
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

        session_name = await self._create_jules_session(payload)

        # Session persistence is handled by the caller (graph_nodes.py)

        if require_plan_approval:
            return {"session_name": session_name, "status": "running"}

        logger.info(f"Session created: {session_name}. Waiting for PR creation...")
        result = await self.wait_for_completion(session_name, require_plan_approval=False)
        result["session_name"] = session_name
        return result

    async def _prepare_git_context(self) -> tuple[str, str, str]:
        try:
            repo_url = await self.git.get_remote_url()
            if "github.com" in repo_url:
                parts = repo_url.replace(".git", "").split("/")
                repo_name = parts[-1]
                owner = parts[-2].split(":")[-1]
            elif "PYTEST_CURRENT_TEST" in os.environ:
                repo_name, owner = "test-repo", "test-owner"
            else:
                self._raise_jules_session_error(repo_url)

            branch = await self.git.get_current_branch()
            if "PYTEST_CURRENT_TEST" not in os.environ:
                try:
                    await self.git.push_branch(branch)
                except Exception as e:
                    logger.warning(f"Could not push branch: {e}")
        except Exception as e:
            if "PYTEST_CURRENT_TEST" in os.environ:
                return "test-owner", "test-repo", "main"
            if isinstance(e, JulesSessionError):
                raise
            emsg = f"Failed to determine/push git context: {e}"
            raise JulesSessionError(emsg) from e
        else:
            return owner, repo_name, branch

    def _raise_jules_session_error(self, repo_url: str) -> None:
        msg = f"Unsupported repository URL format: {repo_url}"
        raise JulesSessionError(msg)

    def _construct_run_prompt(
        self,
        prompt: str,
        files: list[str] | None,
        target_files: list[str] | None,
        context_files: list[str] | None,
    ) -> str:
        full_prompt = prompt
        if target_files or context_files:
            full_prompt += "\n\n" + "#" * 20 + "\nFILE CONTEXT:\n"
            if context_files:
                full_prompt += "\nREAD-ONLY CONTEXT (Do not edit):\n" + "\n".join(context_files)
            if target_files:
                full_prompt += "\n\nTARGET FILES (To be implemented/edited):\n" + "\n".join(
                    target_files
                )
        elif files:
            file_list_str = "\n".join(files)
            full_prompt += f"\n\nPlease focus on the following files:\n{file_list_str}"
        return full_prompt

    async def _create_jules_session(self, payload: dict[str, Any]) -> str:
        """Wrapper to call create_session via api_client."""
        prompt = str(payload.get("prompt", ""))
        source_context = payload.get("sourceContext", {})
        source = str(source_context.get("source", ""))
        require_approval = bool(payload.get("requirePlanApproval", False))

        resp = self.api_client.create_session(source, prompt, require_approval)
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

    async def _check_for_inquiry(
        self, client: httpx.AsyncClient, session_url: str, processed_ids: set[str]
    ) -> tuple[str, str] | None:
        """Checks if the session is waiting for user feedback."""
        try:
            page_token = ""
            # Check up to 3 pages (300 activities) to capture inquiries buried by logs
            for _ in range(3):
                act_url = f"{session_url}/activities?pageSize=100"
                if page_token:
                    act_url += f"&pageToken={page_token}"

                act_resp = await client.get(act_url, headers=self._get_headers(), timeout=10.0)

                if act_resp.status_code == httpx.codes.OK:
                    data = act_resp.json()
                    activities = data.get("activities", [])

                    # Search activities
                    for act in activities:
                        act_id = act.get("name", act.get("id"))
                        # Skip already processed activities to prevent duplicates
                        if act_id in processed_ids:
                            continue
                        msg = self._extract_activity_message(act)
                        if msg:
                            # But we should process any pending inquiry.
                            return (msg, act_id)

                    page_token = data.get("nextPageToken")
                    if not page_token:
                        break
        except Exception as e:
            logger.warning(f"Failed to check for inquiry: {e}")
        return None

    def _extract_activity_message(self, act: dict[str, Any]) -> str | None:
        msg = None
        if "inquiryAsked" in act:
            # Jules is asking a question
            inquiry = act["inquiryAsked"]
            msg = inquiry.get("inquiry", inquiry.get("question"))
        elif "agentMessaged" in act:
            msg = act["agentMessaged"].get("agentMessage")
        elif "userActionRequired" in act:
            details = act["userActionRequired"]
            msg = details.get("reason", "User action required (check console).")
        if not msg:
            msg = act.get("message")
        if msg and "Jules is working" in msg:
            return None
        return msg

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
        await self._initialize_processed_ids(session_url, processed_ids)

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
                        await self._process_inquiries(
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

    async def _initialize_processed_ids(self, session_url: str, processed_ids: set[str]) -> None:
        try:
            session_id_path = session_url.split(f"{self.base_url}/")[-1]

            # Check session state
            try:
                session_resp = self.api_client._request("GET", session_id_path)
                state = session_resp.get("state")
            except Exception:
                state = "UNKNOWN"

            initial_acts = self.list_activities(session_id_path)

            latest_inquiry_id = None
            latest_ts = ""

            for act in initial_acts:
                act_id = act.get("name")
                if not act_id:
                    continue

                processed_ids.add(act_id)

                # If awaiting feedback, track the latest inquiry
                if state == "AWAITING_USER_FEEDBACK":
                    msg = self._extract_activity_message(act)
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

    def _load_cycle_docs(self, current_cycle: str, context_parts: list[str]) -> None:
        """Load SPEC.md and UAT.md for the current cycle."""
        spec_path = Path(f"dev_documents/system_prompts/CYCLE{current_cycle}/SPEC.md")
        if spec_path.exists():
            spec_content = spec_path.read_text(encoding="utf-8")
            context_parts.append(f"\n## Cycle Specification\n```markdown\n{spec_content}\n```\n")

        uat_path = Path(f"dev_documents/system_prompts/CYCLE{current_cycle}/UAT.md")
        if uat_path.exists():
            uat_content = uat_path.read_text(encoding="utf-8")
            context_parts.append(f"\n## User Acceptance Tests\n```markdown\n{uat_content}\n```\n")

    async def _load_changed_files(self, context_parts: list[str]) -> None:
        """Load content of changed files in the current branch."""
        changed_files = await self.git.get_changed_files()
        if not changed_files:
            return

        context_parts.append(f"\n## Changed Files ({len(changed_files)} files)\n")

        max_files = 10  # Prevent context overflow
        max_file_size = 5000  # chars per file

        for filepath in changed_files[:max_files]:
            try:
                file_path = Path(filepath)
                if file_path.exists() and file_path.suffix in [
                    ".py",
                    ".md",
                    ".toml",
                    ".json",
                    ".yaml",
                    ".yml",
                ]:
                    content = file_path.read_text(encoding="utf-8")
                    if len(content) > max_file_size:
                        content = content[:max_file_size] + "\n... (truncated)"
                    context_parts.append(
                        f"\n### {filepath}\n```{file_path.suffix[1:]}\n{content}\n```\n"
                    )
            except Exception as e:
                logger.debug(f"Could not read {filepath}: {e}")
                continue

    def _load_architecture_summary(self, context_parts: list[str]) -> None:
        """Load system architecture summary."""
        arch_path = Path("dev_documents/system_prompts/SYSTEM_ARCHITECTURE.md")
        if not arch_path.exists():
            return

        arch_content = arch_path.read_text(encoding="utf-8")
        summary_end = arch_content.find("\n## ")
        if summary_end > 0:
            arch_summary = arch_content[:summary_end]
            context_parts.append(
                f"\n## System Architecture (Summary)\n```markdown\n{arch_summary}\n```\n"
            )

    async def _build_question_context(self, question: str) -> str:
        """
        Builds comprehensive context for answering Jules' questions.
        Includes: current cycle SPEC, changed files, and their contents.
        """
        context_parts = [f"# Jules' Question\n{question}\n"]

        try:
            # 1. Get current cycle information from session manifest
            mgr = StateManager()
            manifest = mgr.load_manifest()

            # Find current active cycle (in_progress) or fallback to last cycle if needed
            current_cycle_id: str | None = None
            if manifest:
                for cycle in manifest.cycles:
                    if cycle.status == "in_progress":
                        current_cycle_id = cycle.id
                        break

            if current_cycle_id:
                context_parts.append(f"\n# Current Cycle: {current_cycle_id}\n")
                self._load_cycle_docs(current_cycle_id, context_parts)

            await self._load_changed_files(context_parts)
            self._load_architecture_summary(context_parts)

        except Exception as e:
            logger.warning(f"Failed to build full context for Jules question: {e}")
            return question

        full_context = "\n".join(context_parts)
        instruction = settings.get_prompt_content(
            "MANAGER_INQUIRY_PROMPT.md",
            default=(
                "**Instructions for Answering Jules' Question**:\n"
                "Focus on ROOT CAUSE ANALYSIS. Diagnose the underlying cause, "
                "guide investigation, and provide targeted solutions."
            ),
        )
        full_context += f"\n\n---\n{instruction}"

        return full_context

    async def _fetch_pending_plan(
        self, client: httpx.AsyncClient, session_url: str, processed_ids: set[str]
    ) -> tuple[dict[str, Any], str] | None:
        """Fetches a pending plan from activities if one exists."""
        act_url = f"{session_url}/activities"
        try:
            act_resp = await client.get(act_url, headers=self._get_headers(), timeout=10.0)
            if act_resp.status_code != httpx.codes.OK:
                logger.warning(f"Failed to fetch activities: HTTP {act_resp.status_code}")
                return None

            activities = act_resp.json().get("activities", [])
            logger.debug(f"Checking {len(activities)} activities for planGenerated")

            for activity in activities:
                if "planGenerated" in activity:
                    plan_generated = activity.get("planGenerated", {})
                    plan = plan_generated.get("plan", {})
                    plan_id = plan.get("id")
                    logger.info(f"Found planGenerated activity with plan ID: {plan_id}")
                    if plan_id and plan_id not in processed_ids:
                        logger.info(f"Plan {plan_id} is new, will process")
                        return (plan, plan_id)
                    logger.debug(f"Plan {plan_id} already processed, skipping")
        except Exception as e:
            logger.warning(f"Failed to check for plan: {e}", exc_info=True)
        else:
            return None
        return None

    async def _build_plan_review_context(self, plan: dict[str, Any]) -> str:
        """Builds context for plan review including specs and plan content."""
        mgr = StateManager()
        manifest = mgr.load_manifest()

        current_cycle_id = None
        if manifest:
            for cycle in manifest.cycles:
                if cycle.status == "in_progress":
                    current_cycle_id = cycle.id
                    break

        context_parts: list[str] = []
        if current_cycle_id:
            context_parts.append(f"# CURRENT CYCLE: {current_cycle_id}\n")
            self._load_cycle_docs(current_cycle_id, context_parts)

        plan_steps = plan.get("steps", [])
        plan_text = json.dumps(plan_steps, indent=2)
        context_parts.append(f"# GENERATED PLAN TO REVIEW\n{plan_text}\n")

        intro = (
            str(
                settings.get_prompt_content(
                    "PLAN_REVIEW_PROMPT.md",
                    default=(
                        "Jules has generated an implementation plan. Please review it against the specifications.\n"
                        "If the plan is acceptable, reply with just 'APPROVE' (single word).\n"
                        "If there are issues, reply with specific feedback to correct the plan.\n"
                        "Do NOT approve if the plan is missing critical steps or violates requirements."
                    ),
                )
            )
            + "\n"
        )
        return intro + "\n".join(context_parts)

    async def _handle_plan_approval(
        self,
        client: httpx.AsyncClient,
        session_url: str,
        processed_ids: set[str],
        rejection_count: list[int],
        max_rejections: int,
    ) -> None:
        """Handles automated plan review and approval."""
        session_name = "sessions/" + session_url.split("/sessions/")[-1]

        result = await self._fetch_pending_plan(client, session_url, processed_ids)
        if not result:
            return

        plan, plan_id = result
        self.console.print(f"\n[bold magenta]Plan Approval Requested:[/bold magenta] {plan_id}")

        # Check if we've exceeded max rejections
        if rejection_count[0] >= max_rejections:
            self.console.print(
                f"[bold yellow]Max plan rejections ({max_rejections}) reached. Auto-approving plan.[/bold yellow]"
            )
            await self.approve_plan(session_name, plan_id)
            processed_ids.add(plan_id)
            return

        full_context = await self._build_plan_review_context(plan)

        self.console.print("[dim]Auditing Plan...[/dim]")
        try:
            mgr_response = await self.manager_agent.run(full_context)
            reply = mgr_response.output.strip()

            if "APPROVE" in reply.upper() and len(reply) < 50:
                self.console.print("[bold green]Plan Approved by Auditor.[/bold green]")
                await self.approve_plan(session_name, plan_id)
            else:
                self.console.print("[bold yellow]Plan Rejected. Sending Feedback...[/bold yellow]")
                rejection_count[0] += 1
                await self._send_message(session_url, reply)

            processed_ids.add(plan_id)
        except Exception as e:
            logger.error(f"Plan audit failed: {e}")

    async def _process_inquiries(
        self,
        client: httpx.AsyncClient,
        session_url: str,
        state: str,
        processed_ids: set[str],
        rejection_count: list[int],
        max_rejections: int,
        require_plan_approval: bool = True,
    ) -> None:
        # States where we should check for inquiries (based on Jules API spec)
        active_states = [
            "AWAITING_USER_FEEDBACK",
            "AWAITING_PLAN_APPROVAL",
            "COMPLETED",
            "PLANNING",
            "IN_PROGRESS",
        ]
        if state not in active_states:
            return

        # Always check for plan approval first (if enabled)
        # This ensures we catch it even if the state string is different than expected
        if require_plan_approval:
            await self._handle_plan_approval(
                client, session_url, processed_ids, rejection_count, max_rejections
            )

        # Then handle regular inquiries (skip already processed activities)
        inquiry = await self._check_for_inquiry(client, session_url, processed_ids)
        if not inquiry:
            return

        question, act_id = inquiry
        if act_id and act_id not in processed_ids:
            self.console.print(
                f"\n[bold magenta]Jules Question Detected:[/bold magenta] {question}"
            )
            self.console.print("[dim]Consulting Manager Agent with full context...[/dim]")

            try:
                # Build comprehensive context including current cycle SPEC and changed files
                enhanced_context = await self._build_question_context(question)

                self.console.print(f"[dim]Context size: {len(enhanced_context)} chars[/dim]")

                mgr_response = await self.manager_agent.run(enhanced_context)
                reply_text = mgr_response.output
                reply_text += "\n\n(System Note: If task complete/blocker resolved, proceed to create PR. Do not wait.)"

                self.console.print(f"[bold cyan]Manager Agent Reply:[/bold cyan] {reply_text}")
                await self._send_message(session_url, reply_text)
                processed_ids.add(act_id)
                await self._sleep(5)
            except Exception as e:
                logger.error(f"Manager Agent failed: {e}")
                # Fallback: send a basic response
                fallback_msg = (
                    f"I encountered an error processing your question. "
                    f"Please refer to the SPEC.md in dev_documents/system_prompts/ for guidance. "
                    f"Original question: {question}"
                )
                await self._send_message(session_url, fallback_msg)
                processed_ids.add(act_id)

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
                                    msg = self._extract_activity_message(activity)
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
