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
    *   An automated **Committee of Auditors** (3 independent auditors, each reviewing 2 times) performs strict, multi-pass code reviews.
    *   The system iteratively fixes issues (using Jules via session resumption) until the code passes all auditors' quality gates.
    *   **Total: 6 audit-fix cycles** per development cycle for maximum code quality.

*   **🔒 Secure Sandboxed Execution**
    *   **Fully Remote Architecture**: All code execution, testing, and AI-based fixing happens inside a secure, ephemeral **E2B Sandbox**.
    *   Your local environment stays clean. No need to install complex dependencies locally.
    *   The system automatically syncs changes back to your local machine.

*   **✅ Integrated Behavior-Driven UAT**
    *   Quality is not just about code style; it's about meeting requirements.
    *   The system automatically executes tests and verifies them against the behavior definitions in `UAT.md` before any merge.

*   **🤖 Hybrid Agent Orchestration**
    *   Combines the best of breed:
        *   **Google Jules**: For long-context architectural planning, initial implementation, and iterative refinement (fixing).
        *   **LLMReviewer**: For fast, direct API-based code auditing using various LLM providers.
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
*   *Note: All AI agents (Jules, LLMReviewer) operate remotely or via API. No local AI CLI tools required.*

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

*   `JULES_API_KEY`: Required for the Jules autonomous agent (Architect, Coder, Fixer).
*   `E2B_API_KEY`: Required for the secure sandbox environment.
*   `GEMINI_API_KEY` or `GOOGLE_API_KEY`: Required for Gemini models (LLMReviewer Auditor, QA Analyst).
*   `ANTHROPIC_API_KEY`: Optional. Required if using Claude models directly (can use OpenRouter instead).
*   `OPENROUTER_API_KEY`: Optional. Recommended for unified access to multiple model providers.

#### Multi-Model Configuration

You can configure different models for different agents to optimize for cost and intelligence.

**Example `.env` configuration (Hybrid):**

```env
# Smart model for Jules (fixing/refinement) - High capability required
SMART_MODEL=claude-3-5-sonnet-20241022

# Fast model for LLMReviewer (auditing) & QA Analyst - Speed & context required
FAST_MODEL=gemini-2.0-flash-exp

# API Keys
JULES_API_KEY=your_jules_key
E2B_API_KEY=e2b_...
OPENROUTER_API_KEY=sk-or-...
```

## 🚀 Usage

### 1. Initialize Project

```bash
uv run manage.py init
```

Edit `dev_documents/ALL_SPEC.md` with your project requirements.

### 2. Generate Architecture & Start Session

```bash
uv run manage.py gen-cycles
```

This creates a **development session** with:
- Integration branch: `dev/session-{timestamp}`
- Architecture branch: `dev/session-{timestamp}/arch`
- System architecture and cycle plans

**Session is saved** to `.ac_cdd_session.json` for automatic resumption.

### 3. Run Development Cycles

```bash
# Run individual cycles (session auto-loaded)
uv run manage.py run-cycle --id 01
uv run manage.py run-cycle --id 02

# Or run all cycles sequentially
uv run manage.py run-cycle --id all --auto
```

Each cycle:
- Creates branch: `dev/session-{timestamp}/cycle{id}`
- Implements features via Jules
- Runs **6 audit-fix cycles** (3 auditors × 2 reviews each)
- Auto-merges to **integration branch** (not main)

### 4. Finalize Session

```bash
uv run manage.py finalize-session
```

Creates a **final Pull Request** from integration branch to `main`:
- Contains all architecture + cycle implementations
- Enables batch review of entire session
- Merge to deploy to production

**Session-Based Workflow Benefits:**
- ✅ Isolated development - work doesn't pollute `main`
- ✅ Batch review - review entire session at once
- ✅ Easy rollback - delete integration branch to abandon session
- ✅ Clean history - squash merge to `main`

## Development (of this tool)

If you are contributing to the AC-CDD core itself:

*   The core logic is in `dev_src/ac_cdd_core`.
*   Run tests using: `uv run pytest tests/`
*   Linting: `uv run ruff check dev_src/`

## License

[License Name]
