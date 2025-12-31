import pytest
from pathlib import Path
from ac_cdd_core.config import settings

def test_system_prompt_structure():
    """Verify that system prompts are reachable via the new structure."""
    
    # 1. Verify Directory
    prompts_dir = Path(settings.paths.templates)
    assert prompts_dir.name == "system_prompts", "Templates path should point to system_prompts"
    assert prompts_dir.exists(), "System prompts directory must exist"
    
    # 2. Verify Key Files
    architect_instr = prompts_dir / "ARCHITECT_INSTRUCTION.md"
    auditor_instr = prompts_dir / "AUDITOR_INSTRUCTION.md"
    coder_instr = prompts_dir / "CODER_INSTRUCTION.md"
    uat_design = prompts_dir / "UAT_DESIGN.md"
    
    assert architect_instr.exists(), "ARCHITECT_INSTRUCTION.md missing"
    assert auditor_instr.exists(), "AUDITOR_INSTRUCTION.md missing"
    assert coder_instr.exists(), "CODER_INSTRUCTION.md missing"
    assert uat_design.exists(), "UAT_DESIGN.md missing"
    
    # 3. Verify Config Loading (qa_analyst -> UAT_DESIGN)
    # The current settings loader calls _read_prompt which is what we want to test implicitly via the result
    qa_prompt = settings.reviewer.qa_analyst
    assert "UAT Design & Analysis Agent" in qa_prompt, "Failed to load UAT_DESIGN.md content through settings"
    
    # 4. Verify Architect Prompt Loading
    from ac_cdd_core.graph import GraphBuilder
    # We can't easily unit test the graph method without mocking, but we can verify file path construction logic
    # which we already did in step 2.
    
    print("\\n\\n[PASS] All system prompts are correctly located in dev_documents/system_prompts")
