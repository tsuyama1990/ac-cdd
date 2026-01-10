# Known Issues

## Docker Git Authentication - RESOLVED ✅

### Issue
Git operations failed in Docker environment with authentication prompts.

### Root Cause
- `.gitconfig` mount was causing conflicts with `gh auth git-credential`
- Docker container needed GITHUB_TOKEN configuration

### Solution
- Removed `.gitconfig` and `.config/gh` mounts from `docker-compose.yml`
- Added GITHUB_TOKEN-based credential store in `entrypoint.sh`
- Added automatic Git user configuration (user.name, user.email)

### Files Changed
- `docker-compose.yml`
- `entrypoint.sh`
- `.ac_cdd/.env.example`
- `README.md`

---

## SPEC.md Files Not Available in run-cycle - PARTIALLY RESOLVED ⚠️

### Issue
When running `run-cycle`, Jules doesn't have access to CYCLE{xx}/SPEC.md and UAT.md files because they're not in the integration branch.

### Root Causes Found
1. **Jules doesn't create feature branch** - Jules was staying on `main` instead of creating a feature branch
   - **Fixed**: Added explicit feature branch creation in `architect_session_node`
   
2. **Missing GitManager in CycleNodes** - Code referenced `self.git` but it wasn't initialized
   - **Fixed**: Added GitManager to CycleNodes constructor

3. **Merging wrong branch** - We were merging our feature branch instead of Jules's branch
   - **Fixed**: Extract PR head branch using `gh pr view` and merge that branch
   
4. **Jules AI behavior issues** - Jules sometimes:
   - Deletes critical instruction files (ARCHITECT_INSTRUCTION.md, etc.)
   - Fails to create PR
   - Creates files but doesn't commit them properly

### Current Status
The code logic is correct, but Jules AI behavior is unpredictable:
- Sometimes creates SPEC.md files correctly
- Sometimes deletes instruction files
- Sometimes fails to create PR

### Files Changed
- `dev_src/ac_cdd_core/graph_nodes.py` - Added feature branch creation and GitManager
- `dev_src/ac_cdd_core/services/git_ops.py` - Added `create_feature_branch` method
- `dev_src/ac_cdd_core/services/workflow.py` - Fixed merge logic to use PR head branch

### Remaining Issues
**Jules AI Behavior** - This is not a code issue, but an AI model issue:
- Jules sometimes violates instructions
- Jules sometimes fails to create PR
- Jules sometimes deletes files it shouldn't

### Potential Solutions
1. **Improve ARCHITECT_INSTRUCTION.md** - Make instructions more explicit and forceful
2. **Add validation** - Check if SPEC.md files exist after architect session
3. **Fallback mechanism** - If Jules fails, retry or use alternative approach
4. **Use different AI model** - Consider using a more reliable model for architect phase

---

## Commits Related to This Issue

1. `0bbcbef` - Fix Docker GitHub authentication and Git user configuration
2. `da3bfdc` - Fix: Merge architect PR into integration branch after gen-cycles
3. `d3f0df2` - Fix: Get architect branch before creating integration branch
4. `ff6d990` - Fix: Create feature branch before Jules architect session
5. `8bb9aa5` - Fix: Add GitManager to CycleNodes
6. `1dd0b1c` - Fix: Merge Jules's actual PR branch, not our feature branch

---

## Next Steps

### Short-term
- Document Jules behavior issues
- Add validation after architect session
- Improve error handling

### Long-term
- Consider alternative to Jules for architect phase
- Add retry logic for failed sessions
- Implement file existence validation before run-cycle
