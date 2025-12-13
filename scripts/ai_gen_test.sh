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
