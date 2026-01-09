import os  # Added import
from pathlib import Path
from typing import Any

from ac_cdd_core.config import settings
from ac_cdd_core.domain_models import (
    UatAnalysis,
)
from ac_cdd_core.utils import logger
from pydantic_ai import Agent, RunContext
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel


def _load_file_content(filepath: str) -> str:
    path = Path(filepath)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _get_system_context() -> str:
    """Injects global context from ALL_SPEC.md and conventions.md if available."""
    context = []

    # Load ALL_SPEC context (Prefer Structured)
    docs_dir = Path(settings.paths.documents_dir)
    structured_spec_path = docs_dir / "ALL_SPEC_STRUCTURED.md"
    raw_spec_path = docs_dir / "ALL_SPEC.md"

    if structured_spec_path.exists():
        content = structured_spec_path.read_text(encoding="utf-8")
        context.append(f"### Project Specifications (Structured)\n{content}")
    elif raw_spec_path.exists():
        content = raw_spec_path.read_text(encoding="utf-8")
        context.append(f"### Project Specifications (Raw)\n{content}")

    # Load conventions.md
    conventions_path = Path(settings.paths.documents_dir) / "conventions.md"
    if conventions_path.exists():
        content = conventions_path.read_text(encoding="utf-8")
        context.append(f"### Coding Conventions\n{content}")

    return "\n\n".join(context)


def _get_openrouter_api_key() -> str:
    """Retrieves OpenRouter API key with fallbacks."""
    api_key = settings.OPENROUTER_API_KEY or os.getenv("OPENROUTER_API_KEY")
    if api_key:
        return api_key

    # Fallback: Manual .env parsing only if file exists
    env_path = Path(".env")
    if env_path.exists():
        try:
            content = env_path.read_text(encoding="utf-8")
            for line in content.splitlines():
                if line.startswith("OPENROUTER_API_KEY="):
                    parts = line.split("=", 1)
                    if len(parts) > 1:
                        candidate = parts[1].strip().strip('"').strip("'")
                        if candidate:
                            return candidate
        except (OSError, UnicodeDecodeError) as e:
            logger.debug(f"Failed to read .env for OpenRouter key: {e}")

    logger.warning(
        "OPENROUTER_API_KEY is not set. Using dummy key 'sk-dummy'. "
        "This will fail if real API calls are attempted."
    )
    return "sk-dummy"


def get_model(model_name: str) -> Model | str:
    """
    Parses the model name and returns an OpenAIModel with appropriate settings
    if it is an OpenRouter model.
    """
    if model_name.startswith("openrouter/"):
        real_model_name = model_name.replace("openrouter/", "", 1)
        api_key = _get_openrouter_api_key()

        # OpenAIChatModel requires env var for OpenRouter if using provider="openrouter"
        os.environ["OPENROUTER_API_KEY"] = api_key

        return OpenAIChatModel(
            model_name=real_model_name,
            provider="openrouter",
        )

    # If gemini/ prefix exists, or just return the string (let PydanticAI handle it)
    if model_name.startswith("gemini/"):
        return model_name.replace("gemini/", "", 1)

    return model_name


# --- Agents ---
# Auditor Agent is deprecated/removed in favor of LLMReviewer.

# Lazy initialization to avoid requiring API keys at import time
_qa_analyst_agent: Agent[Any, UatAnalysis] | None = None
_manager_agent: Agent[Any, str] | None = None


def get_qa_analyst_agent() -> Agent[Any, UatAnalysis]:
    """Get or create the QA Analyst agent instance."""
    global _qa_analyst_agent  # noqa: PLW0603
    if _qa_analyst_agent is None:
        _qa_analyst_agent = Agent(
            model=get_model(settings.agents.qa_analyst_model),
            system_prompt=settings.get_prompt_content(
                "UAT_DESIGN.md", default="You are a QA Analyst."
            ),
        )

        @_qa_analyst_agent.system_prompt
        def qa_analyst_system_prompt(_ctx: RunContext[Any]) -> str:
            return _get_system_context()

    return _qa_analyst_agent


def get_manager_agent() -> Agent[Any, str]:
    """Get or create the Manager agent instance."""
    global _manager_agent  # noqa: PLW0603
    if _manager_agent is None:
        _manager_agent = Agent(
            model=get_model(settings.agents.auditor_model),
            system_prompt=(
                "You are a Senior Technical Project Manager and Debugging Mentor. "
                "When answering questions from the developer (Jules):\n"
                "1. Focus on ROOT CAUSE ANALYSIS - help identify WHY problems occur, not just HOW to fix them\n"
                "2. Guide systematic investigation - suggest specific files, functions, or debugging steps\n"
                "3. Discourage trial-and-error - promote understanding before fixing\n"
                "4. Be analytical and educational - help Jules become a better problem solver\n"
                "Answer questions accurately, concisely, and with clear reasoning based on project specifications."
            ),
        )

        @_manager_agent.system_prompt
        def manager_system_prompt(_ctx: RunContext[Any]) -> str:
            return _get_system_context()

    return _manager_agent
