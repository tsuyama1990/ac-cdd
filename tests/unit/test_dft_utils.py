from ase.build import bulk

from mlip_autopipec.utils.dft_utils import generate_qe_input


def test_generate_qe_input_silicon():
    """
    Tests the generation of a Quantum Espresso input file for a silicon crystal.
    Verifies that all required sections and key parameters are present and correctly formatted.
    """
    # 1. Create a simple Silicon structure as per UAT
    atoms = bulk('Si', 'diamond', a=5.43)

    # 2. Call the function to be tested
    qe_input = generate_qe_input(atoms, calculation='scf', ecutwfc=40.0)

    # 3. Verify the output string
    # Check for presence of key sections
    assert '&CONTROL' in qe_input
    assert '&SYSTEM' in qe_input
    assert '&ELECTRONS' in qe_input
    assert 'ATOMIC_SPECIES' in qe_input
    assert 'ATOMIC_POSITIONS' in qe_input
    assert 'CELL_PARAMETERS' in qe_input

    # Verify specific parameters from UAT
    assert "calculation = 'scf'" in qe_input
    assert 'ecutwfc = 40.0' in qe_input

    # Verify content of sections
    assert 'nat = 2' in qe_input # 2 atoms in a diamond primitive cell
    assert 'ntyp = 1' in qe_input # 1 type of atom (Si)

    # Verify atomic species section
    assert 'Si' in qe_input
    assert 'Si.pbe.UPF' in qe_input # Check for pseudopotential filename convention

    # Check for correct number of atomic positions
    lines = qe_input.split('\n')
    atomic_positions_index = -1
    for i, line in enumerate(lines):
        if 'ATOMIC_POSITIONS' in line:
            atomic_positions_index = i
            break

    assert atomic_positions_index != -1, "ATOMIC_POSITIONS block not found"

    # Filter for non-empty lines after the ATOMIC_POSITIONS header
    atom_lines = [
        line.strip() for line in lines[atomic_positions_index+1:]
        if line.strip() and not line.strip().startswith(('&', '/'))
    ]
    assert len(atom_lines) >= 2, f"Expected at least 2 atom lines, found {len(atom_lines)}"
    assert 'Si' in atom_lines[0]

    # Verify cell parameters are present
    cell_params_index = -1
    for i, line in enumerate(lines):
        if 'CELL_PARAMETERS' in line:
            cell_params_index = i
            break

    assert cell_params_index != -1, "CELL_PARAMETERS block not found"

    # Check that there are 3 lines of cell vectors
    cell_lines = [
        line.strip() for line in lines[cell_params_index+1:]
        if line.strip() and not line.strip().startswith(('&', '/'))
    ]
    msg = f"Expected at least 3 cell vector lines, found {len(cell_lines)}"
    assert len(cell_lines) >= 3, msg
