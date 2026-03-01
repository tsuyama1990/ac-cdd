"""State model for Jules session management using LangGraph."""

from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, Field


def add_set(a: set[str] | None, b: set[str] | None) -> set[str]:
    a = a or set()
    b = b or set()
    return a | b


class SessionStatus(str, Enum):
    MONITORING = "monitoring"
    INQUIRY_DETECTED = "inquiry_detected"
    ANSWERING_INQUIRY = "answering_inquiry"
    VALIDATING_COMPLETION = "validating_completion"
    CHECKING_PR = "checking_pr"
    REQUESTING_PR_CREATION = "requesting_pr_creation"
    WAITING_FOR_PR = "waiting_for_pr"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


class JulesSessionState(BaseModel):
    """State for managing Jules session lifecycle with LangGraph."""

    # Session identification
    session_url: str = Field(default="")
    session_name: str = Field(default="unknown")
    status: SessionStatus = SessionStatus.MONITORING

    # Jules API state
    jules_state: str | None = None
    previous_jules_state: str | None = None

    # Activity tracking
    processed_activity_ids: Annotated[set[str], add_set] = Field(default_factory=set)
    processed_completion_ids: Annotated[set[str], add_set] = Field(default_factory=set)
    processed_inquiry_ids: Annotated[set[str], add_set] = Field(default_factory=set)
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
    processed_fallback_ids: Annotated[set[str], add_set] = Field(default_factory=set)

    # Timing
    start_time: float = 0.0
    timeout_seconds: float = 7200.0
    poll_interval: float = 120.0

    # Result
    error: str | None = None
    raw_data: dict[str, Any] | None = None

    # Flags for routing decisions
    has_recent_activity: bool = False
    completion_validated: bool = False

    # Stale (silent) Jules detection
    last_jules_state_change_time: float = 0.0  # loop time when jules_state last changed
    stale_nudge_count: int = 0                 # how many nudges we have already sent
