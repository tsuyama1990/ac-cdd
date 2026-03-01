import json
from typing import Any, Protocol

import httpx
from ac_cdd_core.config import settings
from ac_cdd_core.state_manager import StateManager
from ac_cdd_core.utils import logger
from rich.console import Console

console = Console()


class AgentProtocol(Protocol):
    async def run(self, prompt: str) -> Any: ...


class JulesInquiryHandler:
    def __init__(self, manager_agent: AgentProtocol, context_builder: Any, client_ref: Any) -> None:
        self.manager_agent = manager_agent
        self.context_builder = context_builder
        self.client_ref = client_ref

    async def check_for_inquiry(
        self,
        client: httpx.AsyncClient,
        session_url: str,
        processed_ids: set[str],
        jules_state: str | None = None,
    ) -> tuple[str, str] | None:
        """Checks if the session is waiting for user feedback.

        IMPORTANT: Only responds to genuine questions from Jules.
        Jules signals it needs user input by:
        1. Setting session state to AWAITING_USER_FEEDBACK (API-level signal)
        2. Posting an 'inquiryAsked' activity (activity-level signal)
        Both conditions should ideally be true.  In practice, we require at minimum
        that the session state is AWAITING_USER_FEEDBACK to avoid replying to Jules'
        internal monologue (agentMessaged / progressUpdated activities).
        """
        # Guard: only respond if Jules is explicitly waiting for input
        if jules_state not in ("AWAITING_USER_FEEDBACK", "AWAITING_PLAN_APPROVAL", None):
            logger.debug(
                f"Skipping inquiry check: session state '{jules_state}' does not require user input."
            )
            return None

        try:
            page_token = ""
            # Check up to 3 pages (300 activities) to capture inquiries buried by logs
            for _ in range(3):
                act_url = f"{session_url}/activities?pageSize=100"
                if page_token:
                    act_url += f"&pageToken={page_token}"

                act_resp = await client.get(
                    act_url, headers=self.client_ref._get_headers(), timeout=10.0
                )

                if act_resp.status_code == httpx.codes.OK:
                    data = act_resp.json()
                    activities = data.get("activities", [])

                    for act in activities:
                        act_id = act.get("name", act.get("id"))
                        if act_id in processed_ids:
                            continue
                        msg = self.extract_activity_message(act)
                        if msg:
                            return (msg, act_id)

                    page_token = data.get("nextPageToken")
                    if not page_token:
                        break
        except Exception as e:
            logger.warning(f"Failed to check for inquiry: {e}")
        return None

    def extract_activity_message(self, act: dict[str, Any]) -> str | None:
        """Extract a message from an activity ONLY if it is a genuine user-directed inquiry.

        Jules API activity types that represent a real question:
        - ``inquiryAsked``:       Jules is explicitly asking the user a question
          (session enters AWAITING_USER_FEEDBACK state)
        - ``userActionRequired``: Jules cannot proceed without user action

        Activity types that should NOT trigger a response (Jules internal monologue):
        - ``progressUpdated``:    status update / progress log
        - ``agentMessaged``:      Jules internal note / analysis (e.g. Root Cause Analysis)
        - ``planGenerated``:      handled separately by plan-approval flow
        - ``sessionCompleted``:   session end marker
        """
        msg = None
        if "inquiryAsked" in act:
            inquiry = act["inquiryAsked"]
            msg = inquiry.get("inquiry", inquiry.get("question"))
        elif "userActionRequired" in act:
            details = act["userActionRequired"]
            msg = details.get("reason", "User action required (check console).")
        # NOTE: agentMessaged and generic message fields are intentionally NOT handled here.
        # Those are Jules' internal monologue (progress updates, Root Cause Analysis, etc.)
        # and must not be mistaken for questions that require a reply.
        return msg

    async def fetch_pending_plan(
        self, client: httpx.AsyncClient, session_url: str, processed_ids: set[str]
    ) -> tuple[dict[str, Any], str] | None:
        """Fetches a pending plan from activities if one exists."""
        act_url = f"{session_url}/activities"
        try:
            act_resp = await client.get(
                act_url, headers=self.client_ref._get_headers(), timeout=10.0
            )
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
            return None
        return None

    async def build_plan_review_context(self, plan: dict[str, Any]) -> str:
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
            context_parts.append(f"# CURRENT CYCLE: {current_cycle_id}\\n")
            self.context_builder.load_cycle_docs(current_cycle_id, context_parts)

        plan_steps = plan.get("steps", [])
        plan_text = json.dumps(plan_steps, indent=2)
        context_parts.append(f"# GENERATED PLAN TO REVIEW\\n{plan_text}\\n")

        intro = (
            str(
                settings.get_prompt_content(
                    "PLAN_REVIEW_PROMPT.md",
                    default=(
                        "Jules has generated an implementation plan. Please review it against the specifications.\\n"
                        "If the plan is acceptable, reply with just 'APPROVE' (single word).\\n"
                        "If there are issues, reply with specific feedback to correct the plan.\\n"
                        "Do NOT approve if the plan is missing critical steps or violates requirements."
                    ),
                )
            )
            + "\\n"
        )
        return intro + "\\n".join(context_parts)

    async def handle_plan_approval(
        self,
        client: httpx.AsyncClient,
        session_url: str,
        processed_ids: set[str],
        rejection_count: list[int],
        max_rejections: int,
    ) -> None:
        """Handles automated plan review and approval."""
        session_name = "sessions/" + session_url.split("/sessions/")[-1]

        result = await self.fetch_pending_plan(client, session_url, processed_ids)
        if not result:
            return

        plan, plan_id = result
        console.print(f"\\n[bold magenta]Plan Approval Requested:[/bold magenta] {plan_id}")

        # Check if we've exceeded max rejections
        if rejection_count[0] >= max_rejections:
            console.print(
                f"[bold yellow]Max plan rejections ({max_rejections}) reached. Auto-approving plan.[/bold yellow]"
            )
            await self.client_ref.approve_plan(session_name, plan_id)
            processed_ids.add(plan_id)
            return

        full_context = await self.build_plan_review_context(plan)

        console.print("[dim]Auditing Plan...[/dim]")
        try:
            mgr_response = await self.manager_agent.run(full_context)
            reply = mgr_response.output.strip()

            if "APPROVE" in reply.upper() and len(reply) < 50:
                console.print("[bold green]Plan Approved by Auditor.[/bold green]")
                await self.client_ref.approve_plan(session_name, plan_id)
            else:
                console.print("[bold yellow]Plan Rejected. Sending Feedback...[/bold yellow]")
                rejection_count[0] += 1
                await self.client_ref._send_message(session_url, reply)

            processed_ids.add(plan_id)
        except Exception as e:
            logger.error(f"Plan audit failed: {e}")

    async def process_inquiries(
        self,
        client: httpx.AsyncClient,
        session_url: str,
        state: str,
        processed_ids: set[str],
        rejection_count: list[int],
        max_rejections: int,
        require_plan_approval: bool = True,
    ) -> None:
        # State guard: only check for inquiries when Jules is explicitly waiting for input.
        # Jules API docs define two states that require user response:
        #   AWAITING_USER_FEEDBACK    - Jules has a question (inquiryAsked activity)
        #   AWAITING_PLAN_APPROVAL    - Jules is waiting for plan approval
        # All other states (IN_PROGRESS, PLANNING, COMPLETED, etc.) mean Jules is
        # working independently and any messages from it are internal progress updates.
        inquiry_states = ["AWAITING_USER_FEEDBACK", "AWAITING_PLAN_APPROVAL"]
        if state not in inquiry_states:
            return

        if require_plan_approval:
            await self.handle_plan_approval(
                client, session_url, processed_ids, rejection_count, max_rejections
            )

        inquiry = await self.check_for_inquiry(
            client, session_url, processed_ids, jules_state=state
        )
        if not inquiry:
            return

        question, act_id = inquiry
        if act_id and act_id not in processed_ids:
            console.print(f"\\n[bold magenta]Jules Question Detected:[/bold magenta] {question}")
            console.print("[dim]Consulting Manager Agent with full context...[/dim]")

            try:
                # Build comprehensive context including current cycle SPEC and changed files
                enhanced_context = await self.context_builder.build_question_context(question)

                console.print(f"[dim]Context size: {len(enhanced_context)} chars[/dim]")

                mgr_response = await self.manager_agent.run(enhanced_context)
                reply_text = mgr_response.output
                followup = settings.get_prompt_content(
                    "MANAGER_INQUIRY_FOLLOWUP.md",
                    default="(System Note: If task complete/blocker resolved, proceed to create PR. Do not wait.)",
                )
                reply_text += f"\n\n{followup}"

                console.print(f"[bold cyan]Manager Agent Reply:[/bold cyan] {reply_text}")
                await self.client_ref._send_message(session_url, reply_text)
                processed_ids.add(act_id)
                await self.client_ref._sleep(5)
            except Exception as e:
                logger.error(f"Manager Agent failed: {e}")
                # Fallback: send a basic response
                fallback_template = settings.get_prompt_content(
                    "MANAGER_INQUIRY_FALLBACK.md",
                    default="I encountered an error processing your question. Original question: {{question}}",
                )
                fallback_msg = fallback_template.replace("{{question}}", question)
                await self.client_ref._send_message(session_url, fallback_msg)
                processed_ids.add(act_id)
