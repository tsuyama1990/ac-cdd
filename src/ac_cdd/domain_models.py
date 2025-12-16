from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FileArtifact(BaseModel):
    """生成・修正されたファイル単体"""

    model_config = ConfigDict(extra="forbid")
    path: str = Field(..., description="ファイルパス (例: dev_documents/CYCLE01/SPEC.md)")
    content: str = Field(..., description="ファイルの内容")
    language: str = Field("markdown", description="言語 (python, markdown, etc.)")


class CyclePlan(BaseModel):
    """計画フェーズの成果物一式"""

    model_config = ConfigDict(extra="forbid")
    spec_file: FileArtifact
    schema_file: FileArtifact
    uat_file: FileArtifact
    thought_process: str = Field(..., description="なぜこの設計にしたかの思考プロセス")


class AuditResult(BaseModel):
    """監査結果"""

    model_config = ConfigDict(extra="forbid")
    is_approved: bool
    critical_issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class UatAnalysis(BaseModel):
    """UAT実行結果の分析"""

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
