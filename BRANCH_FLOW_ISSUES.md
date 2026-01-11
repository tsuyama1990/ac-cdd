# Branch Flow Issues - Critical Problems

## Current State Analysis

### What User Observed

```
git status
On branch dev/architect-cycle-00-20260110-1640/integration
```

**Problem**: Jules is working from integration branch, not from feat/generate-architecture branch

### Issue 1: SPEC.md/UAT.md Not Accessible

**Expected Flow:**
```
feat/generate-architecture-20260110-1640
├── Contains: SPEC.md, UAT.md for all cycles
└── Jules creates branches FROM HERE
    ├── feat/cycle-01-xxx (from feat/generate-architecture)
    ├── feat/cycle-02-xxx (from feat/generate-architecture)
    └── ...
```

**Actual Flow (WRONG):**
```
dev/architect-cycle-00-20260110-1640/integration
├── Contains: SPEC.md, UAT.md (merged from Jules's arch branch)
└── Jules creates branches FROM HERE
    ├── feat/cycle-01-xxx (from integration)
    └── ...
```

**Why This is Wrong:**
- Integration branch is meant for FINAL integration
- Each cycle should start from feat/generate-architecture (the base with all SPEC.md)
- Current approach loses the connection to the architecture branch

### Issue 2: No Accumulation of Changes

**Expected Flow:**
```
Cycle 01:
├── Branch from: feat/generate-architecture
├── Develop: feat/cycle-01-xxx
├── Merge to: feat/generate-architecture ✅
└── Result: feat/generate-architecture now has Cycle 01 code

Cycle 02:
├── Branch from: feat/generate-architecture (with Cycle 01 code) ✅
├── Develop: feat/cycle-02-xxx
├── Merge to: feat/generate-architecture ✅
└── Result: feat/generate-architecture now has Cycle 01 + 02 code

Final:
├── feat/generate-architecture has ALL cycle code
└── Create PR: feat/generate-architecture → main
```

**Actual Flow (WRONG):**
```
Cycle 01:
├── Branch from: integration
├── Develop: feat/cycle-01-xxx
├── Merge to: ??? (nowhere)
└── Result: Code is lost

Cycle 02:
├── Branch from: integration (no Cycle 01 code) ❌
├── Develop: feat/cycle-02-xxx
├── Merge to: ??? (nowhere)
└── Result: Code is lost, independent of Cycle 01

Final:
├── No accumulated code
└── Each cycle is independent ❌
```

## Root Cause Analysis

### Where Did We Go Wrong?

Looking at our fixes:

**workflow.py:_run_single_cycle() - Line 211-221:**
```python
# CRITICAL: Checkout integration branch before starting coder session
if ib:
    logger.info(f"Checking out integration branch: {ib}")
    git = GitManager()
    await git.checkout_branch(ib)  # ← THIS IS WRONG!
```

**This is the problem!** We're checking out integration branch, but we should be checking out the **feature branch** (feat/generate-architecture).

### What Should Happen

1. **gen-cycles creates:**
   - `feat/generate-architecture-{timestamp}` with all SPEC.md files
   - `dev/architect-cycle-00-{timestamp}/integration` for final integration

2. **run-cycle should:**
   - Checkout `feat/generate-architecture-{timestamp}`
   - Jules creates branch from there
   - After approval, merge back to `feat/generate-architecture-{timestamp}`
   - Repeat for each cycle

3. **After all cycles:**
   - `feat/generate-architecture-{timestamp}` has all code
   - Create final PR: `feat/generate-architecture-{timestamp}` → `main`

## Verification

### Check 1: What's in feat/generate-architecture?

```bash
cd ~/project/test_ac_cdd_mlip_pipelines
git checkout feat/generate-architecture-20260110-1640
ls -la dev_documents/system_prompts/CYCLE*/
```

Expected: SPEC.md and UAT.md for all cycles

### Check 2: What's in integration branch?

```bash
git checkout dev/architect-cycle-00-20260110-1640/integration
ls -la dev_documents/system_prompts/CYCLE*/
```

Expected: Same SPEC.md files (merged from arch)

### Check 3: Where does Jules create branches from?

From logs:
```
INFO: Checking out integration branch: dev/architect-cycle-00-20260110-1640/integration
INFO: Pushing branch dev/architect-cycle-00-20260110-1640/integration to origin...
```

**Confirmed**: Jules is branching from integration ❌

### Check 4: Where are cycle PRs targeting?

```bash
gh pr list --json number,headRefName,baseRefName
```

Expected: PRs should target `feat/generate-architecture-20260110-1640`
Actual: PRs probably target `dev/architect-cycle-00-20260110-1640/integration`

## The Correct Flow

### gen-cycles (Architect Phase)

1. Create `feat/generate-architecture-{timestamp}` from main
2. Jules creates SPEC.md files
3. Jules creates PR: `feat/arch-docs-{session}` → `feat/generate-architecture-{timestamp}`
4. Merge Jules's PR into `feat/generate-architecture-{timestamp}`
5. **DONE** - No integration branch needed yet!

### run-cycle (Implementation Phase)

**For each cycle:**

1. Checkout `feat/generate-architecture-{timestamp}` (the accumulation branch)
2. Jules creates `feat/cycle-XX-{session}` from current branch
3. Jules creates PR: `feat/cycle-XX-{session}` → `feat/generate-architecture-{timestamp}`
4. Auditor reviews
5. After approval: Merge PR into `feat/generate-architecture-{timestamp}`
6. Repeat for next cycle

**Result**: `feat/generate-architecture-{timestamp}` accumulates all changes

### finalize-session (Final Integration)

1. Create integration branch from main (fresh)
2. Merge `feat/generate-architecture-{timestamp}` into integration
3. Create final PR: integration → main
4. Squash merge to main

## What Needs to Change

### 1. Remove integration branch from run-cycle

**workflow.py:_run_single_cycle():**
```python
# WRONG:
await git.checkout_branch(ib)  # integration branch

# RIGHT:
await git.checkout_branch(feature_branch)  # feat/generate-architecture
```

### 2. Store feature branch in manifest

**Manifest should contain:**
```json
{
  "project_session_id": "sessions/xxx",
  "feature_branch": "feat/generate-architecture-20260110-1640",  ← ADD THIS
  "integration_branch": "dev/architect-cycle-00-20260110-1640/integration",
  "cycles": [...]
}
```

### 3. Merge after each cycle

**After Auditor approves:**
```python
# Merge cycle PR into feature branch
await git.checkout_branch(feature_branch)
await git.merge(cycle_pr_branch)
await git.push()
```

### 4. Integration branch only for finalize

Integration branch should only be used in `finalize-session`, not during `run-cycle`.

## Summary

**Current (WRONG):**
- run-cycle uses integration branch
- Each cycle is independent
- No accumulation
- SPEC.md might not be accessible

**Correct:**
- run-cycle uses feature branch (feat/generate-architecture)
- Each cycle builds on previous
- Changes accumulate
- SPEC.md always accessible

This is a fundamental architecture issue that needs to be fixed.
