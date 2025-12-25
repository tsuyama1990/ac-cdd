# Cycle 03 User Acceptance Testing (UAT)

**Version:** 1.0.0
**Status:** Final
**Cycle Goal:** To verify the efficiency and correctness of the new surrogate-based exploration and sampling workflow, and to validate the performance gains from JIT compilation.

## 1. Test Scenarios

This UAT focuses on validating the impact of Module B on the pipeline. The scenarios are designed to confirm that the exploration and sampling process leads to an intelligent selection of structures and that the system's performance remains high despite the added complexity.

| Scenario ID | Priority | Summary                                                                                             |
| :---------- | :------- | :-------------------------------------------------------------------------------------------------- |
| UAT-C03-01  | **High** | Verify that the Explorer module successfully runs and selects a small, diverse subset from a large MD trajectory. |
| UAT-C03-02  | **High** | Confirm end-to-end pipeline execution with the Explorer module enabled.                           |
| UAT-C03-03  | **Medium** | Validate the performance of the Numba-optimised descriptor calculation.                             |
| UAT-C03-04  | **Low**  | Ensure the system can gracefully handle the unavailability of a specified surrogate model.          |

---

### **Scenario UAT-C03-01: Correctness of Structure Sampling**

*   **Description:** This is the most critical test for this cycle. It validates the core functionality of Module B: its ability to explore a conformational space and intelligently select a small number of representative structures. The test will be configured to run a short MD simulation and then sample a fixed number of frames, allowing us to verify the module's primary purpose.
*   **Success Criteria:**
    *   Given a valid `input.yaml`, the Explorer module must be triggered.
    *   It must successfully run a surrogate-powered MD simulation for a predefined number of steps (e.g., 200).
    *   It must then execute the DIRECT sampling workflow.
    *   If the sampling is configured to select `N=15` structures, the module must output a list containing exactly 15 ASE `Atoms` objects.
    *   The selected structures should be diverse. This can be qualitatively verified by ensuring the selected frame indices are spread out across the 200-step trajectory, not just clustered at the beginning.
    *   The process must complete without errors.

---

### **Scenario UAT-C03-02: Full Pipeline Integration**

*   **Description:** This scenario ensures that the new, complex Explorer module is correctly integrated into the end-to-end workflow and that the data it produces is consumable by the downstream modules. It tests the full data flow from `input.yaml` to the final trained potential.
*   **Success Criteria:**
    *   Given a valid `input.yaml`, the full pipeline (Modules A -> B -> C -> D) must execute from start to finish without crashing.
    *   Module A must generate initial structures.
    *   Module B must take these, run MD, sample them, and pass a smaller, curated list of structures to Module C.
    *   Module C must successfully run DFT calculations on the structures provided by Module B.
    *   Module D must successfully train an MLIP on this DFT-labelled data.
    *   A final potential file must be created.

---

### **Scenario UAT-C03-03: Performance Validation**

*   **Description:** This test validates the "Optimisation" part of the cycle's goal. It's designed to confirm that the use of Numba provides a significant, measurable performance improvement in the most computationally intensive part of Module B. This is not about the overall pipeline speed but specifically about the descriptor calculation bottleneck.
*   **Success Criteria:**
    *   A benchmark script will be created that runs the descriptor calculation function on a large, pre-generated trajectory file (e.g., >10,000 frames).
    *   The execution time of the Numba-optimised function must be measured.
    *   The execution time must be significantly faster (e.g., at least 10 times faster) than an equivalent pure Python implementation.
    *   The benchmark test should pass, confirming that our performance target has been met. This ensures the pipeline will not become unusably slow when processing realistic workloads.

---

### **Scenario UAT-C03-04: Surrogate Model Availability**

*   **Description:** This scenario tests the system's robustness to external dependencies, in this case, the pre-trained surrogate models which are typically downloaded from the internet. The system should fail gracefully if a specified model is incorrect or cannot be downloaded.
*   **Success Criteria:**
    *   The `exec_config_dump.yaml` is manually edited to specify a surrogate model name that does not exist (e.g., `"invalid-model-name"`).
    *   When the Explorer module is executed, it should attempt to load this model.
    *   The model loading should fail.
    *   The system must catch this error and terminate gracefully.
    *   A clear, user-friendly error message must be printed, such as "Error: Could not download or find the specified surrogate model 'invalid-model-name'. Please check the model name and your internet connection."
    *   The pipeline should not proceed to the DFT stage.

## 2. Behavior Definitions

### **GIVEN/WHEN/THEN Definitions**

**Scenario: UAT-C03-01**
*   **GIVEN** an `input.yaml` for a simple system.
*   **AND** the pipeline is configured to run a 200-step MD simulation in the Explorer module.
*   **AND** the sampler is configured to select 15 representative structures.
*   **WHEN** the pipeline is executed.
*   **THEN** the Explorer module should generate a trajectory with 200 frames.
*   **AND** the Explorer module's output, which becomes the input for the Labelling Engine, must be a list of exactly 15 `Atoms` objects.
*   **AND** the selected frame indices should not be all from a single, small part of the trajectory.

**Scenario: UAT-C03-02**
*   **GIVEN** a standard `input.yaml` file for a material like Silicon.
*   **AND** the full pipeline is enabled.
*   **WHEN** the user executes the main pipeline script.
*   **THEN** Module A should generate a few initial structures.
*   **AND** Module B should take these structures, run a surrogate MD simulation, and produce a small, curated set of structures for labelling.
*   **AND** Module C should receive this curated set and successfully perform DFT calculations on them.
*   **AND** Module D should receive the labelled data and successfully train a potential.
*   **AND** a final potential file should be present in the output directory.

**Scenario: UAT-C03-03**
*   **GIVEN** a large trajectory file and a benchmark script.
*   **WHEN** the benchmark script is executed, running both a pure Python and a Numba-optimised version of the descriptor calculation.
*   **THEN** the numeric results (the descriptor arrays) from both versions must be approximately equal.
*   **AND** the wall-clock time for the Numba-optimised version must be at least one order of magnitude smaller than the pure Python version.

**Scenario: UAT-C03-04**
*   **GIVEN** a configuration file where the `explorer.surrogate_model` is set to a name that does not exist.
*   **WHEN** the pipeline is executed.
*   **THEN** the program should terminate before starting any MD simulations.
*   **AND** a clear error message identifying the invalid model name must be displayed to the user.
*   **AND** the program must exit with a non-zero status code.