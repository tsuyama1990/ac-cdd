from pathlib import Path
from typing import Any

from pydantic_ai import Agent, RunContext

from src.ac_cdd.config import settings
from src.ac_cdd.domain_models import AuditResult, CyclePlan, UatAnalysis, FileChange

# Model Definition
MODEL_NAME = 'google-gla:gemini-2.0-flash'

def _load_file_content(filepath: str) -> str:
    path = Path(filepath)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""

def _get_system_context() -> str:
    """Injects global context from ALL_SPEC.md and conventions.md if available."""
    context = []

    # Load ALL_SPEC.md
    all_spec_path = Path(settings.paths.documents_dir) / "ALL_SPEC.md"
    if all_spec_path.exists():
        content = all_spec_path.read_text(encoding='utf-8')
        context.append(f"### Project Specifications (ALL_SPEC.md)\n{content}")

    # Load conventions.md
    conventions_path = Path(settings.paths.documents_dir) / "conventions.md"
    if conventions_path.exists():
        content = conventions_path.read_text(encoding='utf-8')
        context.append(f"### Coding Conventions\n{content}")

    return "\n\n".join(context)

# --- Agents ---

# Planner Agent
planner_agent: Agent[Any, CyclePlan] = Agent(
    MODEL_NAME,
    system_prompt=(
        "You are a Senior Software Architect. "
        "Define robust and scalable design specifications based on requirements."
    )
)

@planner_agent.system_prompt
def planner_system_prompt(ctx: RunContext[Any]) -> str:
    return _get_system_context()


# Coder Agent
coder_agent: Agent[Any, list[FileChange]] = Agent(
    MODEL_NAME,
    system_prompt=(
        "You are Jules, a skilled Python Engineer. "
        "Implement high-quality code based on specifications and contracts. "
        "Return a list of file changes."
        "Always explain your thought process."
    )
)

@coder_agent.system_prompt
def coder_system_prompt(ctx: RunContext[Any]) -> str:
    return _get_system_context()


# Auditor Agent
auditor_agent: Agent[Any, AuditResult] = Agent(
    MODEL_NAME,
    system_prompt=(
        "You are the world's strictest Code Auditor (Gemini). "
        "Review code thoroughly for Pydantic contract violations, "
        "security issues, and design principles."
    )
)

@auditor_agent.system_prompt
def auditor_system_prompt(ctx: RunContext[Any]) -> str:
    return _get_system_context()


# QA Analyst Agent
qa_analyst_agent: Agent[Any, UatAnalysis] = Agent(
    MODEL_NAME,
    system_prompt=(
        "You are a QA Manager. "
        "Analyze test logs and report on conformity to requirements and behavior in Markdown."
    )
)

@qa_analyst_agent.system_prompt
def qa_analyst_system_prompt(ctx: RunContext[Any]) -> str:
    return _get_system_context()
