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


@pytest.mark.asyncio
async def test_run_session_success():
    """Test successful session run with PR creation."""
    client = JulesClient()
    
    with (
        patch.object(client.api_client, "create_session", return_value={"name": "sessions/123"}),
        patch.object(client, "wait_for_completion", new_callable=AsyncMock) as mock_wait,
    ):
        mock_wait.return_value = "https://github.com/user/repo/pull/1"
        
        from pathlib import Path
        completion_file = Path("/tmp/test_completion")
        
        pr_url = await client.run_session(
            "session-id", "prompt", [], completion_file
        )
        
        assert pr_url == "https://github.com/user/repo/pull/1"
        mock_wait.assert_called_once()


@pytest.mark.asyncio
async def test_run_session_timeout():
    """Test session timeout handling."""
    from ac_cdd_core.services.jules_client import JulesTimeoutError
    
    client = JulesClient()
    
    with (
        patch.object(client.api_client, "create_session", return_value={"name": "sessions/123"}),
        patch.object(client, "wait_for_completion", new_callable=AsyncMock) as mock_wait,
    ):
        mock_wait.side_effect = JulesTimeoutError("Timeout")
        
        from pathlib import Path
        completion_file = Path("/tmp/test_completion")
        
        with pytest.raises(JulesTimeoutError):
            await client.run_session("session-id", "prompt", [], completion_file)


@pytest.mark.asyncio
async def test_continue_session():
    """Test continuing an existing session."""
    client = JulesClient()
    
    with (
        patch.object(client, "_send_message", new_callable=AsyncMock),
        patch.object(client, "wait_for_completion", new_callable=AsyncMock) as mock_wait,
    ):
        mock_wait.return_value = "https://github.com/user/repo/pull/2"
        
        pr_url = await client.continue_session("sessions/123", "new prompt")
        
        assert pr_url == "https://github.com/user/repo/pull/2"


@pytest.mark.asyncio
async def test_wait_for_completion_pr_created():
    """Test wait_for_completion when PR is created."""
    client = JulesClient()
    
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        # Mock response with PR URL
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "state": "SUCCEEDED",
            "pullRequest": {"url": "https://github.com/user/repo/pull/3"}
        }
        mock_client.get.return_value = mock_response
        
        pr_url = await client.wait_for_completion("sessions/123")
        
        assert pr_url == "https://github.com/user/repo/pull/3"


@pytest.mark.asyncio
async def test_check_for_inquiry_found():
    """Test detecting user inquiry in activities."""
    client = JulesClient()
    
    mock_client = AsyncMock()
    
    # Mock activities response with inquiry
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "activities": [
            {
                "id": "act123",
                "type": "USER_FEEDBACK_REQUESTED",
                "message": "What should I do?"
            }
        ]
    }
    mock_client.get.return_value = mock_response
    
    result = await client._check_for_inquiry(mock_client, "sessions/123")
    
    assert result is not None
    message, activity_id = result
    assert "What should I do?" in message
    assert activity_id == "act123"


@pytest.mark.asyncio
async def test_check_for_inquiry_not_found():
    """Test when no inquiry is present."""
    client = JulesClient()
    
    mock_client = AsyncMock()
    
    # Mock activities response without inquiry
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "activities": [
            {
                "id": "act456",
                "type": "PROGRESS_UPDATE",
                "message": "Working on it"
            }
        ]
    }
    mock_client.get.return_value = mock_response
    
    result = await client._check_for_inquiry(mock_client, "sessions/123")
    
    assert result is None


@pytest.mark.asyncio
async def test_send_message_success():
    """Test sending message to session."""
    client = JulesClient()
    client.base_url = "https://api.example.com"
    client._get_headers = MagicMock(return_value={"Authorization": "Bearer token"})
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 200
        
        await client._send_message("sessions/123", "Hello")
        
        # Verify URL and payload
        args, kwargs = mock_post.call_args
        assert "sessions/123:sendMessage" in args[0]
        assert kwargs["json"]["prompt"] == "Hello"
