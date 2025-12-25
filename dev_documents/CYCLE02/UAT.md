# Cycle 02 User Acceptance Testing (UAT)

**Version:** 1.0.0
**Status:** Final
**Cycle Goal:** To verify that the system can autonomously generate an initial training dataset and train a potential, starting from a minimal, user-provided configuration file.

## 1. Test Scenarios

This UAT focuses on validating the new user-facing functionality (the `input.yaml`) and the correctness of the automated generation and configuration logic. The scenarios are designed to test the main supported use cases and ensure the heuristic engine is making sensible decisions.

| Scenario ID | Priority | Summary                                                                                    |
| :---------- | :------- | :----------------------------------------------------------------------------------------- |
| UAT-C02-01  | **High** | Verify successful end-to-end pipeline execution for an alloy system from `input.yaml`.     |
| UAT-C02-02  | **High** | Verify successful end-to-end pipeline execution for a molecular system from `input.yaml`.   |
| UAT-C02-03  | **Medium** | Confirm the heuristic engine correctly identifies and configures a magnetic system.        |
| UAT-C02-04  | **Medium** | Ensure the system produces a descriptive error message for an invalid `input.yaml`.        |

---

### **Scenario UAT-C02-01: Alloy System End-to-End**

*   **Description:** This is the primary success scenario for this cycle. It tests the complete, enhanced workflow for a typical use case: generating a potential for a binary alloy. It validates the `ConfigExpander`'s ability to identify an alloy, select the SQS algorithm, and configure the rest of the pipeline correctly.
*   **Success Criteria:**
    *   Given an `input.yaml` with `elements: ["Ni", "Al"]`, the pipeline must execute from start to finish without errors.
    *   The system must generate an `exec_config_dump.yaml` file.
    *   The `generation` algorithm in the dump file must be set to `SQS`.
    *   The `SQSGenerator` must be executed, producing a set of ASE `Atoms` objects corresponding to NiAl structures with varying strains.
    *   These structures must be successfully labelled by the `QuantumEspressoRunner`.
    *   A final MLIP file must be created based on the automatically generated and labelled data.
    *   The ASE database must contain more than one structure.

---

### **Scenario UAT-C02-02: Molecular System End-to-End**

*   **Description:** This scenario ensures that the heuristic engine's classification logic is working correctly and that a different, appropriate generation pathway is triggered for molecular systems. It validates the selection and execution of the Normal Mode Sampling (NMS) algorithm.
*   **Success Criteria:**
    *   Given an `input.yaml` with `elements: ["C", "H"]` and a reference `methane.xyz` file, the pipeline must execute without errors.
    *   The system must generate an `exec_config_dump.yaml`.
    *   The `generation` algorithm in the dump file must be set to `NMS`.
    *   The `NMSGenerator` must be executed, producing a set of distorted methane molecules.
    *   These molecular structures must be successfully labelled by the `QuantumEspressoRunner`.
    *   A final MLIP file must be created.

---

### **Scenario UAT-C02-03: Magnetic System Configuration**

*   **Description:** This is a "white-box" test to verify that the `ConfigExpander`'s physical heuristics are working correctly. It specifically checks if the presence of a known magnetic element (like Iron) correctly triggers the magnetic settings in the DFT configuration. This is crucial for obtaining physically correct results for many important materials.
*   **Success Criteria:**
    *   Given an `input.yaml` containing a magnetic element, such as `elements: ["Fe", "Pt"]`.
    *   The `ConfigExpander` must run and produce an `exec_config_dump.yaml`.
    *   Within the `dft_compute` section of the dump file, the `magnetism` parameter must be set to a value like `"ferromagnetic"` or `nspin` must be set to `2`.
    *   The subsequent call to the `QuantumEspressoRunner` should generate QE input files that include the appropriate magnetic flags (`nspin = 2` and starting magnetization values).

---

### **Scenario UAT-C02-04: Invalid Input Handling**

*   **Description:** This scenario tests the system's robustness and user-friendliness when faced with incorrect input. A user might make a typo or provide invalid information, and the system should fail gracefully with a clear, actionable error message rather than a confusing traceback.
*   **Success Criteria:**
    *   Given an `input.yaml` file that is syntactically correct YAML but contains invalid data (e.g., `elements: ["Fe", "InvalidElement"]`).
    *   When the pipeline is executed, it should stop during the `ConfigExpander` stage.
    *   The system must not crash. Instead, it should print a clear error message to the console, such as "Error: Invalid element symbol 'InvalidElement' found in input.yaml."
    *   The process should terminate with a non-zero exit code.
    *   No `exec_config_dump.yaml` or ASE database should be created.

## 2. Behavior Definitions

### **GIVEN/WHEN/THEN Definitions**

**Scenario: UAT-C02-01**
*   **GIVEN** a simple `input.yaml` file containing `system: { elements: ["Ni", "Al"] }`.
*   **AND** a valid Quantum Espresso `pw.x` executable is available.
*   **WHEN** the user executes the main pipeline script with this input file.
*   **THEN** the system should create a detailed `exec_config_dump.yaml` file.
*   **AND** this dump file must specify "SQS" as the generation algorithm.
*   **AND** the system should generate a series of NiAl atomic structures.
*   **AND** the system must successfully calculate the DFT energies and forces for these structures.
*   **AND** the system must train an MLIP on the generated data.
*   **AND** the system must save a final potential file.
*   **AND** the entire process must complete without user intervention.

**Scenario: UAT-C02-02**
*   **GIVEN** an `input.yaml` file with `system: { elements: ["C", "H"] }` and a path to a reference geometry file.
*   **AND** a valid Quantum Espresso `pw.x` executable.
*   **WHEN** the user executes the pipeline.
*   **THEN** the generated `exec_config_dump.yaml` must specify "NMS" as the generation algorithm.
*   **AND** the system must generate a set of distorted molecular structures based on the reference geometry.
*   **AND** the system must successfully label them using DFT.
*   **AND** the system must successfully train and save an MLIP.

**Scenario: UAT-C02-03**
*   **GIVEN** an `input.yaml` file containing `system: { elements: ["Fe", "Si"] }`.
*   **WHEN** the user executes the pipeline.
*   **THEN** the `ConfigExpander` must produce an `exec_config_dump.yaml`.
*   **AND** within this file, the `dft_compute` section must contain settings appropriate for a spin-polarized calculation (e.g., `nspin: 2`).
*   **AND** the Quantum Espresso input files generated later in the process must include these settings.

**Scenario: UAT-C02-04**
*   **GIVEN** an `input.yaml` file containing `system: { elements: ["Bogus"] }`.
*   **WHEN** the user executes the pipeline.
*   **THEN** the program should terminate before starting any DFT calculations.
*   **AND** an error message should be printed to the screen clearly stating that the element "Bogus" is not valid.
*   **AND** the program should exit with a status code indicating failure.