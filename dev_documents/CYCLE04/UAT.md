# Cycle 04 User Acceptance Testing (UAT)

**Version:** 1.0.0
**Status:** Final
**Cycle Goal:** To verify that the on-the-fly (OTF) active learning loop can autonomously identify model weaknesses, trigger retraining, and improve the MLIP.

## 1. Test Scenarios

This UAT is designed to validate the core "intelligence" of the system—its ability to self-correct. The scenarios focus on the behavior of the active learning loop, ensuring it triggers when expected and that the resulting actions lead to a measurably improved potential.

| Scenario ID | Priority | Summary                                                                                             |
| :---------- | :------- | :-------------------------------------------------------------------------------------------------- |
| UAT-C04-01  | **High** | Verify that the active learning loop correctly identifies an out-of-distribution structure and triggers a full retraining cycle. |
| UAT-C04-02  | **High** | Confirm that the newly trained potential shows improved accuracy for the high-uncertainty structure. |
| UAT-C04-03  | **Medium** | Ensure the simulation can be correctly paused and then resumed with the updated potential.          |
| UAT-C04-04  | **Low**  | Verify the correctness of the periodic structure extraction for retraining.                          |

---

### **Scenario UAT-C04-01: Successful Trigger of the Active Learning Loop**

*   **Description:** This is the primary scenario for this cycle. It validates that the entire feedback mechanism is working as intended. The test involves creating a situation where the MLIP is known to be inadequate, and then verifying that the system autonomously detects this and takes the correct actions. We will train an initial potential exclusively on solid-phase, low-temperature data, and then run the active learning simulation on a liquid-phase, high-temperature configuration.
*   **Success Criteria:**
    *   The system must first successfully train an initial MLIP using only low-temperature data.
    *   When the `SimulationEngine` starts the high-temperature simulation, the uncertainty metric must exceed the defined threshold within a reasonable number of steps.
    *   The simulation must pause.
    *   A high-uncertainty structure (from the high-temperature simulation) must be extracted and sent to the `QuantumEspressoRunner`.
    *   This new structure must be successfully labelled with DFT.
    *   The `Trainer` must be invoked a second time, using a dataset that now includes both the original low-temperature data and the new high-temperature data point.
    *   A new, updated MLIP file must be created.

---

### **Scenario UAT-C04-02: Verification of Model Improvement**

*   **Description:** It is not enough for the loop to just run; it must lead to a better model. This scenario verifies that the retraining process actually improves the potential's accuracy. It directly follows on from UAT-C04-01.
*   **Success Criteria:**
    *   Let `S_uncertain` be the high-uncertainty structure that was extracted in the previous scenario.
    *   Let `E_dft` be the true DFT energy of `S_uncertain`.
    *   Let `E_initial_mlip` be the energy of `S_uncertain` as predicted by the *initial* MLIP.
    *   Let `E_updated_mlip` be the energy of `S_uncertain` as predicted by the *updated*, retrained MLIP.
    *   The test must assert that the error of the updated model is significantly smaller than the error of the initial model. That is: `abs(E_updated_mlip - E_dft) < abs(E_initial_mlip - E_dft)`.
    *   This confirms that the active learning cycle is not just busy-work, but is genuinely improving the quality of the potential in the regions where it was previously failing.

---

### **Scenario UAT-C04-03: Pause and Resume of Simulation**

*   **Description:** This scenario tests the technical implementation of the pause-and-resume feature, which relies on the `SimulationEngine`'s generator-based design. It ensures that after the retraining cycle is complete, the production simulation can continue from where it left off, now using the better potential.
*   **Success Criteria:**
    *   Following the successful retraining in scenario UAT-C04-01, the `Orchestrator` must resume the `SimulationEngine`'s generator.
    *   The simulation must continue running from the exact step where it was paused.
    *   Crucially, the simulation must now be using the *updated* MLIP for its force calculations.
    *   The simulation should continue for a further number of steps without immediately re-triggering the uncertainty threshold on the same structure.

---

### **Scenario UAT-C04-04: Correctness of Periodic Extraction**

*   **Description:** This is a "white-box" test to validate the utility function that extracts a small, periodic sub-cell from a large simulation box. An incorrect extraction (e.g., wrong cell vectors, broken molecules) would lead to garbage data being sent to the DFT engine, poisoning the entire training process. This test ensures the integrity of the data being fed back into the loop.
*   **Success Criteria:**
    *   Given a large (e.g., 4x4x4) supercell of a crystal like Silicon from a simulation.
    *   A request is made to extract the local environment around an atom near the center of the box, with a smaller cell size (e.g., 2x2x2).
    *   The resulting extracted `Atoms` object must be periodic.
    *   Its cell vectors must correspond to the requested smaller size.
    *   The number of atoms in the extracted cell must be correct for the smaller volume.
    *   The relative positions of the atoms within the new cell must be correct and consistent with the original supercell.

## 2. Behavior Definitions

### **GIVEN/WHEN/THEN Definitions**

**Scenario: UAT-C04-01**
*   **GIVEN** an initial training set containing only data for solid Silicon at 300K.
*   **AND** the system has trained an initial MLIP from this data.
*   **WHEN** the `SimulationEngine` is started to run a simulation of Silicon at 2000K (liquid phase).
*   **THEN** the calculated uncertainty should exceed the threshold.
*   **AND** the simulation should pause and yield a high-temperature Silicon structure.
*   **AND** this structure should be sent to the DFT labelling module.
*   **AND** the training module should be called again with the combined (300K + 2000K) dataset.
*   **AND** a new potential file, version 2, should be created.

**Scenario: UAT-C04-02**
*   **GIVEN** the high-temperature structure `S_2000K` from the previous test.
*   **AND** its true DFT energy `E_dft`.
*   **AND** the initial potential (`version 1`) and the updated potential (`version 2`).
*   **WHEN** we use both potentials to predict the energy of `S_2000K`.
*   **THEN** the prediction from `version 2` must be closer to `E_dft` than the prediction from `version 1`.

**Scenario: UAT-C04-03**
*   **GIVEN** the simulation was paused at step `N` and retraining has completed.
*   **AND** the orchestrator now holds the path to the `version 2` potential.
*   **WHEN** the orchestrator resumes the simulation.
*   **THEN** the `SimulationEngine` should restart its calculations from step `N+1`.
*   **AND** it must load and use the `version 2` potential for all subsequent force calculations.

**Scenario: UAT-C04-04**
*   **GIVEN** a 128-atom periodic supercell of Silicon.
*   **WHEN** the user requests to extract the periodic environment of a central atom with a cutoff radius that should result in a 16-atom cell.
*   **THEN** the system must return a new, valid ASE `Atoms` object.
*   **AND** this object's cell property must define a smaller, but still periodic, simulation box.
*   **AND** the object must contain exactly 16 atoms.