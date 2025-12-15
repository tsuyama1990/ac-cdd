# 🦋 Refactoring Mission: Migrate to Pydantic AI

## 1. Objective (目的)
現在の「自前HTTPクライアント + 正規表現パース」による不安定な実装を廃止し、Google推奨の **`pydantic-ai` フレームワーク** に完全移行します。
これにより、型安全性、構造化出力の強制、および可観測性（Logfire）を確保し、商用グレードの堅牢なシステムへ昇華させます。

---

## 2. Tasks (実行タスク)

以下の手順でコードベースを修正してください。破壊的変更を含むため、各ステップで整合性を確認すること。

### Task 1: 依存関係の更新
**Target:** `pyproject.toml`
* `dependencies` に以下を追加してください。
    * `"pydantic-ai>=0.0.18"`
    * `"logfire>=2.0.0"`
    * `"devtools"`
* `google-genai` は `pydantic-ai` が内部で使用するため、明示的な依存として残すか、`pydantic-ai` の依存に任せてください。

### Task 2: ドメインモデルの定義 (New File)
**Create:** `src/ac_cdd/domain_models.py`
* AIとの入出力「契約」となる Pydantic モデルを定義してください。
```python
from typing import Literal
from pydantic import BaseModel, Field

class FileArtifact(BaseModel):
    """生成・修正されたファイル単体"""
    path: str = Field(..., description="ファイルパス (例: dev_documents/CYCLE01/SPEC.md)")
    content: str = Field(..., description="ファイルの内容")
    language: str = Field("markdown", description="言語 (python, markdown, etc.)")

class CyclePlan(BaseModel):
    """計画フェーズの成果物一式"""
    spec_file: FileArtifact
    schema_file: FileArtifact
    uat_file: FileArtifact
    thought_process: str = Field(..., description="なぜこの設計にしたかの思考プロセス")

class AuditResult(BaseModel):
    """監査結果"""
    is_approved: bool
    critical_issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)

class UatAnalysis(BaseModel):
    """UAT実行結果の分析"""
    verdict: Literal["PASS", "FAIL"]
    summary: str
    behavior_analysis: str
```

### Task 3: エージェント定義 (New File)
**Create:** `src/ac_cdd/agents.py`
 * 各役割（Planner, Coder, Auditor, QA）ごとの pydantic_ai.Agent を定義してください。
 * モデル: 'google-gla:gemini-2.0-flash-exp' (または最新のGeminiモデル) を使用。
available models
LatestGoogleModelNames = Literal[
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-flash-preview-09-2025",
    "gemini-2.5-flash-image",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash-lite-preview-09-2025",
    "gemini-2.5-pro",
    "gemini-3-pro-preview",
    "gemini-3-pro-image-preview",
]

 * System Prompt: config.py から読み込むのではなく、デコレータ @agent.system_prompt を使用して、動的にコンテキスト（ALL_SPEC.md 等）を注入できる設計にしてください。

### Task 4: Orchestratorの全面書き換え
**Target:** `src/ac_cdd/orchestrator.py`
 * 既存の JulesApiClient, GeminiApiClient の使用を 全廃 してください。
 * 代わりに src/ac_cdd/agents.py で定義したAgentを使用してください。
 * 非同期化: plan_cycle, run_strict_audit などのメソッドを async に変更し、await agent.run(...) で実行してください。
 * 構造化出力: result_type=CyclePlan などを指定し、正規表現パースロジック（_parse_and_save_plan）を削除してください。AIが生成したオブジェクトをそのまま利用してください。

### Task 5: CLIの更新と非同期対応
**Target:** `src/ac_cdd/cli.py`
 * orchestrator.py のメソッドが async になるため、typer コマンド内で import asyncio; asyncio.run(...) を使用して呼び出すように変更してください。
 * audit, fix コマンドも、clients.py ではなく新しい agents.py のエージェントを使用するように書き換えてください。

### Task 6: レガシーコードの削除 (Cleanup)
以下のファイルは不要になるため、削除してください。
 * src/ac_cdd/jules_api_client.py
 * src/ac_cdd/gemini_api_client.py
 * src/ac_cdd/clients.py
 * src/ac_cdd/agent_interface.py (Pydantic AIのAgentがインターフェースとなるため不要)

## 3. Implementation Guidelines (実装ガイドライン)
 * Dependency Injection: ファイルパスや設定値は、RunContext (pydantic_ai の機能) を通じてエージェントに渡す設計にすると、テストが容易になります。
 * Error Handling: pydantic_ai はバリデーションエラー時に自動でリトライするため、複雑な try-except ループは削除して構いません。
 * Logfire: import logfire; logfire.configure() を main.py または cli.py の冒頭に追加し、可観測性を有効化してください。

## 4. Final Verification
 * uv sync を実行し、依存関係を解決すること。
 * uv run manage.py doctor が正常に通ることを確認すること。
