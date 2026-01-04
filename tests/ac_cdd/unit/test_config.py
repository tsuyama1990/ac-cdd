import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from ac_cdd_core.config import Settings


@pytest.fixture
def mock_env():
    with patch.dict(
        os.environ,
        {
            "AC_CDD_REVIEWER__SMART_MODEL": "test-smart-model",
            "AC_CDD_PATHS__DOCUMENTS_DIR": "/tmp/docs",  # noqa: S108
            "AC_CDD_JULES__TIMEOUT_SECONDS": "999",
        },
    ):
        yield


def test_config_env_vars_loaded(mock_env) -> None:
    """Test that environment variables override defaults."""
    # We must instantiate a new Settings object to pick up the env vars
    # because the global 'settings' object is instantiated at import time.
    local_settings = Settings()

    assert local_settings.reviewer.smart_model == "test-smart-model"
    assert str(local_settings.paths.documents_dir) == "/tmp/docs"  # noqa: S108
    assert local_settings.jules.timeout_seconds == 999


def test_config_defaults() -> None:
    """Test default values without env overrides."""
    # Clean env for this test
    with patch.dict(os.environ, {}, clear=True):
        local_settings = Settings()
        assert local_settings.reviewer.smart_model == "claude-3-5-sonnet"
        assert str(local_settings.paths.src) == str(Path.cwd() / "src")
        assert str(local_settings.paths.templates) == str(
            Path.cwd() / "dev_documents" / "templates"
        )


def test_get_template_logic() -> None:
    """Test the template resolution logic priority."""
    local_settings = Settings()
    local_settings.paths.documents_dir = Path("/user/docs")
    local_settings.paths.templates = Path("/system/templates")

    # 1. Mock file existence logic without over-patching

    # We mock only Path.exists.
    # The conflict in previous run was due to nesting patches or autospec issues.

    def side_effect(self) -> bool:
        s = str(self)
        if s.startswith("/user/docs/system_prompts/foo.md"):
            return True
        return bool(s.startswith("/system/templates/bar.md"))

    with patch("pathlib.Path.exists", side_effect=side_effect, autospec=True):
        # Case 1: User override
        result1 = local_settings.get_template("foo.md")
        assert str(result1) == "/user/docs/system_prompts/foo.md"

        # Case 2: System default
        result2 = local_settings.get_template("bar.md")
        assert str(result2) == "/system/templates/bar.md"


def test_get_prompt_content() -> None:
    """Test that prompt content is read correctly."""
    local_settings = Settings()

    # Mock get_template to return a specific path
    with patch.object(Settings, "get_template") as mock_get_template:
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = "MOCKED PROMPT CONTENT"
        mock_get_template.return_value = mock_path

        content = local_settings.get_prompt_content("auditor.md")

        # Check that it tried to resolve the mapped filename
        mock_get_template.assert_called_with("AUDITOR_INSTRUCTION.md")
        assert content == "MOCKED PROMPT CONTENT"


def test_path_separation() -> None:
    """
    Test that Context (Specs) and Target (Code) paths are strictly separated.
    Requirements:
    - get_context_files() returns ONLY files in dev_documents
    - get_target_files() returns ONLY files in src and tests
    """
    local_settings = Settings()

    # Setup mock file system
    # We mock Path.glob, rglob, and exists

    with (
        patch("pathlib.Path.glob") as mock_glob,
        patch("pathlib.Path.rglob") as mock_rglob,
        patch("pathlib.Path.exists", return_value=True),
    ):
        # Mock glob for docs
        # We need to ensure it only returns for the right directory, but since
        # the methods are called on specific paths, we can check the path instance in side_effect?
        # Simpler: just return valid paths and check filtering logic in the test.
        # But the code logic relies on `self.paths.documents_dir.glob`.

        mock_glob.return_value = [Path("/app/dev_documents/spec1.md")]

        # Mock rglob for src/tests
        # get_target_files calls rglob twice: once on src, once on tests
        mock_rglob.side_effect = [
            [Path("/app/src/main.py")],  # src rglob
            [Path("/app/tests/test_main.py")],  # tests rglob
        ]

        context_files = local_settings.get_context_files()
        target_files = local_settings.get_target_files()

        # Verify Context Files
        assert len(context_files) == 1
        assert context_files[0] == "/app/dev_documents/spec1.md"
        # Ensure no src files here
        for f in context_files:
            assert "src" not in f

        # Verify Target Files
        assert len(target_files) == 2
        assert "/app/src/main.py" in target_files
        assert "/app/tests/test_main.py" in target_files
        # Ensure no docs here
        for f in target_files:
            assert "dev_documents" not in f
