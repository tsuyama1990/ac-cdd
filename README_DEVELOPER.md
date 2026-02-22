# AC-CDD Developer Guide: LangGraph フロー修正・拡張ガイド

> 📖 **ユーザー向けドキュメント**: [README.md](./README.md)

このドキュメントは AC-CDD の LangGraph フローを修正・拡張したい開発者向けのガイドです。

---

## 目次

1. [全体アーキテクチャ](#1-全体アーキテクチャ)
2. [グラフ構成ファイル一覧](#2-グラフ構成ファイル一覧)
3. [State の構造](#3-state-の構造)
4. [着目すべきクラスとメソッド](#4-着目すべきクラスとメソッド)
5. [フロー修正方法（具体例付き）](#5-フロー修正方法具体例付き)
   - [5-1. 既存ノードのロジックを変更する](#5-1-既存ノードのロジックを変更する)
   - [5-2. 新しいノードを追加する（Coder グラフ）](#5-2-新しいノードを追加するcoder-グラフ)
   - [5-3. Jules セッション監視に新しいステップを追加する](#5-3-jules-セッション監視に新しいステップを追加する)
   - [5-4. FlowStatus を追加してルーティングを変える](#5-4-flowstatus-を追加してルーティングを変える)
   - [5-5. Prompt をフローから切り離して変更する](#5-5-prompt-をフローから切り離して変更する)
6. [Jules API 公式 State 一覧](#6-jules-api-公式-state-一覧)
7. [テンプレート変数リファレンス](#7-テンプレート変数リファレンス)
8. [テストのベストプラクティス](#8-テストのベストプラクティス)
9. [よくある落とし穴 (Gotchas)](#9-よくある落とし穴-gotchas)
10. [修正時のチェックリスト](#10-修正時のチェックリスト)

---

## 1. 全体アーキテクチャ

AC-CDD には **2 つの独立した LangGraph グラフ**があります。

```
┌─────────────────────────────────────────────────────────────┐
│  Coder Graph (graph.py)                                     │
│                                                             │
│  START → coder_session ──┬─→ auditor → committee_manager   │
│             ↑            │        ↑─────── ↓               │
│             └────────────┘    uat_evaluate                  │
│         (retry/feedback)          ↓                         │
│                                  END                        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  Jules Session Graph (jules_session_graph.py)               │
│  ※ wait_for_completion() から内部的に呼ばれる              │
│                                                             │
│  monitor ──┬─→ answer_inquiry → monitor                    │
│            ├─→ validate_completion ──┬─→ check_pr → END    │
│            │                        └─→ monitor            │
│            │   check_pr ──┬─→ END (PR found)               │
│            │              └─→ request_pr → wait_pr         │
│            └─→ END (FAILED/TIMEOUT)                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. グラフ構成ファイル一覧

| ファイル | 役割 |
|---|---|
| `dev_src/ac_cdd_core/graph.py` | **Coder/Auditor/QA グラフのビルダー**。`GraphBuilder` クラスがグラフの構造（ノード・エッジ）を定義 |
| `dev_src/ac_cdd_core/graph_nodes.py` | **Coder グラフの各ノード実装**。`CycleNodes` クラス。ノードは UseCase を呼ぶ薄いラッパー |
| `dev_src/ac_cdd_core/jules_session_graph.py` | **Jules セッション監視グラフのビルダー**。`build_jules_session_graph()` 関数 |
| `dev_src/ac_cdd_core/jules_session_nodes.py` | **Jules セッション監視グラフの各ノード実装**。`JulesSessionNodes` クラス |
| `dev_src/ac_cdd_core/jules_session_state.py` | Jules セッション監視グラフ専用の State 定義 |
| `dev_src/ac_cdd_core/state.py` | Coder グラフ用の State 定義（`CycleState`） |
| `dev_src/ac_cdd_core/enums.py` | `FlowStatus`（ルーティングキー）と `WorkPhase` の定義 |
| `dev_src/ac_cdd_core/services/coder_usecase.py` | Coder ノードのビジネスロジック |
| `dev_src/ac_cdd_core/services/auditor_usecase.py` | Auditor ノードのビジネスロジック |
| `dev_src/ac_cdd_core/services/committee_usecase.py` | Committee Manager ノードのビジネスロジック |
| `dev_src/ac_cdd_core/services/qa_usecase.py` | QA ノードのビジネスロジック |

---

## 3. State の構造

### CycleState（Coder グラフ）

`dev_src/ac_cdd_core/state.py` に定義。Pydantic BaseModel。

```python
class CycleState(BaseModel):
    cycle_id: str                        # 必須: 処理対象サイクルID (例: "01")
    status: FlowStatus | None = None     # ルーティングの核心。ノードが返す値
    current_phase: WorkPhase = WorkPhase.INIT
    audit_result: AuditResult | None = None
    pr_url: str | None = None
    jules_session_name: str | None = None
    iteration_count: int = 0
    # ... その他多数
```

**重要**: ノードは `dict[str, Any]` を返す。返した key/value が State にマージされる。

```python
# ノードの戻り値の例
return {"status": FlowStatus.READY_FOR_AUDIT, "pr_url": "https://github.com/..."}
# → state.status と state.pr_url が更新される
```

### JulesSessionState（Jules セッション監視グラフ）

`dev_src/ac_cdd_core/jules_session_state.py` に定義。

```python
class JulesSessionState(BaseModel):
    session_url: str                          # Jules API URL
    status: SessionStatus = SessionStatus.MONITORING  # 内部ルーティング用
    jules_state: str | None = None            # Jules API から取得した公式 state
    pr_url: str | None = None
    processed_activity_ids: set[str]          # 重複処理防止
    completion_validated: bool = False        # COMPLETED 遷移確認フラグ
    # ...
```

---

## 4. 着目すべきクラスとメソッド

### `GraphBuilder` (`graph.py`)

グラフ構造の定義のみを担う。**ノードを追加・削除するときに修正する**。

```python
def _create_coder_graph(self) -> StateGraph[CycleState]:
    workflow = StateGraph(CycleState)
    workflow.add_node("coder_session", self.nodes.coder_session_node)  # ノード登録
    workflow.add_edge(START, "coder_session")                          # 固定エッジ
    workflow.add_conditional_edges(                                     # 条件付きエッジ
        "coder_session",
        self.nodes.check_coder_outcome,   # ルーター関数
        {FlowStatus.READY_FOR_AUDIT.value: "auditor", ...}
    )
```

### `CycleNodes` (`graph_nodes.py`)

各ノードを UseCase に委譲するラッパークラス。**グラフに新しいノードを追加するときにメソッドを追加する**。

```python
async def coder_session_node(self, state: CycleState) -> dict[str, Any]:
    from ac_cdd_core.services.coder_usecase import CoderUseCase
    usecase = CoderUseCase(self.jules)
    return dict(await usecase.execute(state))   # UseCase に丸投げ
```

ルーター関数は条件分岐のみ:

```python
def check_coder_outcome(self, state: CycleState) -> str:
    status = state.get("status")
    if status == FlowStatus.READY_FOR_AUDIT:
        return FlowStatus.READY_FOR_AUDIT.value  # グラフのエッジキーに一致する文字列を返す
    ...
```

### `JulesSessionNodes` (`jules_session_nodes.py`)

Jules セッション監視の各ノード。**Jules との通信中に新しいイベントを処理したい場合に修正する**。

主要メソッド:

| メソッド | タイミング | 役割 |
|---|---|---|
| `monitor_session` | ポーリング毎 | Jules の状態を取得し `SessionStatus` に変換 |
| `answer_inquiry` | Jules が質問したとき | Manager Agent に質問させて返答送信 |
| `validate_completion` | Jules が COMPLETED になったとき | 本当に完了か（stale でないか）検証 |
| `check_pr` | バリデーション通過後 | PR URL が存在するか確認 |
| `request_pr_creation` | PR がないとき | Jules に手動 PR 作成を依頼 |
| `wait_for_pr` | PR 待ち中 | PR 作成を待機、タイムアウト管理 |

### `FlowStatus` / `SessionStatus` (`enums.py`, `jules_session_state.py`)

**ルーティングの核心**。ノードが返す status 値と、グラフのエッジキーが完全一致する必要がある。

---

## 5. フロー修正方法（具体例付き）

### 5-1. 既存ノードのロジックを変更する

**例: Coder ノードが 3 回リトライではなく 5 回リトライするようにしたい**

ビジネスロジックは UseCase 側にあるため、`graph_nodes.py` は触らずに UseCase を修正する。

```python
# dev_src/ac_cdd_core/services/coder_usecase.py の _handle_session_failure
def _handle_session_failure(self, ...):
    max_restarts = cycle_manifest.max_session_restarts  # ← 設定値を変える
    # または config/settings でデフォルト値を変える
```

---

### 5-2. 新しいノードを追加する（Coder グラフ）

**例: Auditor の後に「セキュリティスキャン」ノードを追加したい**

**Step 1: UseCase を作成する**

```python
# dev_src/ac_cdd_core/services/security_usecase.py
class SecurityUseCase:
    async def execute(self, state: CycleState) -> dict[str, Any]:
        # スキャンロジック
        if scan_passed:
            return {"status": FlowStatus.SECURITY_PASSED}
        return {"status": FlowStatus.SECURITY_FAILED, "error": "Security scan failed"}
```

**Step 2: `FlowStatus` に新しい値を追加する**

```python
# dev_src/ac_cdd_core/enums.py
class FlowStatus(str, Enum):
    # 既存 ...
    SECURITY_PASSED = "security_passed"   # ← 追加
    SECURITY_FAILED = "security_failed"   # ← 追加
```

**Step 3: `CycleNodes` にノードメソッドを追加する**

```python
# dev_src/ac_cdd_core/graph_nodes.py
async def security_scan_node(self, state: CycleState) -> dict[str, Any]:
    from ac_cdd_core.services.security_usecase import SecurityUseCase
    usecase = SecurityUseCase()
    return dict(await usecase.execute(state))

def route_security(self, state: CycleState) -> str:
    if state.get("status") == FlowStatus.SECURITY_PASSED:
        return "committee_manager"
    return "failed"
```

**Step 4: `graph.py` にノードとエッジを登録する**

```python
# dev_src/ac_cdd_core/graph.py の _create_coder_graph
workflow.add_node("security_scan", self.nodes.security_scan_node)  # ← 追加

# auditor → committee_manager の固定エッジを削除して条件付きに変更
# 変更前:
workflow.add_edge("auditor", "committee_manager")

# 変更後:
workflow.add_edge("auditor", "security_scan")          # auditor の後にスキャン
workflow.add_conditional_edges(
    "security_scan",
    self.nodes.route_security,
    {
        "committee_manager": "committee_manager",
        "failed": END,
    },
)
```

---

### 5-3. Jules セッション監視に新しいステップを追加する

**例: Jules が `PAUSED` 状態になったとき、専用の通知処理を追加したい**

**Step 1: `SessionStatus` に新しい値を追加する**

```python
# dev_src/ac_cdd_core/jules_session_state.py
class SessionStatus(str, Enum):
    # 既存 ...
    PAUSED_DETECTED = "paused_detected"   # ← 追加
```

**Step 2: `JulesSessionNodes` に新しいノードを追加する**

```python
# dev_src/ac_cdd_core/jules_session_nodes.py
async def handle_paused(self, _state_in: JulesSessionState) -> dict[str, Any]:
    """Jules が PAUSED 状態になったときの処理."""
    state = _state_in.model_copy(deep=True)

    console.print("[yellow]Jules session is PAUSED. Sending resume message...[/yellow]")
    # 例: Slack 通知、再開メッセージの送信など
    await self.client._send_message(state.session_url, "Please continue with the implementation.")

    state.status = SessionStatus.MONITORING  # モニタリングに戻す
    return self._compute_diff(_state_in, state)
```

**Step 3: `monitor_session` で PAUSED を検出して遷移させる**

```python
# jules_session_nodes.py の monitor_session 内
if current_state == "PAUSED" and not state.paused_handled:  # 状態に paused_handled フィールドを追加
    state.status = SessionStatus.PAUSED_DETECTED
    return self._compute_diff(_state_in, state)
```

**Step 4: `jules_session_graph.py` にノードとエッジを登録する**

```python
# dev_src/ac_cdd_core/jules_session_graph.py

# route_monitor 関数に分岐を追加
def route_monitor(state):
    if state.status == SessionStatus.PAUSED_DETECTED:
        return "handle_paused"   # ← 追加
    # ... 既存分岐

# build_jules_session_graph 関数内
workflow.add_node("handle_paused", nodes.handle_paused)          # ← 追加
workflow.add_edge("handle_paused", "monitor")                     # 処理後 monitor へ戻る

# route_monitor の mapping に追記
workflow.add_conditional_edges(
    "monitor",
    route_monitor,
    {
        "answer_inquiry": "answer_inquiry",
        "validate_completion": "validate_completion",
        "handle_paused": "handle_paused",    # ← 追加
        "end": END,
        "monitor": "monitor",
    },
)
```

---

### 5-4. FlowStatus を追加してルーティングを変える

**例: Auditor が「警告あり・承認」という新しい状態を返せるようにしたい**

```python
# 1. enums.py に追加
class FlowStatus(str, Enum):
    APPROVED_WITH_WARNINGS = "approved_with_warnings"  # ← 追加

# 2. auditor_usecase.py で返せるようにする
return {"status": FlowStatus.APPROVED_WITH_WARNINGS, "audit_result": result}

# 3. committee_usecase.py でハンドリング
if state.status == FlowStatus.APPROVED_WITH_WARNINGS:
    # 警告込み承認の処理
    return {"status": FlowStatus.CYCLE_APPROVED}

# 4. graph.py の route_committee に追記（必要なら）
# FlowStatus.CYCLE_APPROVED は既存なので route_committee は変更不要
```

---

### 5-5. Prompt をフローから切り離して変更する

**コードを触らずにプロンプトを変えたい場合**:

```bash
mkdir -p dev_documents/system_prompts

# 例: Jules に送るフィードバックメッセージを変更する
cat > dev_documents/system_prompts/AUDIT_FEEDBACK_MESSAGE.md << 'EOF'
# コードレビュー結果

以下の問題が見つかりました：

{{feedback}}

上記をすべて修正し、新しい Pull Request を作成してください。
修正にあたっては SPEC.md の要件を必ず確認してください。
EOF
```

テンプレートとコードの対応は以下の通り:

| 変えたいもの | テンプレートファイル |
|---|---|
| Jules への audit フィードバック | `AUDIT_FEEDBACK_MESSAGE.md` |
| 新規セッション起動時のフィードバック注入 | `AUDIT_FEEDBACK_INJECTION.md` |
| PR 作成依頼メッセージ | `PR_CREATION_REQUEST.md` |
| Manager Agent がJulesの質問に答える指示 | `MANAGER_INQUIRY_PROMPT.md` |
| Coder の実装指示 | `CODER_INSTRUCTION.md` |
| Auditor のコードレビュー指示 | `AUDITOR_INSTRUCTION.md` |

変数は `{{変数名}}` 形式で、利用可能な変数は:

- `{{feedback}}` — 監査フィードバックテキスト（`AUDIT_FEEDBACK_MESSAGE.md`, `AUDIT_FEEDBACK_INJECTION.md`）
- `{{pr_url}}` — 前回の PR URL（`AUDIT_FEEDBACK_INJECTION.md` のみ）
- `{{question}}` — Jules からの質問文（`MANAGER_INQUIRY_FALLBACK.md` のみ）

---

## 6. Jules API 公式 State 一覧

Jules セッションの状態を判定するコードを書く際は、**必ずこの一覧のみを使用する**こと。

| Jules API State | 意味 | 分類 |
|---|---|---|
| `QUEUED` | キュー待ち | 🟡 Active（非終端） |
| `PLANNING` | 計画立案中 | 🟡 Active（非終端） |
| `AWAITING_PLAN_APPROVAL` | 計画承認待ち | 🟡 Active（非終端） |
| `AWAITING_USER_FEEDBACK` | ユーザー回答待ち | 🟡 Active（非終端） |
| `IN_PROGRESS` | 実装中 | 🟡 Active（非終端） |
| `PAUSED` | 一時停止 | 🟡 Active（非終端） |
| `COMPLETED` | 完了 | 🔴 Terminal |
| `FAILED` | 失敗 | 🔴 Terminal |
| `STATE_UNSPECIFIED` | 不明 | 🔴 Terminal 扱い |

❌ **使用禁止**: `RUNNING`, `SUCCEEDED`（API に存在しない）

**Active States の定数例**:

```python
ACTIVE_STATES = {
    "IN_PROGRESS",
    "QUEUED",
    "PLANNING",
    "AWAITING_PLAN_APPROVAL",
    "AWAITING_USER_FEEDBACK",
    "PAUSED",
}

TERMINAL_STATES = {
    "COMPLETED",
    "FAILED",
    "STATE_UNSPECIFIED",
    "UNKNOWN",
}
```

---

## 7. テンプレート変数リファレンス

以下の変数は対応するテンプレートファイル内で `{{変数名}}` の形で使用できます。

| 変数 | 利用可能なテンプレート | 説明 |
|---|---|---|
| `{{cycle_id}}` | `CODER_INSTRUCTION.md`, `AUDITOR_INSTRUCTION.md` | サイクルID（例: `01`, `02`）。コード内で自動置換される |
| `{{feedback}}` | `AUDIT_FEEDBACK_MESSAGE.md`, `AUDIT_FEEDBACK_INJECTION.md` | 監査フィードバックのフルテキスト |
| `{{pr_url}}` | `AUDIT_FEEDBACK_INJECTION.md` | 前回の PR の URL。`{{#pr_url}}...{{/pr_url}}` で条件付きレンダリング可能 |
| `{{question}}` | `MANAGER_INQUIRY_FALLBACK.md` | Jules からの質問文（Manager Agent が失敗した場合のフォールバック用） |

### `{{pr_url}}` の条件付きレンダリング

`AUDIT_FEEDBACK_INJECTION.md` では Mustache 風の条件ブロックが使えます:

```markdown
{{#pr_url}}
Previous PR: {{pr_url}}
{{/pr_url}}
```

`pr_url` が存在する場合はブロックが展開され、存在しない場合はブロックごと削除されます。

---

## 8. テストのベストプラクティス

### ノードのユニットテスト

UseCase と依存関係をすべてモックし、状態遷移のみを検証する。

```python
@pytest.mark.asyncio
async def test_my_new_node(mock_jules: MagicMock) -> None:
    mock_jules.get_session_state.return_value = "COMPLETED"

    usecase = MyNewUseCase(mock_jules)
    state = CycleState(cycle_id="01", status=FlowStatus.SOME_STATUS)

    with patch("ac_cdd_core.services.my_usecase.settings") as mock_settings:
        mock_settings.get_template.return_value.read_text.return_value = "Instruction"
        mock_settings.get_target_files.return_value = []
        mock_settings.get_context_files.return_value = []
        result = await usecase.execute(state)

    assert result["status"] == FlowStatus.EXPECTED_STATUS
```

### テンプレートのモック

テンプレート名ごとに内容を変える場合は `side_effect` を使う:

```python
def mock_get_template(name: str) -> MagicMock:
    m = MagicMock()
    if name == "AUDIT_FEEDBACK_INJECTION.md":
        m.read_text.return_value = "# FEEDBACK\n\n{{feedback}}\n\n{{#pr_url}}\nPrevious PR: {{pr_url}}\n{{/pr_url}}"
    else:
        m.read_text.return_value = "Generic instruction"
    return m

mock_settings.get_template.side_effect = mock_get_template
```

### Jules 状態の mock

```python
# ✅ 正しい（公式 API state を使う）
mock_jules.get_session_state.return_value = "IN_PROGRESS"

# ❌ 間違い（存在しない state）
mock_jules.get_session_state.return_value = "RUNNING"    # NG
mock_jules.get_session_state.return_value = "SUCCEEDED"  # NG
```

---

## 9. よくある落とし穴 (Gotchas)

### ❌ 存在しない Jules API State の使用

```python
# NG: Jules API にこれらは存在しない
if state == "RUNNING": ...
if state == "SUCCEEDED": ...

# OK: 公式 state のみ使用する
if state == "IN_PROGRESS": ...
if state == "COMPLETED": ...
```

### ❌ `asyncio.get_event_loop()` の使用（Python 3.10+ で DeprecationWarning）

async 関数内では `get_running_loop()` を使う:

```python
# NG
elapsed = asyncio.get_event_loop().time() - start_time

# OK（async 関数内では常にループが存在するため安全）
elapsed = asyncio.get_running_loop().time() - start_time
```

### ❌ ルーターの返り値とエッジキーの不一致

ルーター関数が返す文字列は、`add_conditional_edges` の mapping dict のキーと**完全一致**する必要があります:

```python
# graph.py
workflow.add_conditional_edges(
    "my_node",
    self.nodes.my_router,
    {
        "next_node": "next_node",   # ← ルーターが返す値と一致させる
        "failed": END,
    },
)

# graph_nodes.py
def my_router(self, state: CycleState) -> str:
    if ok:
        return "next_node"   # ← 上記 mapping のキーと完全一致
    return "failed"
```

### ❌ テンプレートのモックで全ての名前に同じ内容を返す

`{{feedback}}` などの変数を含むテンプレートは、テスト時に変数を含む内容を返す必要があります:

```python
# NG: AUDIT_FEEDBACK_INJECTION に {{feedback}} が含まれない → 置換が機能しない
mock_settings.get_template.return_value.read_text.return_value = "Generic text"

# OK: テンプレート名ごとに適切な内容を返す
def mock_get_template(name: str) -> MagicMock:
    m = MagicMock()
    if name == "AUDIT_FEEDBACK_INJECTION.md":
        m.read_text.return_value = "# FEEDBACK\n\n{{feedback}}"
    else:
        m.read_text.return_value = "Instruction"
    return m
mock_settings.get_template.side_effect = mock_get_template
```

### ❌ 新しいテンプレートで `{{cycle_id}}` 置換を忘れる

`CODER_INSTRUCTION.md` や `AUDITOR_INSTRUCTION.md` に `{{cycle_id}}` を追加した場合は、
対応する UseCase で必ず置換すること:

```python
instruction = settings.get_template("MY_INSTRUCTION.md").read_text()
instruction = instruction.replace("{{cycle_id}}", str(state.cycle_id))  # 必須
```

---

## 10. 修正時のチェックリスト

フローを修正・追加した後は、必ず以下を確認する:

```bash
# 1. 静的解析（tests/ を含む全ファイル対象）
uv run mypy .
uv run ruff check .

# 2. フォーマット
uv run ruff format .

# 3. 全ユニットテスト
uv run pytest tests/ac_cdd/unit -q
```

### ✅ 確認事項

- [ ] **新しい FlowStatus / SessionStatus** を追加した場合、対応するグラフのエッジキーと完全一致しているか
- [ ] **Jules API state** のチェックで `RUNNING` / `SUCCEEDED` を使っていないか
- [ ] **ノードの戻り値**が `dict[str, Any]` であり、LangGraph が State にマージできる形式か
- [ ] **UseCase が例外を投げる** 場合、ノードかグラフでキャッチしているか
- [ ] **新しいプロンプト文字列**がハードコードされていないか（テンプレート化を検討する）
- [ ] **新しい State フィールド**を追加した場合、`CycleState` / `JulesSessionState` の定義に追加したか
- [ ] **`{{cycle_id}}` を含むテンプレート**を追加した場合、UseCase で `instruction.replace("{{cycle_id}}", ...)` を呼んでいるか
- [ ] **async 関数内**で `asyncio.get_event_loop()` を使っていないか（`get_running_loop()` を使うこと）
- [ ] `uv run mypy .`（`tests/` 含む全体）でエラーが 0 であるか
