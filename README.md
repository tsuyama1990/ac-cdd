# AI-Native Development Template

## 🚀 Getting Started (First Time Experience)

### 1. Prerequisites
Ensure you have the following tools installed:
- `uv` (Python Package Manager)
- `jules` & `gemini` (Google AI CLI Tools)

Run the doctor command to verify your environment:
```bash
uv run manage.py doctor
```

### 2\. Ad-hoc Workflow (Quick Fixes)

Use these commands for quick iterations outside of a formal cycle.

**Auto-Fix (Test Driven Repair):**
Runs tests and automatically assigns Jules to fix failures.

```bash
uv run manage.py fix
```

**Strict Audit (Code Review):**
Uses Gemini to strictly review your `git diff` and assigns Jules to implement fixes.

```bash
uv run manage.py audit
```

### 3\. Cycle-Based Workflow (Contract-Driven)

This is the core workflow for AC-CDD. It enforces strict compliance with specifications and contracts.

**1. Create a New Cycle:**
This generates a template workspace in `dev_documents/CYCLE{id}`.

```bash
uv run manage.py new-cycle "01"
```

Files created:
- `dev_documents/CYCLE01/SPEC.md`: Define your feature specifications here.
- `dev_documents/CYCLE01/schema.py`: Define your Pydantic contracts here (Single Source of Truth).
- `dev_documents/CYCLE01/UAT.md`: Define User Acceptance Testing scenarios.

**2. Start the Automation Loop:**
Once you have edited the files above, trigger the orchestrator.

```bash
uv run manage.py start-cycle "01"
```

The orchestrator will:
1.  **Plan**: Jules analyzes `ALL_SPEC.md` and formulates a detailed implementation plan (Planning Phase).
2.  **Align Contracts**: Update `src/ac_cdd/contracts`.
3.  **Generate Tests**: Create property-based tests from contracts.
4.  **Implement & Refine**: Coding loop with Jules (Coder) and Gemini (Auditor).
    - **Self-Healing**: If implementation fails repeatedly, the plan is automatically revised and re-executed.
5.  **Verify**: Run UAT with Playwright.

See `DEV_FLOW.md` for the full architectural details.
