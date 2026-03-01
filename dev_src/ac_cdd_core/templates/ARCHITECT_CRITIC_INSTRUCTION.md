# CRITIC PHASE: SELF-EVALUATION & CORRECTION

Excellent work generating the initial architecture and implementation plan.
Before we finalize this design, you **MUST** invoke your internal **Critic Agent** to thoroughly review your own work.

Please critically evaluate your proposed `SYSTEM_ARCHITECTURE.md` (and any other design documents you created) against the original requirements in `ALL_SPEC.md`.
**IMPORTANT:** Do NOT modify `ALL_SPEC.md`. Treat it as the absolute source of truth provided by the user.

You must perform your review in the following strict two-step process:

### 1. Verification of the Optimal Approach
First, evaluate whether `SYSTEM_ARCHITECTURE.md` truly represents the absolute best approach to realize `ALL_SPEC.md`.
- Did you explore all possible methodologies, and is this truly the most optimal, modern, and robust realization?
- Are the chosen frameworks, libraries, and design patterns the most appropriate and state-of-the-art for this specific use case?
- Thoroughly verify the technical feasibility. Is there a better, simpler, or more performant way to achieve the exact same user requirements defined in `ALL_SPEC.md`?

### 2. Precision of Cycle Breakdown and Design Details
Second, verify that the high-level architecture defined in `SYSTEM_ARCHITECTURE.md` is accurately, precisely, and exhaustively broken down into the individual implementation cycles.
- Is every single component, data model, and API endpoint defined in the architecture explicitly accounted for in the cycle plan?
- Are the design details and specifications for each cycle precise enough that a developer could implement them without ambiguity?
- Check for circular dependencies between the defined implementation cycles. Is it actually possible to implement and test each cycle completely independently, relying only on previously completed cycles?
- Are the interface boundaries between components and cycles clearly defined?

## INSTRUCTIONS FOR NEXT STEPS:
1. Write down your Critic Agent's deep validation and findings in a new file named `ARCHITECT_CRITIC_REVIEW.md`. Document alternative approaches you considered and why your final approach is superior.
2. Based on your findings, **adjust `SYSTEM_ARCHITECTURE.md` (and other related plans, EXCEPT `ALL_SPEC.md`)** to fix any suboptimal designs, missing details, or vague cycle plans.
3. Commit all changes (including the new review doc).
4. Push your changes and update the Pull Request.

If your Critic Agent confidently concludes that this architecture is already the absolute best possible approach and that the cycle plans are perfectly precise with no room for improvement, state the rationale in `ARCHITECT_CRITIC_REVIEW.md` and declare the task complete.
