# Cycle 01 User Acceptance Testing (UAT)

**Version:** 1.0.0
**Status:** Final
**Cycle Goal:** To verify that the core pipeline can correctly process a given set of atomic structures, label them using Quantum Espresso, and train a basic MLIP from the resulting data.

## 1. Test Scenarios

This UAT focuses on validating the foundational capabilities of the system from a technical user's (e.g., a developer or computational scientist) perspective. The scenarios are designed to ensure the core data processing is reliable, accurate, and robust.

| Scenario ID | Priority | Summary                                                                                        |
| :---------- | :------- | :--------------------------------------------------------------------------------------------- |
| UAT-C01-01  | **High** | Verify successful end-to-end processing of a simple crystalline solid (e.g., Silicon).         |
| UAT-C01-02  | **High** | Verify successful end-to-end processing of a simple molecular system (e.g., a water molecule). |
| UAT-C01-03  | **Medium** | Confirm the Delta Learning mechanism correctly modifies training targets.                      |
| UAT-C01-04  | **Medium** | Ensure the system handles common error conditions gracefully (e.g., failed DFT calculation).   |

---

### **Scenario UAT-C01-01: Crystalline Solid Processing**

*   **Description:** This scenario is the primary validation of the core workflow. It tests the system's ability to handle a periodic, crystalline material, which is a common use case. It will verify input file generation for a crystal, execution of DFT, parsing of energy, forces, and stress, database storage, and the final training step. The test uses a standard, well-understood material (Silicon) to ensure the DFT results can be easily verified against known values.
*   **Success Criteria:**
    *   The pipeline must execute from start to finish without crashing.
    *   The generated Quantum Espresso input file for the silicon unit cell must contain the correct lattice parameters (`CELL_PARAMETERS`) and atomic positions.
    *   The SSSP protocol must correctly select the Si pseudopotential and appropriate cutoff energies.
    *   The final parsed energy from the QE output must be physically reasonable for bulk silicon.
    *   The parsed forces should be very close to zero for this highly symmetric, unperturbed structure.
    *   The parsed stress tensor should also be close to zero.
    *   The labelled silicon structure must be correctly saved to and retrieved from the ASE database.
    *   A final MLIP file must be created.

---

### **Scenario UAT-C01-02: Molecular System Processing**

*   **Description:** This scenario validates the system's ability to handle non-periodic, molecular structures. This is important because the QE input format is different (e.g., `ibrav=0` is not used, and there are no `CELL_PARAMETERS`). It also tests the system's robustness with a multi-element system (Oxygen and Hydrogen).
*   **Success Criteria:**
    *   The pipeline must execute from start to finish without crashing when given a water molecule structure.
    *   The generated QE input file must correctly specify a large vacuum box to avoid self-interaction and must not contain the `CELL_PARAMETERS` card.
    *   The SSSP protocol must select the correct pseudopotentials for both O and H.
    *   The parsed energy and forces must be physically reasonable for a water molecule.
    *   The stress tensor should be effectively zero and correctly parsed.
    *   The labelled water molecule structure must be correctly stored and retrieved from the database.
    *   A final MLIP file must be created based on the molecular data.

---

### **Scenario UAT-C01-03: Delta Learning Mechanism**

*   **Description:** This scenario specifically targets the verification of the Delta Learning implementation. It is not an end-to-end test but rather a "white-box" test to ensure the core logic of the training engine is correct. The goal is to confirm that the training targets provided to the underlying MLIP framework are the *residuals* (DFT minus baseline) and not the raw DFT energies.
*   **Success Criteria:**
    *   During the execution of the `Trainer` class, the system must correctly calculate the energy of a given structure using the hard-coded baseline potential (e.g., ZBL).
    *   The target energy used for training must be precisely equal to `(DFT Energy) - (Baseline Energy)`. This can be verified by inspecting logs or by adding a specific debugging hook.
    *   The final trained potential, when used for prediction, should predict the delta, and when the baseline is added back, it should approximate the original DFT energy.

---

### **Scenario UAT-C01-04: Error Handling for Failed DFT**

*   **Description:** A robust pipeline must be able to handle failures. This scenario simulates a common failure mode: a DFT calculation that fails to converge. The test will involve providing a deliberately "bad" structure that is known to cause SCF convergence issues in Quantum Espresso. The goal is to ensure the system detects the failure and reports it clearly, rather than crashing or producing garbage data.
*   **Success Criteria:**
    *   The `QuantumEspressoRunner` must correctly identify that the QE process has failed (e.g., by checking the exit code or searching for the "JOB DONE" message in the output).
    *   Instead of returning a labelled `Atoms` object, the runner must raise a specific, informative exception (e.g., `DFTRuntimeError`).
    *   The main `Orchestrator` must catch this exception.
    *   The pipeline should stop gracefully and log a clear error message indicating which structure failed to be labelled and why.
    *   The system must not add the failed structure to the database.

## 2. Behavior Definitions

### **GIVEN/WHEN/THEN Definitions**

**Scenario: UAT-C01-01**
*   **GIVEN** a directory containing a single CIF file for a standard 2-atom Silicon primitive cell.
*   **AND** a valid Quantum Espresso `pw.x` executable is available in the environment.
*   **WHEN** the user executes the main pipeline script, pointing it to the input directory.
*   **THEN** the system should create a Quantum Espresso input file for Silicon.
*   **AND** the input file should specify the correct lattice constant and atomic positions.
*   **AND** the system should execute `pw.x` as a subprocess.
*   **AND** the system should parse the resulting output file, extracting the total energy, forces, and stress.
*   **AND** the extracted energy should be a negative value (indicating a bound state).
*   **AND** the magnitude of the force on each atom should be less than 1.0e-4 Ry/au.
*   **AND** the system should write the labelled Silicon `Atoms` object to an ASE database file.
*   **AND** the system should then train an MLIP using this single data point.
*   **AND** a file containing the trained potential must be saved to the working directory.
*   **AND** the entire process must complete without any errors.

**Scenario: UAT-C01-02**
*   **GIVEN** a directory containing a single XYZ file for a water molecule.
*   **AND** a valid Quantum Espresso `pw.x` executable is available in the environment.
*   **WHEN** the user executes the main pipeline script on this input.
*   **THEN** the system should generate a QE input file specifying a large simulation cell (vacuum padding).
*   **AND** the system should execute `pw.x`.
*   **AND** the system should parse the energy and forces from the QE output.
*   **AND** the forces on the atoms should be non-zero and physically reasonable.
*   **AND** the labelled water molecule should be correctly saved to the database.
*   **AND** the system should successfully train an MLIP and save the potential file.

**Scenario: UAT-C01-03**
*   **GIVEN** a DFT-labelled structure with a known energy of -100 eV.
*   **AND** a baseline potential (ZBL) that calculates the energy of this structure as -20 eV.
*   **WHEN** the `Trainer` class processes this structure.
*   **THEN** the target energy value passed to the underlying MLIP fitting algorithm must be exactly -80 eV.

**Scenario: UAT-C01-04**
*   **GIVEN** a directory containing a structure file with two atoms placed unrealistically close together (e.g., 0.1 Angstroms apart).
*   **AND** a valid Quantum Espresso `pw.x` executable.
*   **WHEN** the user executes the pipeline on this input.
*   **THEN** the `QuantumEspressoRunner` should detect that the `pw.x` subprocess either returns a non-zero exit code or fails to produce a valid output file.
*   **AND** the runner should raise a `DFTRuntimeError`.
*   **AND** the main orchestrator should catch the exception and log a user-friendly error message, such as "ERROR: DFT calculation failed for structure file: [filename]".
*   **AND** the pipeline should terminate gracefully without creating a database or a potential file.