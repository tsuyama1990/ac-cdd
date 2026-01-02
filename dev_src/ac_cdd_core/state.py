from typing import TypedDict
from pydantic import BaseModel, Field, field_validator

from .domain_models import AuditResult, CyclePlan, FileOperation, UatAnalysis

class CycleState(BaseModel):
    """LangGraph state for the development cycle."""

    # Required fields
    cycle_id: str

    # Committee State with validation
    current_auditor_index: int = Field(
        default=1, ge=1, description="Current auditor (1-based index)"
    )
    current_auditor_review_count: int = Field(
        default=1, ge=1, description="Current review count for this auditor"
    )
    iteration_count: int = Field(default=0, ge=0)

    # Session Persistence
    jules_session_name: str | None = None
    pr_url: str | None = None
    resume_mode: bool = False
    active_branch: str | None = None

    # Audit State
    audit_result: AuditResult | None = None
    audit_feedback: list[str] = Field(default_factory=list)
    audit_pass_count: int = 0
    audit_retries: int = 0
    audit_logs: str = ""

    # Test State
    test_logs: str = ""
    test_exit_code: int | None = None
    uat_analysis: UatAnalysis | None = None

    # Phase Tracking
    current_phase: str = "init"
    error: str | None = None
    # Add status explicitely to allow safe access
    status: str | None = None

    # Legacy/Optional Fields
    sandbox_id: str | None = None
    plan: CyclePlan | None = None
    code_changes: list[FileOperation] = Field(default_factory=list)
    loop_count: int = 0
    correction_history: list[str] = Field(default_factory=list)
    dry_run: bool = False
    interactive: bool = False
    goal: str | None = None
    approved: bool | None = None
    coder_report: dict | None = None
    planned_cycles: list[str] = Field(default_factory=list)

    # Session tracking
    session_id: str | None = None
    integration_branch: str | None = None
    is_session_finalized: bool = False

    # Architect Config
    planned_cycle_count: int | None = 5

    # Validators
    @field_validator("current_auditor_index")
    @classmethod
    def validate_auditor_index(cls, v: int) -> int:
        from .config import settings
        if v > settings.NUM_AUDITORS:
            raise ValueError(f"Auditor index {v} exceeds NUM_AUDITORS={settings.NUM_AUDITORS}")
        return v

    @field_validator("current_auditor_review_count")
    @classmethod
    def validate_review_count(cls, v: int) -> int:
        from .config import settings
        if v > settings.REVIEWS_PER_AUDITOR:
            raise ValueError(
                f"Review count {v} exceeds REVIEWS_PER_AUDITOR={settings.REVIEWS_PER_AUDITOR}"
            )
        return v

    def __getitem__(self, item):
        return getattr(self, item)

    def get(self, item, default=None):
        return getattr(self, item, default)

    class Config:
        extra = "allow"
        validate_assignment = True
