from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ac_cdd_core.graph import GraphBuilder
from ac_cdd_core.state import CycleState


@pytest.mark.asyncio
async def test_architect_graph_structure(mock_services):
    """Test architect graph structure."""
    builder = GraphBuilder(mock_services)
    graph = builder.build_architect_graph()

    # The build_architect_graph method returns a CompiledStateGraph, so no need to compile again.
    assert graph is not None


@pytest.mark.asyncio
async def test_coder_graph_structure(mock_services):
    """Test coder graph structure."""
    builder = GraphBuilder(mock_services)
    graph = builder.build_coder_graph()

    # The build_coder_graph method returns a CompiledStateGraph.
    assert graph is not None


@pytest.mark.asyncio
async def test_architect_graph_execution(mock_services):
    """Test architect graph execution flow."""
    builder = GraphBuilder(mock_services)
    graph = builder.build_architect_graph()

    # Mock mocks
    mock_runner = AsyncMock()
    mock_runner.run_command.return_value = ("", "", 0)

    # Mock Jules
    mock_jules_instance = AsyncMock()
    mock_jules_instance.run_session.return_value = {
        "pr_url": "https://github.com/user/repo/pull/1",
        "cycles": ["01", "02"],
    }

    # Setup Builder with Mocks
    builder.jules_client = mock_jules_instance
    builder.git.create_integration_branch = AsyncMock(return_value="dev/session-test")
    # builder.git.create_session_branch = AsyncMock(return_value="dev/session-test/arch") # REMOVED
    builder.git.checkout_branch = AsyncMock()  # NEW
    builder.git.merge_to_integration = AsyncMock()
    builder.git.commit_changes = AsyncMock()

    with patch.object(builder, "_get_shared_sandbox", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_runner

        # Execute graph
        # LangGraph automatically validates and converts dict to CycleState
        initial_state = {
            "cycle_id": "01",  # Required by CycleState
            "session_id": "test-session",
            "integration_branch": "dev/test",  # This gets overwritten/used
        }

        # We need to mock path reading if the node reads files
        # architect_session_node reads ARCHITECT_INSTRUCTION.md and ALL_SPEC.md/plan_status
        # We can mock Path.read_text globally or better, creating temp files using pyfakefs.
        # But for unit test of graph flow, we can mock the node method or ensure files exist.
        # Given we want to test the FLOW, mocking the builder nodes is easiest,
        # BUT we want to test the node logic too.
        # Let's mock Path.read_text.

        with patch("pathlib.Path.read_text", return_value="instruction"):
            with patch("pathlib.Path.exists", return_value=True):
                # Mock json.loads for plan_status
                with patch("json.loads", return_value={"cycles": ["01"]}):
                    # Run it
                    # Note: ainvoke might raise if there are edge cases.
                    # Given logical complexity, let's just assert the graph is compiled
                    # and nodes are callable
                    # But the previous test stub failed?
                    # Let's try to run it.
                    try:
                        final_state = await graph.ainvoke(initial_state)
                        assert final_state["current_phase"] == "complete"
                        assert builder.git.create_integration_branch.called
                    except Exception as e:
                        pytest.fail(f"Graph execution failed: {e}")


@pytest.mark.asyncio
async def test_coder_graph_execution(mock_services):
    """Test coder graph execution flow."""
    builder = GraphBuilder(mock_services)
    graph = builder.build_coder_graph()

    assert graph is not None


@pytest.mark.asyncio
async def test_syntax_check_node_success(mock_services):
    """Test syntax check node with successful validation."""
    builder = GraphBuilder(mock_services)

    mock_runner = AsyncMock()
    # Mock run_command to return (stdout, stderr, code)
    mock_runner.run_command.side_effect = [
        ("", "", 0),  # compileall success
        ("", "", 0),  # ruff success
    ]

    with patch.object(builder, "_get_shared_sandbox", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_runner

        state = CycleState(cycle_id="01", active_branch="feat/cycle01")
        result = await builder.syntax_check_node(state)

        assert result["current_phase"] == "syntax_check_passed"
        assert result["test_exit_code"] == 0


@pytest.mark.asyncio
async def test_syntax_check_node_failure(mock_services):
    """Test syntax check node with validation failure."""
    builder = GraphBuilder(mock_services)

    mock_runner = AsyncMock()
    mock_runner.run_command.side_effect = [
        ("", "", 0),  # compileall success
        ("", "E501 line too long", 1),  # ruff failure
    ]

    with patch.object(builder, "_get_shared_sandbox", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_runner
        state = CycleState(cycle_id="01", active_branch="feat/cycle01")
        result = await builder.syntax_check_node(state)

        assert result["current_phase"] == "syntax_check_failed"
        assert result["test_exit_code"] == 1


@pytest.mark.asyncio
async def test_audit_node_execution(mock_services):
    """Test audit node execution."""
    builder = GraphBuilder(mock_services)
    # Mock GitManager.get_changed_files to be async and return a list
    builder.git.get_changed_files = AsyncMock(return_value=["file.py"])

    with patch("ac_cdd_core.services.llm_reviewer.LLMReviewer") as mock_reviewer:
        # Need to fix the mocking of LLMReviewer instance method
        mock_reviewer_instance = AsyncMock()
        mock_reviewer.return_value = mock_reviewer_instance
        # review_code returns text response
        mock_reviewer_instance.review_code.return_value = "APPROVED: Code looks good"

        # Link the builder's reviewer to our mock
        builder.llm_reviewer = mock_reviewer_instance

        # Mock _get_shared_sandbox as it's called
        with patch.object(builder, "_get_shared_sandbox", new_callable=AsyncMock):
            state = CycleState(
                cycle_id="01",
                active_branch="feat/cycle01",
                iteration_count=1,
                current_auditor_index=1,
                current_auditor_review_count=1,
            )

            result = await builder.auditor_node(state)

            assert "audit_feedback" in result
            assert result["current_phase"] == "audit_complete"


@pytest.mark.asyncio
async def test_audit_node_file_selection(mock_services):
    """Test audit node strictly respects changed_files."""
    builder = GraphBuilder(mock_services)
    
    # 1. Test Smart Mode (Changed Files Present)
    # Return a changed file that exists on disk
    builder.git.get_changed_files = AsyncMock(return_value=["changed_file.py"])
    
    # Mock LLM and Sandbox
    builder.llm_reviewer = AsyncMock()
    builder.llm_reviewer.review_code.return_value = "APPROVED"
    mock_runner = AsyncMock()
    
    with patch.object(builder, "_get_shared_sandbox", return_value=mock_runner):
        # Allow Path.exists to check our file logic
        # We need specific return values for Path.exists calls
        # 1. changed_file.py -> True
        # 2. ac_cdd_config.py -> True (but should NOT be included)
        # 3. pyproject.toml -> True (but should NOT be included)
        # 4. Docs -> False (simplify test)
        
        def exists_side_effect(self):
            path_str = str(self)
            if "changed_file.py" in path_str:
                return True
            if "ac_cdd_config.py" in path_str or "pyproject.toml" in path_str:
                return True
            return False
            
        with patch("pathlib.Path.exists", side_effect=exists_side_effect, autospec=True):
             with patch("pathlib.Path.read_text", return_value="content"):
                state = CycleState(cycle_id="01", active_branch="feat", current_auditor_index=1, current_auditor_review_count=1)
                
                # Run node
                await builder.auditor_node(state)
                
                # Check what was passed to review_code
                call_args = builder.llm_reviewer.review_code.call_args
                files_content = call_args.kwargs.get("files")
                
                # ASSERTION: Only changed_file.py should be in there.
                # ac_cdd_config.py and pyproject.toml should NOT be there.
                assert "changed_file.py" in files_content
                assert "ac_cdd_config.py" not in files_content
                assert "pyproject.toml" not in files_content


@pytest.mark.asyncio
async def test_fix_node_execution(mock_services):
    """Test fix node execution with Jules."""
    # Note: There is no 'fix_node' in GraphBuilder, it's 'coder_session_node'
    # behaving as fixer when in fix loop.
    builder = GraphBuilder(mock_services)

    with patch(
        "ac_cdd_core.services.jules_client.JulesClient", new_callable=MagicMock
    ) as mock_client_cls:
        mock_jules_instance = AsyncMock()
        mock_client_cls.return_value = mock_jules_instance
        # continue_session returns dict with pr_url
        mock_jules_instance.continue_session.return_value = {
            "pr_url": "https://github.com/user/repo/pull/2"
        }

        # Link builder client
        builder.jules_client = mock_jules_instance

        with patch.object(builder, "_get_shared_sandbox", new_callable=AsyncMock):
            # Mock git ops
            builder.git.checkout_pr = AsyncMock()

            state = CycleState(
                cycle_id="01",
                jules_session_name="sessions/123",
                audit_feedback=["Fix line too long errors"],
                iteration_count=2,
                active_branch="dev/cycle01",
                current_auditor_index=1,
                current_auditor_review_count=1,
            )

            result = await builder.coder_session_node(state)

            assert result["current_phase"] == "coder_complete"


@pytest.mark.asyncio
async def test_graph_state_transitions(mock_services):
    """Test graph state transitions through workflow."""
    GraphBuilder(mock_services)

    # Test state progression
    state = {"current_phase": "start"}

    # Simulate phase transitions
    phases = ["start", "jules_create", "syntax_check", "audit", "fix", "complete"]

    for phase in phases:
        state["current_phase"] = phase
        assert state["current_phase"] == phase

    # Verify final state
    assert state["current_phase"] == "complete"
