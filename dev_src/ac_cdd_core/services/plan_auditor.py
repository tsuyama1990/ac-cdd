from typing import Any

from ac_cdd_core.config import settings
from ac_cdd_core.domain_models import PlanAuditResult
from pydantic_ai import Agent


class PlanAuditor:
    """
    Validates implementation plans against requirements using an AI agent.
    """

    def __init__(self, agent: Agent[Any, PlanAuditResult] | None = None) -> None:
        self.agent = agent or Agent(
            model=settings.agents.auditor_model,
            output_type=PlanAuditResult,
            system_prompt=(
                "You are an expert Software Architect and QA Auditor. "
                "Your job is to audit implementation plans against provided requirements."
            ),
        )

    async def audit_plan(
        self, plan_details: dict[str, Any], context_files: dict[str, str]
    ) -> PlanAuditResult:
        """
        Audits a plan against the requirements.
        """
        # Construct context
        context_str = "## Reference Requirements\n"
        for fname, content in context_files.items():
            context_str += f"### {fname}\n{content}\n\n"

        plan_str = f"## Proposed Plan\n{plan_details}"

        user_prompt = (
            f"Please audit the following plan against the requirements.\n\n"
            f"{context_str}\n"
            f"{plan_str}\n\n"
            "Evaluate if the plan covers all requirements and is technically sound."
        )

        try:
            result = await self.agent.run(user_prompt)
            # pydantic-ai v1.32.0+ uses .data for structured result
            return result.data  # type: ignore
        except Exception as e:
            return PlanAuditResult(
                status="REJECTED",
                is_approved=False,
                reason=f"Audit process failed: {e}",
            )
