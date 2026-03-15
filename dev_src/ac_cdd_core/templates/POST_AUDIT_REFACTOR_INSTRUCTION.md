# Post-Audit Final Refactoring Instruction

The **Committee of Auditors** has already reviewed and **APPROVED** your functional implementation for **Cycle {{cycle_id}}**. 

Your current logic is correct and meets the requirements. However, this is the **Final Refactoring Phase** for this cycle. Your mission is to take this approved code and refine it into a "Production-Grade" masterpiece.

# CORE PRINCIPLE: HIERARCHICAL DESIGN (Thinking Protocol)
You must follow the architectural hierarchy in your reasoning process:
1. **Global Vision** (`SYSTEM_ARCHITECTURE.md`): Ensure your cycle-level optimizations contribute to the global robustness of the system.
2. **Detailed Design** (`SPEC.md`): Align the final code with a perfectly refined specification.
3. **Code Blueprint** (Schema/Pydantic): Polish the schemas to ensure strict data integrity and optimal typing.
4. **Verification Design** (Tests): Ensure tests reflect the final, polished architecture.

**THINKING BLOCK REQUIREMENT**: At the beginning of your response, you MUST include a `<thought>` block where you analyze the implementation from a holistic perspective and define your "Polish Strategy" before starting refactoring.

# Objectives
1. **Elegant Refactoring**: Optimize for readability, maintainability, and architectural purity without breaking the approved logic.
2. **DRY & SOLID**: Identify any patterns that can be further simplified or decoupled.
3. **Nitpicking for Quality**: Improve variable naming, add missing type hints (ensure 100% coverage), and ensure docstrings are helpful.
4. **Performance Check**: Perform a micro-audit for any O(N^2) loops or excessive I/O that can be optimized now before the final merge.

# Critical Constraints
- **ZERO TOLERANCE FOR MOCKS**: Ensure no `TODO`, `FIXME`, `pass`, or `...` escaped the Audit. If you find any, fix them for real now.
- **SYSTEM INTEGRITY**: Do NOT delete or modify the `.ac_cdd/` directory. Ensure it is in `.gitignore`.
- **PRESERVE BEHAVIOR**: Since the Audit passed, DO NOT change the functional behavior or external API of the logic. Only improve the *internal* quality.

# Process
1. **Holistic Review & Context Gathering**: 
   - Read `SYSTEM_ARCHITECTURE.md`, `ALL_SPEC.md`, and **ALL** individual cycle specification files (specifically `dev_documents/system_prompts/CYCLE{{cycle_id}}/SPEC.md`).
   - Read all existing source code and tests implemented so far.
2. **Architectural Optimization**: 
   - Analyze the whole system to determine if the current cycle's design can be further optimized for better integration and long-term maintainability.
3. **Spec Alignment (Documentation First)**: 
   - Based on your optimized plan, **rewrite the current cycle's `dev_documents/system_prompts/CYCLE{{cycle_id}}/SPEC.md`** if necessary. The `SPEC.md` must accurately reflect the final, superior architecture you intend to deliver.
4. **Foundation Refactoring**: 
   - Update **Pydantic schemas** and **pytest** suites to align with the refined architecture. Ensure the contracts are ironclad.
5. **Coding & Polishing**: 
   - Refactor the business logic to fit the new schemas and spec. Polish for maximum elegance.
6. **Verification**: 
   - Run `ruff check`, `ruff format`, `mypy`, and `pytest`. 
7. **Production Gate (Self-Review)**: 
   - Ensure the code is something you would be proud to put into a mission-critical, high-scale production environment. 

Start by stating your final refinement plan: "The Audit has passed. I have reviewed the system architecture and all cycle specs, and I'm ready to perform the final polish..."
