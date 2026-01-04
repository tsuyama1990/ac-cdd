import shutil
from pathlib import Path

from ac_cdd_core.config import settings


class ContractManager:
    """
    Manages contract files (schemas) synchronization.
    """

    def align_contracts(self, cycle_id: str) -> None:
        """
        Syncs schema.py from the cycle document directory to the contracts directory.
        """
        contracts_dir = Path(settings.paths.contracts_dir)
        cycle_dir = Path(settings.paths.templates) / f"CYCLE{cycle_id}"
        source_schema = cycle_dir / "schema.py"
        target_schema = contracts_dir / f"schema_cycle{cycle_id}.py"

        if not source_schema.exists():
            msg = f"{source_schema} not found."
            raise FileNotFoundError(msg)

        contracts_dir.mkdir(parents=True, exist_ok=True)

        if target_schema.exists():
            backup = target_schema.with_suffix(".py.bak")
            shutil.copy(target_schema, backup)

        shutil.copy(source_schema, target_schema)

        init_file = contracts_dir / "__init__.py"
        import_line = f"from .schema_cycle{cycle_id} import *"

        if init_file.exists():
            content = init_file.read_text(encoding="utf-8")
            if import_line not in content:
                with init_file.open("a", encoding="utf-8") as f:
                    f.write(f"\n{import_line}\n")
        else:
            with init_file.open("w", encoding="utf-8") as f:
                f.write(f"{import_line}\n")
