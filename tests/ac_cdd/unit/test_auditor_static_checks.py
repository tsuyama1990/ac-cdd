from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ac_cdd_core.enums import FlowStatus
from ac_cdd_core.services.auditor_usecase import AuditorUseCase
from ac_cdd_core.state import CycleState


@pytest.mark.asyncio
async def test_auditor_node_includes_static_errors() -> None:
    """
    Verify that if static analysis fails, the feedback includes errors and status is rejected.
    AuditorUseCase is tested directly (no CycleNodes wrapper needed).
    """
    # Mock dependencies for AuditorUseCase
    mock_jules = MagicMock()
    mock_git = AsyncMock()
    mock_llm = MagicMock()

    # Git mock: repo has changed files
    mock_git.checkout_pr = AsyncMock()
    mock_git.get_current_commit = AsyncMock(return_value="abc123")
    mock_git.get_pr_base_branch = AsyncMock(return_value="main")
    mock_git.get_changed_files = AsyncMock(return_value=["src/test.py"])
    mock_git.checkout_branch = AsyncMock()

    async def mock_run_command_side_effect(
        cmd: list[str], check: bool = False, **kwargs: Any
    ) -> tuple[str, str, int]:
        cmd_str = " ".join(cmd)
        if "mypy" in cmd_str:
            return "mypy failure", "error", 1  # Fail
        if "ruff" in cmd_str:
            return "ruff success", "", 0  # Pass
        if "check-ignore" in cmd_str:
            return "", "", 1  # 1 = NOT gitignored
        return "", "", 0

    mock_git.runner = MagicMock()
    mock_git.runner.run_command = AsyncMock(side_effect=mock_run_command_side_effect)

    # LLM mock: returns approval text
    mock_llm.review_code = AsyncMock(return_value="NO ISSUES FOUND")

    usecase = AuditorUseCase(mock_jules, mock_git, mock_llm)

    state = CycleState(cycle_id="99", pr_url="http://pr", feature_branch="feat/1")

    with (
        patch("ac_cdd_core.services.auditor_usecase.settings") as mock_settings,
        patch.object(usecase, "_read_files", new_callable=AsyncMock) as mock_read,
    ):
        mock_settings.get_context_files.return_value = []
        mock_settings.get_template.return_value = MagicMock(
            read_text=MagicMock(return_value="review these files")
        )
        mock_settings.get_target_files.return_value = ["src/test.py"]
        mock_settings.reviewer.smart_model = "gpt-4o"
        mock_settings.reviewer.fast_model = "gpt-3.5-turbo"
        mock_settings.AUDITOR_MODEL_MODE = "smart"
        mock_read.return_value = {"src/test.py": "x = 1"}

        result = await usecase.execute(state)

    # Assertions
    assert result["status"] == FlowStatus.REJECTED
    audit_res = result["audit_result"]
    assert not audit_res.is_approved
    assert "AUTOMATED CHECKS FAILED" in audit_res.feedback
    assert "mypy failure" in audit_res.feedback
    assert "NO ISSUES FOUND" in audit_res.feedback  # LLM text is still there
