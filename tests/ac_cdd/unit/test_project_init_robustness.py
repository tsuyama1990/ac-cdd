from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ac_cdd_core.services.project import ProjectManager


@pytest.mark.asyncio
async def test_initialize_project_robustness(tmp_path: Path) -> None:
    """
    Verifies that initialize_project:
    1. Creates basic file structure
    2. Creates .github/workflows/ci.yml
    3. Requires 'uv' dependencies
    4. Initializes git and performs initial commit/push
    """
    # Setup mocks
    mock_settings = MagicMock()
    mock_settings.paths.documents_dir = tmp_path / "dev_documents"

    # Mock GitManager instance
    mock_git_instance = AsyncMock()
    mock_git_instance.commit_changes.return_value = True
    mock_git_instance.get_remote_url.return_value = "https://github.com/test/repo.git"
    mock_git_instance.get_current_branch.return_value = "main"

    # Mock ProcessRunner instance
    mock_runner_instance = AsyncMock()

    # We need to mock the path to templates
    templates_path = tmp_path / "templates"

    # Mocking Path.cwd is critical because the code uses it to access .github and .gitignore
    with (
        patch("ac_cdd_core.services.project.settings", mock_settings),
        patch("ac_cdd_core.services.project_setup.template_manager.settings", mock_settings),
        patch("ac_cdd_core.services.project_setup.dependency_manager.GitManager", return_value=mock_git_instance),
        patch("ac_cdd_core.services.project_setup.dependency_manager.ProcessRunner", return_value=mock_runner_instance),
        patch("pathlib.Path.cwd", return_value=tmp_path),
        patch("ac_cdd_core.services.project_setup.dependency_manager.Path.cwd", return_value=tmp_path),
        patch("ac_cdd_core.services.project_setup.template_manager.Path.cwd", return_value=tmp_path),
    ):
        # Setup mock template files since template_manager copies them
        templates_path.mkdir(parents=True, exist_ok=True)
        (templates_path / "ALL_SPEC.md").write_text("spec")
        (templates_path / ".env.example").write_text("env")
        (templates_path / ".gitignore.template").write_text("ignore")

        # Execute
        pm = ProjectManager()
        await pm.initialize_project(str(templates_path))

        # --- Assertions ---

        # 1. CI Workflow Generation
        ci_path = tmp_path / ".github" / "workflows" / "ci.yml"
        assert ci_path.exists(), "CI workflow file was not created"
        content = ci_path.read_text()
        assert "uv run ruff check ." in content, "CI should run ruff check"
        assert "uv run mypy ." in content, "CI should run mypy"
        assert "uv sync --all-extras --dev" in content, "CI should sync dev dependencies"

        # 2. Dependency Installation
        # Filter calls for strict checking
        calls = [c[0][0] for c in mock_runner_instance.run_command.call_args_list]

        # Check 'uv init --no-workspace' (since pyproject.toml didn't exist in tmp_path)
        uv_init_called = any(cmd[:2] == ["uv", "init"] for cmd in calls)
        assert uv_init_called, "uv init should be called when pyproject.toml is missing"

        # Check 'uv add --dev ...'
        uv_add_called = any(
            cmd[:3] == ["uv", "add", "--dev"] and "ruff" in cmd and "mypy" in cmd for cmd in calls
        )
        assert uv_add_called, "uv add --dev should be called for linters"

        # 3. Git Operations
        # Check 'git init' via runner (since .git didn't exist)
        git_init_called = any(cmd == ["git", "init"] for cmd in calls)
        assert git_init_called, "git init should be called when .git is missing"

        # Check git add via GitManager
        mock_git_instance._run_git.assert_any_call(["add", "."])

        # Check git commit via GitManager
        mock_git_instance.commit_changes.assert_called_with(
            "Initialize project with AC-CDD structure and dev dependencies"
        )

        # Check git push via GitManager (since remote url mock returned a value)
        mock_git_instance.push_branch.assert_called_with("main")

        # 4. Verify basic files were created
        assert (tmp_path / "dev_documents" / "ALL_SPEC.md").exists()
        assert (tmp_path / ".ac_cdd" / ".env.example").exists()
        assert (tmp_path / ".gitignore").exists()
