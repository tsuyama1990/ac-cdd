# Cycle 01 User Acceptance Testing (UAT)

This document outlines the User Acceptance Testing (UAT) scenarios for Cycle 01 of the MLIP-AutoPipe project. The focus of this cycle is to establish the core functionality of the labelling and training engines. The tests are designed from the perspective of a user who wants to verify that the system can correctly process a given set of structures and produce a valid Machine Learning Interatomic Potential (MLIP). These scenarios represent the fundamental promises of the system at this stage: reliability, robustness against common errors, and correctness of the underlying scientific implementation.

## 1. Test Scenarios

| Scenario ID | Scenario Name                                      | Priority |
| :---------- | :------------------------------------------------- | :------- |
| UAT-C01-01  | Successful End-to-End Workflow (Happy Path)        | High     |
| UAT-C01-02  | Handling of DFT Calculation Failure                | High     |
| UAT-C01-03  | Verification of Delta Learning Implementation      | Medium   |
| UAT-C01-04  | Configuration File Validation                      | Medium   |

---

### **Scenario UAT-C01-01: Successful End-to-End Workflow (Happy Path)**

**Description (Min 300 words):**
This is the most critical scenario for Cycle 01 and represents the primary "happy path" workflow. The purpose of this test is to verify that the system can successfully orchestrate the entire process from start to finish under ideal conditions. The user will start with a small, well-behaved set of atomic structures (e.g., various configurations of a Silicon dimer or a simple bulk crystal) that are known to be easily calculable with Quantum Espresso. The user will provide a valid configuration file specifying the necessary parameters for the DFT calculation and the MLIP training. This test case is fundamental because it validates the entire integrated chain of operations: database interaction, configuration parsing, DFT input generation, external process execution, output parsing, and finally, the machine learning training step. It is the baseline proof that the core components are correctly wired together and can pass data between them seamlessly.

The expectation is that the user can invoke the pipeline via a single command from the command-line interface. The system should then proceed without any errors. It must correctly identify the structures in the input database that require labelling, execute the Quantum Espresso calculations for each one, parse the results, and update the database with the calculated energy, forces, and stresses. Subsequently, the system must gather all the newly labelled data and pass it to the training engine. The training engine should then successfully train an ACE potential based on this data. The final, verifiable output is the creation of a trained model file (e.g., `model.ace`) in the specified output directory. Successful completion of this test demonstrates that all core components are correctly integrated and that the fundamental data flow is sound. It provides the baseline confidence needed to build more complex features in subsequent cycles. A failure in this scenario would indicate a fundamental flaw in the core logic or integration of the pipeline, making it the highest priority to pass before any further development.

---

### **Scenario UAT-C01-02: Handling of DFT Calculation Failure**

**Description (Min 300 words):**
This scenario tests the robustness and resilience of the `LabellingEngine` when faced with a common real-world problem: the failure of a DFT calculation. Not all atomic configurations will lead to a successfully converged Self-Consistent Field (SCF) calculation in Quantum Espresso, especially if the initial geometry is physically unrealistic. A robust scientific workflow must anticipate and handle these failures without crashing or corrupting the overall process. This test is designed to verify that the system handles such failures gracefully rather than aborting the entire run. The user will prepare an input database that includes at least one "bad" structure—for example, a structure with atoms placed impossibly close together, which is known to cause SCF convergence issues, alongside several other valid structures. The goal is to ensure the system can isolate the failure and continue with the viable parts of the dataset.

When the user runs the pipeline, the system is expected to attempt the QE calculation for all structures, including the "bad" one. When the calculation for the problematic structure inevitably fails, the system must not halt the entire workflow. Instead, it should correctly detect the failure by parsing the QE output for error messages or by checking the non-zero exit code of the `pw.x` process. It should then log the error in a clear and informative way, associating the error message with the specific structure that caused it so the user can diagnose the issue later. The failed structure in the database should be marked with a distinct 'failed_labelling' status. Crucially, the pipeline should continue to process all other valid structures in the input set without interruption. The final MLIP should be trained using only the data from the successfully labelled structures. This test is passed if the pipeline completes, a model file is generated based on the valid data, and the database correctly reflects the 'failed_labelling' status of the problematic structure, demonstrating the system's resilience and its ability to salvage value from an imperfect dataset.

---

## 2. Behavior Definitions

**Scenario: UAT-C01-01 - Successful End-to-End Workflow (Happy Path)**

```gherkin
GIVEN a user has an ASE database file named 'structures.db' containing 3 unlabelled silicon crystal structures, each marked with the status 'needs_labelling'.
AND the user has a valid 'input.yaml' configuration file specifying all necessary Quantum Espresso parameters, including the command and pseudopotentials.
AND the configuration file specifies 'ace' as the model type and has 'delta_learning' enabled.
AND the output directory is empty.
WHEN the user executes the command: `mlip-pipe run --config input.yaml`.
THEN the system should start the workflow without any configuration errors.
AND the Labelling Engine should be invoked and successfully execute Quantum Espresso for each of the 3 structures.
AND upon completion of the labelling stage, all 3 structures in the 'structures.db' database should be updated to have a status of 'labelled'.
AND each of the 3 labelled structures, when read from the database, should contain valid, non-zero energy, forces, and stress data.
AND the Training Engine should then be invoked with the data corresponding to these 3 labelled structures.
AND a new file named 'model.ace' should be created in the specified output directory.
AND the process should terminate with a status code of 0 and a clear success message printed to the console.
```

---

**Scenario: UAT-C01-02 - Handling of DFT Calculation Failure**

```gherkin
GIVEN a user has an ASE database file containing 5 unlabelled structures.
AND one of these structures, identified by a unique ID, has two atoms placed only 0.5 Angstroms apart, a configuration guaranteed to cause an SCF failure.
AND the other 4 structures are physically reasonable.
AND the user has a valid 'input.yaml' configuration file.
WHEN the user executes the command: `mlip-pipe run --config input.yaml`.
THEN the system should attempt to run a DFT calculation for all 5 structures.
AND the system should log a clear warning or error message to the console, specifically mentioning the unique ID of the structure that failed to converge.
AND after the labelling stage, a query of the database should show that 4 structures now have the status 'labelled'.
AND the database query should show that the 1 problematic structure now has the status 'failed_labelling'.
AND the Training Engine should be invoked, and it should be provided with a dataset containing only the 4 successfully labelled structures.
AND a new file named 'model.ace' should still be created in the output directory, based on the partial but valid dataset.
AND the process should terminate successfully, having processed all viable structures without crashing.
```

---

**Scenario: UAT-C01-03 - Verification of Delta Learning Implementation**

```gherkin
GIVEN a user has a database with a single labelled structure, a hydrogen dimer at a distance where the DFT-calculated energy is -31.5 eV and the forces are [+0.1, -0.1] eV/A.
AND the baseline Lennard-Jones potential for hydrogen at this same distance is known to calculate an energy of -1.0 eV and forces of [+0.05, -0.05] eV/A.
AND the 'input.yaml' configuration file has the 'delta_learning' parameter set to true.
WHEN the Training Engine's data preparation step is invoked with this single structure.
THEN the target value for the energy that is prepared for the ACE model's training function must be the precise delta: (-31.5 - (-1.0)) = -30.5 eV.
AND the target values for the forces that are prepared must also be the precise delta: [+0.1 - 0.05, -0.1 - (-0.05)] = [+0.05, -0.05] eV/A.
AND after a trivial training run on this single data point, the resulting 'model.ace' should be saved to disk.
```

---

**Scenario: UAT-C01-04 - Configuration File Validation**

```gherkin
GIVEN a user has an 'input.yaml' configuration file that is missing a mandatory field within a nested structure, such as the 'pseudopotentials' dictionary inside the 'dft_compute' section.
AND all other required fields are present.
WHEN the user executes the command: `mlip-pipe run --config input.yaml`.
THEN the system should not start the main workflow or attempt to connect to the database.
AND the system should immediately exit with a non-zero status code, indicating an error.
AND the error message displayed to the user should be clear, human-readable, and specifically identify the missing parameter, for example: "Configuration validation error: 'pseudopotentials' is a required field in the 'dft_compute' section."
```
