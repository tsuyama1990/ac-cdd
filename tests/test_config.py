from ac_cdd_core.config import settings


def test_config_agents_loaded():
    """Test that agents configuration is loaded correctly from files."""
    # Aider configuration holds the prompts and model configs for auditor
    assert settings.aider.auditor is not None
    assert settings.aider.qa_analyst is not None

    # Check for content that actually exists in the prompts or defaults
    assert (
        "DEFAULT_AUDITOR_PROMPT" in settings.aider.auditor
        or "Code Auditor" in settings.aider.auditor
    )
    assert (
        "DEFAULT_QA_ANALYST_PROMPT" in settings.aider.qa_analyst
        or "QA Manager" in settings.aider.qa_analyst
    )


def test_tools_config():
    """Test that tools configuration is loaded"""
    assert settings.tools.jules_cmd == "jules"
    assert settings.tools.gemini_cmd == "gemini"
