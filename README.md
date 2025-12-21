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
    *   An automated **Committee of Auditors** (powered by Aider/Fast Model) performs strict, multi-pass code reviews.
    *   The system iteratively fixes issues (using Aider/Smart Model) until the code passes strict quality gates.

*   **✅ Integrated Behavior-Driven UAT**
    *   Quality is not just about code style; it's about meeting requirements.
    *   The system automatically executes tests and verifies them against the behavior definitions in `UAT.md` before any merge.

*   **🤖 Hybrid Agent Orchestration**
    *   Combines the best of breed:
        *   **Google Jules**: For long-context architectural planning and initial implementation.
        *   **Aider**: For precise, SOTA code editing and repository-aware auditing.
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
*   `GEMINI_API_KEY` or `GOOGLE_API_KEY`: Required for Gemini models (Auditor, QA Analyst).
*   `OPENROUTER_API_KEY`: (Optional) Required if you use OpenRouter models.

#### Multi-Model Configuration

You can configure different models for different agents to optimize for cost and intelligence.

**Example `.env` configuration (Hybrid):**

```env
# Smart model for auditing (Gemini Pro)
SMART_MODEL=gemini-2.5-pro

# Fast model for QA analysis (Gemini Flash)
FAST_MODEL=gemini-2.5-flash

# Use OpenRouter for other agents if configured
OPENROUTER_API_KEY=sk-or-v1-...
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
3.  Run Tests (`pytest`).
4.  Perform UAT Evaluation (QA Analyst).
5.  Perform Strict Auditing (Auditor).
6.  Commit if successful.

## Development (of this tool)

If you are contributing to the AC-CDD core itself:

*   The core logic is in `dev_src/ac_cdd_core`.
*   Run tests using: `uv run pytest tests/`
*   Linting: `uv run ruff check dev_src/`

## License

[License Name]
