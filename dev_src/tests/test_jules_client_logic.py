import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from ac_cdd_core.services.jules_client import JulesClient


class TestJulesClientLogic(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
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

    def tearDown(self):
        self.auth_patcher.stop()

    @patch("asyncio.sleep", return_value=None)
    @patch("httpx.AsyncClient")
    async def test_prioritize_inquiry_over_completed_state(self, mock_httpx_cls, mock_sleep):
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
        r_session_completed.json.return_value = {"state": "COMPLETED", "outputs": []}

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

        mock_client.get.side_effect = [
            r_session_completed,
            r_acts_question,
            r_session_success,
            r_acts_empty,
        ]

        result = await self.client.wait_for_completion(session_id)

        self.client._send_message.assert_called_once()
        self.assertEqual(result["pr_url"], "http://github.com/pr/1")
        print("\\n[TEST PASS] Successfully caught inquiry in COMPLETED state and replied.")

    @patch("asyncio.sleep", return_value=None)
    @patch("httpx.AsyncClient")
    async def test_deduplication_of_existing_activities(self, mock_httpx_cls, mock_sleep):
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
        r_session_completed.json.return_value = {"state": "COMPLETED", "outputs": []}

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
        #    -> Falls through to Success Check (No PR)
        # 3. get(activities) (Logging Check at bottom of loop) -> Empty/Old
        # Iteration 2:
        # 4. get(session) -> SUCCEEDED
        # 5. get(activities) (Check Inquiry) -> Empty
        #    -> Success Check -> Returns PR

        mock_client.get.side_effect = [
            r_session_completed,
            r_acts_old,
            r_acts_logging,
            r_session_success,
            r_acts_empty,
        ]

        await self.client.wait_for_completion(session_id)

        self.client._send_message.assert_not_called()
        print("\\n[TEST PASS] Ignored pre-existing inquiry.")


if __name__ == "__main__":
    unittest.main()
