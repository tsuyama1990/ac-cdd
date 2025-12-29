# Autonomous Development Environment (AC-CDD)
** README.md under root directory can be replaced by the one for actual development.
The same contents can be found in dev_documents/README.md **

An AI-Native Cycle-Based Contract-Driven Development Environment.

## Key Features

*   **🚀 Automated Rapid Application Design (Auto-RAD)**
    *   Just define your raw requirements in `ALL_SPEC.md`.
    *   The `gen-cycles` command automatically acts as an **Architect**, generating `SYSTEM_ARCHITECTURE.md`, detailed `SPEC.md`, and `UAT.md` (User Acceptance Tests) for every development cycle.

*   **🛡️ Committee of Code Auditors**
    *   No more "LGTM" based on loose checks.
    *   An automated **Committee of Auditors** (powered by LLMReviewer/Fast Model) performs strict, multi-pass code reviews.
    *   The system iteratively fixes issues (using Jules/Smart Model) until the code passes strict quality gates.

*   **🔒 Secure Sandboxed Execution**
    *   **Fully Remote Architecture**: All code execution, testing, and AI-based fixing happens inside a secure, ephemeral **E2B Sandbox**.
    *   Your local environment stays clean. No need to install complex dependencies locally.
    *   The system automatically syncs changes back to your local machine.

*   **✅ Integrated Behavior-Driven UAT**
    *   Quality is not just about code style; it's about meeting requirements.
    *   The system automatically executes tests and verifies them against the behavior definitions in `UAT.md` before any merge.

*   **🤖 Hybrid Agent Orchestration**
    *   Combines the best of breed:
        *   **Google Jules**: For long-context architectural planning, initial implementation, and refinement (Fixer).
        *   **LLMReviewer**: For strict, direct API-based code auditing.
        *   **LangGraph**: For robust state management and supervisor loops.

This repository is a template for creating AI-powered software development projects. It separates the agent orchestration logic from the user's product code.

## Directory Structure

*   `dev_src/`: **Agent Core Code.** The source code for the AC-CDD CLI and agents (`ac_cdd_core`).
*   `src/`: **User Product Code.** This is where YOUR project's source code resides. The agents will read and write code here.
*   `dev_documents/`: **Documentation & Artifacts.** Stores design docs (`ALL_SPEC.md`, `SYSTEM_ARCHITECTURE.md`), cycle artifacts (`CYCLE{xx}/`), and templates.
*   `tests/`: Tests for the AC-CDD core logic (you can add your own tests in `src/tests` or similar if you wish, but usually `tests/` here is for the tool itself if you are forking). *Note: The agents will generate tests for YOUR code in `tests/` or as configured.*

## Getting Started

### Prerequisites

*   Python 3.12+
*   `uv` (Universal Python Package Manager)
*   `git`
*   `gh` (GitHub CLI)
*   `gh` (GitHub CLI)
*   *Note: `aider` is NO LONGER required. Auditing and Fixing are handled by direct LLM APIs and Jules.*

### Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-org/autonomous-dev-env.git
    cd autonomous-dev-env
    ```

2.  **Install dependencies:**
    ```bash
    uv sync
    ```

3.  **Setup Environment:**
    Run the initialization wizard to generate your `.env` file.
    ```bash
    uv run manage.py init
    ```

### Configuration

The system is configured via `.env` and `ac_cdd_config.py`.

#### API Keys

You must provide the following keys in your `.env` file:

*   `JULES_API_KEY`: Required for the Jules autonomous agent interface.
*   `E2B_API_KEY`: Required for the secure sandbox environment.
*   `GEMINI_API_KEY` or `GOOGLE_API_KEY`: Required for Gemini models (Auditor).
*   `ANTHROPIC_API_KEY`: Required for Claude models (if used for Audit/Review).
*   `OPENROUTER_API_KEY`: (Optional) Recommended for accessing diverse models for auditing.

#### Multi-Model Configuration

You can configure different models for different agents to optimize for cost and intelligence.

**Example `.env` configuration (Hybrid):**

```env
# Smart model for fixing (Claude 3.5 Sonnet)
SMART_MODEL=claude-3-5-sonnet-20241022

# Fast model for auditing & QA (Gemini Flash)
FAST_MODEL=gemini-2.0-flash-exp

# Sandbox
E2B_API_KEY=e2b_...
```

## Usage

### Architecture Phase

Generate the system architecture and specifications from your `ARCHITECT_INSTRUCTION.md` template.

```bash
uv run manage.py gen-cycles
```

This will:
1.  Create a `design/architecture` branch.
2.  Run the Architect Session using Jules.
3.  Generate `ALL_SPEC.md` and `SYSTEM_ARCHITECTURE.md`.

### Development Cycles

Run a development cycle to implement features.

```bash
# Run Cycle 01
uv run manage.py run-cycle --id 01

# Run automatically (no manual confirmation)
uv run manage.py run-cycle --id 01 --auto
```

This will:
1.  Checkout `feat/cycle01`.
2.  Run the Coder Session (Implementation).
3.  **Run Tests**: Executes in the secure E2B Sandbox.
4.  **UAT Evaluation**: QA Analyst checks results.
5.  **Strict Auditing**: LLMReviewer runs to strictly audit the code.
6.  **Fixing**: If needed, Jules resumes the session to fix code and updates the PR.
7.  Commit if successful.

## Development (of this tool)

If you are contributing to the AC-CDD core itself:

*   The core logic is in `dev_src/ac_cdd_core`.
*   Run tests using: `uv run pytest tests/`
*   Linting: `uv run ruff check dev_src/`

## License

[License Name]
