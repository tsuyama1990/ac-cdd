import shutil
from pathlib import Path

from ac_cdd_core.config import settings
from ac_cdd_core.utils import logger

from .project_setup.dependency_manager import DependencyManager
from .project_setup.permission_manager import PermissionManager
from .project_setup.template_manager import TemplateManager


class ProjectManager:
    """
    Manages project lifecycle operations like creating new cycles.
    """

    def create_new_cycle(self, cycle_id: str) -> tuple[bool, str]:
        """
        Creates a new cycle directory structure.
        Returns (success, message).
        """
        base_path = Path(settings.paths.templates) / f"CYCLE{cycle_id}"
        if base_path.exists():
            return False, f"Cycle {cycle_id} already exists!"

        try:
            base_path.mkdir(parents=True)
            templates_dir = Path(settings.paths.templates) / "cycle"

            missing_templates = []
            for item in ["SPEC.md", "UAT.md", "schema.py"]:
                src = templates_dir / item
                if src.exists():
                    shutil.copy(src, base_path / item)
                else:
                    missing_templates.append(item)

            msg = f"Created new cycle: CYCLE{cycle_id} at {base_path}"
            if missing_templates:
                msg += f"\nWarning: Missing templates: {', '.join(missing_templates)}"

        except Exception as e:
            return False, f"Failed to create cycle: {e}"
        else:
            return True, msg

    async def initialize_project(self, templates_path: str) -> None:
        """Initializes the project structure."""
        template_mgr = TemplateManager()
        docs_dir, env_example_path, gitignore_path, github_dir = template_mgr.setup_templates(
            templates_path
        )

        # Fix permissions if running with elevated privileges
        perm_mgr = PermissionManager()
        await perm_mgr.fix_permissions(
            docs_dir, env_example_path.parent, gitignore_path, github_dir
        )

        # Dependency Installation & Git Initialization
        dep_mgr = DependencyManager()
        await dep_mgr.initialize_dependencies_and_git()

    async def prepare_environment(self) -> None:
        """
        Prepares the environment for execution.
        """
        import os
        from pathlib import Path as _Path

        perm_mgr = PermissionManager()
        docs_dir = _Path(settings.paths.documents_dir)
        await perm_mgr.fix_permissions(docs_dir)

        in_docker = _Path("/.dockerenv").exists() or os.environ.get("DOCKER_CONTAINER") == "true"
        if in_docker:
            logger.info(
                "[ProjectManager] Running inside Docker — skipping 'uv sync' to avoid "
                "contaminating the host .venv with Docker-internal paths (/app/.venv). "
                "The user should run 'uv sync' on their host machine instead."
            )
            return

        dep_mgr = DependencyManager()
        await dep_mgr.sync_dependencies()
