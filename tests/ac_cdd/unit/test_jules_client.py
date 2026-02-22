from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ac_cdd_core.services.jules_client import JulesClient, JulesTimeoutError


@pytest.fixture
def mock_client() -> Generator[JulesClient, None, None]:
    # Use dummy key to pass init
    with patch.dict("os.environ", {"JULES_API_KEY": "dummy"}):
        client = JulesClient()
        client.timeout = 5.0  # Give it plenty of time, we control loop via sleep mock
        client.poll_interval = 0.1
        client.git = AsyncMock()
        client.manager_agent = AsyncMock()
        yield client


@pytest.fixture
def mock_httpx() -> Generator[AsyncMock, None, None]:
    with patch("httpx.AsyncClient") as mock_cls:
        mock_instance = AsyncMock()
        # Setup context manager
        mock_cls.return_value.__aenter__.return_value = mock_instance
        mock_cls.return_value.__aexit__.return_value = None
        yield mock_instance


@pytest.mark.asyncio
async def test_wait_for_completion_sucess_first_try(
    mock_client: JulesClient, mock_httpx: AsyncMock
) -> None:
    """Test finding PR immediately."""
    mock_client._sleep = AsyncMock()

    # Return COMPLETED with PR (official Jules API state - not SUCCEEDED)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "state": "COMPLETED",
        "outputs": [{"pullRequest": {"url": "https://pr"}}],
    }
    mock_httpx.get.return_value = mock_response

    result = await mock_client.wait_for_completion("sessions/123")
    assert result["pr_url"] == "https://pr"

    # Should not sleep if immediate success
    mock_client._sleep.assert_not_called()


@pytest.mark.asyncio
async def test_wait_for_completion_loop_success(
    mock_client: JulesClient, mock_httpx: AsyncMock
) -> None:
    """Test polling loop finds PR after few tries."""
    mock_client._sleep = AsyncMock()

    # Sequence: IN_PROGRESS -> IN_PROGRESS -> COMPLETED
    # NOTE: list_activities also calls GET, we need to handle that or distinguish by URL

    expected_calls = 2

    async def get_side_effect(url: str, **_kwargs: Any) -> MagicMock:
        if "activities" in url:
            return MagicMock(status_code=200, json=lambda: {"activities": []})

        # Session Status
        # We use sleep call count to decide iteration
        if mock_client._sleep.call_count < expected_calls:
            return MagicMock(status_code=200, json=lambda: {"state": "IN_PROGRESS"})

        return MagicMock(
            status_code=200,
            json=lambda: {
                "state": "COMPLETED",
                "outputs": [{"pullRequest": {"url": "https://pr"}}],
            },
        )

    mock_httpx.get.side_effect = get_side_effect

    result = await mock_client.wait_for_completion("sessions/123")
    assert result["pr_url"] == "https://pr"
    assert mock_client._sleep.call_count >= expected_calls


@pytest.mark.asyncio
async def test_wait_for_completion_timeout(mock_client: JulesClient, mock_httpx: AsyncMock) -> None:
    """Test timeout behaves correctly."""
    mock_client.timeout = 0.001
    mock_client._sleep = AsyncMock()

    # Always IN_PROGRESS (never completes → triggers timeout)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"state": "IN_PROGRESS"}

    async def get_mock(url: str, **kwargs: Any) -> MagicMock:
        return mock_response

    mock_httpx.get.side_effect = get_mock

    with pytest.raises(JulesTimeoutError):
        await mock_client.wait_for_completion("sessions/123")


@pytest.mark.asyncio
async def test_interactive_inquiry_handling(
    mock_client: JulesClient, mock_httpx: AsyncMock
) -> None:
    """Test handling of Jules inquiry."""
    mock_client._sleep = AsyncMock()
    mock_client.manager_agent.run.return_value = MagicMock(output="My Answer")

    async def get_side_effect(url: str, **_kwargs: Any) -> MagicMock:
        if "activities" in url:
            # Return question on first call (before sleep/reply)
            # We check if post has been called to determine if we answered
            if not mock_httpx.post.called:
                return MagicMock(
                    status_code=200,
                    json=lambda: {
                        "activities": [
                            {"id": "act1", "type": "USER_FEEDBACK_REQUESTED", "message": "Verify?"}
                        ]
                    },
                )
            return MagicMock(status_code=200, json=lambda: {"activities": [{"id": "act1"}]})

        # Session Status
        if not mock_httpx.post.called:
            return MagicMock(status_code=200, json=lambda: {"state": "AWAITING_USER_FEEDBACK"})

        return MagicMock(
            status_code=200,
            json=lambda: {
                "state": "COMPLETED",
                "outputs": [{"pullRequest": {"url": "https://pr"}}],
            },
        )

    mock_httpx.get.side_effect = get_side_effect
    mock_httpx.post.return_value.status_code = 200

    result = await mock_client.wait_for_completion("sessions/123")

    assert result["pr_url"] == "https://pr"
    assert mock_client.manager_agent.run.called
    assert mock_httpx.post.called
