import asyncio
from typing import Any

from rich.console import Console

from .api import JulesApiClient

console = Console()


class JulesSessionManager:
    """Manages active Jules sessions."""

    def __init__(self, api_client: JulesApiClient) -> None:
        self.api_client = api_client
        self.console = console

    async def list_activities(self, session_id_path: str) -> list[dict[str, Any]]:
        """Delegates activity listing to the API Client."""
        import asyncio

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.api_client.list_activities, session_id_path)

    async def get_latest_plan(self, session_id: str) -> dict[str, Any] | None:
        """Fetches the latest 'planGenerated' activity."""
        session_id_path = (
            session_id if session_id.startswith("sessions/") else f"sessions/{session_id}"
        )
        activities = await self.list_activities(session_id_path)
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
                    activities = await self.list_activities(session_id_path)
                    for activity in activities:
                        if target_type in activity:
                            return activity
                    await asyncio.sleep(interval)
        except TimeoutError:
            return None

    async def approve_plan(self, session_id: str, plan_id: str) -> dict[str, Any]:
        """Approves the specific plan."""
        session_id_path = (
            session_id if session_id.startswith("sessions/") else f"sessions/{session_id}"
        )
        import asyncio

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self.api_client.approve_plan, session_id_path, plan_id
        )

    def _extract_activity_message(self, act: dict[str, Any]) -> str | None:
        if "message" in act:
            return str(act["message"].get("content", ""))
        if "planGenerated" in act:
            plan = act["planGenerated"]
            return f"Plan Generated: {plan.get('summary', 'No summary')}"
        if "planApproved" in act:
            return "Plan Approved"
        if "sessionCompleted" in act:
            return "Session Completed"
        return None
