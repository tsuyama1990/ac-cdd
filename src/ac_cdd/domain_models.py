from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FileArtifact(BaseModel):
    """生成・修正されたファイル単体"""
    model_config = ConfigDict(extra='forbid')
    path: str = Field(..., description="ファイルパス (例: dev_documents/CYCLE01/SPEC.md)")
    content: str = Field(..., description="ファイルの内容")
    language: str = Field("markdown", description="言語 (python, markdown, etc.)")

class CyclePlan(BaseModel):
    """計画フェーズの成果物一式"""
    model_config = ConfigDict(extra='forbid')
    spec_file: FileArtifact
    schema_file: FileArtifact
    uat_file: FileArtifact
    thought_process: str = Field(..., description="なぜこの設計にしたかの思考プロセス")

class AuditResult(BaseModel):
    """監査結果"""
    model_config = ConfigDict(extra='forbid')
    is_approved: bool
    critical_issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)

class UatAnalysis(BaseModel):
    """UAT実行結果の分析"""
    model_config = ConfigDict(extra='forbid')
    verdict: Literal["PASS", "FAIL"]
    summary: str
    behavior_analysis: str

class FileCreate(BaseModel):
    """New file creation"""
    model_config = ConfigDict(extra='forbid')
    operation: Literal["create"] = "create"
    path: str = Field(..., description="Path to the file to create")
    content: str = Field(..., description="Full content of the new file")

class FilePatch(BaseModel):
    """Existing file modification via patch"""
    model_config = ConfigDict(extra='forbid')
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
