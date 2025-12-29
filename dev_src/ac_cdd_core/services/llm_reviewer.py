import litellm
from ac_cdd_core.utils import logger


class LLMReviewer:
    """
    Direct LLM Client for conducting static code reviews.
    Uses litellm to communicate with various LLM providers (OpenRouter, Gemini, etc.).
    """

    def __init__(self) -> None:
        # We rely on litellm's environment variable handling for API keys.
        # Ensure litellm is verbose enough for debugging if needed, but keep logs clean by default.
        litellm.suppress_instrumentation = True

    async def review_code(self, files: dict[str, str], instruction: str, model: str) -> str:
        """
        Sends file contents and instructions to the LLM for review.

        Args:
            files: Dictionary mapping file paths to their content.
            instruction: The prompt/instruction for the review.
            model: The model identifier to use (e.g., 'openrouter/google/gemini-pro-1.5').

        Returns:
            The raw text response from the LLM.
        """
        logger.info(f"LLMReviewer: preparing review for {len(files)} files using model {model}")

        # specific prompt construction
        prompt = self._construct_prompt(files, instruction)

        try:
            # We use litellm.acompletion for async execution
            response = await litellm.acompletion(
                model=model,
                messages=[
                    {"role": "system", "content": "You are an automated code reviewer."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,  # Deterministic output for reviews
            )

            # Extract content from response
            content = response.choices[0].message.content
            return content

        except Exception as e:
            logger.error(f"LLMReviewer failed: {e}")
            return f"SYSTEM_ERROR: LLM API call failed: {e}"

    def _construct_prompt(self, files: dict[str, str], instruction: str) -> str:
        """
        Format the prompt with XML-style tags for clear separation of instruction and files.
        """
        prompt_parts = []
        prompt_parts.append("<instruction>")
        prompt_parts.append(instruction)
        prompt_parts.append("</instruction>")
        prompt_parts.append("")
        prompt_parts.append("<files>")

        for file_path, content in files.items():
            prompt_parts.append(f'<file path="{file_path}">')
            prompt_parts.append(content)
            prompt_parts.append("</file>")

        prompt_parts.append("</files>")

        return "\n".join(prompt_parts)
