# Specification: Cycle 1 - Core CLI Pipeline

## 1. Summary

This document provides the detailed technical specification for the first development cycle of the MLIP-AutoPipe project. The primary objective of Cycle 1 is to build and deliver a functional, end-to-end command-line interface (CLI) that can execute the core data generation pipeline. This foundational version will serve as the robust backbone for all future development. At the completion of this cycle, the application will be capable of generating an initial set of atomic structures for a simple binary alloy, performing a basic Molecular Dynamics (MD) simulation to explore new atomic configurations, sampling a subset of these generated structures using a straightforward random selection algorithm, and storing the final, curated results in a structured, queryable ASE (Atomic Simulation Environment) database. This cycle is focused on correctness, architectural soundness, and delivering a tangible, working product, even if its features are initially limited.

This initial cycle is critical as it focuses on establishing the essential architectural framework that will ensure the long-term maintainability and extensibility of the application. Key architectural deliverables include the creation of the main `PipelineOrchestrator`, which will act as the central coordinator for the entire workflow. A fundamental part of this cycle is the rigorous definition of all data structures for configuration using Pydantic. This schema-first approach is a core design principle, providing automatic validation of user inputs and preventing a wide class of common configuration errors. We will also implement the initial, simplified versions of the four key pipeline components: Generation, Exploration, Sampling, and Storage. While this cycle deliberately excludes the more complex features planned for Cycle 2, such as the hybrid MD/MC engine or intelligent Farthest Point Sampling, it will result in a robust and thoroughly testable command-line tool that successfully automates the fundamental data generation workflow.

The implementation will strictly adhere to a modular design, enforcing a clear separation of concerns between the different components. We will define a set of abstract interfaces for our core components, which will allow for future extensibility and simplified testing by enabling dependency injection. For example, the `PipelineOrchestrator` will depend on an `IStructureGenerator` interface, not a concrete `AlloyGenerator` class. This ensures that the advanced features planned for Cycle 2 can be integrated smoothly without requiring major refactoring of the core logic. By the end of this cycle, a developer or a scientific user will be able to write a simple YAML configuration file, execute the pipeline from their terminal, and receive a usable ASE database of atomic structures. This successful end-to-end execution will prove the viability of the core concept and validate the soundness of our chosen architecture, paving the way for the more advanced and scientifically sophisticated features to come.

## 2. System Architecture

The architecture for Cycle 1 is squarely focused on implementing the foundational command-line interface and the core pipeline components in their simplest functional form. The file structure is designed from the ground up to be modular, scalable, and extensible, promoting a clean separation of concerns that will be critical for future development cycles. Every module has a clearly defined role, and the interaction between them is managed through well-defined interfaces.

**File Structure (ASCII Tree):**

Below is the detailed file and directory structure for the `mlip_autopipec` package. The files and directories that are to be created or significantly modified during this cycle are highlighted in **bold**. This structure adheres to modern Python packaging standards.

```
src/
└── **mlip_autopipec/**
    ├── **__init__.py**
    ├── **__main__.py**
    ├── **cli/**
    │   ├── **__init__.py**
    │   └── **main.py**              # CLI application using Typer/Click, handles user input and config loading.
    ├── **common/**
    │   ├── **__init__.py**
    │   └── **pydantic_models.py**   # Defines all configuration schemas for validation.
    ├── **generators/**
    │   ├── **__init__.py**
    │   ├── **base.py**              # Contains the BaseStructureGenerator abstract base class.
    │   └── **alloy.py**             # A concrete implementation for generating alloy structures.
    ├── **explorers/**
    │   ├── **__init__.py**
    │   └── **md_engine.py**         # A basic MD simulation engine using ASE.
    ├── **samplers/**
    │   ├── **__init__.py**
    │   ├── **base.py**              # Contains the BaseSampler abstract base class.
    │   └── **random_sampler.py**    # A simple implementation of a random sampler.
    ├── **storage/**
    │   ├── **__init__.py**
    │   └── **database_manager.py**  # Encapsulates all logic for writing to the ASE database.
    ├── **pipeline/**
    │   ├── **__init__.py**
    │   └── **orchestrator.py**      # The main PipelineOrchestrator class that drives the workflow.
    ├── **factories.py**             # Factory functions for creating component instances based on config.
    └── **interfaces.py**            # Defines abstract interfaces (e.g., IStructureGenerator) for dependency injection.
```

**Code Blueprints:**

*   `cli/main.py`: This file will serve as the primary entry point for the user-facing command-line application. It will be implemented using the `Typer` library for its modern features and automatic help generation. A main command, let's call it `run`, will be defined to accept a single required argument: the path to a Hydra-compatible YAML configuration file. The core responsibility of this module is to parse that configuration file, validate it against the Pydantic models defined in `common/pydantic_models.py`, and then use the factory functions from `factories.py` to instantiate the necessary components. Finally, it will inject these components into a `PipelineOrchestrator` instance and invoke its `run()` method within a `try/except` block to ensure that any exceptions are caught and handled gracefully, presenting a clean error message to the user.

*   `pipeline/orchestrator.py`: The `PipelineOrchestrator` class is the heart of the application's logic. It will be initialized with a validated `FullConfig` Pydantic object and instances of the core components (generator, explorer, etc.) conforming to the defined interfaces. Its main public method, `run()`, will execute the four pipeline stages in a strict sequence, managing the data flow between them. It will first call the generator to create the initial structures, saving them to a known file path. It will then pass this file path to the explorer, which runs the simulations and produces a trajectory file. This trajectory file's path is then passed to the sampler. Finally, the list of sampled `Atoms` objects is passed to the database manager for persistence. The orchestrator will also be responsible for logging progress at each stage and handling the creation of output directories.

*   `generators/alloy.py`: The `AlloyGenerator` will be the first concrete implementation of the `IStructureGenerator` interface. It will be responsible for creating random alloy structures based on the elemental composition and supercell size defined in the configuration. Its `generate` method must implement a clear set of steps: first, create a base lattice using ASE's tools; second, expand this into a larger supercell; third, randomly assign atomic species to the lattice sites according to the specified composition. After creation, it will apply augmentations like a volumetric strain and a random "rattle" to the atomic positions to introduce initial diversity. Critically, it must include a robust `_validate_structure` method that is called for every generated structure. This method's primary job is to perform an `overlap_check` to discard any configurations where atoms are unrealistically close, ensuring the physical validity of the initial dataset.

*   `explorers/md_engine.py`: The `MDEngine` in Cycle 1 will be a simplified but functional implementation. It will be initialized with an MLIP calculator object (e.g., a pre-trained MACE model). Its primary method, `run()`, will take a list of initial `Atoms` objects. For each one, it will execute a standard Molecular Dynamics simulation using one of ASE's dynamics algorithms, such as `VelocityVerlet`. It will support the two basic thermodynamic ensembles: NVT (constant volume and temperature) and NPT (constant pressure and temperature), selectable via the configuration. The engine's main output will be a single, aggregated `.xyz` trajectory file containing all the atomic configurations from all the simulation runs. In this cycle, it will not yet contain the more advanced logic for hybrid MD/MC or automatic ensemble switching.

*   `samplers/random_sampler.py`: The `RandomSampler` will be the first implementation of the `ISampler` interface. Its `sample()` method will be straightforward: it will take the file path to a trajectory file, read all the frames into memory using ASE's I/O tools, and then use Python's built-in `random.sample` function to select a specified number of frames. This list of selected `Atoms` objects will be its return value.

*   `storage/database_manager.py`: The `DatabaseManager` will provide a clean, high-level API for all interactions with the output database, abstracting away the underlying `ase.db` library calls. It will have a `connect()` method to create or open the database file and an `write_atoms()` method. This method will take a list of `Atoms` objects (as returned by the sampler) and iterate through them, writing each one as a new row in the ASE database. It will be responsible for ensuring that all relevant metadata from the `Atoms` object's calculator results (like potential energy, atomic forces, and stresses) is also correctly saved.

## 3. Design Architecture

The design for Cycle 1 is centered around establishing a robust, schema-driven, and decoupled architecture. The principles of dependency inversion and schema-first development are fundamental to ensuring the system is reliable, testable, and, most importantly, extensible from the very outset.

**Pydantic-Based Schema Design:**

The entire configuration of the pipeline, from the definition of the physical system to the parameters for the MD simulation, will be strictly defined by a set of Pydantic models located in `common/pydantic_models.py`. This approach serves as the "single source of truth" for all possible settings and provides several key benefits: automatic, transparent validation of user input; clear and specific error messages for invalid configurations; and a form of self-documentation for the application's parameters.

*   **`FullConfig`**: This will be the top-level Pydantic model that encapsulates the entire user configuration. It will be composed of other, more specific configuration models for each section of the YAML file.
    *   Producers: The primary producer is the Hydra library, which will parse a user-provided YAML file into a dictionary that is then validated by this model.
    *   Consumers: The main consumer is the `cli.main` module, which uses this validated object to configure the pipeline.
    *   Constraints: To ensure robustness, all fields will be required, and the model will be configured with `extra='forbid'` to prevent users from passing unknown or misspelled configuration keys, which is a common source of errors.

*   **`SystemConfig`**: This model will define the physical system to be generated.
    *   Fields: `elements` (a `List[str]` of chemical symbols), `composition` (a `Dict[str, float]` mapping elements to their fractional composition), `supercell_size` (a `List[int]` of 3 integers for the supercell matrix), `num_initial_structures` (an integer that must be greater than 0).
    *   Constraints: A custom Pydantic validator will be implemented to ensure that the sum of the values in the `composition` dictionary is exactly 1.0 (within a small tolerance). Another validator will check that the keys of the composition dict are a subset of the elements list.

*   **`GenerationConfig`**: This model will hold the settings for the structure generation phase.
    *   Fields: `rattle_std_dev` (a float, must be non-negative), `volumetric_strain` (a float), `min_atomic_distance` (a float, must be positive).
    *   Constraints: These fields define the physical parameters for the initial structure perturbation and validation.

*   **`ExplorationConfig`**: This model will contain the settings for the MD simulation.
    *   Fields: `md_calculator` (a `str` specifying the MLIP to use, e.g., 'mace'), `ensemble` (a Python `Enum` with values 'nvt' or 'npt'), `temperature_k` (a float, must be greater than 0), `time_step_fs` (a float, must be greater than 0), `num_steps` (an integer, must be greater than 0).

*   **`SamplingConfig`**: This model will define the settings for the sampling phase.
    *   Fields: `method` (an `Enum` which, in Cycle 1, will only have one member: 'random'), `num_samples` (an integer, must be greater than 0).

*   **Versioning and Extensibility**: This schema is explicitly designed as version 1. Future cycles will extend these models by adding new, optional fields or new members to the enums (e.g., adding 'fps' to the sampling `method` enum). The use of Pydantic makes this extension straightforward and largely backward-compatible.

**Interfaces and Dependency Inversion:**

To create a modular, loosely coupled, and highly testable system, we will make extensive use of abstract base classes (interfaces) and the dependency inversion principle.

*   **`interfaces.py`**: This new file will define the core abstract interfaces for our components using Python's `abc` module.
    *   `IStructureGenerator`: Will define an abstract `generate()` method.
    *   `IExplorer`: Will define an abstract `run()` method.
    *   `ISampler`: Will define an abstract `sample()` method.

*   **`factories.py`**: This module will contain a set of factory functions (e.g., `create_generator`, `create_sampler`). These functions will take the `FullConfig` object as input, inspect the relevant configuration parameters, and return a concrete implementation of the corresponding interface. For example, `create_generator` will look at the system type in the config and return an instance of `AlloyGenerator`.

*   **`pipeline/orchestrator.py`**: The `PipelineOrchestrator` will **not** be allowed to instantiate concrete classes like `AlloyGenerator` directly. Instead, its constructor will accept instances of the interfaces (`IStructureGenerator`, `IExplorer`, etc.). The responsibility of creating the concrete objects and "injecting" them into the orchestrator will belong to the `cli.main` module, which will use the factories. This decoupling is the single most important design choice for testability, as it allows us to easily inject mock implementations of each component when writing unit tests for the orchestrator.

## 4. Implementation Approach

The implementation for Cycle 1 will proceed in a logical, bottom-up fashion. This approach ensures that each layer of the application is built upon a solid, tested foundation, minimizing integration issues.

1.  **Define Pydantic Models**: The very first step is to implement all the configuration models as described in the Design Architecture section (`SystemConfig`, `ExplorationConfig`, etc.) within the `common/pydantic_models.py` file. This includes writing the custom field validators (e.g., for ensuring the composition sums to 1.0). This initial step is crucial as it creates the data "contract" or schema that all subsequent components will be built against. This allows different parts of the system to be developed in parallel with a shared understanding of the data they will receive.

2.  **Implement Interfaces and Factories**: Immediately after defining the models, the next step is to create the abstract base classes (`IStructureGenerator`, `IExplorer`, `ISampler`) in the `interfaces.py` file. These interfaces formalize the contracts for our core components. Concurrently, the initial factory functions (`create_generator`, `create_sampler`) will be implemented in `factories.py`. In Cycle 1, these factories will have simple logic, likely just containing `if/else` statements that return an `AlloyGenerator` or a `RandomSampler`. However, establishing this pattern from the beginning is essential for the modular architecture and will make adding new component types in Cycle 2 trivial.

3.  **Implement Core Components (in parallel)**: With the data schemas and interfaces in place, the core functional components can be developed, potentially in parallel by different developers.
    *   **Generation**: Implement the `AlloyGenerator` class, ensuring it conforms to the `IStructureGenerator` interface. This will involve using the ASE library to build a crystal lattice, create a supercell, and then randomly assign elements based on the composition from the config. The validation logic, especially the `overlap_check`, is a critical part of this step and must be thoroughly unit tested.
    *   **Exploration**: Implement the basic `MDEngine` class. This will involve wrapping ASE's MD capabilities. The code will need to correctly instantiate and attach the specified MLIP calculator to the `Atoms` object and then run the dynamics (e.g., `VelocityVerlet`) for the configured number of steps, writing each frame to an output file.
    *   **Sampling**: Implement the `RandomSampler` class. This is a relatively straightforward component that reads an `.xyz` trajectory file and uses Python's `random.sample` method to select the desired number of frames.
    *   **Storage**: Implement the `DatabaseManager` class. This will encapsulate the `ase.db.connect` logic and provide a clean method to write a list of `Atoms` objects to the database, ensuring all calculator results are preserved.

4.  **Implement the Pipeline Orchestrator**: Once the core components are complete and unit tested, the `PipelineOrchestrator` can be implemented. Its `run` method will be the glue that wires everything together. It will be responsible for creating a dedicated output directory for each run, calling the generator, then passing the output file paths from one component to the next in the correct sequence. It will also add logging statements to provide visibility into the pipeline's progress.

5.  **Implement the CLI**: The final step is to implement the user-facing entry point in `cli/main.py`. This will use Typer to create a simple and user-friendly command. The command will be responsible for loading the configuration file using Hydra, which will automatically validate it against the `FullConfig` Pydantic model. If validation succeeds, it will use the factories to create the pipeline components, inject them into the `PipelineOrchestrator`, and invoke its `run` method, completing the end-to-end workflow.

## 5. Test Strategy

The testing strategy for Cycle 1 is focused on ensuring the correctness and reliability of the core pipeline functionality.

**Unit Testing Approach (Min 300 words):**

Unit tests are essential for verifying that each individual component of the pipeline behaves as expected in isolation. We will use `pytest` as our testing framework and `pytest-mock` for creating mock objects.

*   **Pydantic Models**: The validation logic within our Pydantic models will be tested thoroughly. For example, for the `SystemConfig`, we will write tests that assert that `ValidationError` is raised if the composition dictionary contains elements not in the `elements` list, or if the composition values do not sum to 1.0. We will also test the success path, ensuring valid configurations are parsed correctly.

*   **Generators**: The `AlloyGenerator` will be tested extensively. We will write a test to confirm that calling `generate()` produces the expected number of `Atoms` objects. Another test will verify that the generated structures have the correct elemental composition. A crucial test will be for the `_validate_structure` method: we will manually create an `Atoms` object with overlapping atoms and assert that the validation method correctly identifies it as invalid.

*   **Orchestrator**: The `PipelineOrchestrator` will be tested using mock implementations of the components it depends on. We will inject mock `IStructureGenerator`, `IExplorer`, `ISampler`, and `DatabaseManager` objects. This allows us to test the orchestrator's logic without performing any real computation or file I/O. For example, we can configure the mock generator to return a specific list of dummy `Atoms` objects and then assert that the orchestrator correctly calls the `run` method of the mock explorer with that exact list. This isolates the orchestrator's coordination logic for testing.

*   **Database Manager**: The `DatabaseManager` will be tested by having it write to an in-memory SQLite database or a temporary file on disk. We will create a list of sample `Atoms` objects, call the `write_atoms` method, and then query the database to assert that the correct number of rows were written and that the metadata (e.g., energy) for each row is correct.

**Integration Testing Approach (Min 300 words):**

While unit tests verify components in isolation, integration tests are crucial for ensuring they work together correctly. For Cycle 1, our primary integration test will be an end-to-end test of the CLI application.

*   **End-to-End CLI Test**: We will use the `click.testing.CliRunner` (or a similar tool for Typer) to invoke the CLI from within a pytest test. The test will be set up as follows:
    1.  **Setup**: A temporary directory will be created using `pytest`'s `tmp_path` fixture. A minimal, valid YAML configuration file will be created in this directory. This configuration will be designed for a very small and fast test case (e.g., a 10-atom system, 100 steps of MD).
    2.  **Execution**: The `CliRunner` will be used to invoke the `mlip-autopipec` command, passing the path to the temporary configuration file.
    3.  **Verification**: After the command finishes, the test will inspect the temporary directory to verify that the expected output files were created. It will assert that an `initial_structures.xyz` file exists, a `trajectory.xyz` file exists, and most importantly, the final `output.db` ASE database exists.
    4.  **Database Assertion**: The test will then connect to the generated `output.db` using ASE's database tools. It will perform queries to assert that the database contains the correct number of rows, corresponding to the `num_samples` parameter in the configuration file. It will also check a few rows to ensure that the atomic data and metadata (like energy and forces, which will be dummy values from a mock calculator) are present and have the correct data types.

This integration test provides a comprehensive validation of the entire pipeline, from configuration parsing to final database output, confirming that all the components are correctly wired together and that the data flows through the system as intended.