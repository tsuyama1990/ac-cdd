# DEV_FLOW.md

## AI-Native Cycle-Based Contract-Driven Development (AC-CDD)

**Version:** 2.0.0
**Status:** Active
**Target:** All Developers & AI Agents

---

## ⚡ TL;DR (要約)

1.  **契約ファースト**: 全ては `Pydantic` スキーマ（契約）から始まる。自然言語仕様よりもコードの契約が優先される。
2.  **AIレバレッジと品質の両立**: **RAD (Rapid Application Development)** のスピード感と、**厳格な契約駆動** による品質管理を統合する。
3.  **分業体制**: 「作るAI (Jules)」と「監査するAI (Gemini)」を戦わせることで、高速開発につきものの品質低下を防ぐ。
4.  **サイクル駆動**: **Spiral Model** の概念を取り入れ、小さなサイクル（Prototype）を回しながら、製品レベルの品質（Production）へと螺旋状に進化させる。

---

## 1. Philosophy (開発哲学)

### RAD (Rapid Application Development) x AI Leverage

本プロジェクトの目的は、AIの圧倒的な実装速度（Leverage）を最大限に活かしつつ、**Rapid Application Development (RAD)** の理念である「プロトタイピングによる高速反復」を実現することです。

しかし、AIによる高速開発は「品質のばらつき」「幻覚」「メンテナンス性の欠如」というリスクを孕んでいます。これらは従来のRADでも問題とされてきた「Speed vs Quality」のトレードオフです。

### AC-CDD: The Quality Guardrails

このトレードオフを解消するために開発されたのが **AC-CDD (AI-Native Cycle-Based Contract-Driven Development)** です。

*   **Prototype Modelの速度**: AIは人間には不可能な速度でコードを生成します。これをプロトタイプとして許容します。
*   **Spiral Modelの進化**: 小さなサイクルを繰り返すことで、システムを段階的に成長させます。
*   **Contract-Drivenの規律**: しかし、各サイクルの出口（マージ）には「世界一厳しい監査人」が待ち構えています。**「契約（Schema）を満たさない限り、どれだけ速く作ってもゴミである」** という哲学の下、品質を担保します。

これにより、**「爆速で作り（AI）、厳格に縛る（Contract）」** という新しいエンジニアリング体験を提供します。

---

## 2. The Iron Triangle (3つの原則)

1.  **Contract is King (契約絶対主義)**
    曖昧な自然言語仕様書は信用しません。型定義された `schema.py` こそがシステムが守るべき唯一の真実です。
2.  **Adversarial AI (敵対的生成)**
    実装者 (Coder) と監査人 (Auditor) を別のAIエージェントとして定義し、意図的に対立させます。甘いコードは監査人によって容赦なくリジェクトされます。
3.  **Cyclic Self-Healing (自己修復ループ)**
    エラーや監査指摘が発生した場合、Orchestratorが自動的に「修正→テスト→再監査」のループを回します。人間が手動で直す必要はありません。

---

## 3. Roles & Players (役割分担)

この開発フローには、明確な役割を持ったプレーヤーが存在します。

| Role | Entity | Description |
| :--- | :--- | :--- |
| **Chief Architect** | 👤 **Human** | プロジェクトの方向性を決め、`SPEC.md` と `schema.py` を記述・承認する最高責任者。 |
| **Orchestrator** | 🤖 **System** | `manage.py`。全体の進行管理、CI監視、Git操作、エージェント間の調停を行う自動化スクリプト。 |
| **The Planner** | 🧠 **Gemini Pro** | 仕様書を読み解き、実装計画を立案する参謀。Spiral Modelにおける計画フェーズ担当。 |
| **The Coder** | 💻 **Jules** | 実装担当。Prototype作成のスペシャリスト。指示に忠実だが、たまに近道しようとするため監視が必要。 |
| **The Auditor** | 👮 **Gemini CLI** | 厳格な監査人。セキュリティ、可読性、設計原則の観点からコードをレビューし、リジェクト権限を持つ。 |
| **QA Analyst** | 🕵️ **Gemini Flash** | テスト結果ログを分析し、何が起きているかを人間に分かりやすく要約する分析官。 |

---

## 4. Workflow (詳細フロー)

開発は以下のステップで進行します。

### Phase 1: Definition (定義)

人間が `new-cycle` コマンドで作業場を作り、仕様を定義します。

1.  **Cycle Init**: `uv run manage.py new-cycle "01"`
2.  **Specify**: 生成された以下のファイルを編集します。
    *   `SPEC.md`: 機能の概要、要件。
    *   `schema.py`: **最重要**。入出力のデータ構造（Pydanticモデル）。
    *   `UAT.md`: ユーザー受け入れテストのシナリオ。

### Phase 2: Orchestration (自動化)

人間が `start-cycle` コマンドを叩くと、Orchestratorが始動します。

```mermaid
graph TD
    Start[User: start-cycle] --> Plan[Planner: 計画立案]
    Plan --> Contract[System: 契約締結]
    Contract --> TestGen[Coder: テスト先行作成]
    TestGen --> CodeLoop{Coding Loop}

    CodeLoop --> Implement[Coder: 実装 (Prototype)]
    Implement --> TestRun[System: Test実行]
    TestRun -- Fail --> Fix[Coder: 修正]
    Fix --> TestRun

    TestRun -- Pass --> Audit[Auditor: 厳格監査 (Quality Gate)]
    Audit -- Reject --> Fix
    Audit -- Approve --> UAT[System: UAT実行]

    UAT -- Fail --> Fix
    UAT -- Pass --> Merge[System: Auto Merge]
    Merge --> End[Completion]
```

### Phase 3: Intervention (介入・修正)

自動化ループの中で解決できない問題が発生した場合、あるいはサイクル外での修正が必要な場合に使用します。

*   **Audit Command**: `uv run manage.py audit`
    *   手動で変更したコードに対し、Auditorを呼び出してレビューを受けます。
*   **Fix Command**: `uv run manage.py fix`
    *   テストが落ちている場合、ログを解析させて自動修正を試みます。

---

## 5. Operation Guide (運用ガイド)

### ベストプラクティス
*   **小さく回す (Spiral Evolution)**: 1つのサイクルで壮大な機能を作ろうとせず、機能を分割して `CYCLE01`, `CYCLE02` と積み上げてください。
*   **契約に時間をかける**: `schema.py` の定義が甘いと、AIは迷走します。型ヒント、Fieldの説明(`description`)は詳細に書いてください。
*   **介入を恐れない**: AIがループに陥った場合、遠慮なく `Ctrl+C` で止め、コードや仕様を手動で修正してから再開してください。

### ディレクトリ構造の意図
*   `dev_documents/`: AIへのインプット専用領域です。ここにある情報はすべて「コンテキスト」として利用されます。
*   `src/ac_cdd/contracts/`: システム全体で確定した「契約」の保管場所です。サイクルが完了すると、`dev_documents/CYCLExx/schema.py` がここに統合されます。

---

*This document is managed by the Architect and enforced by the Orchestrator.*
