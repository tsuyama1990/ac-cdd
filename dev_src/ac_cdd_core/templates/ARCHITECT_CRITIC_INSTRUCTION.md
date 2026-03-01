# CRITIC PHASE: SELF-EVALUATION & CORRECTION

Excellent work generating the initial architecture and implementation plan.
Before we finalize this design, you **MUST** invoke your internal **Critic Agent** to thoroughly review your own work.

Please critically evaluate your proposed `SYSTEM_ARCHITECTURE.md` and `ALL_SPEC.md` against the following strict criteria:

### 1. Cyclic Dependencies and Implementation Order
- Check for circular dependencies between the defined implementation cycles.
- Each cycle MUST strictly depend **only** on previous, completed cycles.
- Is it actually possible to implement and test Cycle $N$ without needing components planned for Cycle $N+1$?

### 2. Implementation Volume & Feasibility
- Is any single cycle overwhelmingly large or overly complex?
- A cycle should represent a contained, testable unit of work. Break it down if it feels unrealistic for a single iteration.

### 3. Integration Risks & Interface Boundaries
- Are the interface boundaries between cycles clearly defined?
- Will the components built in Cycle 1 cleanly integrate with the components built in Cycle 4?

### 4. Over-engineering vs. Missing Requirements
- Is the architecture unnecessarily complex for the given requirements?
- Conversely, does the architecture adequately address all constraints, including database design, routing, security, and state management (where applicable)?

## INSTRUCTIONS FOR NEXT STEPS:
1. Write down your Critic Agent's findings in a new file named `ARCHITECT_CRITIC_REVIEW.md`.
2. Based on these findings, **adjust `ALL_SPEC.md` and `SYSTEM_ARCHITECTURE.md`** to fix any issues found.
3. Commit all changes (including the new review doc).
4. Push your changes and update the Pull Request.

If your Critic Agent finds absolutely no issues (which is rare), simply state so in `ARCHITECT_CRITIC_REVIEW.md` and declare the task complete.
