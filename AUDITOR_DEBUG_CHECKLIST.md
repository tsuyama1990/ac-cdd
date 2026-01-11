# Auditor Debug Checklist

## Issue
Auditor reports files as missing when they exist in the PR.
Jules says files exist, Auditor says they don't.

## Possible Causes

### 1. Docker Image Not Rebuilt ❓
**Check**: When was the last docker build?
**Solution**: Rebuild with latest code
```bash
cd ~/project/test_ac_cdd_mlip_pipelines
docker-compose build --no-cache
```

### 2. Auditor Not Checking Out PR ❓
**Check**: Look for "Checking out PR" in logs
**Expected**: Should see PR checkout before review
**Fix Applied**: commit fee4568 (not yet in Docker image)

### 3. Wrong Base Branch Comparison ❓
**Check**: Look for "Comparing changes against base branch"
**Expected**: Should compare to integration branch, not main
**Fix Applied**: commit 56062db (not yet in Docker image)

### 4. Auditor Reading Wrong Files ❓
**Check**: Look for "DEBUG: Final reviewable files" in logs
**Expected**: Should show actual PR files
**Fix Applied**: Debug logging added in fee4568

## Debug Steps

### Step 1: Verify Latest Code is in Docker
```bash
cd ~/project/test_ac_cdd_mlip_pipelines
docker-compose run --rm ac-cdd ac-cdd --version
# Should show latest version with fixes
```

### Step 2: Check Docker Image Build Date
```bash
docker images | grep ac-cdd
# Check if image is recent (after 2026-01-11 02:30)
```

### Step 3: Rebuild Docker Image
```bash
cd ~/project/test_ac_cdd_mlip_pipelines
docker-compose build --no-cache
```

### Step 4: Run with Debug Logging
```bash
docker-compose run --rm ac-cdd ac-cdd run-cycle --id 01 2>&1 | tee debug.log
```

### Step 5: Check Debug Output
Look for these lines in debug.log:
- ✅ "Checking out integration branch: dev/..."
- ✅ "Checking out PR: https://github.com/.../pull/XX"
- ✅ "Successfully checked out PR branch"
- ✅ "Comparing changes against base branch: dev/..."
- ✅ "DEBUG: Final reviewable files: ['src/...', ...]"
- ✅ "DEBUG: Successfully read N files"
- ✅ "DEBUG: - src/nnp_gen/pipeline.py (XXX chars)"

### Step 6: Verify Files in PR
```bash
cd ~/project/test_ac_cdd_mlip_pipelines
gh pr view <PR_NUMBER> --json files --jq '.files[].path' | grep -E "src/|tests/"
```

## Expected Flow (After Fixes)

1. Start run-cycle
2. Checkout integration branch ✅
3. Jules creates PR from integration
4. Auditor starts
5. **Checkout PR branch** ✅ (NEW FIX)
6. **Compare to integration branch** ✅ (NEW FIX)
7. Read files from PR ✅
8. Review actual PR code ✅
9. Return to integration branch ✅

## If Still Failing After Rebuild

### Check 1: PR Actually Has Files
```bash
gh pr view <PR_NUMBER> --json files --jq '.files[] | select(.path | startswith("src/")) | .path'
```

### Check 2: PR Branch Exists
```bash
git ls-remote origin | grep <PR_BRANCH_NAME>
```

### Check 3: Checkout PR Manually
```bash
gh pr checkout <PR_NUMBER>
ls -la src/
```

### Check 4: Integration Branch Has SPEC.md
```bash
git checkout <INTEGRATION_BRANCH>
ls -la dev_documents/system_prompts/CYCLE01/
```

## Most Likely Cause

**Docker image not rebuilt with latest fixes.**

The fixes for PR checkout (fee4568) and integration branch checkout (56062db) 
were committed but the Docker image in test_ac_cdd_mlip_pipelines was not rebuilt.

**Solution**: Rebuild Docker image and test again.
