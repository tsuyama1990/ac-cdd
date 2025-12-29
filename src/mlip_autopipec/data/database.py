from pathlib import Path

import numpy as np
from ase.atoms import Atoms
from ase.calculators.singlepoint import SinglePointCalculator
from ase.db import connect

from mlip_autopipec.data.models import DFTResult


class AseDB:
    """
    A wrapper class for handling interactions with an ASE (Atomic Simulation Environment)
    SQLite database. This class provides a structured way to write and read atomistic
    simulation data.
    """

    def __init__(self, db_path: str | Path):
        """
        Initialises the AseDB object and connects to the specified database file.

        Args:
            db_path: The file path to the SQLite database. If it doesn't exist,
                     it will be created.
        """
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = connect(self._db_path)

    def write(self, atoms: Atoms, result: DFTResult) -> int:
        """
        Writes an atomic configuration and its associated DFT calculation results
        to the database.

        This method attaches the results to the ase.Atoms object using a
        SinglePointCalculator, which is the standard ASE practice for storing
        energy, forces, and stress. Metadata is stored as key-value pairs.

        Args:
            atoms: The `ase.Atoms` object representing the atomic structure.
            result: A `DFTResult` object containing the calculation outputs.

        Returns:
            The unique ID of the newly created row in the database.
        """
        # Convert 3x3 stress tensor to 6-element Voigt form (xx, yy, zz, yz, xz, xy)
        stress_voigt = [
            result.stress[0][0],
            result.stress[1][1],
            result.stress[2][2],
            result.stress[1][2],
            result.stress[0][2],
            result.stress[0][1],
        ]

        # Attach results to the Atoms object via a SinglePointCalculator
        calc = SinglePointCalculator(
            atoms=atoms,
            energy=result.total_energy_ev,
            forces=np.array(result.forces),
            stress=np.array(stress_voigt),
        )
        atoms.calc = calc

        # Filter out None values from key-value pairs, as ASE DB doesn't support them.
        key_value_pairs = {
            "was_successful": result.was_successful,
            "error_message": result.error_message,
        }
        kvp_filtered = {k: v for k, v in key_value_pairs.items() if v is not None}

        db_id = self._db.write(atoms, key_value_pairs=kvp_filtered)
        return int(db_id)
