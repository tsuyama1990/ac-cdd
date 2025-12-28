# Cycle 99 UAT: QE Input Generator

## Test Case 1: Silicon Crystal
1.  Create a simple Silicon structure:
    ```python
    from ase.build import bulk
    atoms = bulk('Si', 'diamond', a=5.43)
    ```
2.  Call `generate_qe_input(atoms, calculation='scf', ecutwfc=40.0)`.
3.  **Verify:**
    *   Output contains `calculation = 'scf'`
    *   Output contains `ecutwfc = 40.0`
    *   Output contains `ATOMIC_SPECIES` with `Si`
    *   Output contains `ATOMIC_POSITIONS`
