"""LangGraph nodes for Jules session management."""

import asyncio
from typing import Any

import httpx
from ac_cdd_core.jules_session_state import JulesSessionState
from ac_cdd_core.utils import logger
from rich.console import Console

console = Console()


class JulesSessionNodes:
    """Collection of LangGraph nodes for Jules session management."""

    def __init__(self, jules_client: Any) -> None:
        """Initialize with reference to JulesClient for API calls."""
        self.client = jules_client

    async def monitor_session(self, state: JulesSessionState) -> JulesSessionState:
        """Monitor Jules session and detect state changes."""
        # Check timeout
        elapsed = asyncio.get_event_loop().time() - state.start_time
        if elapsed > state.timeout_seconds:
            logger.warning(f"Session timeout after {elapsed}s")
            state.status = "timeout"
            state.error = f"Timed out after {elapsed}s"
            return state

        try:
            async with httpx.AsyncClient() as client:
                # Fetch session state
                response = await client.get(
                    state.session_url, headers=self.client._get_headers()
                )
                response.raise_for_status()
                data = response.json()

                state.jules_state = data.get("state")
                state.raw_data = data

                logger.info(f"Jules session state: {state.jules_state}")

                # Check for failure
                if state.jules_state == "FAILED":
                    error_msg = data.get("error", {}).get("message", "Unknown error")
                    state.status = "failed"
                    state.error = f"Jules Session Failed: {error_msg}"
                    return state

                # Process inquiries (questions and plan approvals)
                await self._process_inquiries_in_monitor(state, client)

                # Check for completion (only COMPLETED state exists in Jules API)
                if state.jules_state == "COMPLETED":
                    state.status = "validating_completion"
                    return state

                # Update activity count
                await self._update_activity_count(state, client)

                # Handle manual user input
                await self.client._handle_manual_input(state.session_url)

        except Exception as e:
            logger.warning(f"Monitor loop error (transient): {e}")

        # Continue monitoring
        await asyncio.sleep(state.poll_interval)
        return state

    async def _process_inquiries_in_monitor(
        self, state: JulesSessionState, client: httpx.AsyncClient
    ) -> None:
        """Check for and process inquiries during monitoring."""
        # Handle plan approval if required
        if state.require_plan_approval:
            await self.client._handle_plan_approval(
                client,
                state.session_url,
                state.processed_activity_ids,
                [state.plan_rejection_count],
                state.max_plan_rejections,
            )

        # Check for regular inquiries
        inquiry = await self.client._check_for_inquiry(
            client, state.session_url, state.processed_activity_ids
        )
        if inquiry:
            question, act_id = inquiry
            if act_id and act_id not in state.processed_activity_ids:
                state.current_inquiry = question
                state.current_inquiry_id = act_id
                state.status = "inquiry_detected"

    async def _update_activity_count(
        self, state: JulesSessionState, client: httpx.AsyncClient
    ) -> None:
        """Update activity count for progress tracking."""
        act_url = f"{state.session_url}/activities"
        try:
            resp = await client.get(act_url, headers=self.client._get_headers(), timeout=10.0)
            if resp.status_code == httpx.codes.OK:
                activities = resp.json().get("activities", [])
                if len(activities) > state.last_activity_count:
                    console.print(f"[dim]Activity Count: {len(activities)}[/dim]")
                    state.last_activity_count = len(activities)
        except Exception:  # noqa: S110
            pass

    async def answer_inquiry(self, state: JulesSessionState) -> JulesSessionState:
        """Answer Jules' inquiry using Manager Agent."""
        if not state.current_inquiry or not state.current_inquiry_id:
            state.status = "monitoring"
            return state

        console.print(
            f"\n[bold magenta]Jules Question Detected:[/bold magenta] {state.current_inquiry}"
        )
        console.print("[dim]Consulting Manager Agent with full context...[/dim]")

        try:
            # Build comprehensive context
            enhanced_context = await self.client._build_question_context(state.current_inquiry)
            console.print(f"[dim]Context size: {len(enhanced_context)} chars[/dim]")

            # Get Manager Agent response
            mgr_response = await self.client.manager_agent.run(enhanced_context)
            reply_text = mgr_response.output
            reply_text += "\n\n(System Note: If task complete/blocker resolved, proceed to create PR. Do not wait.)"

            console.print(f"[bold cyan]Manager Agent Reply:[/bold cyan] {reply_text}")
            await self.client._send_message(state.session_url, reply_text)
            state.processed_activity_ids.add(state.current_inquiry_id)

            # Clear inquiry
            state.current_inquiry = None
            state.current_inquiry_id = None

            await asyncio.sleep(5)

        except Exception as e:
            logger.error(f"Manager Agent failed: {e}")
            fallback_msg = (
                f"I encountered an error processing your question. "
                f"Please refer to the SPEC.md in dev_documents/system_prompts/ for guidance. "
                f"Original question: {state.current_inquiry}"
            )
            await self.client._send_message(state.session_url, fallback_msg)
            state.processed_activity_ids.add(state.current_inquiry_id)

        state.status = "monitoring"
        return state

    async def validate_completion(self, state: JulesSessionState) -> JulesSessionState:
        """Validate if COMPLETED state is genuine or if work is still ongoing."""
        try:
            async with httpx.AsyncClient() as client:
                # Fetch recent activities
                act_url = f"{state.session_url}/activities"
                resp = await client.get(act_url, headers=self.client._get_headers(), timeout=10.0)

                if resp.status_code == httpx.codes.OK:
                    activities = resp.json().get("activities", [])

                    # First, check for sessionCompleted activity (most reliable indicator)
                    has_session_completed = False
                    for activity in activities:
                        if "sessionCompleted" in activity:
                            has_session_completed = True
                            logger.info("Found sessionCompleted activity - session is genuinely complete")
                            break

                    # If sessionCompleted exists, it's genuinely complete
                    if has_session_completed:
                        state.completion_validated = True
                        state.status = "checking_pr"
                        return state

                    # Logic removed: Checking for ongoing work indicators via keywords caused infinite loops
                    # in resume mode (e.g. "next step" in past messages).
                    # If Jules API says COMPLETED, we should trust it and proceed to PR check.
                    # If PR is missing, check_pr will handle it by requesting PR creation.

        except Exception as e:
            logger.warning(f"Failed to validate completion: {e}")

        # If no sessionCompleted found and no ongoing work, proceed cautiously to PR check
        logger.info("No sessionCompleted activity found, but no ongoing work detected. Proceeding to PR check.")
        state.completion_validated = True
        state.status = "checking_pr"
        return state

    async def check_pr(self, state: JulesSessionState) -> JulesSessionState:
        """Check for PR in session outputs and activities."""
        if not state.raw_data:
            state.status = "requesting_pr_creation"
            return state

        # Check session outputs
        for output in state.raw_data.get("outputs", []):
            if "pullRequest" in output:
                pr_url = output["pullRequest"].get("url")
                if pr_url:
                    console.print(f"\n[bold green]PR Created: {pr_url}[/bold green]")
                    state.pr_url = pr_url
                    state.status = "success"
                    return state

        # Check activities
        try:
            async with httpx.AsyncClient() as client:
                act_url = f"{state.session_url}/activities"
                resp = await client.get(act_url, headers=self.client._get_headers(), timeout=10.0)
                if resp.status_code == httpx.codes.OK:
                    activities = resp.json().get("activities", [])
                    for activity in activities:
                        if "pullRequest" in activity:
                            pr_url = activity["pullRequest"].get("url")
                            if pr_url:
                                console.print(f"\n[bold green]PR Created: {pr_url}[/bold green]")
                                logger.info(f"Found PR in activities: {pr_url}")
                                state.pr_url = pr_url
                                state.status = "success"
                                return state
        except Exception as e:
            logger.debug(f"Failed to check activities for PR: {e}")

        # No PR found
        console.print("[yellow]Session Completed but NO PR found.[/yellow]")
        state.status = "requesting_pr_creation"
        return state

    async def request_pr_creation(self, state: JulesSessionState) -> JulesSessionState:
        """Request Jules to create a PR manually."""
        console.print("[cyan]Attempting to create PR manually...[/cyan]")
        console.print("[cyan]Sending message to Jules to commit and create PR...[/cyan]")

        message = (
            "The session has completed successfully, but no Pull Request was created.\n\n"
            "Please commit all your changes and create a Pull Request now.\n\n"
            "**Action Required:**\n"
            "1. Review all the files you've created/modified\n"
            "2. Commit all changes with a descriptive commit message\n"
            "3. Create a Pull Request to the main branch\n\n"
            "Do not wait for further instructions. Proceed immediately."
        )

        await self.client._send_message(state.session_url, message)
        console.print("[dim]Waiting for Jules to create PR...[/dim]")

        state.status = "waiting_for_pr"
        state.fallback_elapsed_seconds = 0
        return state

    async def wait_for_pr(self, state: JulesSessionState) -> JulesSessionState:  # noqa: C901
        """Wait for PR creation after manual request, with session state re-validation."""
        await asyncio.sleep(10)
        state.fallback_elapsed_seconds += 10

        # Check timeout
        if state.fallback_elapsed_seconds >= state.fallback_max_wait:
            logger.warning(
                f"Timeout ({state.fallback_max_wait}s) waiting for Jules to create PR"
            )
            state.status = "timeout"
            state.error = f"Timeout waiting for PR after {state.fallback_max_wait}s"
            return state

        try:
            async with httpx.AsyncClient() as client:
                # Re-check session state (Jules might have gone back to work)
                session_resp = await client.get(
                    state.session_url, headers=self.client._get_headers()
                )
                if session_resp.status_code == httpx.codes.OK:
                    current_state = session_resp.json().get("state")
                    if current_state == "IN_PROGRESS":
                        logger.info(
                            "Session returned to IN_PROGRESS during PR wait. Returning to monitoring."
                        )
                        state.status = "monitoring"
                        state.jules_state = current_state
                        return state

                # Check for PR and new activities
                act_url = f"{state.session_url}/activities"
                act_resp = await client.get(
                    act_url, headers=self.client._get_headers(), timeout=10.0
                )
                if act_resp.status_code == httpx.codes.OK:
                    activities = act_resp.json().get("activities", [])
                    for activity in activities:
                        # Check for PR
                        if "pullRequest" in activity:
                            pr_url = activity["pullRequest"].get("url")
                            if pr_url:
                                console.print(f"[bold green]PR Created: {pr_url}[/bold green]")
                                state.pr_url = pr_url
                                state.status = "success"
                                return state

                        # Log new activities
                        act_id = activity.get("name", activity.get("id"))
                        if act_id and act_id not in state.processed_fallback_ids:
                            msg = self.client._extract_activity_message(activity)
                            if msg:
                                console.print(f"[dim]Jules: {msg}[/dim]")
                            state.processed_fallback_ids.add(act_id)

        except Exception as e:
            logger.debug(f"Error checking for PR/activities: {e}")

        # Progress update
        if state.fallback_elapsed_seconds % 30 == 0:
            console.print(
                f"[dim]Still waiting for PR... ({state.fallback_elapsed_seconds}/{state.fallback_max_wait}s elapsed)[/dim]"
            )

        # Continue waiting
        return state
