from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CycleStatus = Literal["planned", "in_progress", "review_fix", "completed", "failed"]


class CycleManifest(BaseModel):
    """Manifest for a single development cycle."""

    model_config = ConfigDict(extra="forbid")

    id: str
    status: CycleStatus = "planned"
    branch_name: str | None = None
    # Resume-critical field
    jules_session_id: str | None = Field(default=None, description="Active AI session ID")
    current_iteration: int = 1
    pr_url: str | None = None
    last_error: str | None = None
    # Session restart tracking
    session_restart_count: int = Field(
        default=0, description="Number of session restarts attempted"
    )
    max_session_restarts: int = Field(default=2, description="Maximum allowed session restarts")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProjectManifest(BaseModel):
    """Root manifest for the entire project state."""

    model_config = ConfigDict(extra="forbid")

    project_session_id: str
    feature_branch: str | None = None  # Main development branch (feat/generate-architecture-*)
    integration_branch: str  # Final integration branch (for finalize-session)
    qa_session_id: str | None = Field(
        default=None, description="Active QA/Tutorial Generation Session ID"
    )
    cycles: list[CycleManifest] = Field(default_factory=list)
    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FileArtifact(BaseModel):
    """Generated or modified file artifact"""

    model_config = ConfigDict(extra="forbid")
    path: str = Field(..., description="File path (e.g. dev_documents/CYCLE01/SPEC.md)")
    content: str = Field(..., description="File content")
    language: str = Field("markdown", description="Language (python, markdown, etc.)")


class CyclePlan(BaseModel):
    """Planning phase artifacts"""

    model_config = ConfigDict(extra="forbid")
    spec_file: FileArtifact
    schema_file: FileArtifact
    uat_file: FileArtifact
    thought_process: str = Field(..., description="Thought process behind the design")


class ReviewIssue(BaseModel):
    """個別の指摘事項"""

    model_config = ConfigDict(extra="forbid")

    category: Literal[
        "Hardcoding",
        "Scalability",
        "Security",
        "Architecture",
        "Type Safety",
        "Logic Error",
        "Other",
    ] = Field(description="Issue category. Be highly sensitive to 'Hardcoding'.")
    severity: Literal["fatal", "warning"] = Field(
        description="'fatal' MUST be used for SPEC violations and Hardcoding. 'warning' is for non-blocking boy-scout suggestions."
    )
    file_path: str = Field(description="Exact file path where the issue is found.")
    target_code_snippet: str = Field(
        description="The specific snippet of code containing the issue (1-3 lines max) to help the Coder locate it via string search."
    )
    issue_description: str = Field(
        description="Clear and concise description of why this is an issue."
    )
    concrete_fix: str = Field(
        description="EXACT code or structural change required. For 'Hardcoding', explicitly state WHERE to move the constant."
    )


class AuditorReport(BaseModel):
    """レポート全体"""

    model_config = ConfigDict(extra="forbid")

    is_passed: bool = Field(
        description="Must be False if there is at least one 'fatal' issue. Set to True ONLY if there is zero 'fatal' issue."
    )
    summary: str = Field(description="Brief 2-3 sentence summary of the review.")
    fatal_issues: list[ReviewIssue] = Field(
        default_factory=list,
        description="Critical issues that MUST be fixed. You MUST include any Hardcoding of URLs, API keys, paths, or magic numbers here.",
    )
    future_suggestions: list[ReviewIssue] = Field(default_factory=list)


class AuditResult(BaseModel):
    """Audit result"""

    model_config = ConfigDict(extra="forbid")
    status: str | None = None
    is_approved: bool = False
    reason: str | None = None
    feedback: str | None = None
    critical_issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class UatAnalysis(BaseModel):
    """UAT execution analysis"""

    model_config = ConfigDict(extra="forbid")
    verdict: Literal["PASS", "FAIL"]
    summary: str
    behavior_analysis: str


class FileCreate(BaseModel):
    """New file creation"""

    model_config = ConfigDict(extra="forbid")
    operation: Literal["create"] = "create"
    path: str = Field(..., description="Path to the file to create")
    content: str = Field(..., description="Full content of the new file")


class FilePatch(BaseModel):
    """Existing file modification via patch"""

    model_config = ConfigDict(extra="forbid")
    operation: Literal["patch"] = "patch"
    path: str = Field(..., description="Path to the file to modify")
    search_block: str = Field(
        ...,
        description="Exact block of code to search for (must match original file exactly)",
    )
    replace_block: str = Field(
        ..., description="New block of code to replace the search block with"
    )


FileOperation = FileCreate | FilePatch


# --- Spec Structuring Models ---


class Feature(BaseModel):
    name: str
    description: str
    priority: Literal["High", "Medium", "Low"]
    acceptance_criteria: list[str]


class TechnicalConstraint(BaseModel):
    category: str
    description: str


class StructuredSpec(BaseModel):
    """Structured representation of ALL_SPEC.md"""

    project_name: str
    version: str = "1.0.0"
    overview: str = Field(..., description="Executive summary of the project")
    goals: list[str] = Field(..., description="Primary business/learning goals")
    architecture_overview: str = Field(..., description="High-level system design")
    features: list[Feature] = Field(..., description="Initial backlog of features")
    constraints: list[TechnicalConstraint] = Field(default_factory=list)
    terminology: dict[str, str] = Field(default_factory=dict, description="Domain glossary")


# --- System Architecture Models ---


class SystemArchitecture(BaseModel):
    """
    High-level System Architecture Design.
    Generated by Structurer Agent from raw requirements.
    """

    model_config = ConfigDict(extra="forbid")

    project_name: str = Field(..., description="Name of the project")
    background: str = Field(..., description="Project background and context")
    core_philosophy: str = Field(
        ..., description="Core design philosophy (e.g., minimalist, robust, rapid)"
    )
    user_stories: list[str] = Field(..., description="High-level user stories")
    system_design: str = Field(..., description="Overall system design and architecture pattern")
    module_structure: str = Field(
        ..., description="Breakdown of key modules and responsibilities (hierarchical or list)"
    )
    tech_stack: list[str] = Field(..., description="List of technologies and libraries to be used")
    implementation_roadmap: list[str] = Field(..., description="Step-by-step implementation phases")


class PlanAuditResult(BaseModel):
    """Result of AI-on-AI Plan Audit"""

    model_config = ConfigDict(extra="forbid")
    status: Literal["APPROVED", "REJECTED"]
    reason: str
    feedback: str | None = Field(default="", description="Mandatory if REJECTED")
