from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ac_cdd_core.services.jules_client import JulesClient


@pytest.mark.asyncio
async def test_jules_url_construction():
    """Verify _send_message correctly prepends base URL."""
    client = JulesClient()
    client.base_url = "https://api.example.com"
    client._get_headers = MagicMock(return_value={})

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 200

        # Test relative path
        await client._send_message("sessions/123", "hello")

        # Verify URL argument to post
        args, _ = mock_post.call_args
        assert args[0] == "https://api.example.com/sessions/123:sendMessage"


def test_list_activities_delegation():
    """Verify list_activities delegates to api_client."""
    client = JulesClient()
    client.api_client.list_activities = MagicMock(return_value=["act1"])

    result = client.list_activities("sessions/123")
    assert result == ["act1"]
    client.api_client.list_activities.assert_called_once_with("sessions/123")
