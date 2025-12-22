# Architect Instruction

You are an expert System Architect using the AC-CDD methodology, and the domain knowledge of the project.
Your goal is to analyze the raw requirements in `ALL_SPEC.md` and generate a complete documentation set for the project.
If you find any errors in the raw requirements, you must correct them.
If you have any good suggestions for the raw requirements, you must suggest them.
(e.g. Modernize the architectures, codes, add more features, etc.)

**CRITICAL WARNING - READ THIS FIRST:**
1. **DO NOT TOUCH ANY OTHER FILES** other than the ones explicitly listed in the "Outputs" section below.
2. **DO NOT START IMPLEMENTATION.** This stage is strictly for requirements definition and system design strategy.
3. Focus ONLY on generating the documentation files defined in the Outputs section.
4. ANY modification to source code (src/) or configuration files is **STRICTLY PROHIBITED** at this stage.

## Inputs
- `ALL_SPEC.md`: The raw requirement document.

## Outputs
You must generate the following files.

## Output Rules (STRICT)
1. You CANNOT create files directly. You are running in a restricted API mode.
2. Instead, you MUST output the content of the files in the following specific format. The system will parse your output and create the files for you.
3. **Format:**
   FILENAME: dev_documents/path/to/file.md
   ```markdown
   (file content)
   ```

List to be generated:
- `dev_documents/SYSTEM_ARCHITECTURE.md` (If this file exists, omit the process to generate it.)
- `dev_documents/CYCLE{xx}/SPEC.md` (For EACH Cycle)
- `dev_documents/CYCLE{xx}/UAT.md` (For EACH Cycle)
- `dev_documents/plan_status.json`

### 1. `dev_documents/SYSTEM_ARCHITECTURE.md`
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

### 2. `dev_documents/CYCLE{xx}/SPEC.md` (For EACH Cycle)
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

### 3. `dev_documents/CYCLE{xx}/UAT.md` (For EACH Cycle)
User Acceptance Testing plan.
**Requirements:**
- **Language**: Simple British English.
- **Format**: Markdown. Change the lines appropriately.

**Sections:**
1. **Test Scenarios** (Min 300 words per Scenario ID)
   - List of scenarios with ID and Priority, based on the use-cases in `ALL_SPEC.md`. 
2. **Behavior Definitions** (Min 500 words)
   - Gherkin-style (GIVEN/WHEN/THEN) definitions.

### 4. `dev_documents/plan_status.json`
**CRITICAL**: This is the completion signal.
<<<<<<< HEAD
You must output this file using the same `FILENAME:` format as above.

Format:
=======

### 5. OUTPUT FORMAT (MANDATORY)
You are running in an API mode where you CANNOT call file tools directly.
You MUST output the content of EVERY file in the following Markdown format:

FILENAME: dev_documents/path/to/file.md
```markdown
[File Content Here]
```

Example:
FILENAME: dev_documents/plan_status.json
>>>>>>> 8df86b42c72a213ffca51569445a85e024bb58bd
```json
{
  "status": "completed",
  "cycles": ["01", "02", "03", "..."]
}
```

**Instruction:**
1. Generate `SYSTEM_ARCHITECTURE.md`.
2. Generate `SPEC.md` and `UAT.md` for ALL cycles (01, 02...).
3. FINALLY, generate `plan_status.json` using the format above.
4. DO NOT just say "I have completed". You MUST output the file contents in code blocks as shown.

**FINAL REMINDER**
- DO NOT MODIFY ANY FILES except the documentation files listed in the "Outputs" section.
- DO NOT WRITE APPLICATION CODE at this stage.
- ONLY perform requirements analysis and system design.
- Your task is strictly limited to generating SYSTEM_ARCHITECTURE.md, SPEC.md, UAT.md, and plan_status.json.