import os
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load environment variables from .env file
load_dotenv()

# Constants
PROMPT_FILENAME_MAP = {
    "auditor.md": "AUDITOR_INSTRUCTION.md",
    "coder.md": "CODER_INSTRUCTION.md",
    "architect.md": "ARCHITECT_INSTRUCTION.md",
}


def _detect_package_dir() -> str:
    """
    Detects the main package directory under /opt/ac_cdd/ac_cdd_core or dev_src/
    """
    # 1. Check Docker installed location
    docker_path = Path("/opt/ac_cdd/ac_cdd_core")
    if docker_path.exists():
        return str(docker_path)

    # 2. Check local dev location
    src_path = Path("dev_src")
    if src_path.exists():
        for p in src_path.iterdir():
            if p.is_dir() and (p / "__init__.py").exists():
                return str(p)

    return "dev_src/ac_cdd_core"


class PathsConfig(BaseModel):
    workspace_root: Path = Field(default_factory=Path.cwd)
    documents_dir: Path = Field(default_factory=lambda: Path.cwd() / "dev_documents")
    package_dir: str = Field(default_factory=_detect_package_dir)
    contracts_dir: str = ""
    sessions_dir: str = ".jules/sessions"
    src: Path = Field(default_factory=lambda: Path.cwd() / "src")
    tests: Path = Field(default_factory=lambda: Path.cwd() / "tests")
    templates: Path = Field(default_factory=lambda: Path.cwd() / "dev_documents" / "templates")
    # For local testing fallback
    prompts_dir: str = "dev_src/ac_cdd_core/prompts"

    @model_validator(mode="after")
    def _set_dependent_paths(self) -> "PathsConfig":
        if not self.contracts_dir:
            self.contracts_dir = f"{self.package_dir}/contracts"
        return self


class JulesConfig(BaseModel):
    executable: str = "jules"
    timeout_seconds: int = 7200
    polling_interval_seconds: int = 120
    base_url: str = "https://jules.googleapis.com/v1alpha"


class ToolsConfig(BaseModel):
    jules_cmd: str = "jules"
    gh_cmd: str = "gh"
    audit_cmd: str = "bandit"
    uv_cmd: str = "uv"
    mypy_cmd: str = "mypy"
    ruff_cmd: str = "ruff"
    gemini_cmd: str = "gemini"
    required_executables: list[str] = ["uv", "git"]


class SandboxConfig(BaseModel):
    """Configuration for E2B Sandbox execution"""

    template: str | None = None
    timeout: int = 7200
    cwd: str = "/home/user/project"
    dirs_to_sync: list[str] = ["src", "tests", "contracts", "dev_documents", "dev_src"]
    files_to_sync: list[str] = [
        "pyproject.toml",
        "uv.lock",
        ".auditignore",
        "README.md",
    ]
    install_cmd: str = "pip install --no-cache-dir ruff"
    test_cmd: list[str] = ["uv", "run", "pytest"]
    lint_check_cmd: list[str] = ["uv", "run", "ruff", "check", "--fix", "."]
    type_check_cmd: list[str] = ["uv", "run", "mypy", "src/"]
    security_check_cmd: list[str] = ["uv", "run", "bandit", "-r", "src/", "-ll"]


class AgentsConfig(BaseModel):
    # Models
    auditor_model: str
    qa_analyst_model: str


class ReviewerConfig(BaseModel):
    smart_model: str = Field(
        description="Model for editing code (Fixer)",
    )
    fast_model: str = Field(
        description="Model for reading/auditing code",
    )

    # Prompts are now loaded dynamically via methods on Settings,
    # as they depend on paths that might change.
    # We remove static prompt fields here to avoid confusion.


class SessionConfig(BaseModel):
    """Session-based development configuration."""

    session_id: str | None = None
    integration_branch_prefix: str = "dev"
    auto_merge_to_integration: bool = True
    final_merge_strategy: Literal["merge", "squash", "rebase"] = "squash"
    auto_delete_session_branches: bool = True


class Settings(BaseSettings):
    """
    Application settings, loaded from environment variables.
    Prefix: AC_CDD_
    """

    # Core settings
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
    MAX_ITERATIONS: int = 3

    # Constants
    filename_spec: str = "ALL_SPEC.md"
    filename_arch: str = "SYSTEM_ARCHITECTURE.md"
    max_audit_retries: int = 2
    required_env_vars: list[str] = ["JULES_API_KEY", "E2B_API_KEY"]
    default_cycles: list[str] = ["01", "02", "03", "04", "05"]
    architect_context_files: list[str] = [
        "ALL_SPEC.md",
        "SPEC.md",
        "UAT.md",
        "ARCHITECT_INSTRUCTION.md",
    ]

    # Nested Configurations
    session: SessionConfig = Field(default_factory=SessionConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    jules: JulesConfig = Field(default_factory=JulesConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    # AgentsConfig/ReviewerConfig have required fields, so no default_factory unless we mock it or allow empty.
    # Pydantic Settings will populate from env vars.
    agents: AgentsConfig
    reviewer: ReviewerConfig

    model_config = SettingsConfigDict(
        env_prefix="AC_CDD_",
        env_nested_delimiter="__",
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    @model_validator(mode="before")
    @classmethod
    def load_legacy_env_vars(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Check for legacy/global env vars and inject if missing from structured data
            smart = os.getenv("SMART_MODEL")
            fast = os.getenv("FAST_MODEL")

            # Load API Keys from unprefixed env vars
            for key in ["JULES_API_KEY", "OPENROUTER_API_KEY", "E2B_API_KEY"]:
                if key not in data or data[key] is None:
                    val = os.getenv(key)
                    if val:
                        data[key] = val

            if smart or fast:
                # Update Agents Config (default construct if missing)
                agents = data.get("agents", {})
                if not isinstance(agents, dict): agents = {}

                if smart and "auditor_model" not in agents:
                    agents["auditor_model"] = smart
                if fast and "qa_analyst_model" not in agents:
                    agents["qa_analyst_model"] = fast
                data["agents"] = agents

                # Update Reviewer Config
                reviewer = data.get("reviewer", {})
                if not isinstance(reviewer, dict): reviewer = {}

                if smart and "smart_model" not in reviewer:
                    reviewer["smart_model"] = smart
                if fast and "fast_model" not in reviewer:
                    reviewer["fast_model"] = fast
                data["reviewer"] = reviewer

        return data

    @property
    def current_session_id(self) -> str:
        """Get or generate session ID from timestamp with milliseconds."""
        if self.session.session_id:
            return self.session.session_id
        from datetime import datetime

        now = datetime.now()
        return f"session-{now.strftime('%Y%m%d-%H%M%S-%f')[:20]}"

    @property
    def integration_branch(self) -> str:
        return f"{self.session.integration_branch_prefix}/{self.current_session_id}/integration"

    def get_template(self, name: str) -> Path:
        """
        Resolve a template path.
        Priority:
        1. User override: /app/dev_documents/system_prompts/{name}
        2. System default: /opt/ac_cdd/templates/{name}
        3. Local dev fallback: ./dev_documents/system_prompts/{name}
        """
        # 1. User Override (Context)
        user_path = self.paths.documents_dir / "system_prompts" / name
        if user_path.exists():
            return user_path

        # 2. System Default (Docker)
        system_path = self.paths.templates / name
        if system_path.exists():
            return system_path

        # 3. Local Dev Fallback
        # dev_src/ac_cdd_core/config.py -> .../dev_documents/system_prompts
        local_dev_path = (
            Path(__file__).parent.parent.parent / "dev_documents" / "system_prompts" / name
        )
        if local_dev_path.exists():
            return local_dev_path

        # Return default path even if missing (let caller handle)
        return system_path

    def get_prompt_content(self, filename: str, default: str = "") -> str:
        """
        Reads prompt content using the logic that was previously in ac_cdd_config.py
        """
        target_filename = PROMPT_FILENAME_MAP.get(filename, filename)

        # Try to find the file
        path = self.get_template(target_filename)

        # If not found via template logic, check legacy/fallback locations if needed
        # But get_template covers User and System locations.

        if path.exists():
            return path.read_text(encoding="utf-8").strip()

        # Fallback: Check System Defaults (Fallback in source code)
        # This was in ac_cdd_config.py as dev_src/ac_cdd_core/prompts
        fallback_path = Path(self.paths.prompts_dir) / filename
        if fallback_path.exists():
            return fallback_path.read_text(encoding="utf-8").strip()

        return default

    def get_context_files(self) -> list[str]:
        """Auditor/Coderにとっての参照専用ファイル(仕様書)のパスリスト"""
        p = self.paths.documents_dir
        if not p.exists():
            # Fallback for local testing
            p = Path.cwd() / "dev_documents"

        if p.exists():
            return [str(f) for f in p.glob("*.md")]
        return []

    def get_target_files(self) -> list[str]:
        """Auditor/Coderにとっての編集対象ファイル(コード)のパスリスト"""
        targets = []

        src = self.paths.src
        if not src.exists():
            src = Path.cwd() / "src"

        tests = self.paths.tests
        if not tests.exists():
            tests = Path.cwd() / "tests"

        if src.exists():
            targets.extend([str(p) for p in src.rglob("*.py")])

        if tests.exists():
            targets.extend([str(p) for p in tests.rglob("*.py")])

        return targets


# Global settings object
settings = Settings()  # type: ignore[call-arg]
