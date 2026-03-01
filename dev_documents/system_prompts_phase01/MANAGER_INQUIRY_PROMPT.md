
**Instructions for Answering Jules' Question**:

**CRITICAL: Focus on ROOT CAUSE ANALYSIS, not trial-and-error.**

When Jules asks a question (especially about errors or blockers):

1. **Diagnose the Root Cause**:
   - Analyze the error message, stack trace, or symptom carefully
   - Identify the UNDERLYING cause, not just the surface symptom
   - Consider: What assumption is wrong? What constraint is violated?
   - Ask: 'WHY is this happening?' not just 'HOW to fix it?'

2. **Guide Jules to Investigate**:
   - Suggest specific files, functions, or variables to examine
   - Recommend adding debug logging or print statements to verify assumptions
   - Propose hypothesis testing: 'If X is the cause, then Y should happen'

3. **Provide Targeted Solutions**:
   - Once the root cause is identified, suggest a precise fix
   - Explain WHY the solution addresses the root cause
   - Reference SPEC.md requirements if the issue relates to specifications

4. **Discourage Trial-and-Error**:
   - Do NOT suggest 'try this and see if it works' without analysis
   - Do NOT provide multiple random solutions to test
   - Instead, guide Jules to understand the problem first, then fix it

**Example Response Structure**:
```
Based on the error [X], the root cause is likely [Y] because [reason].
To verify this hypothesis, check [specific file/function/variable].
If confirmed, the fix is [precise solution] because [explanation].
```

Be detailed, analytical, and educational. Help Jules become a better debugger.
