from typing import Any

from ac_cdd_core.config import settings
from ac_cdd_core.domain_models import PlanAuditResult
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel


def _create_model(model_str: str) -> str | Any:
    """Create appropriate model instance from model string."""
    # If model string starts with "openrouter/", use OpenAIModel with OpenRouter provider
    if model_str.startswith("openrouter/"):
        # Extract the model name (remove "openrouter/" prefix)
        model_name = model_str.replace("openrouter/", "", 1)
        # Use OpenAIModel with openrouter provider
        return OpenAIModel(model_name, provider="openrouter")
    # Otherwise, return the model string as-is for pydantic-ai to infer
    return model_str


class PlanAuditor:
    """
    Validates implementation plans against requirements using an AI agent.
    """

    def __init__(self, agent: Agent[Any, PlanAuditResult] | None = None) -> None:
        self.agent = agent or Agent(
            model=_create_model(settings.agents.auditor_model),
            output_type=PlanAuditResult,
            system_prompt=(
                "You are an expert Software Architect and QA Auditor. "
                "Your job is to audit ARCHITECTURAL PLANS (not implementation code) against requirements. "
                "Understand that an Architect creates high-level design and file structure, "
                "NOT detailed implementation code. The actual coding will be done by a Coder in a later phase."
            ),
        )

    async def audit_plan(
        self, plan_details: dict[str, Any], context_files: dict[str, str],
        phase: str = "coder"  # "architect" or "coder"
    ) -> PlanAuditResult:
        """
        Audits a plan against the requirements.
        Args:
            plan_details: The plan to audit
            context_files: Reference requirements (SPEC.md, etc.)
            phase: "architect" for high-level architectural plans (gen-cycles),
                   "coder" for detailed implementation plans (run-cycle)
        """
        # Construct context
        context_str = "## Reference Requirements\n"
        for fname, content in context_files.items():
            context_str += f"### {fname}\n{content}\n\n"

        plan_str = f"## Proposed Plan\n{plan_details}"

        # Different prompts for different phases
        if phase == "architect":
            user_prompt = (
                f"Please audit the following ARCHITECTURAL PLAN against the requirements.\n\n"
                f"{context_str}\n"
                f"{plan_str}\n\n"
                "**IMPORTANT CONTEXT:**\n"
                "This is an ARCHITECTURAL PLAN from the Architect phase. The Architect's job is to:\n"
                "- Define the system structure and file organization\n"
                "- Specify what components/modules need to be created\n"
                "- Outline the high-level approach for each cycle\n"
                "The Architect does NOT write actual implementation code - that's the Coder's job.\n\n"
                "**APPROVAL CRITERIA:**\n"
                "- APPROVE if the plan identifies the key components and files needed\n"
                "- APPROVE if the plan addresses the main requirements from SPEC.md\n"
                "- APPROVE if the plan follows a logical implementation order\n"
                "- Do NOT reject for lacking detailed implementation code - that's expected\n"
                "- REJECT only if the plan is missing critical architectural components or has major structural flaws\n\n"
                "Be pragmatic: A good architectural plan outlines WHAT to build and WHERE, not HOW to code it. "
                "If it covers the main components and structure, APPROVE it."
            )
        else:  # coder phase
            user_prompt = (
                f"Please audit the following IMPLEMENTATION PLAN against the requirements.\n\n"
                f"{context_str}\n"
                f"{plan_str}\n\n"
                "**IMPORTANT CONTEXT:**\n"
                "This is an IMPLEMENTATION PLAN from the Coder (Jules) for a SPECIFIC CYCLE.\n"
                "The Coder's job is to:\n"
                "- Implement the actual code for the components REQUIRED IN THIS CYCLE ONLY\n"
                "- Write tests and ensure functionality FOR THIS CYCLE'S FEATURES\n"
                "- Follow the architecture defined in the Architect phase\n\n"
                "**CRITICAL SCOPE LIMITATION:**\n"
                "- The context above includes 'CURRENT CYCLE: XX' - this defines which cycle you're reviewing\n"
                "- The SPEC.md and UAT.md files are for THIS SPECIFIC CYCLE ONLY\n"
                "- Do NOT require features from other cycles to be implemented in this plan\n"
                "- The plan should focus ONLY on what's specified in the provided SPEC.md\n"
                "- Future cycles will handle additional features - that's by design\n\n"
                "**APPROVAL CRITERIA:**\n"
                "- APPROVE if the plan covers the implementation steps for THIS CYCLE'S requirements (as defined in SPEC.md)\n"
                "- APPROVE if the plan includes testing and verification for THIS CYCLE'S features\n"
                "- APPROVE if the plan is technically sound and feasible\n"
                "- Do NOT reject for missing features that are not in THIS CYCLE'S SPEC.md\n"
                "- REJECT only if the plan is missing critical steps for THIS CYCLE or has major technical flaws\n\n"
                "Be pragmatic: A good implementation plan covers THIS CYCLE'S tasks thoroughly. "
                "If it addresses the requirements in the provided SPEC.md, APPROVE it."
            )

        try:
            result = await self.agent.run(user_prompt)
        except Exception as e:
            return PlanAuditResult(
                status="REJECTED",
                is_approved=False,
                reason=f"Audit process failed: {e}",
            )
        else:
            # pydantic-ai v1.32.0+ uses .data for structured result
            return result.data  # type: ignore
