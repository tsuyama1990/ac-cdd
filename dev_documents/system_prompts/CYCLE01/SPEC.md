# Specification: MLIP Structure Generator - CYCLE01

## 1. Summary

This document provides the detailed technical specification for the first development cycle (CYCLE01) of the MLIP Structure Generator. The primary objective of this cycle is to deliver a robust, command-line-driven application that implements the core, end-to-end pipeline for generating foundational training datasets. This initial version will serve as a powerful tool for expert users in the computational materials science community and will establish a stable, validated, and extensible architecture upon which more advanced features, such as a graphical user interface and more sophisticated simulation techniques, can be built in subsequent cycles. The scope of CYCLE01 is intentionally focused on delivering a minimum viable product (MVP) that is both functional and reliable, capable of handling common, scientifically relevant use cases from day one. We are prioritizing correctness, stability, and a powerful command-line interface to ensure the tool is immediately useful for research purposes.

The core of this cycle revolves around the implementation of the `PipelineRunner`, the central orchestrator that manages the flow of data through four distinct, sequential stages: Generation, Exploration, Sampling, and Storage. This modular design is a key architectural choice, promoting separation of concerns and testability. For the Generation stage, we will implement generators for two fundamental and widely-used material types: multi-component alloys (e.g., CuAu, NiTi) and simple covalent structures (e.g., silicon, diamond). These generators will be supported by a crucial set of physics-based validation routines to ensure that all generated structures are physically plausible from the outset. This includes checks to prevent atoms from overlapping to an unphysical degree and logic to automatically create a sufficiently large "supercell" to avoid periodic self-interaction artifacts, which are common pitfalls in molecular simulations.

For the Exploration stage, the focus is on creating a standard, yet powerful, Molecular Dynamics (MD) engine. This engine will be capable of running simulations in both the canonical (NVT, constant volume) and isothermal-isobaric (NPT, constant pressure) ensembles, providing the necessary thermodynamic controls for basic materials simulations like annealing or equilibration. A key architectural feature to be implemented is the robust parallel execution of these simulations using Python's `ProcessPoolExecutor`. This design will incorporate a "late binding" strategy for the MLIP calculator, a critical optimization that avoids the need to serialize and transfer large ML models between processes. The engine will also feature sophisticated error handling to ensure that the inevitable failure of a single simulation (due to high temperature instabilities) does not jeopardise a large-scale, multi-day computational job.

Finally, the Sampling and Storage stages will be implemented with straightforward, effective solutions perfectly suited for this initial cycle. A random sampling algorithm will be used to select a representative subset of structures from the vast number generated during exploration. While simple, this provides a solid baseline for dataset creation. The selected structures, along with their essential metadata (potential energy, configuration parameters), will then be stored in a standard ASE (Atomic Simulation Environment) database, which is backed by SQLite. This choice of output format ensures immediate interoperability with the vast ecosystem of existing tools in the materials science community. The entire system will be configurable via YAML files parsed by the powerful Hydra framework, and a clean command-line interface (CLI) will serve as the primary user interaction point. By the end of this cycle, a user will be able to define a simple alloy, run the generation pipeline from the command line, and receive a high-quality, ready-to-use training dataset suitable for training a state-of-the-art MLIP.

## 2. System Architecture

The architecture for CYCLE01 is designed to be a modular and scalable foundation for the entire project. It focuses on implementing the essential components of the pipeline, with clear separation of concerns to facilitate testing, maintenance, and future expansion. The design strictly follows object-oriented principles, using abstract base classes to define clear interfaces for key components like generators and samplers. This ensures that the system can be easily extended in the future without requiring significant refactoring of the core pipeline logic. The file structure is organized logically to reflect this modular design, making the codebase easy for new developers to navigate.

**File Structure for CYCLE01:**
The following file structure will be created. Files to be implemented in this cycle are marked in **bold**. This structure separates configuration, source code, and entry points, which is a standard best practice.

```
nnp-structure-generator/
├── configs/                  # Directory for all Hydra configuration files
│   ├── system/               # Configs defining the material system
│   │   ├── **alloy.yaml**
│   │   └── **covalent.yaml**
│   ├── exploration/          # Configs defining the simulation parameters
│   │   └── **default.yaml**
│   └── **main_config.yaml**    # Top-level Hydra configuration file
├── src/
│   └── nnp_gen/
│       ├── **__init__.py**
│       ├── generators/         # Module for Stage 1: Structure Generation
│       │   ├── **__init__.py**
│       │   ├── **base.py**        # Abstract base class and core validation logic
│       │   ├── **alloy.py**       # Concrete generator for alloy systems
│       │   └── **covalent.py**    # Concrete generator for covalent systems
│       ├── explorers/          # Module for Stage 2: Simulation Exploration
│       │   ├── **__init__.py**
│       │   └── **md_engine.py**   # Core MD simulation engine and parallel runner
│       ├── samplers/           # Module for Stage 3: Data Sampling
│       │   ├── **__init__.py**
│       │   ├── **base.py**        # Abstract base class for samplers
│       │   └── **random.py**      # Simple random sampler implementation
│       ├── storage/            # Module for Stage 4: Data Storage
│       │   ├── **__init__.py**
│       │   └── **db_writer.py**   # Logic to write to the ASE database
│       ├── pipeline/           # Module for the main pipeline orchestration
│       │   ├── **__init__.py**
│       │   └── **runner.py**      # The main PipelineRunner class
│       ├── common/             # Package for shared code and data models
│       │   ├── **__init__.py**
│       │   ├── **physics.py**     # Core physics validation functions
│       │   └── **schemas.py**     # Pydantic configuration schemas
│       └── utils/              # General utility functions
│           └── **__init__.py**
├── **main.py**                   # CLI entry point using Hydra and Click
└── **pyproject.toml**            # Project dependencies and tool configuration
```

**Component Breakdown:**
This section provides a detailed blueprint of the key classes and modules to be implemented in this cycle.

*   **`main.py`**: This is the main entry point for the application. It will be a simple script that uses the Hydra library's `@hydra.main` decorator to handle the parsing of command-line arguments and configuration files. Its primary responsibility is to instantiate the `PipelineRunner` with the generated configuration object and then call the main `run()` method to start the entire workflow.

*   **`pipeline/runner.py` -> `PipelineRunner`**: This class is the heart of the application, acting as the central orchestrator. Its `run` method will execute the four stages in the correct order:
    1.  Initialize the appropriate generator (e.g., `AlloyGenerator`) based on the configuration. This is a factory pattern.
    2.  Call the generator's `generate()` method to create the initial seed structures and save them to a temporary file.
    3.  Set up the `ProcessPoolExecutor` for parallel execution and dispatch the `run_single_md_process` function as a separate job for each seed structure. This is the main computational step.
    4.  Once all exploration jobs are complete, it will gather the paths to the trajectory files.
    5.  Initialize the `RandomSampler`.
    6.  Call the sampler's `sample()` method to select a subset of structures.
    7.  Initialize the database writer and call its `write()` method to save the final structures to the specified database file.

*   **`generators/base.py` -> `BaseGenerator`**: This abstract class will define the public interface for all generators using Python's `abc` module. It will contain the concrete implementations of the crucial, shared validation methods:
    *   `_check_overlap(atoms, threshold)`: Iterates through all pairs of atoms to ensure their distance is above a minimum threshold. It will raise a custom `PhysicsViolationError` if the check fails, providing a clear error message.
    *   `_ensure_supercell_size(atoms, cutoff)`: Checks the periodic boundary condition vectors to ensure the cell is larger than the potential cutoff in all three dimensions, automatically creating a supercell (e.g., a 2x2x2 replication) if necessary.
    *   `apply_rattle(atoms, stdev)`: Applies a small Gaussian noise to the atomic positions to break perfect symmetry, which is often important for starting MD simulations.
    This class will have an abstract method `generate(self) -> List[Atoms]` that must be implemented by all concrete generator subclasses.

*   **`generators/alloy.py` -> `AlloyGenerator`**: A concrete implementation of `BaseGenerator`. It will be initialized with parameters like the list of elements, their desired composition ratios, and a base lattice structure (e.g., 'fcc', 'bcc'). It will use ASE's standard structure generation utilities to create the initial crystal structure and then implement the logic to randomly substitute atoms to achieve the desired stochastic composition. It will then rigorously apply all the validation methods from its parent class.

*   **`explorers/md_engine.py` -> `MDEngine` and `run_single_md_process`**: This file contains the most critical and computationally intensive logic for this cycle.
    *   **`run_single_md_process`**: This is a top-level function, not a class method, designed specifically to be the target for the `ProcessPoolExecutor`. Its role is to:
        1.  Receive a single ASE `Atoms` object and the exploration configuration as arguments.
        2.  Instantiate the MLIP calculator (e.g., MACE) **inside the worker process**. This "late binding" is the key to performance and stability, as it avoids the need to pickle and transfer the large, complex PyTorch model from the main process.
        3.  Instantiate the `MDEngine` class.
        4.  Wrap the call to the engine's `run` method in a robust `try...except` block to gracefully handle simulation crashes (e.g., from atoms moving too fast). If a `PhysicsViolationError` occurs, it will dump the problematic structure to a file for later analysis and return `None` instead of crashing the whole pool.
    *   **`MDEngine`**: This class encapsulates the logic for a single simulation run. Its `run` method will:
        1.  Take an `Atoms` object and attach the newly instantiated calculator.
        2.  Based on the configuration, set up the appropriate ASE dynamics object (e.g., `Langevin` for NVT, `Berendsen` for NPT).
        3.  Attach a trajectory logger (`ase.io.Trajectory`) to save the state of the simulation at regular intervals.
        4.  Run the dynamics for the specified number of steps.

*   **`samplers/random.py` -> `RandomSampler`**: This class will implement a simple but effective sampling strategy. It will be initialized with a list of trajectory files. Its `sample` method will read all the structures from these files into memory, then use Python's `random.sample` function to select a specified number of structures to be included in the final dataset.

*   **`storage/db_writer.py`**: This module will contain a simple function that takes a list of `Atoms` objects and a destination path. It will use ASE's `ase.db.connect` function to create or open a SQLite database and then iterate through the list of structures, writing each one, along with key metadata (e.g., potential energy, temperature, pressure), into the database.

## 3. Design Architecture

This cycle's design architecture is centered on creating a robust and type-safe system using Pydantic-based schemas for configuration. This is a modern and highly effective approach that ensures all inputs to the system are validated upfront, preventing a large class of runtime errors that arise from simple misconfigurations. This design promotes the concept of "data contracts" between different components of the pipeline, making the system as a whole more reliable and easier to debug. By defining the structure of our configuration explicitly, we also make the system easier to understand for new users and developers, as the schemas serve as a form of documentation.

**Pydantic-based Configuration Schemas:**
We will define a set of Pydantic models that map directly to our Hydra YAML configuration files. This provides several key benefits: auto-completion in IDEs, static analysis from tools like MyPy, and, most importantly, runtime validation with user-friendly error messages.

```python
# In a new file, src/nnp_gen/common/schemas.py

from pydantic import BaseModel, Field, model_validator
from typing import List, Dict, Literal, Union

class BaseGeneratorConfig(BaseModel):
    """Base model for all generator configurations."""
    rattle_stdev: float = Field(0.01, ge=0, description="Standard deviation for atomic position rattle.")

class AlloyGeneratorConfig(BaseGeneratorConfig):
    name: Literal["alloy"] = "alloy"
    elements: List[str] = Field(..., min_length=2, description="List of element symbols for the alloy.")
    composition: Dict[str, float] = Field(..., description="Dictionary mapping elements to their fractional composition.")
    lattice_constant: float = Field(..., gt=0, description="Lattice constant in Angstroms.")
    crystal_structure: Literal["fcc", "bcc"] = "fcc"

    @model_validator(mode='after')
    def check_composition(self):
        if set(self.elements) != set(self.composition.keys()):
            raise ValueError("Elements and composition keys must match.")
        if abs(sum(self.composition.values()) - 1.0) > 1e-6:
            raise ValueError("Composition values must sum to 1.0.")
        return self

class CovalentGeneratorConfig(BaseGeneratorConfig):
    name: Literal["covalent"] = "covalent"
    element: str = Field(..., description="The element for the covalent crystal.")
    crystal_structure: Literal["diamond", "graphite"] = "diamond"

class MDConfig(BaseModel):
    """Configuration for the Molecular Dynamics exploration stage."""
    calculator: str = Field("MACE", description="The MLIP calculator to use.")
    temperature_K: float = Field(300.0, gt=0, description="Simulation temperature in Kelvin.")
    pressure_bar: float = Field(1.0, ge=0, description="Simulation pressure in bar (for NPT).")
    ensemble: Literal["NVT", "NPT"] = "NVT"
    steps: int = Field(10000, gt=0, description="Number of MD steps to run.")
    timestep_fs: float = Field(1.0, gt=0, description="Timestep in femtoseconds.")

class SamplingConfig(BaseModel):
    """Configuration for the sampling stage."""
    method: Literal["random"] = "random"
    n_samples: int = Field(100, gt=0, description="Number of structures to select for the final dataset.")

class MainConfig(BaseModel):
    """The top-level configuration model."""
    generator: Union[AlloyGeneratorConfig, CovalentGeneratorConfig] = Field(..., discriminator='name')
    exploration: MDConfig
    sampling: SamplingConfig
    db_path: str = "final_structures.db"
```

**Data Flow and Consumers/Producers:**
*   **Producers:** The primary data producer is the `MDEngine`, which generates a trajectory of ASE `Atoms` objects, representing the time evolution of the system. The various `Generator` classes are also initial producers, creating the seed `Atoms` objects that start the simulations.
*   **Consumers:** The `RandomSampler` is a consumer of the trajectory data produced by the `MDEngine`. The `DBWriter` is the final consumer in the pipeline, taking the list of sampled `Atoms` objects from the sampler and persisting them to long-term storage.
*   **Data Invariants:** The system enforces several critical invariants to ensure physical and computational correctness:
    *   Every `Atoms` object passed between stages in a simulation context must have a valid `calculator` object attached.
    *   The simulation cell for periodic systems must always be larger than the MLIP's cutoff radius in all three Cartesian directions. This is a fundamental requirement for valid periodic simulations and is enforced by the `BaseGenerator`.
    *   The composition of elements in a generated alloy structure must strictly match the user's specification. This is validated by a Pydantic `model_validator`.
    *   All configuration values must be physically reasonable (e.g., temperature > 0 K). This is enforced by Pydantic `Field` constraints.

**Extensibility and Versioning:**
This Pydantic-based design is highly extensible. To add a new generator (e.g., for ionic crystals in CYCLE02), a developer would simply define a new `IonicGeneratorConfig` class and add it to the `Union` type in the `MainConfig.generator` field. Hydra's `instantiate` functionality, combined with this discriminated union, will automatically handle the construction of the correct generator object. This makes adding new features clean and reduces the chance of introducing bugs. The system will not require explicit versioning in CYCLE01, but the structured nature of the schemas provides a clear path for future backward-compatibility. For example, if a parameter is renamed, we could use Pydantic's `Field` aliases to support both the old and new names temporarily during a transition period.

## 4. Implementation Approach

The implementation will be carried out in a logical, step-by-step manner, prioritizing the foundational components first to enable incremental testing. This approach, often called "bottom-up" development, ensures that each component is well-tested and robust before being integrated into the larger system. The entire development process will be guided by the principle of "test-driven development" where practical.

1.  **Project Scaffolding:** Initialize the project with the directory structure outlined in Section 2. Create the `pyproject.toml` file with the initial set of dependencies, which will include `ase`, `hydra-core`, `pydantic`, `torch`, `mace-torch`, `pytest`, `ruff`, and `mypy`. The strict linter and type-checker configurations will be set up from the beginning to ensure high code quality throughout the project.

2.  **Configuration Schemas:** Implement the Pydantic schemas in `src/nnp_gen/common/schemas.py`. This is a critical first step as it will define the "data contracts" and public API for the entire application, guiding the implementation of all other modules. Unit tests will be written for these schemas to ensure the validation logic (e.g., checking that alloy compositions sum to 1.0) is correct.

3.  **Generator Implementation:**
    *   Start with the `BaseGenerator` abstract class in `generators/base.py`. Implement the core validation logic (`_check_overlap`, `_ensure_supercell_size`, `apply_rattle`) and write extensive unit tests to ensure they function correctly under various edge cases.
    *   Implement the `AlloyGenerator` and `CovalentGenerator` as subclasses of `BaseGenerator`. These will use ASE's built-in functions for creating lattices and will contain the logic for setting the chemical species correctly. Each generator will have its own dedicated test file.

4.  **Storage Implementation:** Implement the `db_writer.py` module. This is a simple, isolated component with no dependencies on the rest of the pipeline, so it can be developed and tested early. It will contain a single function that takes a list of `Atoms` objects and saves them to an ASE database.

5.  **MD Engine (Core Logic):** This is the most complex part of the cycle.
    *   Begin by implementing the `MDEngine` class. Focus on the core logic of setting up and running a single simulation using ASE's dynamics objects. Initially, the calculator can be hard-coded to a simple, fast potential like ASE's built-in EMT potential to simplify testing.
    *   Next, implement the `run_single_md_process` wrapper function. This is where the late-binding of the actual MLIP calculator will be implemented. This logic will be tested carefully.
    *   Finally, implement the robust error handling and crash-dumping mechanism within this wrapper. The unit test for this will involve a mock calculator that intentionally raises an exception.

6.  **Pipeline Orchestrator:** Implement the `PipelineRunner` class. This will tie all the previously created and tested components together. The initial implementation will be a linear script that calls each component in sequence. Integration testing will begin at this stage.

7.  **Parallel Execution:** Integrate `ProcessPoolExecutor` into the `PipelineRunner`. The `run_single_md_process` function will be submitted as a task for each of the seed structures. The results (paths to trajectory files) will be collected and passed to the next stage.

8.  **Sampling:** Implement the `RandomSampler` class and its corresponding test file. This component is straightforward and will be one of the last pieces of core logic to be implemented.

9.  **CLI Entry Point:** Create `main.py` and use Hydra's `@hydra.main` decorator to create the main application entry point. This will be the final step to make the application runnable from the command line and will be tested via subprocess calls in the integration test suite.

## 5. Test Strategy

The test strategy for CYCLE01 focuses on ensuring the correctness of the core physics, the stability of the simulation pipeline, and the robustness of the command-line interface. A high level of test coverage is a primary goal for this foundational cycle.

**Unit Testing Approach (Min 300 words):**
Unit tests will be written using the `pytest` framework and will be placed in a separate `tests/` directory that mirrors the `src/` layout. The primary goal is to test each component in complete isolation from the others, using mocks and stubs where necessary.

*   **Generators:** For `AlloyGenerator`, tests will assert that the generated `Atoms` object has the correct chemical symbols and that their ratio matches the requested composition. We will test edge cases, such as a 50/50 binary alloy and a more complex ternary alloy. We will also test that providing inconsistent `elements` and `composition` lists raises a `ValidationError`. For `CovalentGenerator`, tests will verify that the correct crystal structure (e.g., diamond) is created with the correct lattice parameters.
*   **Physics Validation:** The validation methods in `BaseGenerator` will be tested rigorously. `_check_overlap` will be tested with a known "colliding" structure, and we will assert that it raises the expected `PhysicsViolationError`. `_ensure_supercell_size` will be tested with a cell that is too small in one, two, and all three dimensions, and we will verify that the resulting supercell has the correct, expanded dimensions and that the atomic positions have been correctly mapped into the new cell.
*   **MDEngine:** Unit testing the `MDEngine` is complex due to its reliance on external calculators. We will use a mock calculator (e.g., ASE's built-in EMT potential or a `MagicMock` object) for these tests to avoid the overhead and complexity of a real MLIP. Tests will verify that the correct dynamics object (`Langevin` or `Berendsen`) is attached to the `Atoms` object based on the configuration and that the simulation `run()` method is called the correct number of times. We will also test the crash-dumping mechanism by creating a mock `run` method that raises an exception, and we will assert that the dump file is created with the correct information.
*   **Schemas:** We will write dedicated tests for the Pydantic schemas to ensure they correctly parse valid configuration dictionaries and, more importantly, raise `ValidationError` with informative messages for invalid ones (e.g., an alloy with only one element, a negative temperature, a composition that does not sum to 1.0).

**Integration Testing Approach (Min 300 words):**
Integration tests will verify that the different components of the pipeline work together as expected, from the command line to the final database output. These tests will be slower than unit tests and will be marked as such in `pytest` to allow for running them separately.

*   **End-to-End Pipeline Test:** A key integration test will be a "smoke test" that runs the entire pipeline on a very small and simple system (e.g., a 2-atom Si cell, running for only 10 MD steps with a fast EMT potential). The test will execute the `main.py` script as a subprocess with a minimal, dedicated configuration file. The success of the test will be determined by three assertions: 1) The process exits with a code of 0. 2) The final ASE database file is created at the specified path. 3) The database contains the exact number of structures specified in the sampling configuration. This test is the single most important one as it ensures that all the components are wired together correctly.
*   **CLI and Configuration Test:** We will test the command-line interface by running `main.py` with various command-line overrides for the Hydra configuration. For example, we will run the pipeline and override the temperature: `python main.py exploration.temperature_K=500`. We will then inspect the output database or logs (if any) to confirm that the new temperature was correctly used in the simulation. This validates the crucial integration between our application and the Hydra configuration framework. We will also test that providing an invalid override (e.g., for a parameter that doesn't exist) causes Hydra to exit with an error.
*   **Parallel Execution Test:** We will run the pipeline smoke test with `max_workers` set to 2 or more. This test is not to check for scientific correctness (which is hard to do with parallel MD) but to ensure that the application does not deadlock or crash due to race conditions or pickling errors when using the `ProcessPoolExecutor`. The primary assertion is simply that the process finishes successfully and produces a database with the correct number of structures.
