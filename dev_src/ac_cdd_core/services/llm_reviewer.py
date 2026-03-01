import litellm
from ac_cdd_core.domain_models import AuditorReport
from ac_cdd_core.utils import logger
from pydantic import ValidationError


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
        Validates the output strictly against the AuditorReport Pydantic schema.
        """
        total_files = len(target_files) + len(context_docs)
        logger.info(f"LLMReviewer: preparing structured review for {total_files} files using model {model}")

        # specific prompt construction with strict separation
        prompt = self._construct_prompt(target_files, context_docs, instruction)

        # Retry logic (up to 2 retries, total 3 attempts)
        for attempt in range(3):
            try:
                response = await litellm.acompletion(
                    model=model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are an automated code reviewer. You must strictly follow the "
                                "provided instructions and only review the target code. You MUST return valid JSON."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    response_format=AuditorReport,
                    temperature=0.0,  # Deterministic output for reviews
                )

                content_str = response.choices[0].message.content

                # Parse the response safely into our robust Pydantic model
                report = AuditorReport.model_validate_json(content_str)
                return self._format_as_markdown(report)

            except (ValidationError, Exception) as e:
                logger.warning(f"LLMReviewer attempt {attempt+1} failed to parse JSON: {e}")
                if attempt == 2:
                    logger.error("LLMReviewer failed completely after 3 attempts.")
                    return f"-> REVIEW_FAILED\n\n### Critical Issues\n- **Issue**: SYSTEM_ERROR: LLM API generated invalid JSON. ({e})\n  - Location: `Unknown` (Line Unknown)\n  - Concrete Fix: Ensure your changes are simple and try again."

        return "-> REVIEW_FAILED\n\n### Critical Issues\n- **Issue**: SYSTEM_ERROR: Review loop failed unexpectedly\n  - Location: `Unknown`\n  - Concrete Fix: Ensure your changes are simple and try again."

    def _format_as_markdown(self, report: AuditorReport) -> str:
        """Converts the deeply nested AuditorReport Pydantic object into a clean Markdown string for the Coder."""
        feedback = "-> REVIEW_PASSED\n\n" if report.is_passed else "-> REVIEW_FAILED\n\n"

        feedback += f"### Summary\n{report.summary}\n\n"

        if report.fatal_issues:
            feedback += "### Critical Issues\n"
            for issue in report.fatal_issues:
                feedback += f"- **[{issue.category.upper()}]**: {issue.issue_description}\n"
                feedback += f"  - **Location**: `{issue.file_path}` (Line {issue.line_number})\n"
                feedback += f"  - **Target Snippet**:\n    ```\n    {issue.target_code_snippet}\n    ```\n"
                feedback += f"  - **Concrete Fix**: {issue.concrete_fix}\n\n"

        if report.future_suggestions:
            feedback += "### Future Architecture Suggestions\n"
            for issue in report.future_suggestions:
                feedback += f"- **[{issue.category.upper()}]**: {issue.issue_description}\n"
                feedback += f"  - **Location**: `{issue.file_path}` (Line {issue.line_number})\n"
                feedback += f"  - **Suggestion**: {issue.concrete_fix}\n\n"

        return feedback

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
