# Cycle 04 User Acceptance Testing (UAT)

This document outlines the User Acceptance Testing scenarios for Cycle 04 of the MLIP-AutoPipe project. The focus of this cycle is the implementation of the `SimulationEngine` and the on-the-fly (OTF) active learning loop. These tests are designed to verify, from a user's perspective, that the system can use a trained MLIP to explore a material's dynamics, correctly detect when it encounters novel configurations outside its training domain, and automatically trigger a re-training cycle to improve itself. The successful completion of these UATs will confirm that the pipeline has evolved from a linear generator into a cyclical, self-improving system.

## 1. Test Scenarios

| Scenario ID | Scenario Name                                      | Priority |
| :---------- | :------------------------------------------------- | :------- |
| UAT-C04-01  | Successful Triggering of Active Learning Loop      | High     |
| UAT-C04-02  | Dynamic Adjustment of Uncertainty Threshold        | High     |
| UAT-C04-03  | Simulation Resumption with Improved Potential      | Medium   |

---

### **Scenario UAT-C04-01: Successful Triggering of Active Learning Loop**

**Description (Min 300 words):**
This is the central UAT scenario for Cycle 04, as it verifies that the entire active learning feedback mechanism is functioning correctly and delivering its intended value. The user will set up a scenario designed to deliberately push the simulation into an unknown region of phase space, forcing the system to confront the limits of its initial knowledge. For example, the initial training data (generated in the first part of the pipeline run) might only contain configurations of a solid crystal phase of a material, all generated at a low temperature like 300K. The user will then configure the `SimulationEngine` to run a new simulation using this potential, but at a much higher temperature, for example, 1500K, which is high enough to cause the material to melt.

The initial MLIP, having never seen a liquid phase, should exhibit high uncertainty when the atoms begin to break their crystal lattice and move into disordered, liquid-like configurations. The system is expected to detect this spike in uncertainty from the ensemble of potentials. When the uncertainty surpasses the configured threshold, the simulation must pause automatically. The user will then verify that the system correctly extracts the novel, liquid-like structure, sends it back to the `LabellingEngine` to get a high-fidelity DFT label, and then re-trains the MLIP with this new, valuable data point included. The user can verify success by observing the system's logs, which should clearly indicate that the uncertainty threshold was breached, that a new structure was sent for labelling (and its ID should be logged), and that the `TrainingEngine` was invoked a second time to create a next-generation potential. This test provides end-user validation that the system is not static but can actively and autonomously improve its own potential when it encounters new physics.

---

### **Scenario UAT-C04-02: Dynamic Adjustment of Uncertainty Threshold**

**Description (Min 300 words):**
This scenario tests the intelligence and adaptability of the uncertainty trigger. Using a fixed, arbitrary uncertainty threshold can be problematic: if set too high, the model may never re-train even when it should; if set too low, it may re-train too often on configurations that are only marginally new, wasting expensive DFT resources. The "dynamic percentile" approach is designed to solve this by setting a threshold based on the model's current knowledge. This test will verify its correct implementation from a user's point of view. The user will configure the active learning strategy in their `input.yaml` to use a dynamic threshold, for example, by setting `uncertainty_threshold: "dynamic_95percentile"`.

The user will start a workflow as normal. After the initial MLIP ensemble is trained, the user will expect the system to automatically calculate the uncertainty values for all the structures in the *initial* training set. The 95th percentile of this distribution of "known" uncertainties will then become the initial threshold for the first simulation. The user will verify this by checking the logs for a message clearly stating the calculated initial threshold, for example: "Initial dynamic uncertainty threshold set to: 0.45 eV/A". As the simulation runs, a re-train will only be triggered if a new structure has an uncertainty greater than this value. After one or more re-training cycles, the training set will have grown. The user will then verify that after the next re-training completes, the system *re-calculates* the 95th percentile threshold based on the new, larger, more diverse training set, and that this new, likely higher, threshold is used for the subsequent simulation. This demonstrates to the user that the system's definition of "uncertain" correctly adapts as the model becomes more knowledgeable and robust.

---

## 2. Behavior Definitions

**Scenario: UAT-C04-01 - Successful Triggering of Active Learning Loop**

```gherkin
GIVEN the system has already run the initial stages and produced an MLIP ensemble for Silicon, trained only on solid-state data generated at 300K.
AND the 'active_learning' section of the user's config file specifies `max_generations: 1` and a fixed `uncertainty_threshold: 0.5`.
AND the 'simulation' section of the config specifies running a new MD simulation at a high temperature of 2000K.
WHEN the Orchestrator starts the `SimulationEngine` for the first active learning generation.
THEN an MD simulation using the initial MLIP ensemble should begin, and its progress should be displayed.
AND as the simulated crystal structure begins to melt and disorder due to the high temperature, the logged uncertainty metric should be seen to increase.
AND when the uncertainty of a simulation frame exceeds the 0.5 threshold, the MD simulation should be paused.
AND the system should log a clear message, such as "Uncertainty threshold breached at step 12345. Extracting structure for re-training."
AND the system should log that this high-uncertainty structure is being submitted to the Labelling Engine.
AND after the labelling is complete, the system should log that it is invoking the Training Engine for the next generation.
AND a new set of model files, versioned for the new generation (e.g., in a 'gen_1' directory), should be created.
AND the active learning loop should then terminate as the `max_generations` limit has been reached.
```

---

**Scenario: UAT-C04-02 - Dynamic Adjustment of Uncertainty Threshold**

```gherkin
GIVEN the system is configured with `uncertainty_threshold: "dynamic_95percentile"`.
AND an initial MLIP ensemble has been trained on a dataset of 100 structures.
WHEN the active learning loop is about to begin the first simulation generation.
THEN the system should first log that it is calculating the uncertainty across the initial training set.
AND it should compute the 95th percentile of these known uncertainty values.
AND it should log a clear, user-visible message stating the result, like "Initial dynamic uncertainty threshold set to: 0.48 eV/A".
AND this value (0.48) should be used as the trigger for the first simulation run.

GIVEN that the first simulation run finds 5 new structures, and the model is re-trained on a new, augmented dataset of 105 structures.
WHEN the active learning loop is about to begin the second simulation generation.
THEN the system should again log that it is re-calculating the uncertainty across the now-larger training set.
AND it should compute a new 95th percentile value from this updated distribution.
AND it should log a new message with the updated value, e.g., "Updated dynamic uncertainty threshold set to: 0.51 eV/A".
AND this new, higher value should be used as the trigger for the subsequent simulation run.
```

---

**Scenario: UAT-C04-03 - Simulation Resumption with Improved Potential**

```gherkin
GIVEN the system has just completed one active learning cycle, triggered by an uncertain structure at simulation time step 5,432.
AND it has produced an improved potential ensemble, versioned as 'gen_1'.
WHEN the Orchestrator starts the next generation of the active learning loop.
THEN the `SimulationEngine` should log a message indicating that it is loading the new 'gen_1' potential.
AND the MD simulation should resume execution from time step 5,433, not from the beginning (time step 0).
AND the system should log a message confirming this, such as "Resuming simulation from step 5433 with improved potential."
```
