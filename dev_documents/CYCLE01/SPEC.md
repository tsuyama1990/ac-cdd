# Cycle 01 Specification: The Core Engine (Foundation)

**Version:** 1.0.0
**Status:** Final
**Cycle Goal:** To establish the project's foundational architecture and implement the minimum viable pipeline: the ability to take a predefined set of atomic structures, label them using an automated DFT engine, and train a basic Machine Learning Interatomic Potential (MLIP).

## 1. Summary

Cycle 01 lays the critical groundwork for the entire MLIP-AutoPipe project. The primary objective of this cycle is to construct the backbone of the pipeline, focusing on the two most fundamental components: the automated DFT labelling engine and the MLIP training engine. This cycle intentionally omits the complexities of automated structure generation and active learning to concentrate on creating a robust, reliable, and verifiable core. We will establish the modern Python project structure using `pyproject.toml` and the `uv` toolchain, which will ensure a reproducible and high-performance development environment from day one.

The core deliverable for this cycle is a linear, manually-driven workflow. A developer will be able to provide a directory of atomic structures in a standard format (e.g., CIF files). The system will then process each of these files, invoking an external Quantum Espresso (QE) engine to perform single-point DFT calculations. The implementation will abstract away the complexities of this process, automatically generating the correct QE input files, executing the calculation, parsing the resulting output files to extract the essential labels (energy, forces, stresses), and storing these labelled structures in a persistent ASE database.

Following the labelling stage, the system will feed this newly created dataset into the training engine. This engine will be responsible for training a modern MLIP, such as one based on the Atomic Cluster Expansion (ACE) or MACE framework. A key feature to be implemented from the outset is the "Delta Learning" strategy. This technique involves training the model to predict the residual between the high-accuracy DFT results and a lower-fidelity but physically sound baseline potential (like the Ziegler-Biersack-Littmark potential for repulsive interactions). This ensures that the resulting MLIP behaves physically reasonably even in regions where training data is sparse, preventing catastrophic failures like atomic collapse. By the end of this cycle, we will have a functional, albeit not yet autonomous, pipeline that proves the viability of our core components and provides a solid foundation upon which all future automation will be built.

## 2. System Architecture

The architecture for Cycle 01 is a simplified, linear subset of the final system architecture. It consists of a central orchestrator that directs data flow between the Labelling Engine, the ASE Database, and the Training Engine. User interaction is manual at this stage, limited to providing the initial, unlabelled structures.

**Component Breakdown:**

*   **Project Structure:** The project will be set up as a standard Python package. All source code will reside in `src/mlip_pipe/`. Dependencies, project metadata, and scripts will be managed via a central `pyproject.toml` file. The `uv` tool will be used for all environment and package management tasks, ensuring speed and consistency.
*   **Orchestrator (`orchestrator.py`):** A primary `Orchestrator` class will be created to manage the sequence of operations. For this cycle, its logic will be straightforward:
    1.  Accept a path to a directory of input structures.
    2.  Iterate through each structure.
    3.  For each structure, invoke the Labelling Engine.
    4.  Store the returned, labelled structure in the ASE Database.
    5.  Once all structures are processed, retrieve the complete dataset from the database.
    6.  Invoke the Training Engine with this dataset.
    7.  Save the resulting trained potential to a specified output file.
*   **ASE Database Utility (`utils/ase_db.py`):** A dedicated utility module will provide a simple, high-level interface for interacting with an ASE (Atomic Simulation Environment) database, which will likely be a simple SQLite file for this cycle. It will provide methods like `connect(db_path)`, `write_atoms(atoms_object)`, and `get_all_atoms()`. This abstracts the database logic and ensures data is stored in a structured, queryable format.
*   **Module C: Labelling Engine (`modules/c_labelling_engine.py`):** This is a cornerstone of the cycle. The `QuantumEspressoRunner` class will encapsulate all logic for interacting with QE. It will not execute QE directly but will generate the command-line arguments to run it as a subprocess. Its key responsibility is the dynamic generation of QE input files based on an incoming ASE `Atoms` object. It will automatically determine atomic species, positions, and cell parameters. Crucially, it will implement a robust parameter selection scheme based on the SSSP (Standard Solid State Pseudopotentials) protocol, which will allow it to automatically choose appropriate pseudopotentials and plane-wave cutoff energies. After execution, it must be capable of parsing the plain-text QE output to find and extract the final total energy, the forces on each atom, and the stress tensor, attaching this information to the original `Atoms` object before returning it.
*   **Module D: Training Engine (`modules/d_training_engine.py`):** This module will house the `Trainer` class. It will be initialized with the configuration for a specific MLIP framework (e.g., MACE). Its main method, `train(dataset)`, will take the list of labelled ASE `Atoms` objects from the database. It will perform the necessary data preparation and then use the underlying framework's library to fit the potential. The implementation of Delta Learning is a critical part of this module. It will require adding a step that pre-calculates the energy of each structure using a simple, hard-coded baseline potential (e.g., ZBL) and then subtracting this from the DFT target energy before passing the data to the training algorithm.

## 3. Design Architecture

This cycle focuses on establishing clean interfaces and robust, single-responsibility classes that can be extended in future cycles.

**Key Classes and APIs:**

*   **`mlip_pipe.orchestrator.Orchestrator`**
    *   `__init__(self, config)`: Initializes with a configuration object that specifies paths and parameters.
    *   `run_labelling_and_training(self, input_dir: str, output_potential: str)`: The main entry point for the Cycle 01 workflow. It orchestrates the entire process from reading files to saving the final potential.

*   **`mlip_pipe.utils.ase_db.DatabaseManager`**
    *   `__init__(self, db_path: str)`: Connects to the SQLite database file.
    *   `write(self, atoms: ase.Atoms)`: Writes a single ASE Atoms object to the database, ensuring that the calculated energy, forces, and stress are included as attached properties.
    *   `get_dataset(self) -> list[ase.Atoms]`: Retrieves all Atoms objects from the database, effectively creating the training set.

*   **`mlip_pipe.modules.c_labelling_engine.QuantumEspressoRunner`**
    *   `__init__(self, config)`: Takes a configuration specifying the path to the `pw.x` executable and other DFT parameters.
    *   `label_structure(self, atoms: ase.Atoms) -> ase.Atoms`:
        1.  **Input:** An ASE `Atoms` object containing atomic configuration.
        2.  **Process:**
            *   Generates a QE input file (`.in`) in a temporary directory. This includes automatically setting cards like `ATOMIC_SPECIES`, `ATOMIC_POSITIONS`, and `CELL_PARAMETERS`.
            *   Uses the SSSP protocol logic to select pseudopotentials and determine `ecutwfc` and `ecutrho`.
            *   Constructs and executes the `pw.x` command as a subprocess.
            *   Monitors the subprocess for completion or errors.
            *   Parses the QE output file (`.out`) to find the `!` final energy, the `Forces` block, and the `stress` tensor.
        3.  **Output:** Returns the original `Atoms` object with the `energy`, `forces`, and `stress` arrays attached to its `calc` results dictionary.

*   **`mlip_pipe.modules.d_training_engine.Trainer`**
    *   `__init__(self, config)`: Takes a configuration specifying the MLIP framework (e.g., 'MACE') and its hyperparameters.
    *   `train(self, dataset: list[ase.Atoms])`:
        1.  **Input:** A list of DFT-labelled ASE `Atoms` objects.
        2.  **Process:**
            *   For each `Atoms` object in the dataset, it calculates the energy using a baseline reference potential (e.g., ZBL).
            *   It computes the target energy for the MLIP as `delta_energy = dft_energy - baseline_energy`.
            *   It prepares the data in the format expected by the chosen MLIP framework.
            *   It calls the fitting function from the MLIP library.
            *   It saves the trained model to a file.
        3.  **Output:** Returns the file path to the saved potential.

## 4. Implementation Approach

The implementation will proceed in a logical, bottom-up fashion, starting with the lowest-level utilities and building up to the final orchestrator.

1.  **Project Setup:** Initialize the project using `uv`. Create the `pyproject.toml` file, defining initial dependencies such as `ase`, `numpy`, and a chosen MLIP library (e.g., `mace-torch`). Set up the basic directory structure (`src/mlip_pipe`, `tests`, etc.).

2.  **ASE Database Utility:** Implement the `DatabaseManager` class first. This is a simple but critical component that other parts of the system will depend on. Write unit tests to verify that it can create a database, write Atoms objects (with and without calculator results), and read them back correctly.

3.  **Quantum Espresso Wrapper:** This is the most complex part of the cycle.
    *   Begin by focusing on input file generation. Write a function that takes an `Atoms` object and produces a valid, well-formatted QE input string. This should be tested independently.
    *   Implement the SSSP logic. This might involve creating a simple data structure (like a dictionary) that maps elements to their recommended pseudopotential file names and cutoff energies.
    *   Implement the output parsing logic. Create functions that can robustly parse a sample QE output file to find the specific markers for energy, forces, and stress, and handle potential variations in formatting.
    *   Combine these pieces into the `QuantumEspressoRunner` class. The `label_structure` method will call these internal functions in sequence. Mock the actual `subprocess.run` call during unit testing to avoid dependency on a real QE installation.

4.  **Training Engine:**
    *   Implement the `Trainer` class.
    *   First, implement the baseline potential calculation. This could be a simple function that takes an `Atoms` object and returns a ZBL energy.
    *   Implement the main `train` method. The initial version can simply pass the data to the MLIP library without the delta learning.
    *   Add the delta learning logic by integrating the baseline potential calculation into the `train` method. Unit tests should verify that the target energies are being correctly modified before training.

5.  **Orchestrator:** Finally, implement the `Orchestrator` class. Its implementation will be relatively straightforward as it will mostly involve creating instances of the other classes and calling their methods in the correct order.

6.  **Integration Testing:** Once all components are built, write an integration test that uses a real, simple structure (e.g., Si dimer) and a real (but fast) QE calculation to verify the entire workflow from start to finish. This test will be slow and will be marked as such, but it is essential for verifying that the components work together correctly.

## 5. Test Strategy

Testing in Cycle 01 is focused on ensuring the correctness and reliability of the core data processing components.

**Unit Testing Approach (Min 300 words):**
Unit tests will form the backbone of our quality assurance. Each class will have a corresponding test file (e.g., `test_orchestrator.py`). We will use `pytest` as our test runner and `pytest-mock` to isolate components.

*   **`TestQuantumEspressoRunner`:** The `subprocess.run` call to `pw.x` will be mocked. We will provide a mock `Atoms` object and assert that the generated QE input file string is exactly correct. We will also test the parser by feeding it a static, pre-saved QE output file and asserting that it extracts the correct floating-point values for energy, forces, and stress. We will test edge cases, such as systems with and without lattice vectors (molecules vs. crystals) and systems containing different element types, ensuring the SSSP protocol selects the correct parameters. Error handling will also be tested: what happens if the QE output file does not contain the final energy? The parser should raise an appropriate exception.

*   **`TestTrainer`:** The `Trainer` will be tested without actually training a model, which would be too slow. We will mock the underlying MLIP library's `fit()` function. The tests will focus on data preparation. We will provide a sample dataset and assert that the `train` method correctly calculates the delta energies by comparing them to pre-calculated values. We will verify that the data is transformed into the precise format expected by the mocked `fit()` function.

*   **`TestDatabaseManager`:** These tests will interact with a real, temporary SQLite database file. We will test the full lifecycle: creating a database, writing several `Atoms` objects with different properties, and then reading them all back to ensure the data is identical. We will verify that calculator results (energy, forces) are correctly serialized and deserialized.

**Integration Testing Approach (Min 300 words):**
While unit tests verify components in isolation, integration tests ensure they communicate correctly. For Cycle 01, one primary integration test is required, which we can call `test_full_pipeline_si_dimer`.

This test will be a complete, end-to-end run of the pipeline on a minimal, physically simple system: a two-atom silicon dimer. This test will *not* use mocks for Quantum Espresso. It will require a real `pw.x` executable to be in the system's PATH.

The test will perform the following steps:
1.  Programmatically create an ASE `Atoms` object for the Si dimer.
2.  Instantiate the `Orchestrator`.
3.  Call the main orchestrator method, pointing it to the Si dimer object.
4.  The orchestrator will invoke the `QuantumEspressoRunner`, which will generate a real input file and execute a real `pw.x` calculation. Since the system is tiny, this will be fast (a few seconds).
5.  The runner will parse the output and return the labelled `Atoms` object.
6.  The orchestrator will save this object to a temporary database.
7.  The orchestrator will then invoke the `Trainer`. For the integration test, the training itself can be mocked or configured to run for only a single epoch to ensure the data is passed correctly without spending significant time.
8.  The test will assert that the final potential file is created. More importantly, it will query the database and assert that the energy and forces read from the database for the Si dimer are physically reasonable and close to expected values.

This test provides an invaluable guarantee that the data contracts between the different components are solid and that the system works in a real-world environment. It will be marked as a "slow" test and may be run less frequently than the unit tests.