## Task Execution Steps
1.  **Analyze** the provided `ALL_SPEC.md` deeply.
2.  **Architect & Decompose:**
    * Design the global architecture following the instructions in `ARCHITECT_INSTRUCTION.md`.
    * **CRITICAL:** Break down the ENTIRE project into a sequence of logical cycles (CYCLE01, CYCLE02, ... CYCLE_N).
    * Ensure NO requirements are left behind. Every feature in `ALL_SPEC.md` must be assigned to a specific cycle.
3.  **Generate Artifacts:**
    * Create `SYSTEM_ARCHITECTURE.md` (containing the full roadmap) adhering to the strict format in `ARCHITECT_INSTRUCTION.md`.
    * Sequentially generate the document sets (`SPEC`, `UAT`, `schema.py`) for **EVERY** cycle defined in your roadmap.

## Output Strategy (Handling Long Content)
Since the full documentation will likely exceed output limits, strictly follow this procedure:

1.  **Phase 1:** Output `SYSTEM_ARCHITECTURE.md` first. This defines the roadmap.
2.  **Phase 2:** Output artifacts for **CYCLE01**, then **CYCLE02**, and so on reference the `SYSTEM_ARCHITECTURE.md`.
3.  **Stop Condition:**
    * If you can finish everything, output `plan_status.json` at the very end.
    * **If you reach the token limit:** Stop exactly at the end of a file block, write **`[TO BE CONTINUED]`**, and wait for my prompt to continue.
    * **DO NOT** summarize or skip cycles to save space. Quality is priority.

## Output Format
Please start the output using the following format:

````markdown
# ARCHITECTURE & CYCLE PLANNING REPORT

## 1. `dev_documents/SYSTEM_ARCHITECTURE.md`
```markdown
(Content: Follow the strict format defined in ARCHITECT_INSTRUCTION.md)
```

## 2. `dev_documents/CYCLE{xx}/SPEC.md` (For EACH Cycle)
```markdown
(Content for CYCLE{xx})
```

## 3. `dev_documents/CYCLE{xx}/UAT.md` (For EACH Cycle)
```markdown
(Content for CYCLE{xx})
```

## 4. `dev_documents/plan_status.json`
```json
{
  "status": "completed",
  "cycles": ["01", "02", "03", "..."]
}
``` 