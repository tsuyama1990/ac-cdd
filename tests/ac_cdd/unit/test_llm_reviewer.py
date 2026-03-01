from unittest.mock import AsyncMock, patch

import pytest
from ac_cdd_core.services.llm_reviewer import LLMReviewer


@pytest.fixture
def reviewer() -> LLMReviewer:
    return LLMReviewer()


@pytest.mark.asyncio
async def test_review_code_success(reviewer: LLMReviewer) -> None:
    """Test successful code review call."""
    target_files = {"main.py": "print('hello')"}
    context_files = {"spec.md": "# Spec"}
    instruction = "Review this code."
    model = "test-model"

    from ac_cdd_core.domain_models import AuditorReport

    valid_json = AuditorReport(
        is_passed=True, summary="Refactored code", fatal_issues=[], future_suggestions=[]
    ).model_dump_json()

    # Mock litellm.acompletion
    mock_response = AsyncMock()
    mock_response.choices = [
        type("obj", (object,), {"message": type("obj", (object,), {"content": valid_json})})
    ]

    with patch("litellm.acompletion", return_value=mock_response) as mock_completion:
        # UPDATED SIGNATURE: target_files, context_docs, instruction, model
        result = await reviewer.review_code(target_files, context_files, instruction, model)

        assert "APPROVE" in result
        assert "Refactored code" in result
        mock_completion.assert_called_once()

        # Verify prompt structure in call args
        call_kwargs = mock_completion.call_args.kwargs
        messages = call_kwargs["messages"]
        prompt = messages[1]["content"]

        # Verify strict separation markers
        assert "🚫 READ-ONLY CONTEXT" in prompt
        assert "🎯 AUDIT TARGET" in prompt
        assert "File: spec.md (READ-ONLY SPECIFICATION)" in prompt
        assert "File: main.py (AUDIT TARGET)" in prompt


@pytest.mark.asyncio
async def test_review_code_api_failure(reviewer: LLMReviewer) -> None:
    """Test error handling when API fails."""
    target_files = {"main.py": "content"}
    context_files: dict[str, str] = {}

    with patch("litellm.acompletion", side_effect=Exception("API Error")):
        result = await reviewer.review_code(target_files, context_files, "inst", "model")

        assert "REJECT" in result
        assert "API Error" in result
