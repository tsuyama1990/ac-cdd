# Branch Flow Fix - Test Instructions

## Prerequisites

1. Ensure you're in the test project directory:
   ```bash
   cd ~/project/test_ac_cdd_mlip_pipelines
   ```

2. Rebuild Docker image with latest code:
   ```bash
   docker-compose build --no-cache
   ```

---

## Test 1: Resume Session with Existing Architecture

### Step 1: Resume session
```bash
docker-compose run --rm ac-cdd ac-cdd resume-session feat/generate-architecture-20260110-1640 --cycles 8
```

**Expected Output:**
```
Resuming session with existing branches:
  Feature branch: feat/generate-architecture-20260110-1640
  Integration branch: dev/architect-cycle-00-20260110-1640/integration
  Cycles: 8

✅ Session resumed!
Session ID: resume-20260111-XXXXXX

You can now run:
  ac-cdd run-cycle --id 01
  ac-cdd run-cycle --id all
```

### Step 2: Run Cycle 01
```bash
docker-compose run --rm ac-cdd ac-cdd run-cycle --id 01
```

**What to Check in Logs:**

1. ✅ **Feature branch checkout:**
   ```
   INFO: Checking out feature branch: feat/generate-architecture-20260110-1640
   INFO: Successfully checked out feature branch
   ```

2. ✅ **PR target:**
   Look for PR URL in logs, then check:
   ```bash
   gh pr view <PR_NUMBER> --json baseRefName --jq '.baseRefName'
   ```
   Should output: `feat/generate-architecture-20260110-1640` (NOT integration branch)

3. ✅ **Auditor comparison:**
   ```
   Comparing changes against base branch: feat/generate-architecture-20260110-1640
   ```

4. ✅ **Return to feature branch:**
   ```
   Returning to feature branch: feat/generate-architecture-20260110-1640
   Successfully returned to feature branch
   ```

5. ✅ **No .egg-info files:**
   ```
   DEBUG: Final reviewable files: ['src/nnp_gen/...', 'tests/...']
   ```
   Should NOT contain `.egg-info` files

6. ✅ **SPEC.md accessible:**
   No errors about missing SPEC.md or UAT.md files

---

## Test 2: Verify Branch State After Cycle

### After Cycle 01 completes (approved or rejected):

```bash
# Check current branch
git branch --show-current
# Should be: feat/generate-architecture-20260110-1640

# Check if changes are accumulated (if approved)
git log --oneline -5
# Should show merge commits if cycle was approved
```

---

## Test 3: Run Multiple Cycles

```bash
docker-compose run --rm ac-cdd ac-cdd run-cycle --id 02
```

**What to Check:**

1. ✅ Starts from feature branch (with Cycle 01 code if it was approved)
2. ✅ PR targets feature branch
3. ✅ Changes accumulate

---

## Test 4: Verify PR Targets

```bash
# List all PRs
gh pr list --json number,headRefName,baseRefName

# Check specific PR
gh pr view <PR_NUMBER> --json baseRefName,headRefName
```

**Expected:**
- `baseRefName`: `feat/generate-architecture-20260110-1640` ✅
- `headRefName`: `feat/cycle-XX-implementation-...` or similar

**NOT:**
- `baseRefName`: `dev/architect-cycle-00-.../integration` ❌

---

## Success Criteria

- [ ] resume-session creates manifest successfully
- [ ] run-cycle checks out feature branch (not integration)
- [ ] Jules creates PR targeting feature branch
- [ ] SPEC.md and UAT.md are accessible
- [ ] Auditor compares against feature branch
- [ ] No .egg-info files in review
- [ ] Auditor returns to feature branch after review
- [ ] Multiple cycles accumulate in feature branch

---

## Troubleshooting

### Issue: "No feature branch found in manifest"
**Solution:** Run resume-session again

### Issue: PR targets integration branch
**Check:** Docker image was rebuilt with latest code
```bash
docker-compose build --no-cache
```

### Issue: SPEC.md not found
**Check:** Feature branch has SPEC.md files
```bash
git checkout feat/generate-architecture-20260110-1640
ls -la dev_documents/system_prompts/CYCLE01/
```

### Issue: .egg-info files still in review
**Check:** Latest code is in Docker image
```bash
docker-compose run --rm ac-cdd python -c "
import sys
sys.path.insert(0, '/opt/ac_cdd/ac_cdd_core/dev_src/ac_cdd_core')
from graph_nodes import CycleNodes
import inspect
source = inspect.getsource(CycleNodes.auditor_node)
print('✅ Filter code present' if 'build_artifact_patterns' in source else '❌ Old code')
"
```

---

## Reporting Results

Please report:
1. Which tests passed ✅
2. Which tests failed ❌
3. Any unexpected behavior
4. Logs from failed tests

If all tests pass, the branch flow fix is successful! 🎉
