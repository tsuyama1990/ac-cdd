import re

file_path = "dev_src/ac_cdd_core/services/project.py"
with open(file_path) as f:
    text = f.read()

# Replace Imports
new_imports = """from ac_cdd_core.config import settings
from ac_cdd_core.utils import logger
from .project_setup.template_manager import TemplateManager
from .project_setup.dependency_manager import DependencyManager
from .project_setup.permission_manager import PermissionManager
"""
text = text.replace("from ac_cdd_core.config import settings\nfrom ac_cdd_core.utils import logger\n", new_imports)

# Rewrite initialize_project
new_init_project = """    async def initialize_project(self, templates_path: str) -> None:
        \"\"\"Initializes the project structure.\"\"\"
        template_mgr = TemplateManager()
        docs_dir, env_example_path, gitignore_path, github_dir = template_mgr.setup_templates(templates_path)

        # Fix permissions if running with elevated privileges
        perm_mgr = PermissionManager()
        await perm_mgr.fix_permissions(docs_dir, env_example_path.parent, gitignore_path, github_dir)

        # Dependency Installation & Git Initialization
        dep_mgr = DependencyManager()
        await dep_mgr.initialize_dependencies_and_git()"""

# Replace initialize_project entirely
init_pattern = r"    async def initialize_project\(self, templates_path: str\) -> None:.*?        # ---------------------------------------------------------\n        # Dependency Installation & Git Initialization\n        # ---------------------------------------------------------\n.*?        except Exception as e:\n            logger\.warning\(f\"Git operations failed: \{e\}\"\)"
text = re.sub(init_pattern, new_init_project, text, flags=re.DOTALL)

# Rewrite prepare_environment
new_prep_env = """    async def prepare_environment(self) -> None:
        \"\"\"
        Prepares the environment for execution.
        \"\"\"
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
        await dep_mgr.sync_dependencies()"""

prep_pattern = r"    async def prepare_environment\(self\) -> None:.*?            logger\.warning\(f\"\[ProjectManager\] Dependency sync failed: \{e\}\"\)"
text = re.sub(prep_pattern, new_prep_env, text, flags=re.DOTALL)

# Delete fix_permissions, _fix_permissions, _copy_default_templates
methods_to_delete = [
    r"    async def fix_permissions\(self, \*paths: Path\) -> None:.*?        await self\._fix_permissions\(\*paths\)\n\n",
    r"    async def _fix_permissions\(self, \*paths: Path\) -> None:.*?            logger\.debug\(f\"Could not fix permissions via chmod: \{e\}\"\)\n\n",
    r"    def _copy_default_templates\(self, system_prompts_dir: Path\) -> None:.*?                logger\.debug\(f\"Skipping \{template_file\} \(already exists\)\"\)\n"
]

for pattern in methods_to_delete:
    text = re.sub(pattern, "", text, flags=re.DOTALL)

with open(file_path, "w") as f:
    f.write(text)

print("Done")
