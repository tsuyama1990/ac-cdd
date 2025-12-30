from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

load_dotenv()  # Explicitly load .env into os.environ

from pydantic import BaseModel, Field, model_validator  # noqa: E402
from pydantic_settings import BaseSettings, SettingsConfigDict  # noqa: E402


def _detect_package_dir() -> str:
    """
    Detects the main package directory under dev_src/.
    Looks for the first directory containing __init__.py.
    """
    src_path = Path("dev_src")
    if src_path.exists():
        for p in src_path.iterdir():
            if p.is_dir() and (p / "__init__.py").exists():
                return str(p)
    return "dev_src/ac_cdd_core"


PROMPT_FILENAME_MAP = {
    "auditor.md": "AUDITOR_INSTRUCTION.md",
    "coder.md": "CODER_INSTRUCTION.md",
    "architect.md": "ARCHITECT_INSTRUCTION.md",
    "planner.md": "CYCLE_PLANNING_PROMPT.md",
}


def _read_prompt(filename: str, default: str) -> str:
    # 1. Map legacy filenames to new template names
    target_filename = PROMPT_FILENAME_MAP.get(filename, filename)

    # 2. Check User Templates (Priority 1: Mapped Name)
    user_template_mapped = Path("dev_documents/templates") / target_filename
    if user_template_mapped.exists():
        return user_template_mapped.read_text(encoding="utf-8").strip()

    # 3. Check User Templates (Priority 2: Direct Name)
    user_template_direct = Path("dev_documents/templates") / filename
    if user_template_direct.exists():
        return user_template_direct.read_text(encoding="utf-8").strip()

    # 4. Check System Defaults (Fallback)
    system_prompt = Path("dev_src/ac_cdd_core/prompts") / filename
    if system_prompt.exists():
        return system_prompt.read_text(encoding="utf-8").strip()

    return default


class PathsConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    documents_dir: str = "dev_documents"
    package_dir: str = Field(default_factory=_detect_package_dir)
    contracts_dir: str = ""
    sessions_dir: str = ".jules/sessions"
    src: str = "src"
    tests: str = "tests"
    templates: str = "dev_documents/templates"
    property_tests: str = "tests/property"
    unit_tests: str = "tests/unit"
    e2e_tests: str = "tests/e2e"
    # New: Prompts directory path
    prompts_dir: str = "dev_src/ac_cdd_core/prompts"

    @model_validator(mode="after")
    def _set_dependent_paths(self) -> "PathsConfig":
        if not self.contracts_dir:
            self.contracts_dir = f"{self.package_dir}/contracts"
        return self


class JulesConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    # Default to regular command name 'jules'
    executable: str = "jules"
    timeout_seconds: int = 7200
    polling_interval_seconds: int = 120


class ToolsConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    jules_cmd: str = "jules"
    gh_cmd: str = "gh"
    audit_cmd: str = "bandit"
    uv_cmd: str = "uv"
    mypy_cmd: str = "mypy"
    ruff_cmd: str = "ruff"
    gemini_cmd: str = "gemini"
    jules_base_url: str = "https://jules.googleapis.com/v1alpha"


class SandboxConfig(BaseSettings):
    """Configuration for E2B Sandbox execution"""

    model_config = SettingsConfigDict(extra="ignore")
    template: str | None = None  # None uses default (base)
    timeout: int = 3600  # Default timeout in seconds (increased to 2 hours)
    cwd: str = "/home/user/project"
    dirs_to_sync: list[str] = ["src", "tests", "contracts", "dev_documents", "dev_src"]
    files_to_sync: list[str] = [
        "pyproject.toml",
        "uv.lock",
        ".auditignore",
        "README.md",
        "ac_cdd_config.py",
    ]
    install_cmd: str = "pip install --no-cache-dir ruff"
    test_cmd: list[str] = ["uv", "run", "pytest"]
    lint_check_cmd: list[str] = ["uv", "run", "ruff", "check", "--fix", "."]
    type_check_cmd: list[str] = ["uv", "run", "mypy", "src/"]
    security_check_cmd: list[str] = ["uv", "run", "bandit", "-r", "src/", "-ll"]


class AgentsConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    # Models
    auditor_model: str = Field(
        default="openrouter/google/gemini-pro-1.5", validation_alias="SMART_MODEL"
    )
    qa_analyst_model: str = Field(
        default="openrouter/google/gemini-flash-1.5", validation_alias="FAST_MODEL"
    )


class ReviewerConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    smart_model: str = Field(
        default="claude-3-5-sonnet",
        description="Model for editing code (Fixer)",
        validation_alias="SMART_MODEL",
    )
    fast_model: str = Field(
        default="openrouter/google/gemini-flash-1.5",
        description="Model for reading/auditing code",
        validation_alias="FAST_MODEL",
    )

    # Prompts (Content loaded via _read_prompt)
    auditor: str = Field(
        default_factory=lambda: _read_prompt("auditor.md", "DEFAULT_AUDITOR_PROMPT")
    )
    qa_analyst: str = Field(
        default_factory=lambda: _read_prompt("qa_analyst.md", "DEFAULT_QA_ANALYST_PROMPT")
    )


class PromptsConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    property_test_template: str = Field(
        default_factory=lambda: _read_prompt("property_test_template.md", "DEFAULT_TEST_PROMPT")
    )
    # Explicit file path reference as requested
    structurer: str = Field(
        default_factory=lambda: _read_prompt("structurer.md", "DEFAULT_STRUCTURER_PROMPT")
    )


class Settings(BaseSettings):
    JULES_API_KEY: str | None = None
    OPENROUTER_API_KEY: str | None = None
    MAX_RETRIES: int = 10
    DUMMY_CYCLE_ID: str = "00"
    E2B_API_KEY: str | None = None

    # GCP Config for Jules API
    GCP_PROJECT_ID: str | None = None
    GCP_REGION: str = "us-central1"

    # Committee Config
    NUM_AUDITORS: int = 3
    REVIEWS_PER_AUDITOR: int = 2
    MAX_ITERATIONS: int = 3  # Fixed Iteration Mode

    # Session Config
    class SessionConfig(BaseModel):
        """Session-based development configuration."""

        # Session ID (auto-generated from timestamp if None)
        session_id: str | None = None

        # Integration branch settings
        integration_branch_prefix: str = "dev"
        auto_merge_to_integration: bool = True

        # Final merge settings
        final_merge_strategy: Literal["merge", "squash", "rebase"] = "squash"
        auto_delete_session_branches: bool = True

    session: SessionConfig = Field(default_factory=SessionConfig)

    paths: PathsConfig = PathsConfig()
    jules: JulesConfig = JulesConfig()
    tools: ToolsConfig = ToolsConfig()
    sandbox: SandboxConfig = SandboxConfig()
    agents: AgentsConfig = AgentsConfig()
    reviewer: ReviewerConfig = ReviewerConfig()
    prompts: PromptsConfig = PromptsConfig()

    # Computed Properties
    @property
    def current_session_id(self) -> str:
        """Get or generate session ID from timestamp with milliseconds."""
        if self.session.session_id:
            return self.session.session_id
        # Generate from timestamp with milliseconds to prevent collisions
        from datetime import datetime

        now = datetime.now()
        return f"session-{now.strftime('%Y%m%d-%H%M%S-%f')[:20]}"  # YYYYMMDD-HHMMSS-mmm

    @property
    def integration_branch(self) -> str:
        """Get integration branch name for current session."""
        return f"{self.session.integration_branch_prefix}/{self.current_session_id}/integration"

    # Model Config
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="allow")


config = Settings()
