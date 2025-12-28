from ase import Atoms
from ase.data import atomic_masses, atomic_numbers


def generate_qe_input(atoms: Atoms, calculation: str = 'scf', ecutwfc: float = 30.0) -> str:
    """
    Generates a Quantum Espresso input string for the given atomic structure.

    Args:
        atoms: The ASE Atoms object.
        calculation: The type of calculation (e.g., 'scf', 'relax').
        ecutwfc: The wavefunction cutoff energy in Ry.

    Returns:
        A string containing the formatted QE input file.
    """

    symbols = sorted(list(set(atoms.get_chemical_symbols())))
    ntyp = len(symbols)
    nat = len(atoms)

    # Control block
    control_block = f"""&CONTROL
    calculation = '{calculation}'
    pseudo_dir = './'
    outdir = './out'
/
"""

    # System block
    system_block = f"""&SYSTEM
    ibrav = 0
    nat = {nat}
    ntyp = {ntyp}
    ecutwfc = {ecutwfc}
/
"""

    # Electrons block
    electrons_block = """&ELECTRONS
    conv_thr = 1.0e-8
/
"""

    # Atomic species block
    atomic_species_lines = ["ATOMIC_SPECIES"]
    for symbol in symbols:
        atomic_number = atomic_numbers[symbol]
        mass = atomic_masses[atomic_number]
        pseudo_file = f"{symbol}.pbe.UPF"
        atomic_species_lines.append(f"  {symbol:<2}  {mass:10.4f}  {pseudo_file}")
    atomic_species_block = "\n".join(atomic_species_lines) + "\n"

    # Cell parameters block
    # Note: QE expects angstrom for CELL_PARAMETERS
    cell_params_lines = ["CELL_PARAMETERS {angstrom}"]
    for vector in atoms.cell:
        cell_params_lines.append(
            f"  {vector[0]:12.8f} {vector[1]:12.8f} {vector[2]:12.8f}"
        )
    cell_parameters_block = "\n".join(cell_params_lines) + "\n"

    # Atomic positions block
    # Note: QE expects crystal coordinates for this format
    atomic_positions_lines = ["ATOMIC_POSITIONS {crystal}"]
    positions = atoms.get_scaled_positions()
    for symbol, pos in zip(atoms.get_chemical_symbols(), positions, strict=True):
        atomic_positions_lines.append(
            f"  {symbol:<2}  {pos[0]:12.8f} {pos[1]:12.8f} {pos[2]:12.8f}"
        )
    atomic_positions_block = "\n".join(atomic_positions_lines) + "\n"

    return (
        control_block +
        system_block +
        electrons_block +
        atomic_species_block +
        cell_parameters_block +
        atomic_positions_block
    )
