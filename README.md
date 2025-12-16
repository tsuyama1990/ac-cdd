# AC-CDD: AI-Native Development Orchestrator

**Rapid Application Development with Strict Quality Gates**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![uv](https://img.shields.io/badge/managed%20by-uv-purple)](https://github.com/astral-sh/uv)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

このレポジトリは、**AC-CDD (AI-Native Cycle-Based Contract-Driven Development)** アーキテクチャの実装です。
AIによる **Rapid Application Development (RAD)** の圧倒的なスピードと、**Contract-Driven** な厳格な品質管理を融合させ、安全かつ高速なソフトウェア開発を実現します。

理論や詳細なフローについては [👉 DEV_FLOW.md](DEV_FLOW.md) を参照してください。

---

## ⚡ TL;DR (Quick Start)

```bash
# 1. 準備 (依存関係と.env)
uv run manage.py init

# 2. サイクル作成 (仕様書テンプレート生成)
uv run manage.py new-cycle "01"

# 3. 自動化開始 (仕様書を書いた後に実行)
uv run manage.py start-cycle "01"
```

---

## 🛠️ Setup (初期設定)

### 1. Prerequisites
以下のツールがインストールされている必要があります。
* **uv**: Pythonパッケージマネージャー ([インストール方法](https://github.com/astral-sh/uv))
* **git**: バージョン管理
* **gh**: GitHub CLI (PR作成・マージ用)

環境が整っているかは、以下のコマンドで診断できます。

```bash
uv run manage.py doctor
```

### 2. Configure
初回起動時に `.env` ファイルを生成します。

```bash
uv run manage.py init
```
*画面の指示に従い、必要なAPIキー（Google Gemini API Key等）を入力してください。*

---

## 🚀 Usage (操作方法)

### A. Core Workflow (AC-CDD)

開発は「サイクル」という単位で進行します。

#### 1. Create Cycle (計画)
新しい開発サイクルのための作業ディレクトリを作成します。

```bash
uv run manage.py new-cycle "01"
```
作成された `dev_documents/CYCLE01/` 内の `SPEC.md` (仕様), `schema.py` (契約), `UAT.md` (受入テスト) を編集します。

#### 2. Start Cycle (実行)
Orchestratorを起動し、実装・テスト・監査のループを回します。

```bash
# 基本実行
uv run manage.py start-cycle "01"

# 自動承認モード (確認プロンプトをスキップ)
uv run manage.py start-cycle "01" --yes

# ドライラン (変更を行わず動作確認)
uv run manage.py start-cycle "01" --dry-run
```

### B. Ad-hoc Utilities (便利ツール)

サイクル外での修正や監査に使用します。

#### 🩺 Fix (自動修正)
テストを実行し、失敗箇所をAIに修正させます。
(`pytest --last-failed` で高速にフィードバックループを回します)

```bash
uv run manage.py fix
```

#### 🕵️ Audit (厳格監査)
現在の `git diff` に対して、「世界一厳しいコードレビュー」を行い、修正案を提示・適用させます。

```bash
uv run manage.py audit
```

---

## 📁 Directory Structure

主要なディレクトリ構成のみ抜粋します。

* `manage.py`: **Entrypoint**. すべての操作はここから行います。
* `ac_cdd.toml`: システム設定ファイル。
* `dev_documents/`: **Human Space**. 人間が仕様やドキュメントを記述する場所。
* `src/ac_cdd/`: **Code Space**. アプリケーション本体。
* `tests/`: **Test Space**. 自動生成されたテストコード。

---

[詳細なアーキテクチャと役割分担については DEV_FLOW.md へ](DEV_FLOW.md)
