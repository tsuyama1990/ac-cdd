from pathlib import Path

from ase.atoms import Atoms

from mlip_autopipec.data.database import AseDB
from mlip_autopipec.utils import dft_utils


class LabellingEngine:
    """
    This class encapsulates the logic for performing automated Density Functional
    Theory (DFT) calculations using Quantum Espresso. It acts as a robust wrapper
    that handles input file generation, execution of the DFT code, parsing of the
    output, and storage of the results in the project's database.
    """

    def __init__(self, qe_command: str, db: AseDB):
        """
        Initialises the LabellingEngine.

        Args:
            qe_command: The command-line instruction to execute Quantum Espresso's
                        pw.x, including any MPI prefixes (e.g., "mpirun -np 4 pw.x").
            db: An initialised AseDB object for database interactions.
        """
        self._qe_command = qe_command
        self._db = db

    def execute(
        self,
        atoms: Atoms,
        pseudo_dir: str | Path,
        ecutwfc: int = 60,
        kpts: tuple[int, int, int] = (4, 4, 4),
    ) -> int:
        """
        Executes the full DFT labelling workflow for a given atomic structure.

        This method performs the following steps:
        1. Generates a Quantum Espresso input file from the `ase.Atoms` object.
        2. Runs the Quantum Espresso calculation as a subprocess.
        3. Parses the output to extract energy, forces, and stress.
        4. Writes the results to the ASE database.

        Args:
            atoms: The `ase.Atoms` object representing the structure to be calculated.
            pseudo_dir: The path to the directory containing pseudopotential files.
            ecutwfc: The plane-wave energy cutoff for the calculation (in Ry).
            kpts: The k-point mesh for the calculation.

        Returns:
            The unique database ID of the newly created record.
        """
        work_dir = Path.cwd()
        input_filepath = work_dir / "QE_input.in"

        # 1. Generate input file
        input_content = dft_utils.generate_qe_input(
            atoms=atoms, pseudo_dir=pseudo_dir, ecutwfc=ecutwfc, kpts=kpts
        )
        with open(input_filepath, "w") as f:
            f.write(input_content)

        # 2. Run Quantum Espresso
        success, stdout, stderr = dft_utils.run_qe(self._qe_command, input_filepath)

        if not success:
            # Handle cases where the pw.x executable itself fails
            # (e.g., file not found, MPI error)
            result = dft_utils.parse_qe_output(stdout + "\n" + stderr)
            result.was_successful = False
            if not result.error_message:
                result.error_message = (
                    f"Subprocess failed with return code != 0. Stderr: {stderr}"
                )
        else:
            # 3. Parse the output
            result = dft_utils.parse_qe_output(stdout)

        # 4. Save results to the database
        db_id = self._db.write(atoms, result)

        # Clean up input file
        input_filepath.unlink()

        return db_id
