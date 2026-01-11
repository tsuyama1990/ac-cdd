"""Unit tests for gen-cycles --count option functionality."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ac_cdd_core.graph_nodes import CycleNodes
from ac_cdd_core.state import CycleState


class TestGenCyclesCountOption:
    """Test suite for --count option in gen-cycles command."""

    def test_state_propagation_with_count(self) -> None:
        """Test that requested_cycle_count is correctly stored in CycleState."""
        # Test with count specified
        state = CycleState(cycle_id="00", requested_cycle_count=3)
        assert state.requested_cycle_count == 3
        assert state.get("requested_cycle_count") == 3

    def test_state_propagation_without_count(self) -> None:
        """Test that requested_cycle_count defaults to None when not specified."""
        # Test without count (default behavior)
        state = CycleState(cycle_id="00")
        assert state.requested_cycle_count is None
        assert state.get("requested_cycle_count") is None

    @pytest.mark.asyncio
    async def test_prompt_injection_with_count(self, tmp_path: Any) -> None:
        """Test that architect_session_node injects constraint when count is specified."""
        # Setup mocks
        mock_sandbox = MagicMock()
        mock_jules = AsyncMock()
        mock_jules.run_session = AsyncMock(return_value={"status": "success"})

        # Create a temporary instruction file
        instruction_content = "Original architect instruction."

        # Mock settings.get_template to return our test content
        with (
            patch("ac_cdd_core.graph_nodes.settings") as mock_settings,
            patch("ac_cdd_core.graph_nodes.GitManager") as mock_git_cls,
        ):
            # Configure GitManager mock instance
            mock_git_instance = mock_git_cls.return_value
            mock_git_instance.create_feature_branch = AsyncMock()
            mock_git_instance.merge_pr = AsyncMock()

            mock_template = MagicMock()
            mock_template.read_text.return_value = instruction_content
            mock_settings.get_template.return_value = mock_template
            mock_settings.get_context_files.return_value = []

            # Create CycleNodes instance
            nodes = CycleNodes(sandbox_runner=mock_sandbox, jules_client=mock_jules)

            # Create state with requested_cycle_count
            state = CycleState(cycle_id="00", requested_cycle_count=5)

            # Execute the node
            await nodes.architect_session_node(state)

            # Verify run_session was called
            assert mock_jules.run_session.called

            # Get the actual prompt argument passed to run_session
            call_args = mock_jules.run_session.call_args
            actual_prompt = call_args.kwargs["prompt"]

            # Verify the constraint was injected
            assert "IMPORTANT CONSTRAINT" in actual_prompt
            assert "exactly 5 implementation cycles" in actual_prompt
            assert instruction_content in actual_prompt

    @pytest.mark.asyncio
    async def test_prompt_no_injection_without_count(self, tmp_path: Any) -> None:
        """Test that architect_session_node does NOT inject constraint when count is not specified."""
        # Setup mocks
        mock_sandbox = MagicMock()
        mock_jules = AsyncMock()
        mock_jules.run_session = AsyncMock(return_value={"status": "success"})

        # Create a temporary instruction file
        instruction_content = "Original architect instruction."

        # Mock settings.get_template to return our test content
        with (
            patch("ac_cdd_core.graph_nodes.settings") as mock_settings,
            patch("ac_cdd_core.graph_nodes.GitManager") as mock_git_cls,
        ):
            # Configure GitManager mock instance
            mock_git_instance = mock_git_cls.return_value
            mock_git_instance.create_feature_branch = AsyncMock()
            mock_git_instance.merge_pr = AsyncMock()

            mock_template = MagicMock()
            mock_template.read_text.return_value = instruction_content
            mock_settings.get_template.return_value = mock_template
            mock_settings.get_context_files.return_value = []

            # Create CycleNodes instance
            nodes = CycleNodes(sandbox_runner=mock_sandbox, jules_client=mock_jules)

            # Create state WITHOUT requested_cycle_count
            # BUT: CycleState defaults planned_cycle_count to 5 (from definition in state.py)
            # So if we want NO injection, we must explicitly set planned_cycle_count to None if allowed
            # or check that it uses planned_cycle_count logic.
            # In updated graph_nodes.py logic:
            # if requested_cycle_count: use it
            # elif planned_cycle_count: use it

            # If we want to test "no constraint", we need both to be None.
            state = CycleState(cycle_id="00", requested_cycle_count=None, planned_cycle_count=None)

            # Execute the node
            await nodes.architect_session_node(state)

            # Verify run_session was called
            assert mock_jules.run_session.called

            # Get the actual prompt argument passed to run_session
            call_args = mock_jules.run_session.call_args
            actual_prompt = call_args.kwargs["prompt"]

            # Verify the constraint was NOT injected
            assert "IMPORTANT CONSTRAINT" not in actual_prompt
            assert "implementation cycles" not in actual_prompt
            assert actual_prompt == instruction_content

    @pytest.mark.parametrize("count_value", [1, 2, 3, 5, 10])
    @pytest.mark.asyncio
    async def test_prompt_injection_various_counts(self, count_value: int) -> None:
        """Test that the correct count value is injected for various inputs."""
        # Setup mocks
        mock_sandbox = MagicMock()
        mock_jules = AsyncMock()
        mock_jules.run_session = AsyncMock(return_value={"status": "success"})

        instruction_content = "Test instruction."

        with (
            patch("ac_cdd_core.graph_nodes.settings") as mock_settings,
            patch("ac_cdd_core.graph_nodes.GitManager") as mock_git_cls,
        ):
            # Configure GitManager mock instance
            mock_git_instance = mock_git_cls.return_value
            mock_git_instance.create_feature_branch = AsyncMock()
            mock_git_instance.merge_pr = AsyncMock()

            mock_template = MagicMock()
            mock_template.read_text.return_value = instruction_content
            mock_settings.get_template.return_value = mock_template
            mock_settings.get_context_files.return_value = []

            nodes = CycleNodes(sandbox_runner=mock_sandbox, jules_client=mock_jules)

            state = CycleState(cycle_id="00", requested_cycle_count=count_value)

            await nodes.architect_session_node(state)

            call_args = mock_jules.run_session.call_args
            actual_prompt = call_args.kwargs["prompt"]

            # Verify the specific count is in the prompt
            assert f"exactly {count_value} implementation cycles" in actual_prompt
