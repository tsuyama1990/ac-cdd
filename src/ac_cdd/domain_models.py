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
