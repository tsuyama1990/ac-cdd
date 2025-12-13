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
