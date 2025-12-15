import tomllib
from pathlib import Path

from pydantic import ConfigDict, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _detect_package_dir() -> str:
    """
    Detects the main package directory under src/.
    Looks for the first directory containing __init__.py.
    """
    src_path = Path("src")
    if src_path.exists():
        for p in src_path.iterdir():
            if p.is_dir() and (p / "__init__.py").exists():
                return str(p)
    # Fallback to standard conventions or strict default
    return "src/ac_cdd"

class PathsConfig(BaseSettings):
    model_config = ConfigDict(extra="ignore")
    documents_dir: str = "dev_documents"

    # Dynamic package detection
    package_dir: str = Field(default_factory=_detect_package_dir)

    # Dependent defaults (handled in validator)
    contracts_dir: str = ""

    sessions_dir: str = ".jules/sessions"
    src: str = "src"
    tests: str = "tests"
    templates: str = "dev_documents/templates"

    @model_validator(mode="after")
    def _set_dependent_paths(self) -> "PathsConfig":
        if not self.contracts_dir:
            self.contracts_dir = f"{self.package_dir}/contracts"
        return self

class ToolsConfig(BaseSettings):
    model_config = ConfigDict(extra="ignore")
    jules_cmd: str = "jules"
    gh_cmd: str = "gh"
    audit_cmd: str = "bandit"
    uv_cmd: str = "uv"
    mypy_cmd: str = "mypy"
    gemini_cmd: str = "gemini"
    jules_base_url: str = "https://jules.googleapis.com/v1alpha"

class AgentsConfig(BaseSettings):
    model_config = ConfigDict(extra="ignore")
    architect: str = "DEFAULT_ARCHITECT_PROMPT"
    coder: str = "DEFAULT_CODER_PROMPT"
    tester: str = "DEFAULT_TESTER_PROMPT"
    auditor: str = "DEFAULT_AUDITOR_PROMPT"
    qa_analyst: str = "DEFAULT_QA_ANALYST_PROMPT"

class PromptsConfig(BaseSettings):
    model_config = ConfigDict(extra="ignore")
    property_test_template: str = "DEFAULT_TEST_PROMPT"

class Settings(BaseSettings):
    MAX_RETRIES: int = 10

    paths: PathsConfig = PathsConfig()
    tools: ToolsConfig = ToolsConfig()
    agents: AgentsConfig = AgentsConfig()
    prompts: PromptsConfig = PromptsConfig()

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @classmethod
    def load_from_toml(cls, toml_path: str = "ac_cdd.toml") -> "Settings":
        # Load from toml manually since pydantic-settings generic support
        # is often via extra dependencies or specific source classes.
        # Here we mix environment variables (default behavior) with TOML values.

        # Initialize with defaults/env vars
        settings = cls()

        path = Path(toml_path)
        if path.exists():
            with open(path, "rb") as f:
                data = tomllib.load(f)

            # Update nested models if keys exist in TOML
            if "paths" in data:
                settings.paths = PathsConfig(**data["paths"])
            if "tools" in data:
                settings.tools = ToolsConfig(**data["tools"])
            if "agents" in data:
                settings.agents = AgentsConfig(**data["agents"])
            if "prompts" in data:
                settings.prompts = PromptsConfig(**data["prompts"])

        return settings

settings = Settings.load_from_toml()
