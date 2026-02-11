import shutil
from pathlib import Path

from ac_cdd_core.config import settings
from ac_cdd_core.utils import logger


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

    async def initialize_project(self, templates_path: str) -> None:  # noqa: C901, PLR0912, PLR0915
        """
        Initializes the project structure.
        """
        from ac_cdd_core.process_runner import ProcessRunner
        from ac_cdd_core.services.git_ops import GitManager

        docs_dir = Path(settings.paths.documents_dir)
        docs_dir.mkdir(parents=True, exist_ok=True)

        # Ensure templates directory exists
        templates_dest = Path(templates_path)
        templates_dest.mkdir(parents=True, exist_ok=True)

        # Create ALL_SPEC.md (Project Specs) if not exists
        all_spec_dest = docs_dir / "ALL_SPEC.md"
        if not all_spec_dest.exists():
            all_spec_dest.write_text(
                "# Project Specifications\n\nDefine your project requirements here.",
                encoding="utf-8",
            )

        # Create USER_TEST_SCENARIO.md (Target User Experience) if not exists
        uts_dest = docs_dir / "USER_TEST_SCENARIO.md"
        if uts_dest.exists() and uts_dest.is_dir():
             logger.warning(f"Removing directory {uts_dest} to replace with file")
             shutil.rmtree(uts_dest)

        if not uts_dest.exists():
            uts_content = """# User Test Scenario & Tutorial Plan

## Aha! Moment
Describe the "Magic Moment" where the user first realizes the value of this software.
(e.g., "The user runs one command and sees a beautiful report generated instantly.")

## Prerequisites
List what the user needs before running the tutorial.
(e.g., "OpenAI API Key", "Docker installed")

## Success Criteria
What defines a successful user experience?
(e.g., "The tutorial runs from start to finish without errors in under 5 minutes.")
"""
            uts_dest.write_text(uts_content, encoding="utf-8")
            logger.info(f"✓ Created {uts_dest}")

        # Create other necessary dirs
        (docs_dir / "contracts").mkdir(exist_ok=True)

        # Create system_prompts directory and default templates
        system_prompts_dir = docs_dir / "system_prompts"
        system_prompts_dir.mkdir(exist_ok=True)

        # Copy default instruction templates if they don't exist
        self._copy_default_templates(system_prompts_dir)

        # Create .env.example in project root (NOT in .ac_cdd yet)
        # The .ac_cdd directory will be created later by gen-cycles
        env_example_path = Path.cwd() / ".ac_cdd" / ".env.example"
        env_example_path.parent.mkdir(exist_ok=True)

        if not env_example_path.exists():
            env_example_content = """# AC-CDD Configuration File
# Copy this file to .ac_cdd/.env and fill in your actual API keys

# ============================================================================
# Required API Keys
# ============================================================================

# Jules API Key (Required for AI-powered development agent)
# Get your key from: https://jules.googleapis.com/
JULES_API_KEY=your-jules-api-key-here

# E2B API Key (Required for sandbox execution)
# Get your key from: https://e2b.dev/
E2B_API_KEY=your-e2b-api-key-here

# OpenRouter API Key (Required if using OpenRouter models)
# Get your key from: https://openrouter.ai/
OPENROUTER_API_KEY=your-openrouter-api-key-here

# ============================================================================
# Model Configuration (Simplified)
# ============================================================================
# You only need to set SMART_MODEL and FAST_MODEL.
# These will be used for all agents (Auditor, QA Analyst, Reviewer, etc.)

# SMART_MODEL: Used for complex tasks like code editing and architecture
# Examples:
#   - OpenRouter: openrouter/meta-llama/llama-3.3-70b-instruct:free
#   - Anthropic: claude-3-5-sonnet
#   - Gemini: gemini-2.0-flash-exp
SMART_MODEL=openrouter/meta-llama/llama-3.3-70b-instruct:free

# FAST_MODEL: Used for reading, auditing, and analysis tasks
# Examples:
#   - OpenRouter: openrouter/nousresearch/hermes-3-llama-3.1-405b:free
#   - Anthropic: claude-3-5-sonnet
#   - Gemini: gemini-2.0-flash-exp
FAST_MODEL=openrouter/nousresearch/hermes-3-llama-3.1-405b:free

# ============================================================================
# Optional: Advanced Configuration
# ============================================================================
# Uncomment and modify these if you need fine-grained control

# Override specific agent models (optional)
# AC_CDD_AGENTS__AUDITOR_MODEL=openrouter/meta-llama/llama-3.3-70b-instruct:free
# AC_CDD_AGENTS__QA_ANALYST_MODEL=openrouter/nousresearch/hermes-3-llama-3.1-405b:free

# Override reviewer models (optional)
# AC_CDD_REVIEWER__SMART_MODEL=openrouter/meta-llama/llama-3.3-70b-instruct:free
# AC_CDD_REVIEWER__FAST_MODEL=openrouter/nousresearch/hermes-3-llama-3.1-405b:free

# ============================================================================
# Notes
# ============================================================================
# 1. After copying this to .ac_cdd/.env, it will be automatically loaded
# 2. Never commit your actual API keys to version control
# 3. The .ac_cdd/.env file is already in .gitignore
"""
            env_example_path.write_text(env_example_content, encoding="utf-8")
            logger.info(f"✓ Created .env.example at {env_example_path}")
            logger.info("  Please copy it to .ac_cdd/.env and fill in your API keys:")
            logger.info(f"  cp {env_example_path} .ac_cdd/.env")

        # Update .gitignore to exclude .env files
        gitignore_path = Path.cwd() / ".gitignore"
        gitignore_entries = [
            "# AC-CDD Configuration",
            ".env",
            ".ac_cdd/",  # Ignore entire state directory
            ".ac_cdd/project_state_local.json",
            "dev_documents/project_state.json",
            "dev_documents/project_state_local.json",
        ]

        if gitignore_path.exists():
            content = gitignore_path.read_text(encoding="utf-8")
            entries_to_add = [entry for entry in gitignore_entries if entry not in content]
            if entries_to_add:
                with gitignore_path.open("a", encoding="utf-8") as f:
                    f.write("\n" + "\n".join(entries_to_add) + "\n")
                logger.info("✓ Updated .gitignore")
        else:
            gitignore_path.write_text("\n".join(gitignore_entries) + "\n", encoding="utf-8")
            logger.info("✓ Created .gitignore")

        # Create .github/workflows/ci.yml
        github_dir = Path.cwd() / ".github"
        workflows_dir = github_dir / "workflows"
        workflows_dir.mkdir(parents=True, exist_ok=True)

        ci_yml_path = workflows_dir / "ci.yml"
        if not ci_yml_path.exists():
            ci_content = """name: CI

on:
  push:
    branches: [ main, master, "dev/**", "feature/**" ]
  pull_request:
    branches: [ main, master, "dev/**", "feature/**" ]

jobs:
  quality:
    name: Code Quality
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          version: "latest"

      - name: Set up Python
        run: uv python install 3.12

      - name: Install Dependencies
        run: uv sync --all-extras --dev

      - name: Lint (Ruff)
        run: uv run ruff check .

      - name: Check Formatting (Ruff)
        run: uv run ruff format --check .

      - name: Type Check (Mypy)
        run: uv run mypy .

      - name: Run Tests (Pytest)
        run: uv run pytest
"""
            ci_yml_path.write_text(ci_content, encoding="utf-8")
            logger.info(f"✓ Created CI workflow at {ci_yml_path}")

        # Fix permissions if running with elevated privileges
        await self._fix_permissions(docs_dir, env_example_path.parent, gitignore_path, github_dir)

        # ---------------------------------------------------------
        # Dependency Installation & Git Initialization
        # ---------------------------------------------------------
        runner = ProcessRunner()
        git = GitManager()

        # 1. Initialize uv project (if needed)
        # Check if pyproject.toml exists
        if not (Path.cwd() / "pyproject.toml").exists():
            logger.info("Initializing pyproject.toml...")
            await runner.run_command(["uv", "init", "--no-workspace"], check=False)

        # 2. Add Development Dependencies
        # This creates/updates uv.lock and installs tools locally
        logger.info("Installing development dependencies (ruff, mypy, pytest)...")
        try:
            await runner.run_command(
                ["uv", "add", "--dev", "ruff", "mypy", "pytest", "pytest-cov"], check=True
            )
            logger.info("✓ Dependencies installed successfully.")
        except Exception as e:
            logger.warning(f"Failed to install dependencies: {e}")

        # 3. Git Operations
        # Check if git is initialized
        if not (Path.cwd() / ".git").exists():
            logger.info("Initializing Git repository...")
            await runner.run_command(["git", "init"], check=True)

        try:
            # Add all files
            await git._run_git(["add", "."])

            # Commit
            if await git.commit_changes(
                "Initialize project with AC-CDD structure and dev dependencies"
            ):
                logger.info("✓ Changes committed.")

                # Push to main if remote exists
                try:
                    remote_url = await git.get_remote_url()
                    if remote_url:
                        # Ensure we are on main branch
                        current_branch = await git.get_current_branch()
                        logger.info(f"Pushing {current_branch} to origin...")
                        await git.push_branch(current_branch)
                        logger.info("✓ Successfully pushed to remote.")
                    else:
                        logger.info("No remote 'origin' configured. Skipping push.")
                except Exception as e:
                    logger.warning(f"Failed to push to remote: {e}")
            else:
                logger.info("No changes to commit.")

        except Exception as e:
            logger.warning(f"Git operations failed: {e}")

    async def prepare_environment(self) -> None:
        """
        Prepares the environment for execution:
        1. Fixes permissions of key directories.
        2. Syncs dependencies using uv.
        """
        # Fix permissions first
        docs_dir = Path(settings.paths.documents_dir)
        await self.fix_permissions(docs_dir)

        # Sync dependencies
        from ac_cdd_core.process_runner import ProcessRunner

        runner = ProcessRunner()

        logger.info("[ProjectManager] Syncing dependencies...")
        try:
            # 1. Try sync
            await runner.run_command(["uv", "sync", "--dev"], check=True)

            # 2. Verify linters
            _, _, code_ruff = await runner.run_command(
                ["uv", "run", "ruff", "--version"], check=False
            )
            _, _, code_mypy = await runner.run_command(
                ["uv", "run", "mypy", "--version"], check=False
            )

            if code_ruff != 0 or code_mypy != 0:
                logger.info("[ProjectManager] Installing missing linters...")
                await runner.run_command(["uv", "add", "--dev", "ruff", "mypy"], check=True)

            logger.info("[ProjectManager] Environment prepared.")
        except Exception as e:
            logger.warning(f"[ProjectManager] Dependency sync failed: {e}")

    async def fix_permissions(self, *paths: Path) -> None:
        """Fix file ownership to current user if created with elevated privileges."""
        # Call the internal implementation (which was _fix_permissions)
        await self._fix_permissions(*paths)

    async def _fix_permissions(self, *paths: Path) -> None:  # noqa: C901, PLR0912, PLR0915
        """Internal Fix file ownership implementation."""
        import os
        import pwd
        # ... (rest of implementation is same as original)

        # Determine target UID and GID
        uid: int | None = None
        gid: int | None = None
        target_user: str | None = None

        # Priority 1: Docker environment (HOST_UID/HOST_GID from docker-compose.yml)
        if "HOST_UID" in os.environ and "HOST_GID" in os.environ:
            try:
                uid = int(os.environ["HOST_UID"])
                gid = int(os.environ["HOST_GID"])
                target_user = f"host user (UID={uid})"
                logger.info(f"Detected Docker environment: HOST_UID={uid}, HOST_GID={gid}")
            except ValueError:
                logger.debug("Invalid HOST_UID/HOST_GID values")

        # Priority 2: sudo environment (SUDO_USER)
        if uid is None and "SUDO_USER" in os.environ:
            actual_user = os.environ["SUDO_USER"]
            try:
                pw_record = pwd.getpwnam(actual_user)
                uid = pw_record.pw_uid
                gid = pw_record.pw_gid
                target_user = actual_user
                logger.info(f"Detected sudo environment: user={actual_user}")
            except KeyError:
                logger.debug(f"User {actual_user} not found")

        # Priority 3: Current user (if not root)
        if uid is None:
            current_user = os.environ.get("USER")
            if current_user and current_user != "root":
                try:
                    pw_record = pwd.getpwnam(current_user)
                    uid = pw_record.pw_uid
                    gid = pw_record.pw_gid
                    target_user = current_user
                except KeyError:
                    pass

        # 1. Try to fix ownership (chown) if we have a target user
        if uid is not None and gid is not None and uid != 0:
            try:
                for path in paths:
                    if path.exists():
                        for item in [path, *list(path.rglob("*"))]:
                            try:
                                os.chown(item, uid, gid)
                            except (PermissionError, OSError) as e:
                                logger.debug(f"Could not fix ownership for {item}: {e}")
                logger.info(f"✓ Fixed file ownership for {target_user}")
            except Exception as e:
                logger.debug(f"Could not chown: {e}")

        # 2. ALWAYS relax permissions (chmod 666/777) as a safety net
        # This ensures Docker-created files are editable even if chown failed or if mapping is weird
        try:
            for path in paths:
                if path.exists():
                    for item in [path, *list(path.rglob("*"))]:
                        try:
                            if item.is_dir():
                                item.chmod(0o777)
                            else:
                                item.chmod(0o666)
                        except (PermissionError, OSError) as e:
                            logger.debug(f"Could not relax permissions for {item}: {e}")
            logger.debug("✓ Set permissive file permissions (rw-rw-rw-)")
        except Exception as e:
            logger.debug(f"Could not fix permissions via chmod: {e}")

    def _copy_default_templates(self, system_prompts_dir: Path) -> None:
        """Copy default instruction templates to system_prompts directory."""
        # Define template files to copy
        template_files = [
            "ARCHITECT_INSTRUCTION.md",
            "AUDITOR_INSTRUCTION.md",
            "CODER_INSTRUCTION.md",
            "REFACTOR_INSTRUCTION.md",
            "UAT_DESIGN.md",
            "MANAGER_INSTRUCTION.md",
            "MANAGER_INQUIRY_PROMPT.md",
            "PLAN_REVIEW_PROMPT.md",
            "QA_TUTORIAL_INSTRUCTION.md",
        ]

        # Source directory: package templates (always available)
        source_dir = Path(__file__).parent.parent / "templates"

        if not source_dir.exists():
            logger.warning(f"Template source directory not found: {source_dir}")
            return

        for template_file in template_files:
            source_file = source_dir / template_file
            dest_file = system_prompts_dir / template_file

            # Only copy if source exists and destination doesn't exist
            if source_file.exists() and not dest_file.exists():
                try:
                    shutil.copy(source_file, dest_file)
                    logger.info(f"✓ Created {template_file}")
                except Exception as e:
                    logger.warning(f"Failed to copy {template_file}: {e}")
            elif dest_file.exists():
                logger.debug(f"Skipping {template_file} (already exists)")
