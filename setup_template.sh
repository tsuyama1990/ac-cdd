#!/bin/bash
set -e

echo "Initializing Autonomous Development Template..."

# Create directories
mkdir -p documents
mkdir -p contracts
mkdir -p scripts
mkdir -p src
mkdir -p tests/property
mkdir -p tests/integration

# 1. pyproject.toml
cat <<'EOF' > pyproject.toml
[project]
name = "autonomous-dev-template"
version = "0.1.0"
description = "A template for AI-native development with Jules and uv"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "fastapi",
    "pydantic",
    "python-dotenv",
]

[dependency-groups]
dev = [
    "hypothesis",
    "pytest",
    "pytest-cov",
    "ruff",
    "vcrpy",
]

[tool.ruff]
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I"]
ignore = []

[tool.pytest.ini_options]
addopts = "--cov=src --cov-report=term-missing"
testpaths = ["tests"]
EOF

# 2. .env.example
cat <<'EOF' > .env.example
JULES_API_KEY=your_key_here
EOF

# 3. .gitignore
cat <<'EOF' > .gitignore
__pycache__/
*.py[cod]
*$py.class
.env
.venv/
.coverage
htmlcov/
dist/
build/
*.egg-info/
.pytest_cache/
.ruff_cache/
.hypothesis/
EOF

# 4. documents/requirements.md
cat <<'EOF' > documents/requirements.md
# Product Requirement Document (PRD)

## 1. 背景と目的 (Context)
## 2. ターゲットユーザー (Persona)
## 3. ユーザーストーリー (User Stories)
## 4. 機能要件 (Functional Requirements)
## 5. 非機能要件 (Non-Functional Requirements)
EOF

# 5. documents/architecture.md
cat <<'EOF' > documents/architecture.md
# Architecture Decision Record (ADR)

## 1. 技術スタック (Tech Stack)
- Language: Python 3.12+
- Package Manager: uv
- Framework: FastAPI
- Testing: pytest, hypothesis, vcrpy

## 2. データモデル設計 (Data Models)
## 3. API設計方針 (API Design)
## 4. ディレクトリ構造方針 (Directory Structure)
EOF

# 6. documents/conventions.md
cat <<'EOF' > documents/conventions.md
# Coding Conventions

- **Package Management**: Always use `uv`. Do not use `pip` directly.
  - Install dependencies: `uv add <package>`
  - Run scripts/tests: `uv run <command>`
- **Contract-Driven Development**:
  - Always modify `contracts/schemas.py` first when changing data structures.
  - Implementation must strictly follow the Pydantic models defined in `contracts/schemas.py`.
EOF

# 7. contracts/schemas.py
cat <<'EOF' > contracts/schemas.py
from pydantic import BaseModel, Field, ConfigDict

# これはサンプルです。実際のデータモデルに置き換えてください。
class ExampleModel(BaseModel):
    """
    AIエージェントへの指示:
    このモデルはSingle Source of Truthとして機能します。
    すべての入出力はこのディレクトリで定義されたPydanticモデルに準拠させてください。
    """
    id: int = Field(..., gt=0, description="ユニークID")
    name: str = Field(..., min_length=1, max_length=100, description="ユーザー名")
    is_active: bool = Field(default=True, description="有効フラグ")

    model_config = ConfigDict(extra="forbid") # 厳格なスキーマ検証を強制
EOF

# 8. contracts/__init__.py
touch contracts/__init__.py

# 9. scripts/ai_fix.sh
cat <<'EOF' > scripts/ai_fix.sh
#!/bin/bash
set -e

LOG_FILE="pytest_run.log"

echo "Running tests..."
# Run pytest and capture both stdout and stderr to a log file
# We use '|| true' so the script doesn't exit immediately on test failure,
# allowing us to process the failure.
if uv run pytest > "$LOG_FILE" 2>&1; then
    echo "Tests passed!"
    rm "$LOG_FILE"
    exit 0
else
    echo "Tests failed. Invoking Jules for autofix..."
    # Using cat to pipe log content to stdin of jules command
    cat "$LOG_FILE" | jules remote new --session "autofix-$(date +%s)" \
        "テストが失敗しました。ログを分析し、src/内のコードを修正してください"
fi
EOF

# 10. scripts/ai_gen_test.sh
cat <<'EOF' > scripts/ai_gen_test.sh
#!/bin/bash
set -e

SCHEMA_FILE="contracts/schemas.py"
OUTPUT_FILE="tests/property/test_schemas_pbt.py"

if [ ! -f "$SCHEMA_FILE" ]; then
    echo "Error: $SCHEMA_FILE not found."
    exit 1
fi

echo "Generating Hypothesis tests from $SCHEMA_FILE..."

PROMPT="入力されたPydanticモデル定義に基づき、Hypothesisを使用したプロパティベーステストコードを作成してください。
出力先は $OUTPUT_FILE としてください。
全てのフィールドに対して、境界値や異常値（空文字、None、最大長オーバーなど）を含むStrategyを適用すること。"

cat "$SCHEMA_FILE" | jules remote new "$PROMPT"
EOF

# Make scripts executable
chmod +x scripts/ai_fix.sh
chmod +x scripts/ai_gen_test.sh

# 11. src/__init__.py and tests/__init__.py
touch src/__init__.py
touch tests/__init__.py

echo "Template setup complete."
