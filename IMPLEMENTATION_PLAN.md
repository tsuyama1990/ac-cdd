# Implementation Plan - Fix Branch Flow

## Overview

Fix the fundamental branch flow issue where run-cycle uses integration branch instead of feature branch.

---

## Step 1: Add feature_branch to Manifest ✅

**Goal**: Store the feature branch name in the manifest so run-cycle can use it.

**Files to Change**:
- `state.py`: Add `feature_branch` field to `ProjectManifest`
- `services/workflow.py`: Save feature_branch in gen-cycles

**Changes**:
```python
# state.py
class ProjectManifest(BaseModel):
    project_session_id: str
    integration_branch: str | None = None
    feature_branch: str | None = None  # ← ADD THIS
    cycles: list[CycleInfo]
    created_at: str
    updated_at: str
```

**Test**:
```bash
# Run gen-cycles
docker-compose run --rm ac-cdd ac-cdd gen-cycles --cycles 2

# Check manifest
docker-compose run --rm ac-cdd python -c "
import asyncio
from ac_cdd_core.session_manager import SessionManager
async def check():
    mgr = SessionManager()
    manifest = await mgr.load_manifest()
    print(f'Feature branch: {manifest.feature_branch}')
    print(f'Integration branch: {manifest.integration_branch}')
asyncio.run(check())
"
```

**Expected Output**:
```
Feature branch: feat/generate-architecture-20260111-XXXX
Integration branch: dev/architect-cycle-00-20260111-XXXX/integration
```

---

## Step 2: Use feature_branch in run-cycle ✅

**Goal**: Make run-cycle checkout feature branch instead of integration branch.

**Files to Change**:
- `services/workflow.py`: Change `_run_single_cycle()` to use feature_branch

**Changes**:
```python
# workflow.py:_run_single_cycle()
# BEFORE:
if ib:
    await git.checkout_branch(ib)  # integration branch

# AFTER:
fb = manifest.feature_branch
if fb:
    await git.checkout_branch(fb)  # feature branch
```

**Test**:
```bash
# Run one cycle
docker-compose run --rm ac-cdd ac-cdd run-cycle --id 01

# Check logs for:
# "Checking out integration branch: feat/generate-architecture-..."
# NOT "...integration"
```

**Expected**:
- Jules creates branch from feature branch
- PR targets feature branch
- SPEC.md is accessible

---

## Step 3: Update Auditor base branch comparison ✅

**Goal**: Auditor should compare against feature branch, not integration.

**Files to Change**:
- `graph_nodes.py`: Change `auditor_node()` to use feature_branch

**Changes**:
```python
# graph_nodes.py:auditor_node()
# BEFORE:
base_branch = state.get("integration_branch", "main")

# AFTER:
base_branch = state.get("feature_branch") or state.get("integration_branch", "main")
```

**Test**:
```bash
# Run cycle and check logs
docker-compose run --rm ac-cdd ac-cdd run-cycle --id 01

# Look for:
# "Comparing changes against base branch: feat/generate-architecture-..."
```

**Expected**:
- Auditor compares to feature branch
- Shows only THIS cycle's changes

---

## Step 4: Merge cycle PR into feature branch after approval ✅

**Goal**: After Auditor approves, merge the cycle PR into feature branch.

**Files to Change**:
- `graph_nodes.py`: Add merge logic in `committee_manager_node()`

**Changes**:
```python
# After final approval, merge PR into feature branch
if final_approval:
    feature_branch = state.get("feature_branch")
    pr_url = state.get("pr_url")
    
    if feature_branch and pr_url:
        # Merge PR into feature branch
        await git.checkout_branch(feature_branch)
        await git.merge_pr(pr_url)
        await git.push()
```

**Test**:
```bash
# Run cycle until approval
docker-compose run --rm ac-cdd ac-cdd run-cycle --id 01

# After approval, check feature branch
git checkout feat/generate-architecture-XXXX
git log --oneline -5

# Should see merge commit
```

**Expected**:
- Cycle 01 code is merged into feature branch
- Feature branch has accumulated changes

---

## Step 5: Pass feature_branch in CycleState ✅

**Goal**: Make feature_branch available throughout the graph.

**Files to Change**:
- `state.py`: Add `feature_branch` to `CycleState`
- `services/workflow.py`: Pass feature_branch when creating state

**Changes**:
```python
# state.py
class CycleState(TypedDict, total=False):
    cycle_id: str
    project_session_id: str
    integration_branch: str | None
    feature_branch: str | None  # ← ADD THIS
    # ... rest
```

**Test**:
```bash
# Run cycle and check state is passed correctly
# (covered by previous tests)
```

---

## Step 6: Update gen-cycles to save feature_branch ✅

**Goal**: gen-cycles should save the feature branch to manifest.

**Files to Change**:
- `services/workflow.py`: Update `run_gen_cycles()` to save feature_branch

**Changes**:
```python
# After creating feature branch
manifest = ProjectManifest(
    project_session_id=session_id_val,
    feature_branch=architect_branch,  # ← ADD THIS
    integration_branch=integration_branch,
    cycles=[...],
    created_at=...,
    updated_at=...
)
await mgr.save_manifest(manifest)
```

**Test**:
```bash
# Run gen-cycles
docker-compose run --rm ac-cdd ac-cdd gen-cycles --cycles 2

# Check manifest (Step 1 test)
```

---

## Step 7: Integration branch only for finalize (Future) 🔮

**Goal**: Integration branch should only be used in finalize-session.

**Note**: This is a future enhancement. For now, we keep integration branch but don't use it in run-cycle.

---

## Testing Strategy

### Test 1: Fresh gen-cycles + run-cycle
```bash
# Clean start
cd ~/project/test_ac_cdd_mlip_pipelines
git checkout main
git branch -D feat/generate-architecture-* 2>/dev/null || true

# Gen cycles
docker-compose run --rm ac-cdd ac-cdd gen-cycles --cycles 2

# Run cycle 01
docker-compose run --rm ac-cdd ac-cdd run-cycle --id 01

# Verify:
# 1. PR targets feat/generate-architecture-*
# 2. SPEC.md is accessible
# 3. After approval, changes are in feat/generate-architecture-*
```

### Test 2: Multiple cycles accumulate
```bash
# Run cycle 02
docker-compose run --rm ac-cdd ac-cdd run-cycle --id 02

# Check feature branch
git checkout feat/generate-architecture-*
ls -la src/

# Should see:
# - Cycle 01 code
# - Cycle 02 code
```

### Test 3: run-cycle --id all
```bash
# Run all cycles
docker-compose run --rm ac-cdd ac-cdd run-cycle --id all

# Check feature branch has all code
git checkout feat/generate-architecture-*
git log --oneline --graph
```

---

## Rollback Plan

If anything goes wrong:

```bash
# Revert to previous commit
cd ~/project/ac-cdd
git revert HEAD
git push origin main

# Rebuild Docker
cd ~/project/test_ac_cdd_mlip_pipelines
docker-compose build --no-cache
```

---

## Success Criteria

- ✅ Manifest contains feature_branch
- ✅ run-cycle uses feature_branch, not integration_branch
- ✅ PRs target feature_branch
- ✅ SPEC.md is accessible from feature_branch
- ✅ Each cycle's changes accumulate in feature_branch
- ✅ Auditor compares against feature_branch
- ✅ After all cycles, feature_branch has complete code

---

## Current Status

- [ ] Step 1: Add feature_branch to Manifest
- [ ] Step 2: Use feature_branch in run-cycle
- [ ] Step 3: Update Auditor base branch
- [ ] Step 4: Merge cycle PR after approval
- [ ] Step 5: Pass feature_branch in CycleState
- [ ] Step 6: Update gen-cycles to save feature_branch
- [ ] Step 7: Integration branch only for finalize (Future)

**Next**: Start with Step 1
