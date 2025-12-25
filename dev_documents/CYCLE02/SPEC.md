# Cycle 02 Specification: Automated Configuration and Structure Generation

**Version:** 1.0.0
**Status:** Final
**Cycle Goal:** To eliminate the need for manual preparation of input structures by implementing the automated configuration and initial structure generation modules. This cycle makes the pipeline significantly more user-friendly and autonomous.

## 1. Summary

Cycle 02 builds directly upon the foundation laid in Cycle 01, tackling the critical first step of the automated workflow: intelligent data input and generation. The primary goal is to transition the system from a manually-driven tool to a user-friendly, semi-autonomous pipeline. This will be achieved by implementing two key pieces of functionality: the "Two-Tier Configuration" strategy and "Module A: The Structure Generator."

First, we will develop the **Config Expander**, a heuristic engine that embodies the core philosophy of "removing the human from the loop." This component will be responsible for parsing a minimal, user-friendly `input.yaml` file, which contains only the most essential information, such as the chemical formula. The engine will then apply a set of physics-based rules and material science heuristics to automatically deduce the system's characteristics. It will determine the bonding type (alloy, molecular, ionic, or covalent) and use this classification to make intelligent decisions about all other necessary parameters. It will generate a complete, verbose, and reproducible `exec_config_dump.yaml` file, specifying everything from DFT parameters (based on the SSSP protocol) to the appropriate structure generation algorithm.

Second, we will implement **Module A: Structure Generator**. This module acts as a factory for creating diverse and physically meaningful initial atomic configurations without the need for expensive simulations. Guided by the bond type determined by the Config Expander, it will select and execute the most suitable generation algorithm. For metallic alloys, it will generate Special Quasirandom Structures (SQS) to model chemical disorder. For isolated molecules, it will use Normal Mode Sampling (NMS) to explore the vibrational phase space. For ionic systems, it will employ an Ab Initio Random Structure Searching (AIRSS)-like approach to find stable and metastable polymorphs. This module ensures that the initial dataset is not just a random collection of atoms but a physically relevant starting point for training the MLIP. Upon completion of this cycle, a user will be able to initiate the entire MLIP creation process simply by providing a chemical formula, marking a major step towards a fully automated pipeline.

## 2. System Architecture

The architecture in Cycle 02 introduces two new major components—the Config Expander and Module A—at the very beginning of the existing pipeline. The Orchestrator's logic will be updated to incorporate these new stages.

**Component Breakdown:**

*   **Config Expander (`config/expander.py`):** This new component acts as the brain of the initial setup. It will contain the logic to parse the minimal `input.yaml`.
    *   **Bond Type Heuristics:** It will use libraries like `pymatgen` to analyze the electronegativity and known properties of the constituent elements to classify the system into one of four categories: Alloy, Molecule, Ionic, Covalent. This classification is the critical decision point that guides subsequent choices.
    *   **Parameter Generation:** Based on the bond type, it will populate a Pydantic `FullConfig` model. This includes selecting the right algorithm for Module A, setting appropriate DFT parameters (e.g., enabling spin polarization for magnetic elements like Iron), and defining default simulation parameters for later cycles.
    *   **Output:** Its primary output is the fully specified `exec_config_dump.yaml`, which will be saved to disk for reproducibility and used to drive the rest of the workflow.

*   **Module A: Structure Generator (`modules/a_structure_generator.py`):** This module will be designed as a factory. The Orchestrator will query it with the algorithm name specified in the `FullConfig`.
    *   **`StructureGeneratorFactory`:** A central function or class that, given a name (e.g., "SQS"), returns an instance of the corresponding generator class.
    *   **`SQSGenerator`:** A class dedicated to generating SQS configurations. It will likely use an external, well-tested tool like `icet` or `mcsqs` from the `ATAT` package, wrapped in a Python subprocess call. It will generate not just the ideal stoichiometry but also apply various strains and create off-stoichiometry configurations to enrich the dataset.
    *   **`NMSGenerator`:** A class for performing Normal Mode Sampling. It will take a reference molecular structure, compute its Hessian matrix (potentially using a low-cost calculator), and generate a set of distorted structures by displacing atoms along the calculated normal modes.
    *   **`AIRSSGenerator`:** A class that implements a simplified version of Ab Initio Random Structure Searching. It will generate random positions for atoms within a simulation cell, subject to constraints like minimum interatomic distances, to create a variety of plausible crystal structures.

*   **Orchestrator (`orchestrator.py`):** The orchestrator's `run` method will be updated with the new preamble:
    1.  Load `input.yaml`.
    2.  Instantiate and run `ConfigExpander` to generate `exec_config_dump.yaml`.
    3.  Load the `FullConfig`.
    4.  Instantiate `StructureGeneratorFactory` with the algorithm specified in the config.
    5.  Call the generator's `generate()` method to create the initial list of ASE `Atoms` objects.
    6.  Proceed with the Cycle 01 workflow: pass the generated structures to the Labelling Engine and then the Training Engine.

The data flow is now extended: `input.yaml` -> `ConfigExpander` -> `exec_config_dump.yaml` -> `Orchestrator` -> `Module A` -> `List[Atoms]` -> `Module C` -> `Module D`.

## 3. Design Architecture

The design focuses on creating a clear separation between the configuration logic and the scientific generation algorithms, and making the latter easily extensible.

**Key Classes and APIs:**

*   **`mlip_pipe.config.expander.ConfigExpander`**
    *   `expand_config(self, min_config_path: str) -> FullConfig`: Takes the path to `input.yaml`, parses it, applies heuristics, and returns a validated Pydantic `FullConfig` object.
    *   `_determine_bond_type(self, elements: list[str]) -> str`: Internal method that contains the logic for classifying the system.
    *   `_populate_dft_params(self, elements: list[str]) -> DFTConfig`: Internal method to select DFT parameters based on SSSP and element properties.

*   **`mlip_pipe.data_models.MinimalConfig` & `FullConfig`**
    *   The Pydantic data models will be expanded. `MinimalConfig` will only have a few fields. `FullConfig` will be extended to include a new section for structure generation, e.g., `generation: { "algorithm": "SQS", "parameters": {...} }`.

*   **`mlip_pipe.modules.a_structure_generator.StructureGenerator` (Abstract Base Class)**
    *   An abstract base class with a single method: `generate(self, config) -> list[ase.Atoms]`. All specific generators will inherit from this, ensuring a consistent interface.

*   **`mlip_pipe.modules.a_structure_generator.SQSGenerator(StructureGenerator)`**
    *   `generate(self, config)`: Implements the generation of SQS structures. It will parse the relevant configuration, construct a command-line call to an external SQS code, execute it, and parse the output files to create a list of ASE `Atoms` objects.

*   **`mlip_pipe.modules.a_structure_generator.NMSGenerator(StructureGenerator)`**
    *   `generate(self, config)`: Implements Normal Mode Sampling. It requires a reference structure and will contain the logic for calculating and applying displacements along normal modes.

*   **`mlip_pipe.modules.a_structure_generator.GeneratorFactory`**
    *   `get_generator(name: str) -> StructureGenerator`: A simple factory function that takes the algorithm name from the config and returns an instance of the corresponding concrete generator class.

## 4. Implementation Approach

The implementation will be staged to build the new functionality before integrating it into the main pipeline.

1.  **Data Models:** First, update the Pydantic models in `data_models.py`. Define the schemas for `MinimalConfig` and add the new `generation` section to `FullConfig`.

2.  **Config Expander:**
    *   Start by implementing the `_determine_bond_type` heuristic. This will involve using `pymatgen` or a similar library. Write extensive unit tests for this classification logic, covering clear-cut cases (e.g., NaCl is ionic, FePt is an alloy, H2O is molecular) and edge cases.
    *   Implement the main `expand_config` method. Write unit tests that provide a `MinimalConfig` and assert that the returned `FullConfig` object is populated with the correct, expected values for all fields. For example, for a Fe-containing system, `dft_config.magnetism` should be set to "ferromagnetic".

3.  **Structure Generators:**
    *   Implement each generator class (`SQSGenerator`, `NMSGenerator`, etc.) one at a time.
    *   For generators that wrap external tools (like `SQSGenerator`), the implementation will focus on correct command-line argument construction and robust output parsing. The unit tests for this class will mock the `subprocess.run` call and provide sample output files to test the parser.
    *   For generators with internal logic (like `NMSGenerator`), the unit tests will verify the correctness of the physical calculations (e.g., ensuring the generated displacement vectors are orthogonal).

4.  **Factory and Orchestrator Integration:**
    *   Implement the simple `GeneratorFactory`.
    *   Modify the `Orchestrator` to call the `ConfigExpander` at the beginning of its run.
    *   Add the logic to the `Orchestrator` to use the factory to get the correct generator and then call its `generate()` method.
    *   The output of the `generate()` method (the list of `Atoms` objects) will then be fed into the existing labelling and training workflow from Cycle 01.

5.  **End-to-End Integration Test:** Create a new integration test that starts from a minimal `input.yaml` (e.g., for FePt). The test will run the entire, extended pipeline: `ConfigExpander` -> `SQSGenerator` -> `QuantumEspressoRunner` -> `Trainer`. The test will assert that a final potential file is created and that no errors occurred during the process. This validates that all new and old components work together seamlessly.

## 5. Test Strategy

Testing for Cycle 02 is focused on the correctness of the heuristic logic and the output of the various generation algorithms.

**Unit Testing Approach (Min 300 words):**
Unit tests will be critical for verifying the complex logic of the new components.

*   **`TestConfigExpander`:** This will be the most important test suite. We will create a series of test cases with different `input.yaml` contents.
    *   **Alloy Test:** Input `{"elements": ["Fe", "Pt"]}`. Assert that the returned `FullConfig` has `generation.algorithm == "SQS"` and `dft.magnetism` is enabled.
    *   **Molecule Test:** Input `{"elements": ["H", "O"]}`. Assert `generation.algorithm == "NMS"`.
    *   **Ionic Test:** Input `{"elements": ["Na", "Cl"]}`. Assert `generation.algorithm == "AIRSS"`.
    *   **Error Test:** Input an invalid element symbol. Assert that a `ValidationError` is raised.
    Each test will check not just the high-level algorithm selection but also the low-level parameter defaults to ensure they are sensible.

*   **`TestGenerators`:** Each generator will have its own test file.
    *   **`TestSQSGenerator`:** We will mock the subprocess call to the external SQS code. We will provide sample text output from a successful SQS run and assert that our Python parser correctly converts it into a list of ASE `Atoms` objects with the right compositions and structures.
    *   **`TestNMSGenerator`:** We will provide a simple molecule (e.g., H2O) and a pre-computed Hessian matrix. The test will run the `generate` method and assert that the returned structures have been displaced from the original geometry and that the number of generated structures is correct.
    *   **`TestAIRSSGenerator`:** This test will verify that the generated structures have the correct density and that atoms are not placed too close to each other, respecting the minimum distance constraints.

**Integration Testing Approach (Min 300 words):**
The primary integration test will validate the new, fully automated workflow from the user's starting point (`input.yaml`).

*   **`test_full_pipeline_from_minimal_config`:**
    1.  **Setup:** Create a temporary directory containing a minimal `input.yaml` for a simple binary alloy like AlNi.
    2.  **Execution:** Run the main orchestrator, pointing it to this `input.yaml`.
    3.  **Process:** The test will execute the entire pipeline:
        *   `ConfigExpander` should run and produce a `exec_config_dump.yaml`.
        *   `SQSGenerator` should be selected and run, producing a set of AlNi structures.
        *   `QuantumEspressoRunner` should label these structures (using a real QE call for this integration test).
        *   `Trainer` should train an MLIP on this DFT data.
    4.  **Assertions:**
        *   Assert that the `exec_config_dump.yaml` file exists and contains the expected configuration (e.g., SQS algorithm).
        *   Assert that the ASE database is created and populated with multiple labelled AlNi structures.
        *   Assert that the final MLIP file is created.
        *   Assert that the entire process completes with an exit code of 0.

This single, comprehensive test ensures that the data contracts between the new components (`ConfigExpander`, `Module A`) and the existing components (`Module C`, `Module D`) are correct and that the enhanced orchestrator logic works as designed. It provides a high level of confidence in the system's newfound autonomy.