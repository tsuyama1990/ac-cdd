# Development Flow (AC-CDD)

## Graph Architecture

The core orchestration is handled by `LangGraph`.

```mermaid
stateDiagram-v2
stateDiagram-v2
    [*] --> CheckArtifacts
    CheckArtifacts --> Planner: No Artifacts
    CheckArtifacts --> SpecWriter: Artifacts Exist (Offline Plan)
    Planner --> SpecWriter: Reads ALL_SPEC.md -> Generates Cycle Plan
    SpecWriter --> Coder: Schema & Property Tests Ready

    state ImplementationLoop {
        Coder --> Tester: Code Implemented
        Tester --> Auditor: Tests Passed
        Tester --> Coder: Tests Failed (Fix)
        Auditor --> UAT: Strict Audit Passed
        Auditor --> Coder: Audit Failed (Fix)
    }

    UAT --> Coder: UAT Failed (Fix)
    UAT --> [*]: UAT Passed (Cycle Complete)
```

## Data Flow

1. **CycleState**: Passed between nodes, containing `cycle_id`, `plan`, `audit_result`, `sandbox_id`.
2. **Sandbox**:
   - `SandboxRunner` syncs `src/` and `tests/` to E2B.
   - Executes `pytest`, `ruff`, `mypy`.
   - Returns logs/exit codes to Graph.
3. **Local FS**:
   - Agents read/write source files locally.
   - "Source of Truth" is always local Git repo.

## Agents

- **Planner**: Architect (Gemini 2.5 Pro)
- **Coder**: Senior Engineer (Gemini 2.5 Flash)
- **QA Analyst**: Test Engineer (Gemini 2.5 Flash)
- **Auditor**: Security Specialist (Gemini 2.5 Pro)
