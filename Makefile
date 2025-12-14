.PHONY: install test lint format audit clean

install:
	uv sync --all-extras --dev

test:
	uv run pytest tests/

lint:
	uv run ruff check src tests
	uv run mypy src tests

format:
	uv run ruff check --fix src tests
	uv run ruff format src tests

audit:
	uv run manage.py audit

clean:
	rm -rf .ruff_cache .pytest_cache .coverage
	find . -type d -name "__pycache__" -exec rm -rf {} +
