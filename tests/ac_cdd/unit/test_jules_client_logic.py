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
            self.client.context_builder.build_question_context = AsyncMock(return_value="mock context")

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
        Verify that if state is COMPLETED but there is a NEW inquiry,
        we prioritize answering the inquiry over returning "Success/No PR".
        """
        mock_client = AsyncMock()
        mock_httpx_cls.return_value.__aenter__.return_value = mock_client

        session_id = "sessions/123"
        activity_id = "sessions/123/activities/456"

        # Initial Load
        self.client.list_activities = MagicMock(return_value=[])
        self.client._send_message = AsyncMock()

        # Responses
        r_session_completed = MagicMock()
        r_session_completed.status_code = 200
        r_session_completed.json.return_value = {"state": "RUNNING", "outputs": []}

        r_acts_question = MagicMock()
        r_acts_question.status_code = 200
        r_acts_question.json.return_value = {
            "activities": [{"name": activity_id, "agentMessaged": {"agentMessage": "Question?"}}]
        }

        r_session_success = MagicMock()
        r_session_success.status_code = 200
        r_session_success.json.return_value = {
            "state": "SUCCEEDED",
            "outputs": [{"pullRequest": {"url": "http://github.com/pr/1"}}],
        }

        r_acts_empty = MagicMock()
        r_acts_empty.status_code = 200
        r_acts_empty.json.return_value = {"activities": []}

        # Sequence:
        # Iteration 1:
        # 1. get(session) -> COMPLETED
        # 2. get(activities) (Check Inquiry) -> FOUND Question
        #    -> Sends Reply, Sleeps, Continues
        # Iteration 2:
        # 3. get(session) -> SUCCEEDED w/ PR
        # 4. get(activities) (Check Inquiry) -> Empty (No new questions)
        #    -> Falls through to Success Check -> Returns PR

        state_responses = [r_session_completed, r_session_completed, r_session_success, r_session_success]
        activity_responses = [r_acts_empty, r_acts_question, r_acts_empty, r_acts_empty]

        async def dynamic_get(url: str, **kwargs: Any) -> MagicMock:
            print(f"MOCK REQUEST: {url}")
            if url.endswith("/activities") or "pageSize" in url:
                return activity_responses.pop(0) if activity_responses else r_acts_empty
            else:
                return state_responses.pop(0) if state_responses else r_session_success

        mock_client.get.side_effect = dynamic_get

        result = await self.client.wait_for_completion(session_id)

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
        r_session_completed.json.return_value = {"state": "RUNNING", "outputs": []}

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
            "state": "SUCCEEDED",
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
        # 3. get(session) -> SUCCEEDED
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
            else:
                call_counts["state"] += 1
                if call_counts["state"] in (1, 2):
                    return r_session_completed
                return r_session_success

        mock_client.get.side_effect = dynamic_get

        await self.client.wait_for_completion(session_id)

        self.client._send_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
