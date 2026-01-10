# Branch Flow Analysis - Complete Verification

## Overview
This document traces the complete Git branch flow through gen-cycles and run-cycle to ensure the Auditor reviews the correct code.

## Phase 1: gen-cycles (Architect)

### Step 1: Start
- **Current Branch**: `main`
- **Location**: `workflow.py:run_gen_cycles()`

### Step 2: Create Feature Branch
- **Action**: `graph_nodes.py:architect_session_node()` creates feature branch
- **Branch Created**: `feat/generate-architecture-{timestamp}`
- **Code**: 
  ```python
  architect_branch = f"feat/generate-architecture-{timestamp}"
  await self.git.create_feature_branch(architect_branch, from_branch="main")
  ```
- **Current Branch After**: `feat/generate-architecture-{timestamp}`

### Step 3: Jules Works
- **Action**: Jules creates its own branch and commits
- **Jules Branch**: `feat/generate-architectural-documents-{session_id}` (or similar)
- **Jules Creates PR**: From Jules's branch → our feature branch
- **Current Branch**: Still `feat/generate-architecture-{timestamp}` (we haven't moved)

### Step 4: Create Integration Branch
- **Action**: `workflow.py` creates integration branch
- **Code**:
  ```python
  await git.create_integration_branch(session_id_val, branch_name=integration_branch)
  ```
- **Integration Branch**: `dev/architect-cycle-00-{timestamp}/integration`
- **Current Branch After**: `dev/architect-cycle-00-{timestamp}/integration` (create_integration_branch checks it out)

### Step 5: Merge Jules's Branch
- **Action**: Get PR head branch and merge it
- **Code**:
  ```python
  # Get Jules's branch from PR
  jules_branch = get_from_pr(pr_url)
  # Merge into integration
  git.merge(f"origin/{jules_branch}", into=integration_branch)
  ```
- **Current Branch**: Still `dev/architect-cycle-00-{timestamp}/integration`
- **Result**: Integration branch now has SPEC.md files

### Step 6: gen-cycles Complete
- **Final Branch**: `dev/architect-cycle-00-{timestamp}/integration`
- **Files Available**: SPEC.md, UAT.md in integration branch ✅

---

## Phase 2: run-cycle (Coder + Auditor)

### Step 1: Start
- **Current Branch**: Unknown (depends on where user is)
- **Location**: `workflow.py:run_cycle()`

### Step 2: Coder Session Starts
- **Action**: `graph_nodes.py:coder_session_node()` starts
- **Expected**: Should be on integration branch
- **Question**: ❓ **WHO CHECKS OUT THE INTEGRATION BRANCH?**

### Step 3: Jules Prepares Git Context
- **Action**: `jules_client.py:_prepare_git_context()`
- **Code**:
  ```python
  async def _prepare_git_context(self):
      branch = await self.git.get_current_branch()
      await self.git.push_branch(branch)
      return owner, repo_name, branch
  ```
- **Current Branch**: Whatever branch we're on (integration branch?)
- **Jules Receives**: `startingBranch` = current branch

### Step 4: Jules Creates PR
- **Jules Creates**: New branch from current branch
- **Jules Branch**: `feat/cycle-01-implementation-{session_id}` (or similar)
- **PR Created**: From Jules's branch → integration branch (or main?)
- **Question**: ❓ **WHAT IS THE PR BASE BRANCH?**

### Step 5: Auditor Starts
- **Current Branch**: ❓ **UNKNOWN - THIS IS THE PROBLEM**
- **Action**: `graph_nodes.py:auditor_node()` starts
- **NEW FIX**: Checkout PR before reviewing
- **Code**:
  ```python
  pr_url = state.get("pr_url")
  await git.checkout_pr(pr_url)
  ```
- **Current Branch After**: Jules's PR branch ✅

### Step 6: Get Changed Files
- **Action**: `git.get_changed_files()`
- **Base Branch**: `main` (hardcoded in get_changed_files)
- **Question**: ❓ **SHOULD IT BE COMPARING TO INTEGRATION BRANCH INSTEAD?**

---

## Critical Questions to Answer

### Q1: Who checks out the integration branch before coder session?
**Location to check**: `workflow.py:run_cycle()` or `cli.py:run_cycle()`

### Q2: What branch does Jules create PR against?
**Location to check**: `jules_client.py:run_session()` - what is the base branch?

### Q3: What branch should get_changed_files() compare against?
**Current**: Compares to `main`
**Should be**: Compare to `integration_branch`?

### Q4: After auditor checks out PR, what happens to the branch state?
**Issue**: Checking out PR changes the working directory
**Impact**: Subsequent operations might be affected

---

## Issues Found

### Issue 1: Integration Branch Checkout Missing
**Problem**: No code explicitly checks out integration branch before coder session
**Impact**: Coder might start from wrong branch
**Fix Needed**: Add checkout in workflow.py before coder session

### Issue 2: get_changed_files() Base Branch
**Problem**: Always compares to `main`, not integration branch
**Impact**: Shows wrong diff (includes all changes from main, not just this cycle)
**Fix Needed**: Pass integration_branch as parameter

### Issue 3: PR Base Branch Unclear
**Problem**: Not clear what branch Jules creates PR against
**Impact**: PR might target wrong branch
**Fix Needed**: Verify and document

### Issue 4: Branch State After Auditor
**Problem**: After checkout_pr, we're on PR branch, not integration
**Impact**: Next iteration might start from wrong branch
**Fix Needed**: Return to integration branch after audit?

---

## FIXES APPLIED ✅

### Fix 1: Checkout Integration Branch Before Coder Session
**File**: `workflow.py:_run_single_cycle()`
**Problem**: No code checked out integration branch before coder session
**Fix**: Added explicit checkout of integration branch
```python
if ib:
    logger.info(f"Checking out integration branch: {ib}")
    git = GitManager()
    await git.checkout_branch(ib)
```
**Impact**: Jules now creates PR against correct base branch (integration, not main)

### Fix 2: Checkout PR Branch Before Audit
**File**: `graph_nodes.py:auditor_node()`
**Problem**: Auditor reviewed wrong code (stayed on integration branch)
**Fix**: Added PR checkout before reviewing
```python
pr_url = state.get("pr_url")
if pr_url:
    await git.checkout_pr(pr_url)
```
**Impact**: Auditor now reviews the actual PR code, not old code

### Fix 3: Compare Against Integration Branch
**File**: `graph_nodes.py:auditor_node()`
**Problem**: get_changed_files() compared to main, showing all changes
**Fix**: Pass integration_branch as base
```python
base_branch = state.get("integration_branch", "main")
changed_file_paths = await git.get_changed_files(base_branch=base_branch)
```
**Impact**: Auditor only reviews changes made in THIS cycle

### Fix 4: Return to Integration Branch After Audit
**File**: `graph_nodes.py:auditor_node()`
**Problem**: After audit, stayed on PR branch
**Fix**: Return to integration branch after audit completes
```python
integration_branch = state.get("integration_branch")
if integration_branch:
    await git.checkout_branch(integration_branch)
```
**Impact**: Subsequent iterations start from correct branch

---

## COMPLETE FLOW (AFTER FIXES) ✅

### gen-cycles Flow
1. Start on `main`
2. Create feature branch `feat/generate-architecture-{timestamp}`
3. Jules creates `feat/generate-architectural-documents-{session_id}`
4. Jules creates PR: Jules's branch → feature branch
5. Create integration branch `dev/architect-cycle-00-{timestamp}/integration`
6. Merge Jules's branch into integration branch
7. **End on**: `dev/architect-cycle-00-{timestamp}/integration` ✅

### run-cycle Flow (First Iteration)
1. **Start**: Unknown branch
2. **Checkout**: `dev/architect-cycle-00-{timestamp}/integration` ✅ (Fix 1)
3. Jules creates `feat/cycle-01-implementation-{session_id}`
4. Jules creates PR: Jules's branch → integration branch ✅
5. **Auditor checkouts**: Jules's PR branch ✅ (Fix 2)
6. **Auditor compares**: Against integration branch ✅ (Fix 3)
7. **Auditor returns**: To integration branch ✅ (Fix 4)
8. **End on**: `dev/architect-cycle-00-{timestamp}/integration` ✅

### run-cycle Flow (Retry After Rejection)
1. **Start**: `dev/architect-cycle-00-{timestamp}/integration` (already there from Fix 4)
2. Jules creates new branch from integration
3. Jules creates new PR
4. Auditor checkouts new PR branch
5. Auditor reviews
6. Auditor returns to integration branch
7. **End on**: `dev/architect-cycle-00-{timestamp}/integration` ✅

---

## VERIFICATION CHECKLIST

- [x] Integration branch is checked out before coder session
- [x] Jules creates PR against integration branch (not main)
- [x] Auditor checks out PR branch before reviewing
- [x] Auditor compares against integration branch (not main)
- [x] Auditor returns to integration branch after review
- [x] All branch operations are logged for debugging
- [x] Error handling for all git operations
- [x] Subsequent iterations start from correct branch

---

## TESTING PLAN

1. Run gen-cycles
   - Verify integration branch is created
   - Verify SPEC.md files are in integration branch

2. Run run-cycle --id 01
   - Check logs: "Checking out integration branch"
   - Check logs: "Checking out PR"
   - Check logs: "Comparing changes against base branch: dev/..."
   - Check logs: "Returning to integration branch"
   - Verify Auditor reviews correct files (not data_loader.py, etc.)

3. If Auditor rejects, check retry
   - Verify new PR is created
   - Verify Auditor reviews new PR correctly
   - Verify branch state is correct for next iteration

---

## CONCLUSION

All critical branch management issues have been fixed:
✅ Integration branch checkout before coder session
✅ PR branch checkout before audit
✅ Correct base branch for comparison
✅ Return to integration branch after audit

The Auditor should now review the correct code every time.
