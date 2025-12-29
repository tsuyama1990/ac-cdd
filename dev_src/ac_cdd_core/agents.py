import os  # Added import
from pathlib import Path
from typing import Any

from ac_cdd_core.config import settings
from ac_cdd_core.domain_models import (
    UatAnalysis,
)
from pydantic_ai import Agent, RunContext
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


def get_model(model_name: str) -> Any:
    """
    Parses the model name and returns an OpenAIModel with appropriate settings
    if it is an OpenRouter model.
    """
    if model_name.startswith("openrouter/"):
        # Example: openrouter/anthropic/claude-3.5-sonnet -> anthropic/claude-3.5-sonnet
        real_model_name = model_name.replace("openrouter/", "", 1)

        # Get API key from settings
        api_key = settings.OPENROUTER_API_KEY
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is not set but OpenRouter model is requested.")

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

# QA Analyst Agent
qa_analyst_agent: Agent[Any, UatAnalysis] = Agent(
    model=get_model(settings.agents.qa_analyst_model),
    system_prompt=settings.reviewer.qa_analyst,
)


@qa_analyst_agent.system_prompt
def qa_analyst_system_prompt(ctx: RunContext[Any]) -> str:
    return _get_system_context()


# Manager Agent (for handling clarifying questions)
manager_agent: Agent[Any, str] = Agent(
    model=get_model(settings.agents.qa_analyst_model),
    system_prompt=(
        "You are the Technical Project Manager. Answer clarifying questions "
        "from the developer concerning the project specifications and conventions "
        "accurately and concisely."
    ),
)


@manager_agent.system_prompt
def manager_system_prompt(ctx: RunContext[Any]) -> str:
    return _get_system_context()
