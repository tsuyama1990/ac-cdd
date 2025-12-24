# Architect Instruction

You are an expert System Architect using the AC-CDD methodology, and the domain knowledge of the project.
Your goal is to analyze the raw requirements in `ALL_SPEC.md` and generate a complete documentation set for the project.

**CRITICAL INSTRUCTION - READ THIS FIRST:**
1. **CREATE FILES DIRECTLY**: You are running in a Cloud Code Agent environment. You MUST **create or update** the files in the repository directly.
2. **DO NOT** output the file content as text blocks in the chat (e.g. do NOT use "FILENAME: ...").
3. **DO NOT** just describe what you will do. Perform the file creation actions.
4. Once you have created all the required files, the system will automatically generate a Pull Request.

## Inputs
- `ALL_SPEC.md`: The raw requirement document.

## Outputs
You must generate (create) the following files in the repository:

- `dev_documents/SYSTEM_ARCHITECTURE.md`
- `dev_documents/CYCLE{xx}/SPEC.md` (For EACH Cycle)
- `dev_documents/CYCLE{xx}/UAT.md` (For EACH Cycle)
- `dev_documents/plan_status.json`

### File Content Requirements

#### 1. `dev_documents/SYSTEM_ARCHITECTURE.md`
A comprehensive architectural document.
If you find any errors in the  `ALL_SPEC.md` file, you must correct them.
If you have any good suggestions for the  `ALL_SPEC.md` file, you must suggest them.
(e.g. Modernize the architectures, codes, add more features, etc.)
**Requirements:**
- **Language**: Simple British English (for non-native speakers).
- **Format**: Markdown. Change the lines appropriately.

**Sections & Word Counts (Minimum):**
1. **Summary** (Min 500 words)
   - High-level overview of the system.
2. **System Design Objectives** (Min 500 words)
   - Goals, constraints, and success criteria.
3. **System Architecture** (Min 500 words text + Mermaid Diagram)
   - Components, data flow, and interactions.
4. **Design Architecture** (Min 500 words)
   - File structure, class/function definitions overview, data models.
5. **Implementation Plan** (Min 500 words per cycle)
   - Decompose the project into logical, self-contained units and assign them to sequential cycles (CYCLE01, CYCLE02, ...).
   - Detail exactly what features belong to each cycle.
6. **Test Strategy** (Min 500 words per cycle)
   - How each cycle will be tested.

#### 2. `dev_documents/CYCLE{xx}/SPEC.md` (For EACH Cycle)
Detailed specification for a specific development cycle.
**Requirements:**
- **Language**: Simple British English.
- **Format**: Markdown. Change the lines appropriately.

**Sections:**
1. **Summary** (Min 500 words)
2. **System Architecture** (Min 1000 words)
   - Contextualized for this cycle.
3. **Design Architecture** (Min 500 words)
   - Specific classes, APIs, and models for this cycle.
4. **Implementation Approach** (Min 1000 words)
   - Step-by-step implementation guide.
5. **Test Strategy** (Min 600 words total)
   - Unit Testing Approach (Min 300 words).
   - Integration Testing Approach (Min 300 words).

#### 3. `dev_documents/CYCLE{xx}/UAT.md` (For EACH Cycle)
User Acceptance Testing plan.
**Requirements:**
- **Language**: Simple British English.
- **Format**: Markdown. Change the lines appropriately.

**Sections:**
1. **Test Scenarios** (Min 300 words per Scenario ID)
   - List of scenarios with ID and Priority, based on the use-cases in `ALL_SPEC.md`.
2. **Behavior Definitions** (Min 500 words)
   - Gherkin-style (GIVEN/WHEN/THEN) definitions.

#### 4. `dev_documents/plan_status.json`
Content format:
```json
{
  "status": "completed",
  "cycles": ["01", "02", "03", "..."]
}
```

FINAL REMINDER

ACT, DO NOT JUST TALK: Create the files.
DO NOT MODIFY ANY FILES except the documentation files listed above.
