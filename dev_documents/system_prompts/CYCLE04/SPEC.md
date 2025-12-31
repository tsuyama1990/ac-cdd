# Cycle 04 Specification: Active Learning and Long-Timescale Simulation

## 1. Summary

Cycle 04 represents the culmination of the project's core vision: transforming the linear, one-shot pipeline into a fully autonomous, self-improving, closed-loop system. This cycle introduces the `SimulationEngine` (Module E) and the On-the-Fly (OTF) active learning workflow. Until now, the pipeline could generate a high-quality MLIP based on an initial, intelligently selected dataset. However, that potential's reliability was confined to the conformational space explored during the initial sampling. Any simulation that ventured beyond this "known" territory would be an extrapolation, with no guarantee of accuracy. The active learning loop shatters this fundamental limitation. The system will now use the bespoke MLIP it has just trained to run realistic, long-timescale simulations, but it will do so with a crucial self-awareness: it will continuously monitor the model's own confidence in its predictions. This cycle elevates the system from a potential *generator* to a potential *refiner*, creating a model that learns and adapts based on its own experiences.

The cornerstone of this cycle is the implementation of a robust uncertainty quantification (UQ) metric. During a Molecular Dynamics (MD) or Kinetic Monte Carlo (kMC) simulation driven by the newly trained MLIP, the `SimulationEngine` will evaluate this UQ metric at every step. A high UQ score signifies that the simulation has entered a novel region of the atomic configuration space where the model is effectively "guessing" because it has not seen similar data during its training. When this uncertainty exceeds a pre-defined, dynamic threshold, the active learning loop is triggered. The simulation is automatically paused, the "uncertain" atomic structure is extracted, and it is sent back to the `LabellingEngine` (Module C) for a high-fidelity DFT calculation. The resulting new data point—a confirmed, accurate label in a previously unknown region—is then added to the training set. The MLIP is re-trained by the `TrainingEngine` (Module D) with this augmented dataset. The simulation then resumes from the exact point it was paused, but now equipped with an improved, more knowledgeable potential.

This iterative refinement process allows the MLIP to grow and adapt, becoming progressively more robust and accurate as it explores more of the potential energy surface. This is particularly crucial for studying complex phenomena like phase transitions or chemical reactions, where the system can encounter unexpected intermediate states. Furthermore, this cycle will see the integration of advanced simulation methods like Adaptive Kinetic Monte Carlo (kMC). While MD is excellent for exploring thermal vibrations, kMC is designed to efficiently explore rare events like atomic diffusion or chemical reactions, which are often the most scientifically interesting phenomena and occur on timescales inaccessible to direct MD. By coupling kMC with active learning, the system can autonomously discover new reaction pathways and build a potential that is accurate for both the stable states and the critical transition states that connect them.

## 2. System Architecture

The introduction of Module E fundamentally changes the system's topology from a linear pipeline to a cyclical graph. It creates a powerful feedback loop where the output of the training stage (the MLIP) is actively used to generate new input for the labelling stage, thereby closing the loop of model improvement.

The new, cyclical architecture works as follows:
1.  **Initial Potential Generation:** The initial workflow (Cycles 01-03) proceeds as normal. A minimal user config is expanded, initial seed structures are generated (Module A), an exploration phase with a surrogate model selects a high-value set of candidate structures (Module B), these are labelled with high-precision DFT (Module C), and a baseline MLIP, now an ensemble of models for UQ, is trained (Module D). This initial model is considered version 0 (e.g., `model_v0_ensemble/`).
2.  **Entering the Active Learning Loop:** The `WorkflowOrchestrator` now enters the main active learning loop, which is configured to run for a certain number of "generations" or iterations. It passes the initial trained MLIP ensemble to the `SimulationEngine` (Module E).
3.  **Monitored Simulation:** Module E starts a long-running MD or kMC simulation using the potential.
4.  **Uncertainty Detection:** At each step of the simulation, an uncertainty metric is calculated (e.g., the variance of force predictions across the model ensemble). If this uncertainty value exceeds a dynamically-adjusted threshold, the loop is triggered:
    a. **Pause and Extract:** The simulation is immediately paused. The current atomic configuration, which caused the high uncertainty, is extracted. Special care is taken here to handle periodic boundaries correctly, ensuring a physically meaningful, complete structure is saved for labelling.
    b. **Notify Orchestrator:** The `SimulationEngine` signals to the `Orchestrator` that a new candidate structure has been found.
    c. **On-Demand Labelling:** The `Orchestrator` sends this single structure to the `LabellingEngine` (Module C) for a DFT calculation. This is a key difference from the initial batch labelling; here, calculations are done on-demand for individual, high-value configurations.
    d. **Dataset Augmentation:** Once the DFT calculation is complete and the structure is labelled, the new data point is added to the existing training set in the central ASE Database.
    e. **Model Re-training:** The `Orchestrator` invokes the `TrainingEngine` (Module D) again. The `TrainingEngine` re-trains the MLIP ensemble from scratch using the now-augmented dataset (all previous data plus the new point). This produces an improved ensemble, version 1 (`model_v1_ensemble/`).
5.  **Resume with Improved Model:** The `SimulationEngine` is then loaded with the new, improved potential ensemble, and the simulation is resumed from the exact state (positions, velocities, etc.) where it was paused.
6.  **Continuation:** This loop (Simulate -> Detect Uncertainty -> Label -> Re-train -> Resume) continues for the user-defined number of generations. With each iteration, the potential becomes more robust, and the frequency of encountering uncertain structures is expected to decrease as the model's domain of applicability expands.

This architecture enables the MLIP to "learn on the job," ensuring that the final potential is robust and reliable across all the configurations it actually encounters during a realistic simulation, which is a far more rigorous validation than simply testing on a static, pre-computed set of structures.

## 3. Design Architecture

The design for Cycle 04 focuses on the `SimulationEngine` class, the logic for uncertainty quantification, and the significant modifications to the `Orchestrator` required to manage the new cyclical workflow. The design must be robust enough to handle state management, model versioning, and the seamless pausing and resuming of complex simulations.

**New and Updated Classes:**

*   **`SimulationEngine` (`modules/e_simulation_engine.py`):** This is the primary new component.
    *   `__init__(self, config: FullConfig, db_wrapper: AseDB)`: Takes the complete configuration and the database wrapper.
    *   `run_otf_simulation(self, initial_atoms: ase.Atoms, mlip_model_paths: List[str]) -> Optional[ase.Atoms]`: The main public method. It loads the ensemble of MLIP models, attaches a calculator that uses them, and starts or resumes the simulation. If an uncertain structure is found, it performs the necessary extraction and returns the `ase.Atoms` object of that structure. If the simulation completes without exceeding the threshold, it returns `None`.
    *   `_run_md_step(self)`: A private method that executes a single step of the MD simulation, including calculating the forces and updating positions.
    *   `_calculate_uncertainty(self, atoms: ase.Atoms) -> float`: A crucial private method. It will implement the chosen uncertainty metric. For an ensemble, this method will involve getting force predictions from each of the loaded potentials for the current atomic configuration. The uncertainty will then be calculated as a scalar value, for instance, the maximum standard deviation of the force components across all atoms.
    *   `_extract_structure_for_retraining(self, atoms: ase.Atoms) -> ase.Atoms`: A private method that takes the high-uncertainty `Atoms` object and applies the necessary boundary treatment (e.g., creating a buffer region, passivation for covalent systems) before it is sent to the database. This is critical for ensuring that the structure sent for DFT labelling is physically realistic.

*   **`Orchestrator` (`orchestrator.py`):**
    *   The main `run_full_pipeline` method will be refactored to manage the active learning loop. After the initial training (which now produces an ensemble), it will enter a `for` or `while` loop that iterates for the configured number of `max_generations`.
    *   Inside the loop, it will instantiate and call `SimulationEngine.run_otf_simulation`. If the method returns a new `Atoms` object, the orchestrator will trigger a single-structure labelling run with Module C, followed by a retraining run with Module D on the augmented dataset.
    *   It will need to manage the paths to the evolving MLIP models, creating new directories for each generation (e.g., `run_outputs/gen_0/model_0.ace`, `run_outputs/gen_1/model_0.ace`) to ensure full provenance and prevent overwriting.

**Updated Data Models (`config/models.py`):**

*   A new Pydantic model, `ActiveLearningParams(BaseModel)`, will be added to `FullConfig` to provide user control over the loop.
*   Fields will include:
    *   `max_generations: int`: The maximum number of re-training iterations to perform.
    *   `uncertainty_threshold: Union[float, Literal["dynamic_95percentile"]]`: The threshold for triggering re-training. Allowing a dynamic, percentile-based value is a key feature for adaptability.
    *   `md_steps_per_generation: int`: The number of MD steps to run within one generation before the loop proceeds to the next.
    *   `ensemble_size: int`: The number of models to train in the committee for uncertainty quantification (e.g., 5).

**Uncertainty Quantification Design:**
The choice of uncertainty metric is critical. The implementation will rely on a committee of models. The `TrainingEngine` will be modified so that, when active learning is enabled, it trains not one, but an `ensemble_size` number of MLIPs. Each model will be trained on the same data but with different random initializations for their weights, which is often sufficient to create a diverse enough ensemble. During the simulation phase, the `_calculate_uncertainty` method will, at each step, get the force predictions from all models in the committee for the current atomic configuration. The uncertainty will be defined as the standard deviation of these force predictions, likely taking the maximum standard deviation over all atoms and all force components. A large standard deviation implies the models disagree significantly, indicating a region of high uncertainty where the models are extrapolating.

## 4. Implementation Approach

The implementation will be carefully staged to build the simulation engine, the uncertainty metric, and finally the closed loop that connects them back to the rest of the pipeline.

1.  **Configuration:**
    *   The `ActiveLearningParams` Pydantic model will be implemented and integrated into the `FullConfig`.
    *   The `ConfigExpander` will be updated to provide sensible defaults for these new parameters, such as `max_generations: 5` and `ensemble_size: 5`, so that active learning is enabled by default.

2.  **Update Training Engine for Ensembles:**
    *   The `TrainingEngine.run()` method will be modified. It will check the configuration for `ensemble_size`. If the size is greater than 1, it will run its internal training loop multiple times with different random seeds, saving each resulting model to a uniquely named file (e.g., `model_v0_committee_0.ace`, `model_v0_committee_1.ace`) in a generation-specific directory.

3.  **Implement the `SimulationEngine`:**
    *   Development will start with the basic simulation logic in `_run_md_step`. This will be similar to the MD run in Cycle 03, but its calculator will be a custom one that holds references to the entire ensemble of bespoke MLIPs trained by Module D.
    *   The `_calculate_uncertainty` method will be implemented next. This method will be the heart of the active learning logic. It will iterate through the list of loaded committee models, call `get_forces()` on each, and then compute the standard deviation of the resulting force arrays along the committee axis.
    *   The public `run_otf_simulation` method will be implemented to tie these together. It will contain the main MD loop which, at each step, calls `_run_md_step` and then `_calculate_uncertainty`. It will check the uncertainty against the threshold and, if exceeded, will call `_extract_structure_for_retraining` and then exit the loop, returning the new structure.
    *   The implementation of `_extract_structure_for_retraining` will be particularly careful, using ASE's built-in functions to handle periodic boundaries and ensure the extracted cell is whole and physically meaningful.

4.  **Implement the Active Learning Loop in the `Orchestrator`:**
    *   The main `run_full_pipeline` logic in the orchestrator will be significantly refactored. After the first call to the `TrainingEngine`, it will enter a `for` loop that iterates from `0` to `max_generations - 1`.
    *   Inside the loop, it will instantiate and call the `SimulationEngine`, passing it the list of model paths for the current generation.
    *   If the `SimulationEngine` returns a new structure, the orchestrator will:
        *   Add the new structure to the database with status `needs_labelling`.
        *   Call the `LabellingEngine` for just that one structure.
        *   Call the `TrainingEngine` again, but this time providing the *entire accumulated dataset* (original data + all new points found so far) to create the next generation of models.
    *   The orchestrator will also be responsible for managing the model file versions, creating a new subdirectory for each generation's models.

5.  **Integration of Advanced kMC:**
    *   After the MD-based active learning loop is functional and tested, the `SimulationEngine` will be extended to support kMC. This will likely involve interfacing with an external code like `LAMMPS` or a specialized library like `EON`.
    *   The uncertainty check will be adapted for the kMC workflow. Instead of checking at every time step, it will be more effective to check the uncertainty on the new configurations found after a successful kMC saddle point search and state-to-state transition.

Testing this cycle is complex because it involves a stateful, evolving loop where the behavior of one iteration depends on the results of the previous one.

## 5. Test Strategy

Testing Cycle 04 requires verifying not just individual components, but the correctness and stability of the feedback loop itself. The tests must confirm that the system can detect uncertainty, trigger re-training, and improve its model as designed.

**Unit Testing Approach (Min 300 words):**

*   **`TrainingEngine` Ensemble:** The modification to the `TrainingEngine` to produce an ensemble of models must be unit-tested. A test will be added that runs the engine with `ensemble_size` set to 5. The test will mock the underlying ACE `fit` call but will assert that this mocked function is called exactly 5 times. It will also assert that after the run, 5 distinct model files (e.g., `model_committee_0.ace` through `model_committee_4.ace`) are created in the output directory.
*   **Uncertainty Calculation:** The `_calculate_uncertainty` method is the core of the new logic and requires rigorous unit testing. A test will be created where we manually create two mock "model" objects. These mocks will have a `get_forces` method that returns a pre-defined NumPy array. The test will call the `_calculate_uncertainty` method with an input `Atoms` object. In one test case, the mock models will be configured to return very similar force arrays, and we will assert that the calculated uncertainty is very low. In another case, they will be configured to return very different force arrays, and we will assert that the calculated uncertainty is high. This directly validates the correctness of the statistical calculation.
*   **Structure Extraction:** The `_extract_structure_for_retraining` method is critical for data integrity. Its unit test will create a periodic `ase.Atoms` object where some atoms have been moved outside the principal unit cell (a common occurrence in MD). The test will call the extraction method and assert that the returned `Atoms` object has had its atomic positions wrapped back into the unit cell, producing a sensible, non-fragmented structure suitable for a subsequent DFT calculation.

**Integration and End-to-End Testing (Min 300 words):**

*   **Single Loop Test (The "E2E-Loop" Test):** This will be the most important and comprehensive test of the entire project. It is a carefully controlled end-to-end test designed to verify one full iteration of the active learning cycle, confirming all components work together.
    1.  **Setup:**
        *   Start with a minimal config for a very simple system (e.g., an H2 molecule). The config will specify `max_generations: 1`.
        *   The initial training set will be deliberately minimal, containing just two points: H2 at its equilibrium distance, and H2 stretched to 1.5 times its equilibrium. This creates a model that "knows" about equilibrium but not about dissociation.
        *   The `LabellingEngine` will be mocked to provide pre-computed DFT values instantly.
        *   The `TrainingEngine` will be run for real, but on this tiny dataset, it will be very fast. It will be configured to produce an ensemble of simple potentials.
        *   The `SimulationEngine` will be configured to run a short MD simulation where the H2 molecule is stretched to 3.0 times its equilibrium, a region it was not trained on.
        *   The uncertainty threshold will be set to a low value to guarantee it will be triggered when the bond is stretched.
    2.  **Execution:** The test will invoke the full pipeline from the CLI.
    3.  **Verification:** The test will assert the following sequence of events occurred, in order:
        *   An initial ensemble of models is trained and saved.
        *   The `SimulationEngine` starts and runs the MD simulation.
        *   The uncertainty threshold is triggered. The test will capture the structure that triggered the event and assert that it is indeed a "stretched" H2 molecule (bond length ~3.0).
        *   The mocked `LabellingEngine` is called **exactly one more time** for this new stretched configuration.
        *   The `TrainingEngine` is called **a second time**. The test will assert that the input dataset for this second call is larger than the first one (original data + the new point).
        *   A new, improved ensemble of models (e.g., in a `gen_1` directory) is saved.
        *   The pipeline terminates successfully.

This E2E-Loop test provides high confidence that the entire feedback mechanism is correctly wired and that the system is capable of learning and improving itself as designed.
