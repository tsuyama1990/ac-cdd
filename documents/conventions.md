# Coding Conventions

- **Package Management**: Always use `uv`. Do not use `pip` directly.
  - Install dependencies: `uv add <package>`
  - Run scripts/tests: `uv run <command>`
- **Contract-Driven Development**:
  - Always modify `contracts/schemas.py` first when changing data structures.
  - Implementation must strictly follow the Pydantic models defined in `contracts/schemas.py`.
