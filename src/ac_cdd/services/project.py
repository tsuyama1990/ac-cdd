import shutil
from pathlib import Path

from ac_cdd.config import settings


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
        except Exception as e:
            return False, f"Failed to create cycle: {e}"
