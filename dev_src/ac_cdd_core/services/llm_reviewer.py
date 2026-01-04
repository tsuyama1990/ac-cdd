import litellm
from ac_cdd_core.utils import logger


class LLMReviewer:
    """
    Direct LLM Client for conducting static code reviews.
    Uses litellm to communicate with various LLM providers (OpenRouter, Gemini, etc.).
    """

    def __init__(self, sandbox_runner: object | None = None) -> None:
        # sandbox_runner is accepted for dependency injection compatibility
        # even if not strictly used by this class (files are passed as content)
        self.sandbox = sandbox_runner

        # We rely on litellm's environment variable handling for API keys.
        # Ensure litellm is verbose enough for debugging if needed, but keep logs clean by default.
        litellm.suppress_instrumentation = True

    async def review_code(
        self,
        target_files: dict[str, str],
        context_docs: dict[str, str],
        instruction: str,
        model: str,
    ) -> str:
        """
        Sends file contents and instructions to the LLM for review.

        Args:
            target_files: Dictionary mapping file paths to their content (Code to be reviewed).
            context_docs: Dictionary mapping file paths to their content (Read-only specs).
            instruction: The prompt/instruction for the review.
            model: The model identifier to use.

        Returns:
            The raw text response from the LLM.
        """
        total_files = len(target_files) + len(context_docs)
        logger.info(f"LLMReviewer: preparing review for {total_files} files using model {model}")

        # specific prompt construction with strict separation
        prompt = self._construct_prompt(target_files, context_docs, instruction)

        try:
            # We use litellm.acompletion for async execution
            response = await litellm.acompletion(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an automated code reviewer. You must strictly follow the "
                            "provided instructions and only review the target code."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,  # Deterministic output for reviews
            )

            # Extract content from response
            content = response.choices[0].message.content
            return str(content)

        except Exception as e:  # noqa: BLE001
            logger.error(f"LLMReviewer failed: {e}")
            return f"SYSTEM_ERROR: LLM API call failed: {e}"

    def _construct_prompt(
        self, target_files: dict[str, str], context_docs: dict[str, str], instruction: str
    ) -> str:
        """
        Format the prompt with strict Context/Target separation.
        """

        # 1. Context Section (Specs)
        context_section = ""
        for name, content in context_docs.items():
            context_section += f"\nFile: {name} (READ-ONLY SPECIFICATION)\n```\n{content}\n```\n"

        # 2. Target Section (Code)
        target_section = ""
        for name, content in target_files.items():
            # Add python hint for .py files
            lang = "python" if name.endswith(".py") else ""
            target_section += f"\nFile: {name} (AUDIT TARGET)\n```{lang}\n{content}\n```\n"

        # 3. Assemble Prompt
        return f"""
{instruction}

###################

🚫 READ-ONLY CONTEXT (GROUND TRUTH)

The following files define the specifications.
You must NOT critique, review, or suggest changes to these files.
Use them ONLY as the reference to judge the code.

###################
{context_section}

###################

🎯 AUDIT TARGET (CODE TO REVIEW)

Strictly review the following files against the context above.
Provide feedback ONLY for these files.

###################
{target_section}
"""
