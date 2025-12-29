import numpy as np
from ase.atoms import Atoms
from ase.calculators.lj import LennardJones


def get_lj_potential(atoms: Atoms) -> float:
    """
    Calculates the potential energy of a system using the Lennard-Jones potential.

    Note: This uses default ASE parameters for Argon (Ar). It serves as a
    simple, fast baseline for the Delta Learning demonstration. For a real
    scientific application, element-specific parameters would be required.

    Args:
        atoms: The `ase.Atoms` object.

    Returns:
        The total potential energy in eV.
    """
    # Using default ASE LJ parameters which are for Argon
    calc = LennardJones()
    atoms.calc = calc
    return atoms.get_potential_energy()


def get_lj_forces(atoms: Atoms) -> np.ndarray:
    """
    Calculates the atomic forces of a system using the Lennard-Jones potential.

    Args:
        atoms: The `ase.Atoms` object.

    Returns:
        A numpy array of forces on each atom.
    """
    # Ensure a calculator is attached from the potential function first
    if not atoms.calc:
        get_lj_potential(atoms)
    return atoms.get_forces()
