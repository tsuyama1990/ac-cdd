import unittest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from ac_cdd_core.services.jules_client import JulesClient


class TestJulesClientLogic(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        # Patch dependencies to avoid real API calls or Auth
        self.auth_patcher = patch("google.auth.default", return_value=(MagicMock(), "test-project"))
        self.auth_patcher.start()

        # Initialize client
        with patch.object(JulesClient, "__init__", lambda x: None):  # Skip init
            self.client = JulesClient()
            self.client.base_url = "https://mock.api"
            self.client.timeout = 5
            self.client.poll_interval = 0.1
            self.client.console = MagicMock()
            self.client.manager_agent = AsyncMock()
            self.client.manager_agent.run.return_value = MagicMock(output="Manager Reply")
            self.client.credentials = MagicMock()
            self.client._get_headers = MagicMock(return_value={})
            self.client.credentials.token = "mock_token"  # noqa: S105
            self.client._sleep = AsyncMock()

            # FIX: Add context_builder
            self.client.context_builder = MagicMock()
            self.client.context_builder.build_question_context = AsyncMock(
                return_value="mock context"
            )

            # FIX: Add inquiry handler back since __init__ is skipped
            from ac_cdd_core.services.jules.inquiry_handler import JulesInquiryHandler

            self.client.inquiry_handler = JulesInquiryHandler(
                manager_agent=self.client.manager_agent,
                context_builder=MagicMock(),
                client_ref=self.client,
            )

            # FIX: Add api_client mock which is now used by wait_for_completion
            self.client.api_client = MagicMock()
            self.client.api_client.api_key = "mock_key"

    def tearDown(self) -> None:
        self.auth_patcher.stop()

    @patch("asyncio.sleep", return_value=None)
    @patch("httpx.AsyncClient")
    async def test_prioritize_inquiry_over_completed_state(
        self, mock_httpx_cls: Any, _mock_sleep: Any
    ) -> None:
        """
        Verify correct inquiry semantics:
        - agentMessaged (Jules internal monologue e.g. Root Cause Analysis) is IGNORED.
        - inquiryAsked in AWAITING_USER_FEEDBACK state triggers Manager Agent reply.

        Old behavior (wrong): the code replied to any agentMessaged regardless of state.
        New behavior (correct): ONLY inquiryAsked + AWAITING_USER_FEEDBACK triggers a reply.
        """
        mock_client = AsyncMock()
        mock_httpx_cls.return_value.__aenter__.return_value = mock_client

        session_id = "sessions/123"
        monologue_id = "sessions/123/activities/monologue"
        question_id = "sessions/123/activities/question"

        self.client.list_activities = MagicMock(return_value=[])
        self.client._send_message = AsyncMock()

        call_counts: dict[str, int] = {"state": 0, "activities": 0}

        def state_response(call_n: int) -> MagicMock:
            mock = MagicMock()
            mock.status_code = 200
            if call_n == 1:
                mock.json.return_value = {"state": "IN_PROGRESS", "outputs": []}
            elif call_n == 2:
                mock.json.return_value = {"state": "AWAITING_USER_FEEDBACK", "outputs": []}
            else:
                mock.json.return_value = {
                    "state": "COMPLETED",
                    "outputs": [{"pullRequest": {"url": "http://github.com/pr/1"}}],
                }
            return mock

        def activities_response(call_n: int) -> MagicMock:
            mock = MagicMock()
            mock.status_code = 200
            if call_n == 1:
                # Monologue while IN_PROGRESS - must be ignored
                mock.json.return_value = {
                    "activities": [
                        {"name": monologue_id, "agentMessaged": {"agentMessage": "Root Cause Analysis..."}}
                    ]
                }
            elif call_n == 2:
                # Genuine question while AWAITING_USER_FEEDBACK - must be answered
                mock.json.return_value = {
                    "activities": [
                        {"name": question_id, "inquiryAsked": {"inquiry": "Which file should I edit?"}}
                    ]
                }
            else:
                mock.json.return_value = {"activities": []}
            return mock

        async def dynamic_get(url: str, **kwargs: Any) -> MagicMock:
            if "activities" in url:
                call_counts["activities"] += 1
                return activities_response(call_counts["activities"])
            call_counts["state"] += 1
            return state_response(call_counts["state"])

        mock_client.get.side_effect = dynamic_get

        result = await self.client.wait_for_completion(session_id)

        # Manager agent MUST have been called exactly once (for the genuine inquiryAsked only)
        self.client._send_message.assert_called_once()
        assert result["pr_url"] == "http://github.com/pr/1"


    @patch("asyncio.sleep", return_value=None)
    @patch("httpx.AsyncClient")
    async def test_deduplication_of_existing_activities(
        self, mock_httpx_cls: Any, _mock_sleep: Any
    ) -> None:
        """
        Verify that existing activities are IGNORED and do not trigger a reply.
        """
        mock_client = AsyncMock()
        mock_httpx_cls.return_value.__aenter__.return_value = mock_client

        session_id = "sessions/123"
        old_activity_id = "sessions/123/activities/old"

        self.client.list_activities = MagicMock(
            return_value=[
                {"name": old_activity_id, "agentMessaged": {"agentMessage": "Old Question"}}
            ]
        )

        self.client._send_message = AsyncMock()

        # Responses
        r_session_completed = MagicMock()
        r_session_completed.status_code = 200
        r_session_completed.json.return_value = {"state": "IN_PROGRESS", "outputs": []}

        r_acts_old = MagicMock()
        r_acts_old.status_code = 200
        r_acts_old.json.return_value = {
            "activities": [
                {"name": old_activity_id, "agentMessaged": {"agentMessage": "Old Question"}}
            ]
        }

        r_session_success = MagicMock()
        r_session_success.status_code = 200
        r_session_success.json.return_value = {
            "state": "COMPLETED",
            "outputs": [{"pullRequest": {"url": "http://github.com/pr/1"}}],
        }

        r_acts_empty = MagicMock()
        r_acts_empty.status_code = 200
        r_acts_empty.json.return_value = {"activities": []}

        r_acts_logging = MagicMock()
        r_acts_logging.status_code = 200
        r_acts_logging.json.return_value = {"activities": []}

        # Sequence:
        # Iteration 1:
        # 1. get(session) -> COMPLETED
        # 2. get(activities) (Check Inquiry) -> Old Activity (Ignored)
        #    -> Logic: if duplicate, continue (skip rest of loop)
        # Iteration 2:
        # 3. get(session) -> COMPLETED
        # 4. get(activities) (Check Inquiry) -> Empty
        #    -> Success Check -> Returns PR

        call_counts = {"state": 0, "activities": 0}

        async def dynamic_get(url: str, **kwargs: Any) -> MagicMock:
            if url.endswith("/activities"):
                call_counts["activities"] += 1
                if call_counts["activities"] == 1:
                    return r_acts_old
                if call_counts["activities"] == 2:
                    return r_acts_logging
                return r_acts_empty
            call_counts["state"] += 1
            if call_counts["state"] in (1, 2):
                return r_session_completed
            return r_session_success

        mock_client.get.side_effect = dynamic_get

        await self.client.wait_for_completion(session_id)

        self.client._send_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
