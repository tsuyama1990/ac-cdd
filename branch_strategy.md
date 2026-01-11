# AC-CDD Branch Strategy

Complete branch management strategy for the AC-CDD workflow.

---

## Table of Contents

1. [Overview](#overview)
2. [Branch Types](#branch-types)
3. [Workflow Phases](#workflow-phases)
4. [Branch Naming Conventions](#branch-naming-conventions)
5. [PR Strategy](#pr-strategy)
6. [Rollback Strategy](#rollback-strategy)
7. [Best Practices](#best-practices)

---

## Overview

### Design Philosophy

AC-CDD uses a **integration-first** branch strategy where:

1. **Main branch is protected** - Only receives final, validated implementations
2. **Integration branch is the working base** - All development happens here
3. **Temporary branches are short-lived** - Created by Jules, merged and deleted
4. **Rollback is easy** - Failed sessions can be discarded entirely

### Key Principles

- ✅ **Isolation**: Each session has its own integration branch
- ✅ **Accumulation**: Cycles build on each other within integration branch
- ✅ **Safety**: Main branch only receives completed, tested implementations
- ✅ **Simplicity**: Clear naming conventions and minimal branch types

---

## Branch Types

### 1. Main Branch

**Name**: `main`

**Purpose**: Production-ready code

**Characteristics**:
- Protected branch
- Only receives squash merges from integration branches
- Never directly modified during AC-CDD workflow
- Always in a deployable state

**Lifetime**: Permanent

---

### 2. Integration Branch

**Name**: `dev/int-{YYYYMMDD-HHMM}`

**Example**: `dev/int-20260111-2130`

**Purpose**: Working base for a complete development session

**Characteristics**:
- Created at the start of `gen-cycles`
- Receives all architecture and cycle PRs
- Acts as "main" for the duration of the session
- Can be discarded if session fails
- Merged to main only after all cycles complete successfully

**Lifetime**: From `gen-cycles` to `finalize-session`

**Created by**: `workflow.py` (gen-cycles)

**Merged to**: `main` (manual, squash merge)

---

### 3. Jules's Architecture Branch

**Name**: `jules/arch-{session_id}`

**Example**: `jules/arch-13699060115265162899`

**Purpose**: Architecture document generation

**Characteristics**:
- Created by Jules during `gen-cycles`
- Contains SPEC.md and UAT.md files
- Short-lived (deleted after merge)

**Lifetime**: Minutes to hours

**Created by**: Jules (Google AI)

**Merged to**: Integration branch (auto-merge after approval)

---

### 4. Jules's Cycle Implementation Branches

**Name**: `jules/c{XX}-{session_id}`

**Example**: `jules/c01-13699060115265162899`, `jules/c02-13699060115265162899`

**Purpose**: Individual cycle implementation

**Characteristics**:
- Created by Jules during `run-cycle`
- Contains source code, tests, and documentation
- Short-lived (deleted after merge)
- Each cycle builds on previous cycles

**Lifetime**: Minutes to hours

**Created by**: Jules (Google AI)

**Merged to**: Integration branch (auto-merge after approval)

---

## Workflow Phases

### Phase 1: gen-cycles

**Purpose**: Generate architecture and create integration branch

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Create Integration Branch                               │
│    main → dev/int-20260111-2130                            │
└─────────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Jules Generates Architecture                            │
│    - Checkout: dev/int-20260111-2130                       │
│    - Jules creates: jules/arch-13699060115265162899        │
│    - Files: SPEC.md, UAT.md for all cycles                │
└─────────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Create PR                                                │
│    jules/arch-13699060115265162899 → dev/int-20260111-2130 │
└─────────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Auto-Merge (after approval)                             │
│    Architecture files now in integration branch            │
└─────────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. Save Manifest                                            │
│    integration_branch: dev/int-20260111-2130               │
└─────────────────────────────────────────────────────────────┘
```

**Branch State After gen-cycles**:
```
main (unchanged)

dev/int-20260111-2130 (integration branch)
  ← Contains architecture files
  ← Ready for cycle implementations

jules/arch-13699060115265162899 (deleted after merge)
```

---

### Phase 2: run-cycle (Single Cycle)

**Purpose**: Implement one cycle

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Checkout Integration Branch                             │
│    git checkout dev/int-20260111-2130                      │
└─────────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Jules Implements Cycle                                  │
│    - Starting branch: dev/int-20260111-2130                │
│    - Jules creates: jules/c01-13699060115265162899         │
│    - Files: Source code, tests, logs                       │
└─────────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Create PR                                                │
│    jules/c01-13699060115265162899 → dev/int-20260111-2130  │
└─────────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Auditor Reviews Code                                    │
│    - Compare against integration branch                    │
│    - Provide feedback if needed                            │
└─────────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. Auto-Merge (after approval)                             │
│    Cycle 01 code now in integration branch                 │
└─────────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. Update Manifest                                          │
│    cycle_01: status = "completed"                          │
└─────────────────────────────────────────────────────────────┘
```

**Branch State After Cycle 01**:
```
dev/int-20260111-2130 (integration branch)
  ← Contains architecture + Cycle 01 code
  ← Ready for Cycle 02

jules/c01-13699060115265162899 (deleted after merge)
```

---

### Phase 3: run-cycle --id all

**Purpose**: Implement all cycles sequentially

```
For each cycle (01 → 08):
  ┌─────────────────────────────────────────────────┐
  │ Checkout Integration Branch                    │
  │ (contains all previous cycles)                 │
  └─────────────────────────────────────────────────┘
                    ↓
  ┌─────────────────────────────────────────────────┐
  │ Jules Implements Current Cycle                  │
  │ jules/c{XX}-{session_id}                       │
  └─────────────────────────────────────────────────┘
                    ↓
  ┌─────────────────────────────────────────────────┐
  │ Create PR → Integration Branch                 │
  └─────────────────────────────────────────────────┘
                    ↓
  ┌─────────────────────────────────────────────────┐
  │ Auditor Reviews                                 │
  └─────────────────────────────────────────────────┘
                    ↓
  ┌─────────────────────────────────────────────────┐
  │ Auto-Merge                                      │
  │ Integration branch accumulates changes         │
  └─────────────────────────────────────────────────┘
                    ↓
  Next Cycle (builds on previous)
```

**Key Point**: Each cycle starts with **all previous cycles' code** because they were auto-merged.

**Branch State After All Cycles**:
```
dev/int-20260111-2130 (integration branch)
  ← Contains architecture + Cycles 01-08
  ← Ready for final review

jules/c01-65162899 (deleted)
jules/c02-65162899 (deleted)
...
jules/c08-65162899 (deleted)
```

---

### Phase 4: finalize-session

**Purpose**: Merge integration branch to main

```
┌─────────────────────────────────────────────────────┐
│ 1. Manual Review                                    │
│    Review entire integration branch                │
└─────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────┐
│ 2. Create Final PR                                  │
│    dev/int-20260111-2130 → main                    │
└─────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────┐
│ 3. Squash Merge to Main                            │
│    All cycles compressed into single commit        │
└─────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────┐
│ 4. Delete Integration Branch                       │
│    git branch -D dev/int-20260111-2130             │
└─────────────────────────────────────────────────────┘
```

**Branch State After Finalize**:
```
main
  ← Contains all architecture + cycles
  ← Clean, single commit

dev/int-20260111-2130 (deleted)
```

---

## Branch Naming Conventions

### Integration Branch

**Format**: `dev/int-{YYYYMMDD-HHMM}`

**Examples**:
- `dev/int-20260111-2130`
- `dev/int-20260115-0945`

**Rationale**:
- `dev/` prefix indicates development branch
- `int` = integration
- Timestamp ensures uniqueness
- Short and readable

---

### Jules's Branches

**Architecture Branch**:
- Format: `jules/arch-{session_id}`
- Example: `jules/arch-13699060115265162899`

**Cycle Branches**:
- Format: `jules/c{XX}-{session_id}`
- Examples: `jules/c01-13699060115265162899`, `jules/c02-13699060115265162899`

**Note**:
- Uses the full numeric session ID (without `sessions/` prefix)
- Ensures 1:1 mapping with Jules API sessions
- Avoids any potential collision risks

**Rationale**:
- `jules/` prefix indicates Jules-created branches
- `arch` or `c{XX}` clearly indicates purpose
- Full session ID guarantees uniqueness and traceability
- Consistent pattern across all Jules branches

---

## PR Strategy

### Auto-Merge Conditions

PRs are automatically merged when:

1. ✅ **Jules session completes successfully**
2. ✅ **Auditor approves** (or auto-approves after max retries)
3. ✅ **All CI checks pass** (if configured)

### Merge Method

**Squash Merge** for all Jules PRs:
- Keeps integration branch history clean
- Each cycle = one commit
- Easy to review and rollback

**Command**:
```bash
gh pr merge <PR_NUMBER> --squash --auto
```

### Manual Review

Only the **final PR** (integration → main) requires manual review:
- Human validates entire implementation
- Ensures quality before production
- Can request changes if needed

---

## Rollback Strategy

### Scenario 1: Single Cycle Fails

**Problem**: Cycle 03 implementation is broken

**Solution**: Revert the merge commit
```bash
git checkout dev/int-20260111-2130
git revert <merge_commit_hash>
git push
```

**Then**: Re-run cycle 03
```bash
ac-cdd run-cycle --id 03
```

---

### Scenario 2: Multiple Cycles Fail

**Problem**: Cycles 05-08 are all broken

**Solution**: Reset integration branch to before Cycle 05
```bash
git checkout dev/int-20260111-2130
git reset --hard <commit_before_cycle_05>
git push --force
```

**Then**: Re-run cycles 05-08
```bash
ac-cdd run-cycle --id 05,06,07,08
```

---

### Scenario 3: Entire Session Fails

**Problem**: Architecture or fundamental design is wrong

**Solution**: Delete integration branch and start over
```bash
# Delete local branch
git branch -D dev/int-20260111-2130

# Delete remote branch
git push origin --delete dev/int-20260111-2130

# Start fresh
ac-cdd gen-cycles --cycles 8
```

**Benefit**: Main branch is untouched, no cleanup needed

---

## Best Practices

### 1. One Session at a Time

**Recommendation**: Complete one session before starting another

**Rationale**:
- Avoids confusion between integration branches
- Easier to track progress
- Simpler rollback if needed

**If parallel sessions are needed**:
```
dev/int-20260111-2130  (Session A: Feature X)
dev/int-20260111-1500  (Session B: Feature Y)
```

---

### 2. Regular Cleanup

**After successful finalize**:
```bash
# Delete merged integration branch
git branch -D dev/int-20260111-2130
git push origin --delete dev/int-20260111-2130

# Prune deleted remote branches
git fetch --prune
```

**Automated cleanup** (recommended):
- Add to `finalize-session` command
- Automatic deletion after merge to main

---

### 3. Branch Protection Rules

**Main Branch**:
- ✅ Require pull request reviews
- ✅ Require status checks to pass
- ✅ Require branches to be up to date
- ✅ Do not allow force pushes
- ✅ Do not allow deletions

**Integration Branches**:
- ✅ Require status checks (optional)
- ❌ Allow force pushes (for rollback)
- ❌ Require reviews (auto-merge handles this)

---

### 4. Monitoring and Logging

**Track branch lifecycle**:
```
[INFO] Created integration branch: dev/int-20260111-2130
[INFO] Jules created architecture PR #123
[INFO] Auto-merged PR #123 to integration branch
[INFO] Jules created cycle 01 PR #124
[INFO] Auto-merged PR #124 to integration branch
...
[INFO] All cycles completed
[INFO] Created final PR #132 to main
[INFO] Integration branch merged to main
[INFO] Deleted integration branch: dev/int-20260111-2130
```

---

## Comparison: Old vs New Strategy

### Old Strategy (Current Implementation)

```
main
  ↑ (manual PR)
feat/generate-architecture-{timestamp}
  ↑ (Jules's architecture PR)
  ↑ (Jules's cycle PRs)
  
Problems:
- ❌ Feature branch lives for weeks
- ❌ Integration branch created but unused
- ❌ No auto-merge (manual intervention needed)
- ❌ Cycles don't build on each other
- ❌ Long branch names
```

### New Strategy (Recommended)

```
main
  ↑ (manual PR, squash merge)
dev/int-20260111-2130
  ↑ (Jules's architecture PR - auto-merged)
  ↑ (Jules's cycle PRs - auto-merged)
  
Benefits:
- ✅ Integration branch is the working base
- ✅ Auto-merge after approval
- ✅ Each cycle builds on previous
- ✅ Easy rollback (delete integration branch)
- ✅ Short, consistent naming
- ✅ Main stays clean
```

---

## Implementation Checklist

To migrate to the new strategy:

### Phase 1: Integration Branch
- [ ] Rename `feat/generate-architecture-*` to `dev/int-{YYYYMMDD-HHMM}`
- [ ] Remove unused integration branch creation code
- [ ] Update manifest to use new branch name

### Phase 2: Auto-Merge
- [ ] Implement `GitManager.merge_pr()` method
- [ ] Add auto-merge after auditor approval
- [ ] Add auto-merge to `workflow.py`

### Phase 3: Branch Naming
- [ ] Shorten session IDs (last 8 digits)
- [ ] Update Jules branch naming: `jules/arch-*`, `jules/c{XX}-*`
- [ ] Update all branch references in code

### Phase 4: Testing
- [ ] Test gen-cycles with new naming
- [ ] Test run-cycle --id all with auto-merge
- [ ] Test rollback scenarios
- [ ] Test finalize-session

### Phase 5: Documentation
- [ ] Update dev_flow.md
- [ ] Update README.md
- [ ] Add rollback guide
- [ ] Update CLI help text

---

## Conclusion

The new branch strategy provides:

1. **Safety**: Main branch is always clean
2. **Flexibility**: Easy rollback at any level
3. **Automation**: Auto-merge reduces manual work
4. **Clarity**: Simple, consistent naming
5. **Scalability**: Supports parallel sessions

By using integration branches as the working base and auto-merging approved PRs, AC-CDD achieves a fully automated, safe, and maintainable development workflow.

---

*Last Updated: 2026-01-11*
*Version: 2.0 (New Strategy)*
