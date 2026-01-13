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

    def initialize_project(self, templates_path: str) -> None:
        """
        Initializes the project structure.
        """
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
            ".ac_cdd/.env",
            "dev_documents/project_state.json",
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

        # Fix permissions if running with elevated privileges
        self._fix_permissions(docs_dir, env_example_path.parent, gitignore_path)

    def _fix_permissions(self, *paths: Path) -> None:  # noqa: C901, PLR0912
        """Fix file ownership to current user if created with elevated privileges."""
        import os
        import pwd

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
            "UAT_DESIGN.md",
            "MANAGER_INSTRUCTION.md",
            "MANAGER_INQUIRY_PROMPT.md",
            "PLAN_REVIEW_PROMPT.md",
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
