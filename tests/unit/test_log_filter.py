def test_clean_logs_logic():
    """
    Test that the clean_logs internal function (simulated here)
    correctly removes pip/uv installation noise.
    """

    # This is the exact cleaning logic from graph.py (as we intend it to be)
    # We duplicate it here to TDD it, then we sync it back.
    def clean_logs(text: str) -> str:
        lines = text.splitlines()
        cleaned = []
        # Expanded keywords based on user report
        block_keywords = [
            "Uninstalling",
            "Successfully installed",
            "Successfully uninstalled",
            "Attempting uninstall",
            "Found existing",
            "Obtaining file://",
            "Built autonomous-dev-env",
            "Uninstalled",
            "Installed",
            "Downloading",
            "Using cached",
            "Requirement already satisfied",
        ]
        for line in lines:
            if not any(k in line for k in block_keywords):
                cleaned.append(line)
        return "\n".join(cleaned)

    noise_sample = """
Uninstalling anyio-4.11.0:
Successfully uninstalled anyio-4.11.0
Attempting uninstall: pydantic
Found existing installation: pydantic 2.12.4
Uninstalling pydantic-2.12.4:
Successfully uninstalled pydantic-2.12.4
Successfully installed aider-chat-0.86.1 aiohttp-3.12.15
ERROR: file or directory not found: tests/
"""

    cleaned = clean_logs(noise_sample)

    assert "Uninstalling" not in cleaned
    assert "Successfully uninstalled" not in cleaned
    assert "Attempting uninstall" not in cleaned
    assert "Found existing" not in cleaned
    assert "Successfully installed" not in cleaned

    # Crucially, the real error MUST remain
    assert "ERROR: file or directory not found: tests/" in cleaned
    # Empty lines might remain or be stripped, but let's check basic cleanliness
    assert len(cleaned.strip().splitlines()) == 1
