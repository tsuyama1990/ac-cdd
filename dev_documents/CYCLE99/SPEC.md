# Cycle 99 Specification: QE Input Generator (Subset of Cycle 01)

## Objective
Implement the `generate_qe_input` function in `dft_utils.py`.
This function is a critical component of the Labelling Engine (Module C) described in Cycle 01.

## Requirements

### Function Signature
```python
from ase import Atoms

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
    pass
```

### Implementation Details
1.  The function must accept an `ase.Atoms` object.
2.  It should produce a string respecting standard QE input format.
3.  **Key Sections Required:**
    *   `&CONTROL`: `calculation`, `pseudo_dir`, `outdir`
    *   `&SYSTEM`: `ibrav=0`, `nat`, `ntyp`, `ecutwfc`
    *   `&ELECTRONS`: `conv_thr`
    *   `ATOMIC_SPECIES`: Mapping symbol to mass and pseudo file (use `Symbol.pbe.UPF` pattern)
    *   `ATOMIC_POSITIONS`: Crystal coordinates
    *   `CELL_PARAMETERS`: Angstrom

## Constraints
- Use the `ase` library.
- Keep it simple (no complex k-points logic required for this test, defaults are fine).
