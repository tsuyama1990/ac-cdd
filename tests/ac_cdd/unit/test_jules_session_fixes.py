import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ac_cdd_core.jules_session_nodes import JulesSessionNodes, SessionStatus
from ac_cdd_core.jules_session_state import JulesSessionState


@pytest.mark.asyncio
async def test_monitor_session_batching() -> None:
    """Verify monitor_session loops internally for batch polling."""
    # Setup
    mock_client = MagicMock()
    mock_client._get_headers.return_value = {}
    mock_client._sleep = AsyncMock()
    mock_client._check_for_inquiry = AsyncMock(return_value=None)
    mock_client._handle_manual_input = AsyncMock()

    loop = asyncio.get_running_loop()
    start_time = loop.time()
    nodes = JulesSessionNodes(mock_client)
    state = JulesSessionState(session_url="http://test/session", start_time=start_time)

    # Mock httpx in the TARGET MODULE
    with patch("ac_cdd_core.jules_session_nodes.httpx") as mock_httpx:
        # CONFIGURE MOCK CONSTANTS
        mock_httpx.codes.OK = 200

        mock_instance = mock_httpx.AsyncClient.return_value
        mock_instance.__aenter__.return_value = mock_instance

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"state": "IN_PROGRESS", "outputs": []}

        # Use AsyncMock for get
        mock_instance.get = AsyncMock(return_value=mock_resp)

        # Run
        new_state = await nodes.monitor_session(state)

        # Verify
        assert mock_instance.get.call_count == 24
        assert mock_client._sleep.call_count == 12
        assert new_state.status == SessionStatus.MONITORING


@pytest.mark.asyncio
async def test_monitor_session_returns_early_on_change() -> None:
    """Verify monitor_session returns early if state changes to COMPLETED."""
    # Setup
    mock_client = MagicMock()
    mock_client._get_headers.return_value = {}
    mock_client._sleep = AsyncMock()
    mock_client._check_for_inquiry = AsyncMock(return_value=None)
    mock_client._handle_manual_input = AsyncMock()

    loop = asyncio.get_running_loop()
    start_time = loop.time()
    nodes = JulesSessionNodes(mock_client)
    state = JulesSessionState(session_url="http://test/session", start_time=start_time)

    with patch("ac_cdd_core.jules_session_nodes.httpx") as mock_httpx:
        mock_httpx.codes.OK = 200

        mock_instance = mock_httpx.AsyncClient.return_value
        mock_instance.__aenter__.return_value = mock_instance

        mock_resp_prog = MagicMock()
        mock_resp_prog.status_code = 200
        mock_resp_prog.json.return_value = {"state": "IN_PROGRESS", "outputs": []}

        mock_resp_comp = MagicMock()
        mock_resp_comp.status_code = 200
        mock_resp_comp.json.return_value = {"state": "COMPLETED", "outputs": []}

        mock_instance.get = AsyncMock(side_effect=[mock_resp_prog, mock_resp_prog, mock_resp_comp])

        # Run
        new_state = await nodes.monitor_session(state)

        # Verify
        assert mock_instance.get.call_count == 3
        assert mock_client._sleep.call_count == 1
        assert new_state.status == SessionStatus.VALIDATING_COMPLETION


@pytest.mark.asyncio
async def test_validate_completion_stale_detection() -> None:
    """Verify validate_completion handles stale events correctly."""
    # Setup
    mock_client = MagicMock()
    mock_client._get_headers.return_value = {}

    nodes = JulesSessionNodes(mock_client)
    state = JulesSessionState(session_url="http://test/session")
    state.processed_completion_ids.add("act-123")
    state.previous_jules_state = "COMPLETED"

    with patch("ac_cdd_core.jules_session_nodes.httpx") as mock_httpx:
        mock_httpx.codes.OK = 200

        mock_instance = mock_httpx.AsyncClient.return_value
        mock_instance.__aenter__.return_value = mock_instance

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "activities": [{"name": "act-123", "sessionCompleted": {}}],
            "messages": [],
        }

        # AsyncMock for get
        mock_instance.get = AsyncMock(return_value=mock_resp)

        # Run
        new_state = await nodes.validate_completion(state)

        # Verify
        assert new_state.status == SessionStatus.MONITORING


@pytest.mark.asyncio
async def test_validate_completion_stale_but_new_transition() -> None:
    """Verify validate_completion accepts stale event if transition is valid (IN_PROGRESS -> COMPLETED)."""
    # Setup
    mock_client = MagicMock()
    mock_client._get_headers.return_value = {}

    nodes = JulesSessionNodes(mock_client)
    state = JulesSessionState(session_url="http://test/session")
    state.processed_completion_ids.add("act-123")
    state.previous_jules_state = "IN_PROGRESS"

    with patch("ac_cdd_core.jules_session_nodes.httpx") as mock_httpx:
        mock_httpx.codes.OK = 200

        mock_instance = mock_httpx.AsyncClient.return_value
        mock_instance.__aenter__.return_value = mock_instance

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # Fix mock structure: sessionCompleted is a key
        mock_resp.json.return_value = {"activities": [{"name": "act-123", "sessionCompleted": {}}]}

        mock_instance.get = AsyncMock(return_value=mock_resp)

        # Run
        new_state = await nodes.validate_completion(state)

        # Verify
        assert new_state.status == SessionStatus.CHECKING_PR


@pytest.mark.asyncio
async def test_monitor_session_avoids_validation_loop() -> None:
    """Verify monitor_session does NOT go to validation if already validated."""
    # Setup
    mock_client = MagicMock()
    mock_client._get_headers.return_value = {}
    mock_client._sleep = AsyncMock()
    mock_client._check_for_inquiry = AsyncMock(return_value=None)
    mock_client._handle_manual_input = AsyncMock()

    loop = asyncio.get_running_loop()
    start_time = loop.time()
    nodes = JulesSessionNodes(mock_client)
    state = JulesSessionState(session_url="http://test/session", start_time=start_time)

    # Pre-set state to COMPLETED and Validated
    state.jules_state = "COMPLETED"
    state.completion_validated = True

    with patch("ac_cdd_core.jules_session_nodes.httpx") as mock_httpx:
        mock_httpx.codes.OK = 200

        mock_instance = mock_httpx.AsyncClient.return_value
        mock_instance.__aenter__.return_value = mock_instance

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # Jules is still completed
        mock_resp.json.return_value = {"state": "COMPLETED", "outputs": []}

        mock_instance.get = AsyncMock(return_value=mock_resp)

        # Run
        new_state = await nodes.monitor_session(state)

        # Verify
        # Should not change status to VALIDATING_COMPLETION
        # Should remain MONITORING (or whatever it was, default MONITORING)
        assert new_state.status == SessionStatus.MONITORING
        # Should have looped 12 times (batching) because it didn't exit early, 2 calls per loop
        assert mock_instance.get.call_count == 24
