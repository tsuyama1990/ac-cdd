# Cycle 03 Specification: Efficient Exploration with a Surrogate Model

## 1. Summary

Cycle 03 introduces a significant leap in the intelligence and efficiency of the MLIP-AutoPipe pipeline. While the previous cycles established a workflow to automatically generate and label structures, the dataset creation was still "uninformed"—it relied on heuristics that, while physically motivated, could not guarantee that the most important or challenging regions of the potential energy surface were being sampled. This cycle addresses that gap by implementing the `Explorer & Sampler` (Module B), a component designed to actively seek out the most informative atomic configurations for training the MLIP, thereby maximizing the "value" of each expensive DFT calculation. This marks the transition from a purely automated pipeline to an intelligent one that can reason about its own data requirements. The core principle is to invest computational effort in exploration using a cheap model to guide the data acquisition for an expensive one.

The heart of this cycle is the integration of a pre-trained, universal machine learning potential—specifically, the MACE (Multi-ACE) model, which has been trained on the vast Materials Project database—as a computationally inexpensive "surrogate" for DFT. Instead of labelling every heuristically generated structure from Module A, the pipeline will now use this fast, general-purpose MACE model to run large-scale molecular dynamics (MD) simulations. Starting from the initial seed structures, these simulations can explore a vast landscape of temperatures and pressures, generating millions of potential atomic configurations and thermal trajectories at a tiny fraction of the cost of performing the same exploration with DFT. This step effectively generates a massive, computationally cheap "haystack" of candidate structures that covers a much broader region of the material's phase space than heuristic generation alone.

The second key innovation is the implementation of the DIRECT (Descriptor-Informed Representative Endpoint and Cluster-based Trajectory) sampling algorithm. Running a long MD simulation creates a haystack; DIRECT is the intelligent "needle-finder." The true challenge is identifying the small handful of frames from that trajectory that are worth the cost of a DFT calculation. The DIRECT sampler achieves this by first converting the raw MD trajectory into a series of high-dimensional feature vectors, or "descriptors" (like SOAP or ACE), that provide a mathematical fingerprint of the local atomic environment of each frame. These millions of fingerprints are then clustered to identify unique conformational states within the trajectory. Finally, a stratified sampling technique is applied to select a small, diverse subset of frames that represent the full spectrum of explored physics, ensuring that common, low-energy states are sampled, but also that rare, high-energy, or transition states are not missed. This ensures that the final training set is compact, diverse, and information-rich. This cycle is fundamentally about shifting from a brute-force data collection strategy to an intelligent, targeted one, maximizing data efficiency and ultimately leading to more robust and accurate potentials.

## 2. System Architecture

The introduction of Module B alters the pipeline's linear data flow, inserting a critical exploration and filtering step between initial structure generation (Module A) and DFT labelling (Module C). This architectural change is central to the "smart sampling" philosophy of the project, creating a clear separation between low-cost, large-scale exploration and high-cost, targeted data labelling.

The enhanced architectural flow is as follows:
1.  **Initiation:** The workflow begins as in Cycle 02: the user provides a minimal config, the `ConfigExpander` creates a full configuration, and the `StructureGenerator` (Module A) produces an initial set of diverse seed structures which are saved to the database with a 'generated' status.
2.  **Delegation to Explorer:** The `WorkflowOrchestrator` takes these seed structures and, instead of sending them directly for labelling, passes them as input to the new `Explorer & Sampler` (Module B).
3.  **Surrogate-driven MD:** Inside Module B, a loop iterates through each seed structure. Each structure is used as the starting point for a high-speed molecular dynamics simulation. The forces for this MD are not calculated by DFT but by the pre-trained, fast MACE surrogate model. This step generates one or more long trajectory files, containing potentially millions of atomic configurations that explore the thermal landscape around the initial seeds.
4.  **Descriptor Calculation:** After the simulations are complete, the module processes these trajectories. It calculates a structural descriptor (e.g., SOAP) for every single frame. This is a performance-critical step that transforms the Cartesian coordinates of the atoms into a high-dimensional vector representation that is invariant to rotation and permutation, making it suitable for machine learning.
5.  **Intelligent Sampling:** The DIRECT sampling algorithm is then applied to the complete set of all descriptors from all trajectories. This involves two sub-steps:
    a. **Clustering:** An efficient clustering algorithm (like Mini-Batch K-Means) is used to group the millions of descriptor vectors into a smaller, manageable number of clusters. Each cluster represents a distinct type of local atomic environment encountered during the simulations.
    b. **Stratified Sampling:** A sampling algorithm is then run on these clusters. Instead of picking frames randomly, it intelligently selects a few representatives from each cluster, potentially weighting the selection to ensure that both large, stable clusters and small, rare, but important clusters are represented in the final dataset.
6.  **Database Update:** The `Explorer & Sampler` takes the small list of `ase.Atoms` objects corresponding to the selected frames and saves them to the ASE Database. Crucially, it assigns them a new status: `'selected_for_labelling'`. The vast majority of generated frames from the MD trajectories are discarded, having served their purpose for exploration.
7.  **Targeted Labelling:** The `WorkflowOrchestrator` now resumes its main flow. It queries the database specifically for structures with the `'selected_for_labelling'` status and passes only this much smaller, more informative set to the `LabellingEngine` (Module C).
8.  **Final Training:** The pipeline then proceeds as before, with Module C labelling the selected structures and Module D training the final MLIP on this high-quality, information-rich dataset.

This architectural change embodies the "smart-sampling" philosophy. The pipeline now invests its most expensive resource—DFT calculations—only on configurations that have been algorithmically determined to be of high value, dramatically improving the overall efficiency of the potential generation process and leading to a better final product.

## 3. Design Architecture

The design for Cycle 03 centers on the new `ExplorerSampler` class, which encapsulates the entire logic for exploration and sampling. This requires extending the main configuration model to manage the parameters for this new, complex stage of the pipeline. The design prioritizes modularity and performance.

**New and Updated Classes:**

*   **`ExplorerSampler` (`modules/b_explorer_sampler.py`):** This new class is the core of the cycle.
    *   `__init__(self, config: FullConfig, db_wrapper: AseDB)`: It is initialized with the full configuration object and the database wrapper.
    *   `run(self, initial_structures: List[ase.Atoms]) -> int`: This is the main public method called by the orchestrator. It takes the list of seed structures from Module A, orchestrates the internal sequence of MD runs and sampling, updates the database with the final selected structures, and returns the final count.
    *   `_run_mace_md(self, atoms: ase.Atoms) -> ase.io.Trajectory`: A private method responsible for the MD simulation. It will programmatically load the specified pre-trained MACE model, attach it as an ASE `Calculator` to the input `atoms` object, and then use one of ASE's built-in MD integrators (e.g., `ase.md.velocityverde.VelocityVerlet`) to run the simulation and collect the trajectory.
    *   `_calculate_descriptors(self, trajectory: ase.io.Trajectory) -> np.ndarray`: A performance-critical private method. It will iterate through the trajectory frames and compute the chosen structural descriptors using a library like `dscribe`. The implementation will be carefully designed to be parallelizable and will be a prime candidate for Numba JIT compilation to accelerate the process, as this can be a major bottleneck.
    - `_perform_direct_sampling(self, descriptors: np.ndarray, atoms_list: List[ase.Atoms]) -> List[ase.Atoms]`: A private method that implements the core sampling logic. It takes the large NumPy array of descriptors and the corresponding list of `ase.Atoms` objects. It will use an efficient, scalable clustering algorithm (e.g., `sklearn.cluster.MiniBatchKMeans`) to handle the potentially very large number of descriptors. It will then implement the stratified sampling logic to select the final, representative `ase.Atoms` objects.

*   **`Orchestrator` (`orchestrator.py`):**
    *   The main pipeline logic (`run_full_pipeline`) will be updated to insert a call to `ExplorerSampler.run()` after the `StructureGenerator` has finished and before the labelling stage begins.
    *   The subsequent query to the database for labelling will be changed from `get_by_status('needs_labelling')` to the new `get_by_status('selected_for_labelling')`. This change is crucial as it ensures only the filtered, high-value structures are passed to the expensive DFT calculation stage.

**Updated Data Models (`config/models.py`):**

The configuration needs to be extended to control this new module's behavior.

*   A new Pydantic model, `ExplorerParams(BaseModel)`, will be created to hold all settings for this module.
*   This model will be added as a field to the main `FullConfig` model, ensuring validation and type safety.
*   Fields in `ExplorerParams` will include:
    *   `surrogate_model: str`: The name of the pre-trained MACE model to use (e.g., 'mace_mp_0').
    *   `md_temp: float`: The target temperature for the exploratory MD simulation in Kelvin.
    *   `md_steps: int`: The number of MD steps to run for each initial seed structure.
    *   `descriptor_type: Literal['soap', 'ace']`: A literal string to choose the type of descriptor to use for the sampling process.
    *   `sample_count: int`: The target total number of structures to select for DFT labelling after exploring all seeds.

This design cleanly encapsulates the entire exploration and sampling logic within a single, well-defined module. This makes it easy to test in isolation and, in the future, to swap out with different sampling strategies or surrogate models without affecting the rest of the pipeline.

## 4. Implementation Approach

The implementation will focus on integrating the MACE model and building the sampling algorithm, with a strong emphasis on computational performance and robust error handling.

1.  **Dependency and Configuration:**
    *   The first step is to update the project environment. The necessary libraries (`mace-torch` for the surrogate model, `dscribe` for SOAP descriptors, and `scikit-learn` for clustering) will be added to the `[project.dependencies]` section of the `pyproject.toml` file.
    *   The `ExplorerParams` Pydantic model will be implemented in `config/models.py`, and it will be added as a component of the `FullConfig` model.
    *   The `ConfigExpander` from Cycle 02 will be updated to provide sensible, physically-motivated default values for these new parameters in the `exec_config_dump.yaml`, so the user is not required to specify them in the minimal config.

2.  **MACE Integration:**
    *   A utility function will be developed in `utils/` to handle the loading of the pre-trained MACE model. This function will be responsible for downloading the model weights if they are not found locally and caching them for future runs.
    *   A helper function, likely in the `ExplorerSampler` class, will take an `ase.Atoms` object and return it with a MACE `Calculator` instance attached. This will involve using the `mace-torch` library's Python API to load the model. This critical integration point will be thoroughly unit-tested.

3.  **Implement `ExplorerSampler` - MD Simulation:**
    *   The `_run_mace_md` method will be implemented. It will use the MACE calculator utility and ASE's built-in MD integrators, such as `VelocityVerlet`. The method will be configured to save the trajectory to a temporary file for later processing. It will also handle the initialization of velocities to the target temperature.

4.  **Implement `ExplorerSampler` - Descriptors and Sampling (Performance Focus):**
    *   The `_calculate_descriptors` method will be implemented next. This will use the `dscribe` library to generate SOAP descriptors for each frame in the trajectory. Given that this can be a slow process for millions of frames, the code will be carefully profiled. If native Python loops prove to be a bottleneck, a custom implementation that is JIT-compiled with Numba will be developed to achieve near-native performance.
    *   The `_perform_direct_sampling` method will be implemented. It will use an efficient, memory-friendly clustering algorithm like `MiniBatchKMeans` from `scikit-learn`, which is designed to handle datasets that may not fit entirely in memory. After clustering, it will implement the stratified sampling logic, which involves iterating through the cluster labels and picking a proportional number of representatives from clusters of different sizes.

5.  **Implement `ExplorerSampler` - Main Logic and Database Interaction:**
    *   The public `run` method will be implemented to tie all the private methods together in the correct sequence: loop through initial structures, run MD for each, collect all trajectories, calculate descriptors for all frames, perform sampling on the combined dataset, and finally, save the results.
    *   After sampling, this method will interact with the `AseDB` wrapper to save the selected `ase.Atoms` objects to the database with the new `'selected_for_labelling'` status.

6.  **Update `Orchestrator`:**
    *   The orchestrator's central workflow (`run_full_pipeline`) will be modified to insert a call to the newly implemented `ExplorerSampler.run()` method after the `StructureGenerator` and before the `LabellingEngine`.
    *   The database query that gathers structures for the labelling stage will be changed from `get_by_status('needs_labelling')` to `get_by_status('selected_for_labelling')`, ensuring the filtering is effective.

Testing will be paramount throughout this cycle, especially for the performance-critical descriptor calculation and the statistical correctness of the sampling logic.

## 5. Test Strategy

Testing for Cycle 03 will focus on the correctness of the complex new sampling algorithm, the successful integration of the MACE model, and the performance of the data processing steps. The strategy will combine fast unit tests for logic and slower integration tests for module interactions.

**Unit Testing Approach (Min 300 words):**

*   **MACE Integration:** A crucial unit test will be to validate the core integration with `mace-torch`. The test will not run a full MD simulation, which would be slow and require a GPU. Instead, it will create a simple `ase.Atoms` object (e.g., a water molecule), call the helper function to attach the MACE calculator, and then make direct calls to `atoms.get_potential_energy()` and `atoms.get_forces()`. The test will assert that the returned values are of the correct type (float for energy, NumPy array for forces) and shape (N_atoms x 3 for forces). This provides high confidence that the model loading and calculator attachment logic is correct without external dependencies.
*   **Descriptor Calculation:** The `_calculate_descriptors` method will be unit-tested for correctness and to establish a performance baseline. The test will use a small, pre-saved trajectory file (e.g., 10 frames of a 10-atom system). It will run the descriptor calculation and assert that the resulting NumPy array of descriptors has the expected dimensions (`10` x `descriptor_length`). We will compare the output to a pre-computed result to ensure the calculation is correct. Another test will use a larger file and `pytest-benchmark` to ensure the performance of this critical step is acceptable and does not regress in the future.
*   **Sampling Logic:** The `_perform_direct_sampling` method's logic is vital and will be tested with a carefully constructed synthetic dataset. Instead of using real high-dimensional descriptors, the test will create a simple 2D NumPy array where clusters are obvious. For example, we will generate 100 points around (0,0), 50 points around (5,5), and 5 points around (10,10) to simulate clusters of different sizes and densities. We will then run the sampling algorithm with a request to select 3 samples. The test will assert that the function returns exactly one point from the vicinity of each of the three original cluster centers, verifying that the stratified sampling is correctly selecting representatives from all clusters, not just the largest one.

**Integration Testing Approach (Min 300 words):**

*   **`ExplorerSampler` Module Test:** This will be a focused integration test for Module B alone, verifying the interaction of its internal components.
    1.  **Setup:** The test will create a temporary database and add a single initial structure (e.g., a bulk Si cell).
    2.  **Execution:** It will instantiate and run the `ExplorerSampler.run()` method. The real MACE model will be used, but the MD simulation will be limited to a very small number of steps (e.g., 20 steps) to keep the test fast. The descriptor and sampling steps will run on this small trajectory.
    3.  **Verification:** The test will assert that the method completes successfully. It will then query the test database and assert that a specific number of new structures have been added with the status `'selected_for_labelling'`. Crucially, this number should be less than the total number of MD steps (20), proving that the sampling and filtering logic was successfully executed.
*   **Full Pipeline End-to-End Test:** The E2E test from Cycle 02 will be updated to include this new, critical stage. This test verifies that the entire pipeline, including the new module, is correctly wired.
    1.  **Setup:** The test will start with a minimal `input.yaml` file.
    2.  **Execution:** It will run the full pipeline CLI command. The MACE MD simulation will run for a few steps (e.g., 10 steps). The subsequent QE labelling will be mocked to return pre-computed results instantly.
    3.  **Verification:** The key new assertion will be to check the number of times the mocked `LabellingEngine` is called. We will configure the `ExplorerSampler` to select, for example, 3 samples. The test will then verify that the mocked labelling function was called exactly 3 times. This number is independent of the number of seed structures from Module A and much smaller than the 10 steps in the MD simulation. This provides end-to-end confirmation that the sampling module is correctly integrated and is successfully fulfilling its primary purpose: reducing the number of required DFT calculations.
