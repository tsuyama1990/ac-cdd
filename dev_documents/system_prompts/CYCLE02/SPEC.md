# Cycle 02 Specification: Automated Structure Generation & Configuration Expansion

## 1. Summary

Cycle 02 addresses the critical "cold start" problem in MLIP generation: creating a high-quality initial dataset. While Cycle 01 established the core labelling and training workflow, it relied on the user providing a pre-existing set of atomic structures. This cycle removes that dependency by introducing two major components: the `StructureGenerator` (Module A) and the `ConfigExpander` heuristic engine. The overarching goal is to move closer to a true "zero-touch" pipeline, where a user can initiate a complete workflow with a minimal, high-level input, leaving the complex details of data generation and parameter selection to the system. This represents a significant step forward in the project's mission to "remove the human expert from the loop," as these initial setup and data creation stages are often the most reliant on expert intuition and experience. By automating them, we make the tool accessible to a much broader audience and ensure a baseline of quality and reproducibility for every run.

The `StructureGenerator` is designed to be the first active module in the pipeline. Its purpose is to intelligently and automatically create a diverse, physically meaningful set of initial atomic configurations without resorting to expensive first-principles calculations like *ab initio* molecular dynamics. It will achieve this by first classifying the input material into broad categories (alloy, molecular, ionic, covalent) based on established chemical principles. It will then apply a domain-specific heuristic algorithm tailored to the physics of that material class. For example, it will use Special Quasirandom Structures (SQS) to model the configurational disorder in alloys, Normal Mode Sampling (NMS) to explore the vibrational phase space of molecules, and random structure searching for ionic crystals. This ensures the initial dataset has sufficient diversity to train a robust baseline MLIP, covering a range of coordination environments, bond lengths, and local symmetries from the very beginning.

Complementing this is the `ConfigExpander`. This component acts as an "expert system in a box." It takes the user's very simple `input.yaml`—which might only contain the chemical formula—and expands it into the comprehensive `exec_config_dump.yaml` that the pipeline's modules require. This engine will embed physical heuristics to infer a wide range of parameters automatically. For instance, it will select appropriate DFT cutoff energies and pseudopotentials based on the rigorously benchmarked SSSP (Standard Solid State Pseudopotentials) protocol for the given elements. It will also determine a sensible k-point density for Brillouin zone sampling based on cell dimensions, and even suggest a range of simulation temperatures based on the material's estimated melting point. This component is key to the project's core philosophy, as it absolves the user from needing deep knowledge of DFT parameters or simulation best practices, which are significant barriers to entry for many potential users. The successful implementation of these two modules will transform the pipeline from a powerful calculator into an autonomous scientific discovery tool.

## 2. System Architecture

The architecture in Cycle 02 evolves to place Module A and the `ConfigExpander` at the very beginning of the workflow. The process is no longer user-initiated with a complete dataset and a detailed configuration, but rather with a high-level request that the system itself elaborates and executes. This marks a fundamental shift from a user-driven to a system-driven workflow.

The new, more autonomous process flow is as follows:
1.  **User Input:** The user's interaction is simplified to providing a minimal `input.yaml` file. In the simplest case, this file might only contain `system: {elements: ["Fe", "Pt"]}`. This high-level declaration of intent is the sole required input.
2.  **Configuration Expansion:** The `WorkflowOrchestrator`, upon starting, immediately invokes the `ConfigExpander`. This is the first step in the automated process. The `ConfigExpander` reads the minimal config, applies its internal heuristic rules—such as identifying the material type, looking up SSSP parameters for Iron and Platinum, and setting default simulation parameters—and generates the complete `exec_config_dump.yaml` file. This fully specified file is then loaded by the `Orchestrator` to guide all subsequent steps. This two-tier configuration strategy ensures that the core modules always operate with a complete, validated set of parameters.
3.  **Structure Generation:** With a full configuration in hand, the `Orchestrator` then calls the `StructureGenerator` (Module A). The `StructureGenerator` inspects the configuration to find the inferred material type (e.g., "alloy") and then executes the corresponding generation algorithm (e.g., SQS).
4.  **Database Population:** The `StructureGenerator` produces a set of diverse atomic structures (e.g., several SQS cells of different sizes or with different local arrangements). These are then saved into the central ASE Database, and each is assigned the initial status 'needs_labelling'. This populates the work queue for the next stage of the pipeline.
5.  **Core Workflow Execution:** From this point, the workflow proceeds exactly as defined in Cycle 01. The `Orchestrator` queries the database for structures with the 'needs_labelling' status. It passes these newly created structures to the `LabellingEngine` (Module C) for DFT calculations. Once the calculations are complete and the structures are updated to the 'labelled' status, the entire dataset is passed to the `TrainingEngine` (Module D) to produce the final MLIP.

This updated architecture makes the system significantly more autonomous and user-friendly. The user is moved one step further away from the complex technical details, interacting only with a high-level problem description. The `ConfigExpander` acts as a crucial pre-processing and validation step, codifying expert knowledge and preventing common configuration errors. The `StructureGenerator` serves as the new entry point for data creation within the pipeline itself, ensuring that every project starts with a diverse and physically relevant dataset. The ASE Database remains the central point of coordination, seamlessly connecting the output of Module A with the input of Module C and maintaining the transactional, restartable nature of the workflow.

## 3. Design Architecture

The design for Cycle 02 introduces two new major classes, `ConfigExpander` and `StructureGenerator`, and requires a significant update to the configuration models to support the two-tier configuration strategy. This design emphasizes a clear separation of concerns, with dedicated components for configuration, data generation, and workflow orchestration.

**New and Updated Classes:**

*   **`ConfigExpander` (`config/expander.py`):** This class is the "brain" of the initial setup.
    *   `__init__(self, minimal_config: MinimalConfig)`: It is initialized with the user-provided, un-expanded configuration, which has been parsed into a `MinimalConfig` Pydantic model.
    *   `expand(self) -> FullConfig`: This is the main public method. It orchestrates the entire expansion process by calling a series of private, heuristic-based methods and returns a fully populated and validated `FullConfig` object. This method ensures a consistent order of operations for the expansion.
    *   `_infer_bond_type(self) -> str`: A private method that uses established materials science libraries like `pymatgen`. It analyzes the electronegativity differences and known properties of the elements in the configuration to classify the material into one of the primary categories (e.g., 'alloy', 'covalent'). This classification is crucial for downstream decisions.
    *   `_infer_dft_params(self) -> DFTParams`: A private method containing the logic to select DFT parameters. It will contain a data structure mapping elemental species to their recommended SSSP pseudopotential filenames and plane-wave cutoff energies. It will select the maximum cutoff required by any element in the system to ensure consistency and accuracy.
    *   `_infer_simulation_params(self) -> SimulationParams`: A private method to suggest reasonable simulation settings, such as a range of temperatures based on an estimated melting point or a default pressure.

*   **`StructureGenerator` (`modules/a_structure_generator.py`):** This class is responsible for creating the initial raw data.
    *   `__init__(self, config: FullConfig, db_wrapper: AseDB)`: It is initialized with the *complete* configuration generated by the `ConfigExpander` and a reference to the database wrapper for saving its results.
    *   `run(self) -> int`: The main public method. It contains a dispatcher that inspects the `structure_type` from the configuration and calls the appropriate private generation method. It populates the database with the generated structures and returns the total number of structures created.
    *   `_generate_sqs(self)`: A private method to handle SQS generation for alloys. This method will likely serve as a wrapper around a powerful external library like `icet`, managing the subprocess calls and parsing the output back into `ase.Atoms` objects.
    *   `_generate_nms(self)`: A private method for Normal Mode Sampling for molecular systems, which may use ASE's own vibrational modes analysis tools.
    *   `_generate_airss(self)`: A private method for Ab Initio Random Structure Searching for ionic materials.
    *   `_generate_rattle(self)`: A private method for creating disordered structures for covalent materials, likely using ASE's built-in rattling functionalities.

*   **`Orchestrator` (`orchestrator.py`):**
    *   The `__init__` method will be updated. Instead of taking a `FullConfig` object directly, it will now take the path to the minimal config file. Its first action upon initialization will be to instantiate and run the `ConfigExpander`.
    *   A new top-level method, `run_full_pipeline(self)`, will be added. This method will define the new end-to-end workflow: first, call the `StructureGenerator`, and then proceed with the labelling and training logic developed in Cycle 01 (which may be renamed to `_run_labelling_and_training` for clarity).

**Updated Data Models (`config/models.py`):**

The configuration models will be formally split to represent the two-tier system, enforced by Pydantic's validation.

*   `MinimalConfig(BaseModel)`: This new Pydantic model will define the very limited set of parameters a user can (and should) provide. Many fields will be `Optional`. For example: `class SystemConfig(BaseModel): elements: List[str]; composition: Optional[str] = None`. This explicitly defines the minimal user interface.
*   `FullConfig(BaseModel)`: This existing model will be updated to represent the fully specified configuration where every field is mandatory and has a concrete value. The `ConfigExpander`'s primary job is to safely transform a `MinimalConfig` instance into a valid `FullConfig` instance. This provides compile-time safety and clarity for all the core pipeline modules, as they can be designed with the guarantee that they will receive a complete and validated set of parameters.

This design cleanly separates the concerns of configuration expansion from structure generation and the main workflow orchestration, making the system more logical, robust, and easier to manage.

## 4. Implementation Approach

The implementation of Cycle 02 will proceed in a logical order, building the new components with a test-driven mindset and then integrating them into the existing workflow from Cycle 01.

1.  **Update Configuration Models:**
    *   The first and most foundational step is to refactor `config/models.py`. The `MinimalConfig` and `FullConfig` Pydantic models will be defined with clear, distinct fields. The `FullConfig` will contain nested models for each section (e.g., `DFTParams`, `SystemParams`). This schema-first approach is crucial as it defines the data contracts that the new components will adhere to, preventing integration issues later.

2.  **Implement the `ConfigExpander` (Test-Driven):**
    *   Create the `ConfigExpander` class. The development will be test-driven. A test will be written first, asserting that for a given minimal config, the `expand()` method returns a `FullConfig` with specific, expected values.
    *   The private methods will be implemented one by one to make the tests pass. `_infer_bond_type` will be implemented using `pymatgen` to analyze elemental properties.
    *   For `_infer_dft_params`, a YAML or JSON file containing the SSSP protocol data (mapping elements to pseudopotentials and cutoffs) will be created and bundled with the package. The implementation will load this file and use it as a lookup table.
    *   The main `expand` method will be implemented to call these private methods in the correct sequence and construct the final `FullConfig` object. Robust error handling will be added to manage cases where a user provides an unknown element or an unsupported composition.

3.  **Implement the `StructureGenerator` (Test-Driven):**
    *   Create the `StructureGenerator` class. Again, development will be test-driven.
    *   For each generation method (`_generate_sqs`, `_generate_nms`, etc.), a suitable third-party Python library will be identified and added as a dependency (e.g., `icet` for SQS, `ase`'s built-in tools for rattling).
    *   Each private method will be implemented as a clean wrapper around its chosen library. The wrapper's responsibility is to translate the parameters from our `FullConfig` into the format the library expects, run the generation, and then convert the output back into a standardized list of `ase.Atoms` objects. Each of these methods will be unit-tested in isolation, mocking the external library call if necessary.
    *   The main `run` method will be implemented with a simple conditional logic block (e.g., `if self.config.system.structure_type == 'alloy': self._generate_sqs()`) to dispatch to the correct private method based on the configuration.
    *   The interaction with the `AseDB` wrapper from Cycle 01 will be implemented to save the newly created structures to the database.

4.  **Integrate into the `Orchestrator`:**
    *   Modify the `Orchestrator`'s initialisation logic (`__init__`). It will now accept a path to a minimal config file instead of a pre-made `FullConfig` object. It will be responsible for instantiating and running the `ConfigExpander` as its very first action.
    *   Add a call to the `StructureGenerator.run()` method immediately after the configuration has been expanded.
    *   Ensure that the subsequent calls to the labelling and training engines correctly retrieve the newly generated structures from the database by querying for the 'needs_labelling' status.

5.  **Update CLI:**
    *   The `click` CLI implemented in Cycle 01 will be updated to reflect the new workflow. The user will now be instructed to provide a minimal config, and the help text will be updated to explain the new, more powerful and autonomous functionality.

Testing will be performed incrementally. The `ConfigExpander` will be thoroughly unit-tested before the `StructureGenerator` is even started. Similarly, the `StructureGenerator` will be tested to ensure it correctly populates a test database before it is integrated into the full `Orchestrator` workflow. This layered testing approach ensures that by the time we run the final integration test, we have high confidence in each of the constituent parts.

## 5. Test Strategy

The testing for Cycle 02 is focused on the new components that automate the setup phase of the pipeline and their successful integration into the beginning of the existing workflow. The strategy is to heavily unit-test the heuristic logic and then use integration tests to verify the handoff between the new modules and the existing ones.

**Unit Testing Approach (Min 300 words):**

*   **`ConfigExpander`:** This component, being purely logic-based with no external dependencies, is a prime candidate for thorough unit testing.
    *   A comprehensive test suite will be created with a variety of minimal input dictionaries. These will cover different material classes: a simple covalent material (`{elements: ["Si"]}`), a binary alloy (`{elements: ["Fe", "Pt"]}`), and a molecular system (`{elements: ["H", "O"]}`).
    *   For each input, we will instantiate the `ConfigExpander`, run the `expand()` method, and then perform detailed assertions on the resulting `FullConfig` object. We will assert that the `structure_type` is correctly inferred for each case. We will assert that the `DFTParams` contain physically sensible cutoff energies and pseudopotential names derived from our embedded SSSP data. For example, for FePt, the cutoff should be the maximum of the individual cutoffs for Fe and Pt. We will also test edge cases, such as providing an unknown element, and assert that a specific, user-friendly `ConfigurationError` is raised. Another important test will be verifying the override logic: if a user provides an explicit value in their minimal config (e.g., `degauss: 0.05`), the test must assert that this user-provided value is present in the final `FullConfig`, overriding the heuristic default.
*   **`StructureGenerator`:**
    *   Each private generation method (`_generate_sqs`, `_generate_nms`, etc.) will be tested in isolation. To keep the tests fast and focused, we will mock the external libraries they wrap (e.g., `icet`).
    *   The tests will call the method with a sample `FullConfig` object and assert that the mocked library was called with the correct parameters. They will also assert that the method correctly processes the mocked return value and produces a list of valid `ase.Atoms` objects.
    *   The main `run` method will be tested by mocking the private methods. We will provide different `FullConfig` objects (with different `structure_type` values) and assert that the correct private method is called in each case. This verifies the correctness of the internal dispatching logic.

**Integration Testing Approach (Min 300 words):**

*   **Config Expansion and Structure Generation:** This test will verify that the first two new steps, configuration and generation, work together correctly and can successfully populate a database.
    1.  **Setup:** The test will create a minimal `input.yaml` file on the filesystem and a temporary, empty ASE database.
    2.  **Execution:** It will run a test function that mimics the initial steps of the `Orchestrator`. This function will instantiate the `ConfigExpander` with the path to the minimal config, run the `expand()` method, and then pass the resulting `FullConfig` object to an instance of the `StructureGenerator`.
    3.  **Verification:** The test will first assert that the `FullConfig` object created by the expander is valid and contains the expected heuristically determined parameters. Then, after the `StructureGenerator` has run, the test will connect to the temporary database and assert that it has been populated with a non-zero number of structures, and that all of these new structures have the status 'needs_labelling'. This confirms the two new modules can communicate correctly and produce the expected side effect on the database.
*   **Full Pipeline Test from Minimal Config:** This test will be an end-to-end verification of the new, more autonomous workflow, from minimal input to final trained model.
    1.  **Setup:** The test will create a minimal `input.yaml` for a simple, well-behaved system like Silicon.
    2.  **Execution:** It will invoke the entire pipeline via the main CLI entry point. As in Cycle 01, the actual QE execution within the `LabellingEngine` will be mocked to return pre-computed results instantly, and the MLIP training in the `TrainingEngine` will also be mocked to avoid lengthy computations.
    3.  **Verification:** This test will assert a complete chain of outcomes, validating the integration of all modules:
        *   An `exec_config_dump.yaml` file is created on disk and its content is valid.
        *   The database is populated with new structures by the `StructureGenerator`.
        *   The mocked `LabellingEngine` is called for precisely these new structures.
        *   The database status for these structures is correctly updated from 'needs_labelling' to 'labelled'.
        *   The mocked `TrainingEngine` is called with the complete labelled dataset.
        *   A final dummy `model.ace` file is created.

This final integration test provides high confidence that the system can now perform its primary intended function: going from a minimal chemical description to a trained potential in a single, automated run.
