import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load environment variables from .env file
# Priority: .ac_cdd/.env > .env (root)
_ac_cdd_env = Path.cwd() / ".ac_cdd" / ".env"
_root_env = Path.cwd() / ".env"

try:
    if _ac_cdd_env.exists():
        load_dotenv(_ac_cdd_env, override=True)
    elif _root_env.exists():
        load_dotenv(_root_env, override=True)
    else:
        load_dotenv()  # Try default locations
except Exception:
    # If environment loading fails (e.g. in strict docker envs), continue
    # The application will handle missing keys later if they are actually needed
    import logging

    logging.debug("Environment loading failed, will use defaults")

# Constants
PROMPT_FILENAME_MAP = {
    "auditor.md": "AUDITOR_INSTRUCTION.md",
    "coder.md": "CODER_INSTRUCTION.md",
    "architect.md": "ARCHITECT_INSTRUCTION.md",
}


def _detect_package_dir() -> str:
    """Detects the main package directory."""
    docker_path = Path("/opt/ac_cdd/ac_cdd_core")
    if docker_path.exists():
        return str(docker_path)

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
    wait_for_pr_timeout_seconds: int = 900


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
    auditor_model: str = "claude-3-5-sonnet"
    qa_analyst_model: str = "claude-3-5-sonnet"


class ReviewerConfig(BaseModel):
    smart_model: str = Field(
        default="claude-3-5-sonnet",
        description="Model for editing code (Fixer)",
    )
    fast_model: str = Field(
        default="claude-3-5-sonnet",
        description="Model for reading/auditing code",
    )


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
    """

    JULES_API_KEY: str | None = None
    OPENROUTER_API_KEY: str | None = None
    MAX_RETRIES: int = 10
    GRAPH_RECURSION_LIMIT: int = 200
    DUMMY_CYCLE_ID: str = "00"
    E2B_API_KEY: str | None = None

    GCP_PROJECT_ID: str | None = None
    GCP_REGION: str = "us-central1"

    NUM_AUDITORS: int = 3
    REVIEWS_PER_AUDITOR: int = 2
    MAX_ITERATIONS: int = 3

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

    session: SessionConfig = Field(default_factory=SessionConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    jules: JulesConfig = Field(default_factory=JulesConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    reviewer: ReviewerConfig = Field(default_factory=ReviewerConfig)

    # Auditor model selection: "smart" or "fast"
    AUDITOR_MODEL_MODE: Literal["smart", "fast"] = "fast"

    model_config = SettingsConfigDict(
        env_prefix="AC_CDD_",
        env_nested_delimiter="__",
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    @model_validator(mode="before")
    @classmethod
    def load_legacy_env_vars(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Inject legacy/global env vars if missing from structured data."""
        smart = os.getenv("SMART_MODEL")
        fast = os.getenv("FAST_MODEL")

        for key in ["JULES_API_KEY", "OPENROUTER_API_KEY", "E2B_API_KEY"]:
            if (key not in data or data[key] is None) and (val := os.getenv(key)):
                data[key] = val

        if smart or fast:
            cls._update_agents_config(data, smart, fast)
            cls._update_reviewer_config(data, smart, fast)

        return data

    @classmethod
    def _update_agents_config(
        cls, data: dict[str, Any], smart: str | None, _fast: str | None
    ) -> None:
        agents = data.get("agents", {})
        if not isinstance(agents, dict):
            agents = {}
        # Use SMART_MODEL for both auditor and QA analyst (critical tasks)
        if smart and "auditor_model" not in agents:
            agents["auditor_model"] = smart
        if smart and "qa_analyst_model" not in agents:
            agents["qa_analyst_model"] = smart
        data["agents"] = agents

    @classmethod
    def _update_reviewer_config(
        cls, data: dict[str, Any], smart: str | None, fast: str | None
    ) -> None:
        reviewer = data.get("reviewer", {})
        if not isinstance(reviewer, dict):
            reviewer = {}
        if smart and "smart_model" not in reviewer:
            reviewer["smart_model"] = smart
        if fast and "fast_model" not in reviewer:
            reviewer["fast_model"] = fast
        data["reviewer"] = reviewer

    @property
    def current_session_id(self) -> str:
        """Get or generate session ID."""
        if self.session.session_id:
            return self.session.session_id
        now = datetime.now(UTC)
        return f"session-{now.strftime('%Y%m%d-%H%M%S-%f')[:20]}"

    @property
    def integration_branch(self) -> str:
        return f"{self.session.integration_branch_prefix}/{self.current_session_id}/integration"

    def get_template(self, name: str) -> Path:
        """Resolve a template path."""
        user_path = self.paths.documents_dir / "system_prompts" / name
        if user_path.exists():
            return user_path

        system_path = self.paths.templates / name
        if system_path.exists():
            return system_path

        local_dev_path = (
            Path(__file__).parent.parent.parent / "dev_documents" / "system_prompts" / name
        )
        if local_dev_path.exists():
            return local_dev_path

        return system_path

    def get_prompt_content(self, filename: str, default: str = "") -> str:
        """Reads prompt content."""
        target_filename = PROMPT_FILENAME_MAP.get(filename, filename)
        path = self.get_template(target_filename)

        if path.exists():
            return path.read_text(encoding="utf-8").strip()

        fallback_path = Path(self.paths.prompts_dir) / filename
        if fallback_path.exists():
            return fallback_path.read_text(encoding="utf-8").strip()

        return default

    def get_context_files(self) -> list[str]:
        p = self.paths.documents_dir
        if not p.exists():
            p = Path.cwd() / "dev_documents"

        # Explicitly look for the main spec file only
        # User feedback: "ALL_SPEC.md だけでいいんじゃない？" - Strict filtering prevents noise
        spec_file = p / self.filename_spec
        if spec_file.exists():
            return [str(spec_file)]

        # Fallback: if main spec missing, include all MDs (legacy behavior)
        if p.exists():
            return [str(f) for f in p.glob("*.md")]
        return []

    def get_target_files(self) -> list[str]:
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
settings = Settings()
