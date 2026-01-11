# State Management Refactoring Plan

## Current Implementation

### Storage
- Location: Git orphan branch `ac-cdd/state`
- File: `project_state.json`
- Methods: `read_state_file()`, `save_state_file()` in GitManager

### Issues
1. Complex: Orphan branch is hard to understand
2. Slow: Git operations for every read/write
3. Debugging: Hard to inspect state
4. Overkill: Simple JSON doesn't need Git

---

## New Implementation

### Storage
- Location: `.ac_cdd/project_state.json` (local file)
- Backup: Optionally commit to repo (user's choice)
- Simple: Standard file I/O

### Benefits
1. **Simple**: Just read/write JSON file
2. **Fast**: No Git operations
3. **Debuggable**: `cat .ac_cdd/project_state.json`
4. **Flexible**: Can still commit if needed

---

## Migration Strategy

### Phase 1: Create new StateManager (file-based)

```python
# state_manager.py (NEW)
class StateManager:
    """Manages project state using local JSON file."""
    
    STATE_FILE = Path(".ac_cdd/project_state.json")
    
    def load_manifest(self) -> ProjectManifest | None:
        """Load from local file."""
        if not self.STATE_FILE.exists():
            return None
        
        try:
            data = json.loads(self.STATE_FILE.read_text())
            return ProjectManifest(**data)
        except Exception as e:
            logger.error(f"Failed to load manifest: {e}")
            return None
    
    def save_manifest(self, manifest: ProjectManifest) -> None:
        """Save to local file."""
        self.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        manifest.last_updated = datetime.now(UTC)
        self.STATE_FILE.write_text(manifest.model_dump_json(indent=2))
```

### Phase 2: Replace SessionManager with StateManager

**Files to update:**
1. `session_manager.py` → Delete or rename to `state_manager.py`
2. `cli.py` → Replace `SessionManager()` with `StateManager()`
3. `validators.py` → Replace `SessionManager()` with `StateManager()`
4. `workflow.py` → Replace `SessionManager()` with `StateManager()`
5. `jules_client.py` → Replace `SessionManager()` with `StateManager()`

### Phase 3: Remove Git state branch code

**Files to update:**
1. `git_ops.py` → Remove `read_state_file()`, `save_state_file()`
2. No longer need orphan branch operations

---

## Detailed Changes

### 1. Create state_manager.py

```python
from pathlib import Path
import json
from datetime import datetime, UTC
from .domain_models import ProjectManifest, CycleManifest
from .errors import SessionValidationError

class StateManager:
    """Manages project state using local JSON file."""
    
    STATE_FILE = Path(".ac_cdd/project_state.json")
    
    def load_manifest(self) -> ProjectManifest | None:
        if not self.STATE_FILE.exists():
            return None
        
        try:
            data = json.loads(self.STATE_FILE.read_text())
            return ProjectManifest(**data)
        except Exception as e:
            logger.error(f"Failed to load manifest: {e}")
            return None
    
    def save_manifest(self, manifest: ProjectManifest) -> None:
        self.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        manifest.last_updated = datetime.now(UTC)
        self.STATE_FILE.write_text(manifest.model_dump_json(indent=2))
    
    def create_manifest(
        self, project_session_id: str, feature_branch: str, integration_branch: str
    ) -> ProjectManifest:
        manifest = ProjectManifest(
            project_session_id=project_session_id,
            feature_branch=feature_branch,
            integration_branch=integration_branch,
        )
        self.save_manifest(manifest)
        return manifest
    
    def get_cycle(self, cycle_id: str) -> CycleManifest | None:
        manifest = self.load_manifest()
        if not manifest:
            return None
        
        for cycle in manifest.cycles:
            if cycle.id == cycle_id:
                return cycle
        return None
    
    def update_cycle_state(self, cycle_id: str, **kwargs) -> None:
        manifest = self.load_manifest()
        if not manifest:
            raise SessionValidationError("No active project manifest found.")
        
        cycle = next((c for c in manifest.cycles if c.id == cycle_id), None)
        if not cycle:
            raise SessionValidationError(f"Cycle {cycle_id} not found in manifest.")
        
        for key, value in kwargs.items():
            if hasattr(cycle, key):
                setattr(cycle, key, value)
        
        cycle.updated_at = datetime.now(UTC)
        self.save_manifest(manifest)
```

### 2. Update all imports

**Find and replace:**
```python
# OLD
from .session_manager import SessionManager
mgr = SessionManager()

# NEW
from .state_manager import StateManager
mgr = StateManager()
```

**Files:**
- cli.py
- validators.py
- workflow.py
- jules_client.py

### 3. Remove async (no longer needed)

**OLD:**
```python
manifest = await mgr.load_manifest()
await mgr.save_manifest(manifest)
```

**NEW:**
```python
manifest = mgr.load_manifest()
mgr.save_manifest(manifest)
```

---

## Testing Checklist

- [ ] gen-cycles creates `.ac_cdd/project_state.json`
- [ ] resume-session creates `.ac_cdd/project_state.json`
- [ ] run-cycle reads from `.ac_cdd/project_state.json`
- [ ] Cycle status updates correctly
- [ ] No Git state branch operations
- [ ] File is human-readable JSON
- [ ] `.ac_cdd/` is in `.gitignore`

---

## Rollback Plan

If issues occur:
1. Revert commits
2. Restore old SessionManager
3. Keep Git state branch

---

## Benefits Summary

| Aspect | Old (Git state branch) | New (Local file) |
|--------|------------------------|------------------|
| **Complexity** | High (orphan branch) | Low (JSON file) |
| **Speed** | Slow (Git ops) | Fast (file I/O) |
| **Debugging** | Hard (git show) | Easy (cat file) |
| **Portability** | Git-dependent | Standalone |
| **Async** | Required | Not needed |

---

## Next Steps

1. Create `state_manager.py`
2. Update all imports (SessionManager → StateManager)
3. Remove async from all state operations
4. Test thoroughly
5. Remove Git state branch code
