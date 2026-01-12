"""State model for Jules session management using LangGraph."""

from typing import Any, Literal

from pydantic import BaseModel, Field

JulesSessionStatus = Literal[
    "monitoring",
    "inquiry_detected",
    "answering_inquiry",
    "validating_completion",
    "checking_pr",
    "requesting_pr_creation",
    "waiting_for_pr",
    "success",
    "failed",
    "timeout",
]


class JulesSessionState(BaseModel):
    """State for managing Jules session lifecycle with LangGraph."""

    # Session identification
    session_url: str
    session_name: str
    status: JulesSessionStatus = "monitoring"

    # Jules API state
    jules_state: str | None = None

    # Activity tracking
    processed_activity_ids: set[str] = Field(default_factory=set)
    last_activity_count: int = 0

    # Inquiry handling
    current_inquiry: str | None = None
    current_inquiry_id: str | None = None

    # Plan approval
    plan_rejection_count: int = 0
    max_plan_rejections: int = 2
    require_plan_approval: bool = False

    # PR tracking
    pr_url: str | None = None

    # Fallback PR creation tracking
    fallback_elapsed_seconds: int = 0
    fallback_max_wait: int = 900
    processed_fallback_ids: set[str] = Field(default_factory=set)

    # Timing
    start_time: float = 0.0
    timeout_seconds: int = 7200
    poll_interval: int = 120

    # Result
    error: str | None = None
    raw_data: dict[str, Any] | None = None

    # Flags for routing decisions
    has_recent_activity: bool = False
    completion_validated: bool = False
