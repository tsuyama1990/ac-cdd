# Autonomous Development Environment (AC-CDD)

> An AI-Native Cycle-Based Contract-Driven Development Environment.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![Powered by LangGraph](https://img.shields.io/badge/powered_by-LangGraph-green)](https://github.com/langchain-ai/langgraph)
[![Powered by Jules](https://img.shields.io/badge/powered_by-Google_Jules-4285F4)](https://jules.google.com)

## Key Features

*   **🚀 Automated Rapid Application Design (Auto-RAD)**
    *   Just define your raw requirements in `ALL_SPEC.md`.
    *   The `gen-cycles` command automatically acts as an **Architect**, generating `SYSTEM_ARCHITECTURE.md`, detailed `SPEC.md`, and `UAT.md` (User Acceptance Tests) for every development cycle.

*   **🛡️ Committee of Code Auditors**
    *   No more "LGTM" based on loose checks.
    *   An automated **Committee of Auditors** (3 independent audit passes) performs strict, multi-pass code reviews.
    *   The system iteratively fixes issues until the code passes ALL auditors' quality gates.
    *   **Total: Up to 6 audit-fix cycles** (3 auditors × 2 reviews each) per development cycle for maximum code quality.

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

## Deployment Architecture

AC-CDD is designed as a **containerized CLI tool**. You do not clone the tool's source code into your project. Instead, you run the AC-CDD Docker container, which mounts your project directory.

**Directory Structure on User's Host:**

```
📂 my-awesome-app/ (Your Repository)
 ├── 📂 src/              <- Your source code
 ├── 📂 dev_documents/    <- Specifications (ALL_SPEC.md, etc.)
 ├── .env                 <- API Keys
 └── docker-compose.yml   <- Runner configuration
```

**Inside the Docker Container:**

```
[🐳 ac-cdd-core]
 ├── /app (WORKDIR)       <- Your project is mounted here
 ├── /opt/ac-cdd/templates <- Internal system prompts & resources
 └── Python Environment   <- uv, LangGraph, Agents pre-installed
```

## Getting Started

### Prerequisites

*   Docker Desktop or Docker Engine
*   `git`
*   `gh` (GitHub CLI) - Required for authentication with GitHub

### Installation

1.  **Setup `docker-compose.yml`:**
    Download the distribution `docker-compose.yml` to your project root, or create one:

    ```yaml
    services:
      ac-cdd:
        image: tsuyama1990/ac-cdd-agent:latest
        container_name: ac-cdd-agent
        volumes:
          - .:/app
          - ${HOME}/.ac_cdd/.env:/root/.ac_cdd/.env
        env_file:
          - .env
        environment:
          - HOST_UID=${UID:-1000}
          - HOST_GID=${GID:-1000}
        command: ["ac-cdd"]
        stdin_open: true
        tty: true
    ```

2.  **Create an Alias (Recommended):**
    Add this to your shell profile (`.zshrc` or `.bashrc`) for easy access:
    ```bash
    alias ac-cdd='docker-compose run --rm ac-cdd'
    ```

3.  **Setup GitHub Authentication:**
    
    The Docker container needs access to your Git credentials for pushing branches and creating PRs.
    
    **Recommended: Use GITHUB_TOKEN in .ac_cdd/.env**
    
    ```bash
    # Get your GitHub token
    gh auth token
    
    # Add it to .ac_cdd/.env
    echo "GITHUB_TOKEN=$(gh auth token)" >> .ac_cdd/.env
    ```
    
    The `docker-compose.yml` automatically mounts:
    - `~/.ssh` - Your SSH keys (for SSH-based authentication)
    - `SSH_AUTH_SOCK` - SSH agent socket for key forwarding
    
    **Note**: We intentionally do NOT mount `~/.gitconfig` or `~/.config/gh` to avoid conflicts with host-specific `gh auth git-credential` configurations. The GITHUB_TOKEN-based credential store is sufficient for all Git operations.


### Configuration

The system is configured via environment variables. Run `ac-cdd init` to generate a `.env.example` file in the `.ac_cdd/` directory with all necessary configuration options.

#### Quick Setup

1. **Initialize your project:**
   ```bash
   ac-cdd init
   ```

2. **Copy the example configuration:**
   ```bash
   cp .ac_cdd/.env.example .ac_cdd/.env
   ```

3. **Fill in your API keys in `.ac_cdd/.env`**

4. **Verify your configuration:**
   ```bash
   ac-cdd env-verify
   ```

#### API Keys

The `.env` file should contain:

```env
# Required API Keys
JULES_API_KEY=your-jules-api-key-here
E2B_API_KEY=your-e2b-api-key-here
OPENROUTER_API_KEY=your-openrouter-api-key-here

# Simplified Model Configuration
# These two settings control ALL agents (Auditor, QA Analyst, Reviewer, etc.)
SMART_MODEL=openrouter/meta-llama/llama-3.3-70b-instruct:free
FAST_MODEL=openrouter/nousresearch/hermes-3-llama-3.1-405b:free
```

#### Model Configuration (Simplified)

You only need to set **two environment variables** for model configuration:

- **`SMART_MODEL`**: Used for complex tasks (code editing, architecture, auditing)
- **`FAST_MODEL`**: Used for reading and analysis tasks

**Supported Model Formats:**
- OpenRouter: `openrouter/provider/model-name`
- Anthropic: `claude-3-5-sonnet`
- Gemini: `gemini-2.0-flash-exp`

**Advanced Configuration (Optional):**

If you need fine-grained control over specific agents, you can override individual models:

```env
# Override specific agent models (optional)
AC_CDD_AGENTS__AUDITOR_MODEL=openrouter/meta-llama/llama-3.3-70b-instruct:free
AC_CDD_AGENTS__QA_ANALYST_MODEL=openrouter/meta-llama/llama-3.3-70b-instruct:free

# Override reviewer models (optional)
AC_CDD_REVIEWER__SMART_MODEL=claude-3-5-sonnet
AC_CDD_REVIEWER__FAST_MODEL=gemini-2.0-flash-exp

# Choose auditor model mode (optional, default: "fast")
# Options: "smart" (thorough but slower) or "fast" (quicker but less thorough)
AC_CDD_AUDITOR_MODEL_MODE=fast
```

## 🚀 Usage

### 1. Initialize Project

Navigate to your empty project folder and run:

```bash
ac-cdd init
```

This creates the `dev_documents/` structure and `pyproject.toml` (if missing) in your current directory.

**Next Step:** Edit `dev_documents/ALL_SPEC.md` with your raw project requirements.

### 2. Generate Architecture & Start Session

```bash
ac-cdd gen-cycles
```

This acts as the **Architect**:
- Reads `ALL_SPEC.md`
- Generates `SYSTEM_ARCHITECTURE.md`, `SPEC.md`, and `UAT.md`
- Creates an **integration branch** (e.g., `dev/int-{timestamp}`)

**Session state is saved** to `.ac_cdd/project_state.json` for automatic resumption.

### 3. Run Development Cycles

```bash
# Run individual cycles (automated auditing enabled by default)
ac-cdd run-cycle --id 01
ac-cdd run-cycle --id 02

# Or run all cycles sequentially
ac-cdd run-cycle --id all

# Disable automated auditing (not recommended)
ac-cdd run-cycle --id 01 --no-auto
```

Each cycle:
- Implements features via Jules on a temporary branch targeting the integration branch
- Runs **Committee of Auditors** automatically (3 auditors × 2 reviews each)
- Auto-merges successful PRs down to the **integration branch** (not main)

### 4. Finalize Session

```bash
ac-cdd finalize-session
```

Creates a **final Pull Request** from integration branch to `main`.

## 📝 Customizing Prompts (Template Overrides)

AC-CDD uses a layered template system. Every prompt sent to Jules or the auditing agents is loaded from a Markdown template file, which means you can **override any prompt** without touching the core codebase.

### How It Works

Template lookup priority (highest to lowest):

1. **Your project override**: `dev_documents/system_prompts/<TEMPLATE_NAME>.md`
2. **Built-in default**: bundled inside the AC-CDD package

If the file exists in your project's `dev_documents/system_prompts/`, it takes precedence over the built-in default.

### Available Templates

#### Agent Instruction Templates (Main Prompts)

| File | Used By | Description |
|---|---|---|
| `CODER_INSTRUCTION.md` | Jules (Coder) | Main prompt for the Coder agent when implementing features |
| `REFACTOR_INSTRUCTION.md` | Jules (Coder) | Prompt used during refactoring cycles |
| `AUDITOR_INSTRUCTION.md` | LLM Reviewer | Code review instructions for the Auditor agent |
| `ARCHITECT_INSTRUCTION.md` | Architect node | System design and cycle planning instructions |
| `MANAGER_INSTRUCTION.md` | Manager Agent | Orchestration and decision-making instructions |
| `QA_TUTORIAL_INSTRUCTION.md` | QA Agent | Instructions for generating UAT test scripts |
| `QA_AUDITOR_INSTRUCTION.md` | QA Auditor | Instructions for reviewing test results |

#### Jules Interaction Templates (Message Prompts)

These control what AC-CDD *says to Jules* during a session:

| File | Used When | Description |
|---|---|---|
| `AUDIT_FEEDBACK_MESSAGE.md` | After Auditor rejects a PR | Message sent to an existing Jules session asking it to fix issues. Supports `{{feedback}}` variable. |
| `AUDIT_FEEDBACK_INJECTION.md` | When creating a new session after rejection | Appended to the new session's instructions with prior audit feedback. Supports `{{feedback}}` and `{{pr_url}}` variables. |
| `PR_CREATION_REQUEST.md` | When session completes without a PR | Message sent to Jules to request manual PR creation |
| `MANAGER_INQUIRY_PROMPT.md` | When Jules asks a question | Instructions given to the Manager Agent for answering Jules' questions |
| `MANAGER_INQUIRY_FOLLOWUP.md` | After Manager Agent answers Jules | Note appended to agent replies, reminding Jules to proceed |
| `MANAGER_INQUIRY_FALLBACK.md` | When Manager Agent fails | Fallback message sent to Jules if the agent errors. Supports `{{question}}` variable. |
| `PLAN_REVIEW_PROMPT.md` | When Jules requests plan approval | Instructions for the Manager Agent to review Jules' implementation plan |

### Example: Customizing the Audit Feedback

To change how AC-CDD communicates audit results to Jules, create a file in your project:

```bash
mkdir -p dev_documents/system_prompts
cat > dev_documents/system_prompts/AUDIT_FEEDBACK_MESSAGE.md << 'EOF'
# AUDIT FEEDBACK - ACTION REQUIRED

The following issues were identified in your implementation:

{{feedback}}

**Please:**
1. Read each issue carefully
2. Implement the necessary changes
3. Create a new Pull Request when done
EOF
```

### Template Variables

Some templates support `{{variable}}` substitution:

| Variable | Available In | Description |
|---|---|---|
| `{{feedback}}` | `AUDIT_FEEDBACK_MESSAGE.md`, `AUDIT_FEEDBACK_INJECTION.md` | The full audit feedback text |
| `{{pr_url}}` | `AUDIT_FEEDBACK_INJECTION.md` | URL of the previous PR (wrapped in `{{#pr_url}}...{{/pr_url}}` for conditional rendering) |
| `{{question}}` | `MANAGER_INQUIRY_FALLBACK.md` | Jules' original question when the manager agent fails |

## Contributing

If you want to modify the AC-CDD framework itself:

1.  Clone this repository.
2.  Modify code in `dev_src/ac_cdd_core`.
3.  Rebuild the Docker image: `docker build -t ac-cdd .`
4.  Run tests: `uv run pytest tests/ac_cdd/unit -q`
5.  Read the **[Developer Guide](./README_DEVELOPER.md)** for details on extending LangGraph flows, adding nodes, and working with templates.

## License

This project is licensed under the **MIT License** — see the [LICENSE](./LICENSE) file for details.
