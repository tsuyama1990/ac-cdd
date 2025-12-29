from ase import Atoms
from ase.data import atomic_masses, atomic_numbers


def generate_qe_input(atoms: Atoms, calculation: str = "scf", ecutwfc: float = 30.0) -> str:
    """
    Generates a Quantum Espresso input string for the given atomic structure.
    This is a general-purpose function that correctly formats data from the ASE Atoms object.

    Args:
        atoms: The ASE Atoms object representing the structure.
        calculation: The type of calculation (e.g., 'scf', 'relax').
        ecutwfc: The wavefunction cutoff energy in Ry.

    Returns:
        A string containing the formatted QE input file.
    """

    symbols = sorted(list(set(atoms.get_chemical_symbols())))
    ntyp = len(symbols)
    nat = len(atoms)

    # Basic input parameters
    control_params = {
        "calculation": f"'{calculation}'",
        "pseudo_dir": "'./'",
        "outdir": "'./out'",
    }
    system_params = {
        "ibrav": 0,
        "nat": nat,
        "ntyp": ntyp,
        "ecutwfc": ecutwfc,
    }
    electron_params = {"conv_thr": "1.0e-8"}

    # Build the namelist strings
    control_block = (
        "&CONTROL\n"
        + "\n".join(f"    {key} = {value}" for key, value in control_params.items())
        + "\n/\n"
    )
    system_block = (
        "&SYSTEM\n"
        + "\n".join(f"    {key} = {value}" for key, value in system_params.items())
        + "\n/\n"
    )
    electrons_block = (
        "&ELECTRONS\n"
        + "\n".join(f"    {key} = {value}" for key, value in electron_params.items())
        + "\n/\n"
    )

    # Atomic species block
    atomic_species_lines = ["ATOMIC_SPECIES"]
    for symbol in symbols:
        atomic_number = atomic_numbers[symbol]
        mass = atomic_masses[atomic_number]
        pseudo_file = f"{symbol}.pbe.UPF"
        atomic_species_lines.append(f"  {symbol:<4} {mass:10.4f}  {pseudo_file}")
    atomic_species_block = "\n".join(atomic_species_lines) + "\n\n"

    # Cell parameters block (in Angstrom)
    cell_params_lines = ["CELL_PARAMETERS {angstrom}"]
    for vector in atoms.cell:
        cell_params_lines.append(f"  {vector[0]:16.9f} {vector[1]:16.9f} {vector[2]:16.9f}")
    cell_parameters_block = "\n".join(cell_params_lines) + "\n\n"

    # Atomic positions block (in crystal coordinates)
    atomic_positions_lines = ["ATOMIC_POSITIONS {crystal}"]
    positions = atoms.get_scaled_positions()
    for symbol, pos in zip(atoms.get_chemical_symbols(), positions, strict=True):
        atomic_positions_lines.append(f"  {symbol:<4} {pos[0]:16.9f} {pos[1]:16.9f} {pos[2]:16.9f}")
    atomic_positions_block = "\n".join(atomic_positions_lines)

    return (
        control_block
        + system_block
        + electrons_block
        + atomic_species_block
        + cell_parameters_block
        + atomic_positions_block
    )
