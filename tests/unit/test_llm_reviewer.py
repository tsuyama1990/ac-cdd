from unittest.mock import AsyncMock, patch

import pytest
from ac_cdd_core.services.llm_reviewer import LLMReviewer


@pytest.fixture
def reviewer():
    return LLMReviewer()


@pytest.mark.asyncio
async def test_review_code_success(reviewer):
    """Test successful code review call."""
    files = {"main.py": "print('hello')", "utils.py": "def foo(): pass"}
    instruction = "Review this code."
    model = "test-model"

    # Mock litellm.acompletion
    mock_response = AsyncMock()
    mock_response.choices = [
        type("obj", (object,), {"message": type("obj", (object,), {"content": "Refactored code"})})
    ]

    with patch("litellm.acompletion", return_value=mock_response) as mock_completion:
        result = await reviewer.review_code(files, instruction, model)

        assert result == "Refactored code"
        mock_completion.assert_called_once()

        # Verify prompt structure in call args
        call_kwargs = mock_completion.call_args.kwargs
        messages = call_kwargs["messages"]
        prompt = messages[1]["content"]

        assert "<instruction>\nReview this code.\n</instruction>" in prompt
        assert "<file path=\"main.py\">\nprint('hello')\n</file>" in prompt
        assert '<file path="utils.py">\ndef foo(): pass\n</file>' in prompt


@pytest.mark.asyncio
async def test_review_code_api_failure(reviewer):
    """Test error handling when API fails."""
    files = {"main.py": "content"}

    with patch("litellm.acompletion", side_effect=Exception("API Error")):
        result = await reviewer.review_code(files, "inst", "model")

        assert result.startswith("SYSTEM_ERROR")
        assert "API call failed" in result
