# Cycle 04 Specification: The Active Learning Loop

**Version:** 1.0.0
**Status:** Final
**Cycle Goal:** To close the loop and make the pipeline fully autonomous by implementing the on-the-fly (OTF) active learning system (Module E).

## 1. Summary

Cycle 04 is the culmination of the project's core vision: creating a truly autonomous, self-improving system for generating machine learning potentials. This cycle introduces **Module E: The Simulation Engine**, which not only uses the trained MLIP for large-scale simulations but also critically monitors the simulation for regions where the potential is uncertain. By implementing an **On-the-fly (OTF) Active Learning Loop**, we will transform the pipeline from a linear, one-shot generator into a dynamic, iterative process that actively seeks out its own weaknesses and systematically corrects them. This "closes the loop" and embodies the principle of removing the human expert from the process of refining and validating the potential.

The core of this cycle is the implementation of an uncertainty quantification metric, such as an extrapolation grade, which will be calculated at every step of a production Molecular Dynamics (MD) or kinetic Monte Carlo (kMC) simulation. The Simulation Engine will run with the best MLIP trained in the initial phases. If, during the simulation, the system encounters an atomic configuration where the uncertainty metric exceeds a predefined threshold, it signals that the model is operating outside its trusted training domain. When this happens, the simulation is automatically paused. The high-uncertainty structure is carefully extracted—using a periodic embedding technique to preserve the local environment—and is sent back to the beginning of the pipeline, specifically to Module C, for high-fidelity DFT labelling.

This newly labelled data point is then added to the existing training set, and the MLIP is retrained using Module D. The simulation can then be resumed with this improved, more robust potential. This iterative cycle of "simulate -> detect uncertainty -> label -> retrain" allows the potential to progressively expand its applicability and improve its accuracy in a targeted, data-efficient manner. Furthermore, this cycle will include the integration of advanced simulation techniques like adaptive kMC to efficiently explore rare events, ensuring that the active learning process covers not just thermal vibrations but also important transition-state pathways. By the end of this cycle, the MLIP-AutoPipe will be a fully autonomous system capable of generating, validating, and iteratively refining a high-quality potential with minimal human oversight.

## 2. System Architecture

The architecture in Cycle 04 undergoes a fundamental change, shifting from a linear pipeline to a cyclical one. This is managed by the Orchestrator, which will now control the main active learning loop. Module E is the new component that drives this loop.

**Component Breakdown:**

*   **Module E: Simulation Engine (`modules/e_simulation_engine.py`):** This new module is responsible for running production simulations and monitoring uncertainty.
    *   **Simulation Integration:** It will be built on a robust simulation package like LAMMPS, which will be compiled with the necessary extensions to use our trained MLIPs. The system will be responsible for automatically building or providing this dependency.
    *   **Uncertainty Quantification (UQ):** The core of the active learning logic. An efficient UQ metric will be implemented. For committee-based models, this could be the standard deviation of predictions. For models like ACE or MACE, it might involve measuring the distance of a local atomic environment to the environments in the training set (an "extrapolation grade"). This calculation needs to be fast enough to run at every simulation step.
    *   **Structure Extraction:** When the UQ metric exceeds the threshold, the engine must be able to pause the simulation and extract the atomic configuration. To avoid surface effects from simple cluster cutouts, it will implement a **Periodic Embedding** technique: a small, periodic cell centred on the high-uncertainty atom is extracted, preserving the essential boundary conditions for an accurate DFT recalculation.

*   **Orchestrator (`orchestrator.py`):** The orchestrator's role becomes significantly more complex. It will now manage the main "meta-loop" of the entire process.
    *   **Initial Run:** It will first execute the linear pipeline as defined in Cycle 3 (A -> B -> C -> D) to generate an initial, baseline MLIP.
    *   **Active Learning Loop Management:** After the initial training, the orchestrator will enter a loop:
        1.  Initialize Module E with the latest MLIP.
        2.  Start the simulation. The simulation engine runs until it either completes its target number of steps or yields a high-uncertainty structure.
        3.  **If a structure is yielded:**
            a. The orchestrator takes the structure and sends it to Module C for labelling.
            b. The new labelled data is added to the main dataset (stored in the ASE DB).
            c. The orchestrator triggers Module D to retrain the MLIP with the augmented dataset.
            d. The loop continues from step 1 with the improved MLIP.
        4.  **If the simulation completes without exceeding the uncertainty threshold:** The loop terminates, and the process is considered complete.

*   **ASE Database (`utils/ase_db.py`):** The role of the database is now even more central, as it persists the master training set across all iterations of the active learning loop. The orchestrator will continually add new data points to it.

This cyclical architecture represents the final, fully autonomous form of the pipeline.

## 3. Design Architecture

The design for Cycle 04 focuses on a robust `SimulationEngine` and a stateful `Orchestrator` that can manage the iterative workflow.

**Key Classes and APIs:**

*   **`mlip_pipe.modules.e_simulation_engine.SimulationEngine`**
    *   `__init__(self, config)`: Initializes with simulation parameters, the path to the MLIP potential file, and the uncertainty threshold.
    *   `run_simulation(self) -> Generator[Optional[ase.Atoms], None, None]`: This is the core method, designed as a Python generator. It runs the MD or kMC simulation. For most of its execution, it yields `None`. However, when the uncertainty threshold is breached, it `yield`s the high-uncertainty ASE `Atoms` object and pauses its own execution. The orchestrator can then resume the generator after retraining is complete. This generator-based design provides an elegant and efficient way to pause and resume the simulation state.
    *   `_calculate_uncertainty(self, current_configuration) -> float`: An internal method that computes the UQ metric for the current state of the simulation.
    *   `_extract_periodic_embedding(self, atom_index: int) -> ase.Atoms`: An internal method to perform the periodic extraction of the local environment around a specific atom.

*   **`mlip_pipe.orchestrator.Orchestrator`**
    *   `run_full_pipeline(self)`: The main entry point will be refactored.
    *   `_initial_training_run(self) -> str`: An internal method encapsulating the linear A->B->C->D workflow to produce the first MLIP.
    *   `_active_learning_loop(self, initial_potential_path: str)`: The new method that contains the main loop. It will instantiate the `SimulationEngine` and iterate over its generator, managing the calls to Module C and Module D as needed.

*   **State Management:** The orchestrator will need to manage the state of the active learning process, including the current iteration number, the path to the latest potential, and the master dataset. This might be managed internally or persisted to a simple state file.

## 4. Implementation Approach

1.  **Simulation Engine Integration:**
    *   The first step is a technical one: ensuring a suitable simulation engine (e.g., LAMMPS) is available in the environment. This may involve writing a script that automatically downloads and compiles it with the required plugins for using MLIPs.
    *   Implement a basic wrapper in the `SimulationEngine` class that can take an `Atoms` object and a potential file, generate a LAMMPS input script, and run a simple NVT simulation.

2.  **Uncertainty Metric:**
    *   Implement the chosen uncertainty quantification metric. This is a critical research and implementation step. Start with a simple, robust metric (e.g., based on the local descriptor's distance to the training set descriptors).
    *   Write a function `_calculate_uncertainty` and test it on known structures (some similar to the training set, some very different) to ensure it produces a sensible range of values.

3.  **Generator-based Simulation Runner:**
    *   Refactor the basic simulation runner into the generator-based `run_simulation` method.
    *   Inside the main simulation loop, after each step, call `_calculate_uncertainty`.
    *   If the uncertainty exceeds the threshold, `yield` the current `Atoms` object. Otherwise, `yield None`. This structure is key to the pause-and-resume functionality.

4.  **Orchestrator Loop:**
    *   Modify the `Orchestrator` to handle the new cyclical workflow.
    *   After the initial training run, it should enter a `for` loop that iterates over the `SimulationEngine.run_simulation()` generator.
    *   Inside the loop, it will check if the yielded value is an `Atoms` object. If it is, the orchestrator will trigger the labelling and retraining process.

5.  **Periodic Embedding:**
    *   Implement the `_extract_periodic_embedding` function. This requires careful geometric manipulation to correctly extract a sub-cell from the main simulation box while preserving periodicity. Unit tests are crucial here to verify the correctness of the extracted cell vectors and atomic positions.

6.  **End-to-End Test:**
    *   This will be the most comprehensive test in the project. It will start from an `input.yaml`.
    *   It will need to be carefully designed. For example, we could train an initial potential on data from a low-temperature simulation, and then configure the active learning simulation to run at a much higher temperature.
    *   The test will assert that the `SimulationEngine` is started, that it pauses and yields at least one structure (as it explores the new high-temperature phase space), that a retraining cycle is completed, and that the simulation eventually resumes. This validates the entire feedback mechanism.

## 5. Test Strategy

Testing in Cycle 04 is focused on the complex logic of the active learning loop, the correctness of the uncertainty metric, and the robustness of the pause-and-resume mechanics.

**Unit Testing Approach (Min 300 words):**
*   **`TestSimulationEngine`:**
    *   The core `run_simulation` generator method will be tested extensively. We will mock the underlying simulation call (e.g., the LAMMPS subprocess). We will create a mock `_calculate_uncertainty` function that we can control from the test.
    *   **Test Case 1 (No uncertainty):** Configure the mock to always return low uncertainty. Assert that the generator runs to completion and yields `None` at every step.
    *   **Test Case 2 (Immediate uncertainty):** Configure the mock to return high uncertainty on the very first step. Assert that the generator yields an `Atoms` object immediately and then pauses.
    *   **Test Case 3 (Delayed uncertainty):** Configure the mock to return high uncertainty only on step `k`. Assert that it yields `None` for `k-1` steps and then yields an `Atoms` object on step `k`.
    *   The `_extract_periodic_embedding` function will be tested with a known, simple crystal structure (e.g., a 3x3x3 supercell of silicon). We will ask it to extract the environment around a central atom and assert that the resulting `Atoms` object has the correct, smaller periodic cell vectors and contains the correct set of atoms.

*   **`TestOrchestrator`:** The tests will focus on the new loop logic. We will mock the `SimulationEngine`'s generator. By controlling what the mock generator yields, we can test the orchestrator's response. If the mock yields an `Atoms` object, we assert that the orchestrator calls the (mocked) `QuantumEspressoRunner` and `Trainer`. If the mock yields `None`, we assert that these are not called.

**Integration Testing Approach (Min 300 words):**
The main integration test will be an end-to-end validation of the entire active learning cycle.

*   **`test_full_active_learning_cycle`:**
    1.  **Setup:** Create an `input.yaml` for a simple system. The key is to design the test to reliably trigger uncertainty. One way is to create a training set (using Modules A and B) exclusively from low-temperature MD runs, thus generating an initial MLIP that is only valid for low temperatures.
    2.  **Execution:** Run the full orchestrator. The `FullConfig` will be set up to run the active learning simulation (Module E) at a significantly higher temperature.
    3.  **Process and Assertions:**
        *   The orchestrator should first perform the initial training run. Assert that an initial potential file is created.
        *   The orchestrator should then start the `SimulationEngine` with this potential at the high temperature.
        *   **Crucial Assertion:** The test must assert that the `run_simulation` generator yields at least one `Atoms` object. This proves that the system has correctly identified that the high-temperature configurations are outside its initial training domain.
        *   The test will then assert that the `QuantumEspressoRunner` is called again to label this new structure.
        *   It will assert that the `Trainer` is called again to produce a *new*, updated potential file.
        *   Finally, it will assert that the simulation is resumed.

This test provides a high degree of confidence that the entire feedback loop—the core of the system's autonomy—is functioning as designed. It validates that the system can identify its own weaknesses and trigger the appropriate actions to correct them.