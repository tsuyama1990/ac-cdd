import shutil
from pathlib import Path

from ac_cdd_core.config import settings


class ProjectManager:
    """
    Manages project lifecycle operations like creating new cycles.
    """

    def create_new_cycle(self, cycle_id: str) -> tuple[bool, str]:
        """
        Creates a new cycle directory structure.
        Returns (success, message).
        """
        base_path = Path(settings.paths.documents_dir) / f"CYCLE{cycle_id}"
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

            return True, msg
            return True, msg
        except Exception as e:
            return False, f"Failed to create cycle: {e}"

    def initialize_project(self, templates_path: str) -> None:
        """
        Initializes the project structure.
        """
        docs_dir = Path(settings.paths.documents_dir)
        docs_dir.mkdir(parents=True, exist_ok=True)
        
        # Ensure templates directory exists
        templates_dest = Path(templates_path)
        templates_dest.mkdir(parents=True, exist_ok=True)
        
        # Create ARCHITECT_INSTRUCTION.md if not exists
        arch_instr = templates_dest / "ARCHITECT_INSTRUCTION.md"
        if not arch_instr.exists():
            arch_instr.write_text(
                "# Architect Instruction\n\nDefine your system architecture here.",
                encoding="utf-8",
            )

        # Copy ALL_SPEC.md to dev_documents if it exists in templates
        all_spec_template = templates_dest / "ALL_SPEC.md"
        all_spec_dest = docs_dir / "ALL_SPEC.md"
        if all_spec_template.exists() and not all_spec_dest.exists():
            shutil.copy(all_spec_template, all_spec_dest)

        # Create other necessary dirs
        (docs_dir / "contracts").mkdir(exist_ok=True)

