from pathlib import Path

import yaml
from ase.io import read

from mlip_autopipec.data.database import AseDB
from mlip_autopipec.data.models import TrainingConfig
from mlip_autopipec.modules.c_labelling_engine import LabellingEngine
from mlip_autopipec.modules.d_training_engine import TrainingEngine


def run_cycle01_workflow(config_path: str | Path, structure_path: str | Path):
    """
    Orchestrates the simple, linear workflow for Cycle 01.
    This version handles multiple atomic structures from the input file.
    """
    with open(config_path) as f:
        config = yaml.safe_load(f)

    db_path = Path(config["database"]["path"])
    db = AseDB(db_path)
    labeller = LabellingEngine(qe_command=config["labelling"]["qe_command"], db=db)
    training_config = TrainingConfig(**config["training"])
    trainer = TrainingEngine(config=training_config, db=db)

    print(f"Reading initial structures from: {structure_path}")
    # Read all structures from the file using index=':'
    initial_structures = read(structure_path, index=':')
    if not isinstance(initial_structures, list):
        initial_structures = [initial_structures]

    db_ids = []
    for i, atoms in enumerate(initial_structures):
        print(f"Starting Labelling Engine for structure {i+1}/{len(initial_structures)}...")
        db_id = labeller.execute(
            atoms=atoms,
            pseudo_dir=config["labelling"]["pseudo_dir"],
            ecutwfc=config["labelling"]["ecutwfc"],
            kpts=tuple(config["labelling"]["kpts"]),
        )
        print(f"Labelling complete. Data saved with ID: {db_id}")
        db_ids.append(db_id)

    if not db_ids:
        print("No structures were labelled. Exiting.")
        return

    print("Starting Training Engine...")
    trained_model_path = trainer.execute(ids=db_ids)
    print(f"\nWorkflow complete. Model saved to: {trained_model_path}")
