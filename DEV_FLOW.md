
-----

# DESIGN\_FLOW.md

## AIネイティブ・サイクル分割型契約駆動開発 (AC-CDD) アーキテクチャ

**Version:** 1.0.0
**Status:** Active
**Author:** Architect (User) & AI Orchestrator

-----

## 1\. 開発哲学と目的 (Philosophy & Objectives)

本プロジェクトは、大規模言語モデル（LLM）の能力を最大限に引き出し、かつその弱点（幻覚、コンテキスト喪失、品質のばらつき）を構造的に排除するために設計された、次世代の開発フレームワークを採用する。

### 1.1 コア・プリンシプル (The Iron Triangle)

1.  **契約絶対主義 (Contract is King)**
    自然言語の仕様書は曖昧である。`Pydantic` スキーマによって定義された入出力構造（Contracts）のみを「実行可能な正解（Single Source of Truth）」とし、すべての実装はこの契約に従わなければならない。
2.  **権力の分立 (Separation of Powers)**
    「作るAI（Jules）」と「監査するAI（Gemini CLI）」を明確に分離し、対立構造（Adversarial）を作ることで、甘いコードやバグの混入を阻止する。
3.  **サイクル分割と自己修復 (Cyclic Self-Healing)**
    開発を管理可能な小さなサイクルに分割し、各サイクル内で「実装→テスト→監査→修正」のループを自律的に回すことで、人間の介入を承認プロセスのみに限定する。

-----

## 2\. ロールと責任 (Roles & Responsibilities)

| ロール | 担当エージェント | 責任範囲 |
| :--- | :--- | :--- |
| **Chief Architect** | **User** | プロジェクトの方向性決定、`ALL_SPEC.md` の策定、各サイクルの最終承認トリガー実行。 |
| **System Designer** | **Gemini Pro / Antigravity** | 要件定義、グランドデザイン、各サイクルの詳細仕様書 (`SPEC.md`) および契約 (`schema.py`) のドラフト作成。 |
| **Lead Developer** | **Jules (via API)** | 契約に基づく実装、ユニットテスト作成、UATコード生成、PR作成。 |
| **The Auditor** | **Gemini CLI** | "世界一厳格なコード監査人"。セキュリティ、可読性、設計原則の観点からコードを批判し、リジェクトする権限を持つ。 |
| **Orchestrator** | **Python Script (`manage.py`)** | 全エージェントの指揮、CIステータス監視、自動マージ実行、エラーハンドリング。 |

-----

## 3\. ディレクトリ構造と成果物 (Directory Structure & Artifacts)

本プロジェクトは以下のディレクトリ構造を厳守する。

```text
project/
├── manage.py                   # [User Entrypoint] サイクル制御CLI (Typer製)
├── pyproject.toml              # [Config] uv管理、Ruff/Mypy/Pytest設定
├── dev_documents/              # [Documentation] AIへのコンテキスト提供源
│   ├── ALL_SPEC.md             # [Constitution] 全体仕様・グランドデザイン
│   ├── CYCLE01/                # [Cycle Context] サイクルごとの独立した作業領域
│   │   ├── SPEC.md             # [Spec] 詳細仕様書
│   │   ├── UAT.md              # [Requirement] ユーザー受け入れ条件（自然言語）
│   │   ├── schema.py           # [Contract] このサイクルのPydantic定義 (Draft)
│   │   ├── IMPLEMENTATION.md   # [Log] Julesの実装思考ログ (Auto-generated)
│   │   └── AUDIT_LOG.md        # [Log] Gemini監査人の指摘ログ (Auto-generated)
│   └── CYCLE02/...
├── src/
│   ├── ac_cdd/
│   │   ├── contracts/          # [System Contract] システム全体で有効化された契約
│   │   │   └── __init__.py     # ここにあるモデルが絶対正義
│   │   └── orchestrator.py     # [Engine] 自動化ロジック本体
│   └── ...                     # 実装コード
├── tests/
│   ├── property/               # [PBT] Hypothesisによる自動生成テスト
│   └── e2e/                    # [UAT] PlaywrightによるE2Eテスト
```

-----

## 4\. 詳細ワークフロー (Detailed Workflow)

開発プロセスは以下の4つのフェーズで進行する。

### Phase 1: デザイン自動化 (Design Automation)

**主体:** User, Gemini Pro, Antigravity

1.  **憲法の制定**: Userは `dev_documents/ALL_SPEC.md` を作成し、システムの全体像を定義する。
2.  **サイクル計画**: Gemini Proは `ALL_SPEC.md` を読み込み、開発工程を `CYCLE01`, `CYCLE02`... に分割する。
3.  **詳細設計**: 各サイクルフォルダ内に以下のファイルを生成する。
      * `SPEC.md`: 実装レベルの詳細仕様。
      * `UAT.md`: 「何ができれば完了か」を定義するシナリオ。
      * `schema.py`: 入出力を定義する `Pydantic` モデル。**これが最も重要である。**
4.  **User承認**: Userは生成されたドキュメントを確認し、必要であれば修正指示を出す。

-----

### Phase 2: サイクル・トリガー (Cycle Trigger)

**主体:** User

デザインが固まったら、Userは以下のコマンドで「実装と監査の自動化」を開始する。

```bash
uv run manage.py start-cycle 01
```

これ以降、フェーズ4まで人間は基本的に介入しない（エラー発生時を除く）。

-----

### Phase 3: 自律的実装・監査ループ (Autonomous Implementation & Audit Loop)

**主体:** Orchestrator, Jules, Gemini CLI

Orchestratorは以下のステップを順次実行する。

#### Step 3.1: 契約の締結と再調整 (Contract Alignment)

  * `dev_documents/CYCLE{N}/schema.py` を読み込み、`src/ac_cdd/contracts/` 内の既存コードと整合性をチェックする。
  * 問題なければ `src/ac_cdd/contracts/` にマージし、システム全体の「新しい正解」としてコミットする。

#### Step 3.2: テストの先行生成 (Test-First Generation)

  * **Action**: Orchestratorは `src/ac_cdd/contracts/` をJulesに渡す。
  * [cite_start]**Prompt**: 「実装は見せず、契約（Pydantic）のみに基づき、`Hypothesis` を用いたプロパティベーステストを作成せよ」[cite: 32, 33]。
  * **Output**: `tests/property/test_cycle{N}.py`
  * **Benefit**: 実装バイアスのない、純粋な仕様に対するテストが生成される。

#### Step 3.3: 実装と自己修復ループ (Implementation & Self-Healing)

このステップは `CI` が通るまで最大 `N` 回繰り返される。

1.  **Coding**: Julesは `SPEC.md` と `src/ac_cdd/contracts/` を読み込み、実装を行う。思考過程は `IMPLEMENTATION.md` に記録する。
2.  **Commit**: コードをコミットし、PRを作成（または更新）する。
3.  **CI Watch**: Orchestratorは GitHub Actions のステータスをポーリング監視する。
      * 🔴 **Failure**: エラーログ(stdout/stderr)を取得し、Julesにフィードバック。「テストが落ちている。ログを見て修正せよ」。
      * 🟢 **Success**: 次の「厳格監査」へ進む。

#### Step 3.4: 世界一厳格な監査 (The Strictest Audit)

**Role**: Gemini CLI (Auditor)

1.  **Review**: CIを通過したコードに対し、以下の観点でレビューを行う。
      * **Pydantic準拠**: `model_validate` 等を正しく使っているか。
      * **Security**: インジェクション、機密情報のハードコード等のリスク。
      * **Design**: 重複コード、複雑すぎるロジック。
2.  **Judgment**:
      * 🔴 **Reject**: 指摘事項を `AUDIT_LOG.md` に記録。OrchestratorはこれをJulesに突きつけ、Step 3.3へ強制的に戻す。
      * 🟢 **Approve**: 「監査合格」とし、次のUATへ進む。

#### Step 3.5: UATの生成と実行 (UAT Automation)

1.  **Gen**: Julesは `UAT.md` (自然言語シナリオ) を読み込み、**Playwright (Python)** によるE2Eテストコードを `tests/e2e/` に生成する。
2.  **Run**: Orchestratorがテストを実行する。
      * 🔴 **Failure**: シナリオ通りに動いていない。Julesに修正指示（テストコードの修正か、実装の修正か、Julesに判断させる）。
      * 🟢 **Success**: サイクル完了要件を満たしたとみなす。

-----

### Phase 4: 自動マージと完了 (Auto-Merge & Completion)

**主体:** Orchestrator (via `gh` CLI)

UATまで全てのゲートを通過したコードは、出荷可能品質であると定義される。

1.  **Auto-Merge**: Orchestratorは以下のコマンドを実行する。
    ```bash
    gh pr merge --squash --delete-branch --admin
    ```
2.  **Report**: Userに対し、「CYCLE{N} 完了。PR \#XX をマージしました」と通知（Slack/Email/Terminal表示）を行う。
3.  **Next**: Userは成果物を確認し、`start-cycle {N+1}` の準備に入る。

-----

## 5\. オーケストレーション・ロジック (Orchestration Logic)

`src/ac_cdd/orchestrator.py` は以下の擬似コードに基づくロジックを実装する。

```python
class CycleOrchestrator:
    def execute_cycle(self, cycle_id):
        # 1. Contract Alignment
        self.merge_contracts(cycle_id)
        
        # 2. Generate Property Tests
        self.jules.generate_tests(source="src/ac_cdd/contracts")
        
        # 3. Development Loop (Coding -> CI -> Audit)
        audit_passed = False
        attempt = 0
        while not audit_passed and attempt < 10:
            # a. Coding
            self.jules.implement_feature(spec=f"dev_documents/CYCLE{cycle_id}/SPEC.md")
            
            # b. CI Check
            if not self.github.wait_for_ci_pass():
                self.jules.fix_code(feedback="CI Failed", logs=self.github.get_logs())
                attempt += 1
                continue
            
            # c. Strict Audit
            audit_result = self.gemini_auditor.review(code_path="src/")
            if not audit_result.passed:
                self.log_audit(audit_result.comments)
                self.jules.fix_code(feedback=audit_result.comments)
                attempt += 1
                continue
            
            audit_passed = True

        if not audit_passed:
            raise CycleFailedException("Audit failed after 10 attempts.")

        # 4. UAT
        self.jules.generate_uat_code(uat_md=f"dev_documents/CYCLE{cycle_id}/UAT.md")
        # 実際に pytest を実行し、ログを取得してフィードバックする
        if not self.run_playwright_tests():
             # Fail loop ...
             pass

        # 5. Merge
        self.github.merge_pr()
```

-----

## 6\. 技術スタックとツール要件 (Requirements)

  * **Language**: Python 3.12+
  * **Package Manager**: `uv` (すべての依存関係解決に使用)
  * **Version Control**: Git & GitHub CLI (`gh`)
  * **AI Models**:
      * Thinking/Planning: **Gemini 2.0 Flash / Pro**
      * Coding: **Jules (via API)**
  * **Testing Frameworks**:
      * [cite_start]Unit/Prop: `pytest`, `hypothesis` [cite: 32]
      * E2E/UAT: `playwright`
      * [cite_start]Mocking: `vcrpy` [cite: 52]
  * **Linting/Formatting**: `ruff` (厳格モード)

-----

## 7\. 免責と運用上の注意 (Operations)

1.  **AIのループ制限**: 無限課金を防ぐため、Orchestratorは各サイクルの試行回数（`MAX_RETRIES`）を厳格に守る。
2.  **コンフリクト解消**: `schema.py` のマージでコンフリクトが発生した場合、Orchestratorは停止し、Userに介入を求める。
3.  **シークレット管理**: APIキー等は `.env` で管理し、決してGitにコミットしない。Julesが生成したコードにハードコードが含まれていた場合、監査人がこれをリジェクトする。