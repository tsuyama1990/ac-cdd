from enum import Enum


class WorkPhase(str, Enum):
    INIT = "init"
    ARCHITECT = "architect"
    ARCHITECT_DONE = "architect_done"
    CODER = "coder"
    REFACTORING = "refactoring"
    QA = "qa"


class FlowStatus(str, Enum):
    # Common
    FAILED = "failed"
    COMPLETED = "completed"
    END = "end"

    # Architect
    ARCHITECT_COMPLETED = "architect_completed"
    ARCHITECT_FAILED = "architect_failed"

    # Coder / Session
    READY_FOR_AUDIT = "ready_for_audit"
    CODER_RETRY = "coder_retry"
    RETRY_FIX = "retry_fix"
    WAIT_FOR_JULES_COMPLETION = "wait_for_jules_completion"

    # Auditor / Committee
    APPROVED = "approved"
    REJECTED = "rejected"
    WAITING_FOR_JULES = "waiting_for_jules"
    NEXT_AUDITOR = "next_auditor"
    CYCLE_APPROVED = "cycle_approved"

    # UAT & Refactor
    START_REFACTOR = "start_refactor"
    
    # QA
    MAX_RETRIES = "max_retries"
