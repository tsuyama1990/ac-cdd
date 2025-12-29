# tests/unit/test_dft_utils.py
import numpy as np
from ase.build import bulk
from ase.data import atomic_masses, atomic_numbers

from mlip_autopipec.utils.dft_utils import generate_qe_input


def parse_qe_input(qe_input: str) -> dict:
    """A simple parser to extract key information from a QE input string."""
    data = {
        "sections": [],
        "variables": {},
        "atomic_species": [],
        "cell": [],
        "positions": [],
    }
    current_section = None
    lines = qe_input.strip().split("\n")

    for line in lines:
        line = line.strip()
        if not line or line.startswith(("!", "#")):
            continue

        if line.startswith("&"):
            section_name = line.strip("&")
            data["sections"].append(section_name)
            current_section = "variables"
        elif "ATOMIC_SPECIES" in line:
            current_section = "atomic_species"
        elif "ATOMIC_POSITIONS" in line:
            current_section = "atomic_positions"
        elif "CELL_PARAMETERS" in line:
            current_section = "cell_parameters"
        elif line.startswith("/"):
            current_section = None
        elif current_section == "variables" and "=" in line:
            key, value = [p.strip().strip("'\"") for p in line.split("=")]
            try:
                data["variables"][key] = float(value)
            except ValueError:
                data["variables"][key] = value
        elif current_section == "atomic_species":
            parts = line.split()
            if len(parts) == 3:
                symbol, mass, pseudo = parts
                data["atomic_species"].append(
                    {"symbol": symbol, "mass": float(mass), "pseudo": pseudo}
                )
        elif current_section == "cell_parameters":
            parts = line.split()
            if len(parts) == 3:
                data["cell"].append([float(p) for p in parts])
        elif current_section == "atomic_positions":
            parts = line.split()
            if len(parts) == 4:
                symbol, x, y, z = parts
                data["positions"].append({"symbol": symbol, "pos": [float(x), float(y), float(z)]})

    return data


def test_generate_qe_input_is_robust():
    """
    Tests that the QE input generator is robust and general.
    It checks for correctness by parsing the output, not by exact string matching.
    """
    # 1. Setup: Create a standard Silicon structure
    atoms = bulk("Si", "diamond", a=5.43)
    ecutwfc_test = 40.0
    calculation_test = "scf"

    # 2. Execution: Generate the QE input
    qe_input = generate_qe_input(atoms, calculation=calculation_test, ecutwfc=ecutwfc_test)

    # 3. Verification: Parse the output and check values
    parsed_data = parse_qe_input(qe_input)

    # Check sections are present
    assert "CONTROL" in parsed_data["sections"]
    assert "SYSTEM" in parsed_data["sections"]
    assert "ELECTRONS" in parsed_data["sections"]

    # Check key variables
    assert parsed_data["variables"]["calculation"] == calculation_test
    assert parsed_data["variables"]["ecutwfc"] == ecutwfc_test
    assert parsed_data["variables"]["nat"] == len(atoms)
    assert parsed_data["variables"]["ntyp"] == 1

    # Check atomic species
    assert len(parsed_data["atomic_species"]) == 1
    si_species = parsed_data["atomic_species"][0]
    assert si_species["symbol"] == "Si"
    expected_mass = atomic_masses[atomic_numbers["Si"]]
    assert np.isclose(si_species["mass"], expected_mass)
    assert si_species["pseudo"] == "Si.pbe.UPF"

    # Check cell parameters (comparing numpy arrays for tolerance)
    expected_cell = atoms.get_cell()
    assert np.allclose(parsed_data["cell"], expected_cell)

    # Check atomic positions (comparing numpy arrays for tolerance)
    expected_positions = atoms.get_scaled_positions()
    parsed_positions = [p["pos"] for p in parsed_data["positions"]]
    assert np.allclose(parsed_positions, expected_positions)
    parsed_symbols = [p["symbol"] for p in parsed_data["positions"]]
    assert parsed_symbols == atoms.get_chemical_symbols()
