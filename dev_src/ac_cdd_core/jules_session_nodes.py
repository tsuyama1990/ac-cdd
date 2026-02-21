"""LangGraph nodes for Jules session management."""

import asyncio
from typing import Any

import httpx
from ac_cdd_core.jules_session_state import JulesSessionState, SessionStatus
from ac_cdd_core.utils import logger
from rich.console import Console

console = Console()


class JulesSessionNodes:
    """Collection of LangGraph nodes for Jules session management."""

    def __init__(self, jules_client: Any) -> None:
        """Initialize with reference to JulesClient for API calls."""
        self.client = jules_client


    def _compute_diff(self, original: JulesSessionState, current: JulesSessionState) -> dict[str, Any]:
        """Compute dictionary of changed fields for LangGraph checkpointer."""
        updates = {}
        for field in current.model_fields:
            old_val = getattr(original, field)
            new_val = getattr(current, field)
            if old_val != new_val:
                updates[field] = new_val
        return updates

    async def monitor_session(self, _state_in: JulesSessionState) -> dict[str, Any]:  # noqa: C901, PLR0912
        """Monitor Jules session and detect state changes with batched polling."""
        state = _state_in.model_copy(deep=True)

        # Batch polling loop to reduce graph steps
        # Poll for ~60 seconds (12 checks * 5s interval)
        POLL_BATCH_SIZE = 12

        for _ in range(POLL_BATCH_SIZE):
            # Check timeout
            elapsed = asyncio.get_event_loop().time() - state.start_time
            if elapsed > state.timeout_seconds:
                logger.warning(f"Session timeout after {elapsed}s")
                state.status = SessionStatus.TIMEOUT
                state.error = f"Timed out after {elapsed}s"
                return self._compute_diff(_state_in, state)

            try:
                async with httpx.AsyncClient() as client:
                    # Fetch session state
                    response = await client.get(
                        state.session_url, headers=self.client._get_headers()
                    )
                    response.raise_for_status()
                    data = response.json()

                    new_jules_state = data.get("state")
                    if state.jules_state != new_jules_state:
                        state.previous_jules_state = state.jules_state
                    state.jules_state = new_jules_state
                    state.raw_data = data

                    logger.info(f"Jules session state: {state.jules_state}")

                    # Check for failure
                    if state.jules_state == "FAILED":
                        # Debug output for failed state
                        import json

                        logger.error(
                            f"Jules Session FAILED. Response: {json.dumps(data, indent=2)}"
                        )

                        error_msg = data.get("error", {}).get("message", "Unknown error")

                        # Resilience: Check if a PR was created despite the failure
                        # (Sometimes Jules marks session FAILED due to timeout/minor error but PR exists)
                        pr_found = False

                        # Check in outputs
                        for output in data.get("outputs", []):
                            if "github_pull_request" in str(output.get("type", "")):
                                pr_found = True
                                break

                        # Check in activities (if outputs empty)
                        if not pr_found:
                            activities = self.client.list_activities(
                                state.session_url.split("/")[-1]
                            )
                            for act in activities:
                                if "pullRequest" in str(act) or "CreatePullRequest" in str(act):
                                    pr_found = True
                                    break

                        if pr_found:
                            logger.warning(
                                "Session marked FAILED but PR activity detected. Proceeding to validation."
                            )
                            state.status = SessionStatus.CHECKING_PR
                        else:
                            state.status = SessionStatus.FAILED
                            state.error = f"Jules Session Failed: {error_msg}"
                        return self._compute_diff(_state_in, state)

                    # Process inquiries (questions and plan approvals)
                    await self._process_inquiries_in_monitor(state, client)

                    # CRITICAL FIX: If an inquiry was detected, return immediately to handle it.
                    # Do NOT let "COMPLETED" status overwrite a pending question.
                    if state.status == SessionStatus.INQUIRY_DETECTED:
                        return self._compute_diff(_state_in, state)

                    # Reset validation flag if we are back in progress
                    if state.jules_state not in ["COMPLETED", "SUCCEEDED"]:
                        state.completion_validated = False

                    # Check for completion
                    if (
                        state.jules_state in ["COMPLETED", "SUCCEEDED"]
                        and not state.completion_validated
                    ):
                        state.status = SessionStatus.VALIDATING_COMPLETION
                        return self._compute_diff(_state_in, state)

                    # Update activity count
                    await self._update_activity_count(state, client)

                    # Handle manual user input
                    await self.client._handle_manual_input(state.session_url)

            except Exception as e:
                logger.warning(f"Monitor loop error (transient): {e}")

            # Continue monitoring loop
            # We use a short sleep here because we are inside the batch loop
            # state.poll_interval is typically long (120s), but for batching we want shorter interval (5s)
            # We ignore state.poll_interval here and use fixed 5s for responsiveness
            await self.client._sleep(5)

        return self._compute_diff(_state_in, state)

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
                state.status = SessionStatus.INQUIRY_DETECTED

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

    async def answer_inquiry(self, _state_in: JulesSessionState) -> dict[str, Any]:
        """Answer Jules' inquiry using Manager Agent."""
        state = _state_in.model_copy(deep=True)

        if not state.current_inquiry or not state.current_inquiry_id:
            state.status = SessionStatus.MONITORING
            return self._compute_diff(_state_in, state)

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

            await self.client._sleep(5)

        except Exception as e:
            logger.error(f"Manager Agent failed: {e}")
            fallback_msg = (
                f"I encountered an error processing your question. "
                f"Please refer to the SPEC.md in dev_documents/system_prompts/ for guidance. "
                f"Original question: {state.current_inquiry}"
            )
            await self.client._send_message(state.session_url, fallback_msg)
            state.processed_activity_ids.add(state.current_inquiry_id)

        state.status = SessionStatus.MONITORING
        return self._compute_diff(_state_in, state)

    async def validate_completion(self, _state_in: JulesSessionState) -> dict[str, Any]:  # noqa: C901
        """Validate if COMPLETED state is genuine or if work is still ongoing."""
        state = _state_in.model_copy(deep=True)

        try:
            async with httpx.AsyncClient() as client:
                # Fetch recent activities
                act_url = f"{state.session_url}/activities"
                resp = await client.get(act_url, headers=self.client._get_headers(), timeout=10.0)

                if resp.status_code == httpx.codes.OK:
                    activities = resp.json().get("activities", [])

                    # First, check for sessionCompleted activity (most reliable indicator)
                    has_session_completed = False
                    stale_completion_detected = False

                    for activity in activities:
                        if "sessionCompleted" in activity:
                            # Check if this is a stale (already processed) event
                            act_id = activity.get("name", activity.get("id"))
                            if act_id and act_id in state.processed_completion_ids:
                                stale_completion_detected = True
                                continue

                            if act_id:
                                state.processed_completion_ids.add(act_id)

                            has_session_completed = True
                            logger.info(
                                "Found sessionCompleted activity - session is genuinely complete"
                            )
                            break

                    # If sessionCompleted exists (and is new), it's genuinely complete
                    if has_session_completed:
                        state.completion_validated = True
                        state.status = SessionStatus.CHECKING_PR
                        return self._compute_diff(_state_in, state)

                    # If we found a STALE completion, we must NOT fall back to checking PRs
                    # because we are likely in a feedback loop where state hasn't updated yet.
                    if stale_completion_detected:
                        # Allow proceed if we observed a valid IN_PROGRESS -> COMPLETED transition
                        # This handles cases where Jules re-completes but doesn't emit a new completion event
                        if state.previous_jules_state == "IN_PROGRESS":
                            logger.info(
                                "Stale completion detected, BUT valid IN_PROGRESS->COMPLETED transition observed. Treating as complete."
                            )
                        else:
                            logger.info(
                                "Stale completion detected (ignored). Waiting for new Agent activity..."
                            )
                            state.status = SessionStatus.MONITORING
                            return self._compute_diff(_state_in, state)

                    # Logic removed: Checking for ongoing work indicators via keywords caused infinite loops.

                    # NEW FIX: If sessionCompleted is missing, check for distress/objections in the last message.
                    # This prevents auditing when Jules is complaining (e.g. "feedback inconsistent") but ends session.
                    if not has_session_completed:
                        distress_state = await self._check_for_distress_in_messages(state, client)
                        if distress_state:
                            return self._compute_diff(_state_in, distress_state)

                    # If Jules API says COMPLETED, we should trust it and proceed to PR check.
                    # If PR is missing, check_pr will handle it by requesting PR creation.

        except Exception as e:
            logger.warning(f"Failed to validate completion: {e}")

        # If no sessionCompleted found and no ongoing work, proceed cautiously to PR check
        logger.info(
            "No sessionCompleted activity found, but no ongoing work detected. Proceeding to PR check."
        )
        state.completion_validated = True
        state.status = SessionStatus.CHECKING_PR
        return self._compute_diff(_state_in, state)

    async def check_pr(self, _state_in: JulesSessionState) -> dict[str, Any]:  # noqa: C901
        """Check for PR in session outputs and activities."""
        state = _state_in.model_copy(deep=True)

        if not state.raw_data:
            state.status = SessionStatus.REQUESTING_PR_CREATION
            return self._compute_diff(_state_in, state)

        # Check session outputs
        for output in state.raw_data.get("outputs", []):
            if "pullRequest" in output:
                pr_url = output["pullRequest"].get("url")
                if pr_url:
                    console.print(f"\n[bold green]PR Created: {pr_url}[/bold green]")
                    state.pr_url = pr_url
                    state.status = SessionStatus.SUCCESS
                    return self._compute_diff(_state_in, state)

        # Check activities
        try:
            async with httpx.AsyncClient() as client:
                act_url = f"{state.session_url}/activities"
                resp = await client.get(act_url, headers=self.client._get_headers(), timeout=10.0)
                if resp.status_code == httpx.codes.OK:
                    activities = resp.json().get("activities", [])
                    for activity in activities:
                        # Check for PR
                        if "pullRequest" in activity:
                            # Skip already processed activities (stale PRs)
                            act_id = activity.get("name", activity.get("id"))
                            if act_id and act_id in state.processed_activity_ids:
                                continue

                            pr_url = activity["pullRequest"].get("url")
                            if pr_url:
                                console.print(f"\n[bold green]PR Created: {pr_url}[/bold green]")
                                logger.info(f"Found PR in activities: {pr_url}")
                                state.pr_url = pr_url
                                state.status = SessionStatus.SUCCESS
                                return self._compute_diff(_state_in, state)
        except Exception as e:
            logger.debug(f"Failed to check activities for PR: {e}")

        # No PR found
        console.print("[yellow]Session Completed but NO PR found.[/yellow]")
        state.status = SessionStatus.REQUESTING_PR_CREATION
        return self._compute_diff(_state_in, state)

    async def _check_for_distress_in_messages(
        self, state: JulesSessionState, client: httpx.AsyncClient
    ) -> JulesSessionState | None:
        """Checks the last message for distress signals/objections."""
        try:
            # Use existing client to fetch messages
            msgs_url = f"{state.session_url}/messages"
            msg_resp = await client.get(msgs_url, headers=self.client._get_headers())
            if msg_resp.status_code == httpx.codes.OK:
                messages = msg_resp.json().get("messages", [])
                if messages:
                    last_msg = messages[-1]

                    # Verify last message is from AGENT
                    sender = last_msg.get(
                        "author", last_msg.get("role", last_msg.get("type", ""))
                    ).upper()
                    if sender in ["AGENT", "MODEL", "ASSISTANT", "JULES"]:
                        # Check for distress keywords
                        content = last_msg.get("content", "").lower()
                        distress_keywords = [
                            "inconsistent",
                            "cannot act",
                            "faulty audit",
                            "incorrect version",
                            "please manually",
                            "blocked",
                            "error",
                            "issue with",
                            "reiterate",
                        ]
                        if any(k in content for k in distress_keywords):
                            # Generate ID to prevent infinite inquiry loop on same message
                            msg_id = last_msg.get("name") or str(hash(content))

                            if msg_id in state.processed_activity_ids:
                                # Already handled this distress message
                                return None

                            logger.warning(
                                "Detected distress/objection in last message. Treating as inquiry."
                            )
                            state.current_inquiry = last_msg.get("content")
                            state.current_inquiry_id = msg_id
                            state.status = SessionStatus.INQUIRY_DETECTED
                            return state
        except Exception as e:
            logger.warning(f"Failed to check last message content: {e}")
        return None

    async def request_pr_creation(self, _state_in: JulesSessionState) -> dict[str, Any]:
        """Request Jules to create a PR manually."""
        state = _state_in.model_copy(deep=True)

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

        state.status = SessionStatus.WAITING_FOR_PR
        state.fallback_elapsed_seconds = 0
        return self._compute_diff(_state_in, state)

    async def wait_for_pr(self, _state_in: JulesSessionState) -> dict[str, Any]:  # noqa: C901
        """Wait for PR creation after manual request, with session state re-validation."""
        state = _state_in.model_copy(deep=True)

        await self.client._sleep(10)
        state.fallback_elapsed_seconds += 10

        # Check timeout
        if state.fallback_elapsed_seconds >= state.fallback_max_wait:
            logger.warning(f"Timeout ({state.fallback_max_wait}s) waiting for Jules to create PR")
            state.status = SessionStatus.TIMEOUT
            state.error = f"Timeout waiting for PR after {state.fallback_max_wait}s"
            return self._compute_diff(_state_in, state)

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
                        state.status = SessionStatus.MONITORING
                        state.jules_state = current_state
                        return self._compute_diff(_state_in, state)

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
                            # CRITICAL FIX: Ignore already processed activities (stale PRs)
                            act_id = activity.get("name", activity.get("id"))
                            if act_id and act_id in state.processed_activity_ids:
                                continue

                            pr_url = activity["pullRequest"].get("url")
                            if pr_url:
                                console.print(f"[bold green]PR Created: {pr_url}[/bold green]")
                                state.pr_url = pr_url
                                state.status = SessionStatus.SUCCESS
                                return self._compute_diff(_state_in, state)

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
        return self._compute_diff(_state_in, state)
