from typing import Dict, Any
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
import tomllib

class PathsConfig(BaseSettings):
    documents_dir: str = "documents"
    contracts_dir: str = "src/ac_cdd/contracts"
    sessions_dir: str = ".jules/sessions"

class ToolsConfig(BaseSettings):
    jules_cmd: str = "jules"
    gh_cmd: str = "gh"
    audit_cmd: str = "bandit"
    uv_cmd: str = "uv"
    mypy_cmd: str = "mypy"
    gemini_cmd: str = "gemini"

class PromptsConfig(BaseSettings):
    auditor_system: str
    property_test_template: str

class Settings(BaseSettings):
    MAX_RETRIES: int = 10

    paths: PathsConfig = PathsConfig()
    tools: ToolsConfig = ToolsConfig()
    prompts: PromptsConfig = PromptsConfig(
        auditor_system="DEFAULT_AUDITOR_PROMPT",
        property_test_template="DEFAULT_TEST_PROMPT"
    )

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
            if "prompts" in data:
                settings.prompts = PromptsConfig(**data["prompts"])

        return settings

settings = Settings.load_from_toml()
