# System Architecture: MLIP-AutoPipe

**Version:** 1.0.0
**Status:** Final
**Authors:** System Architect

## 1. Summary

The MLIP-AutoPipe (Machine Learning Interatomic Potential - Automated Pipeline) project represents a paradigm shift in computational materials science. Its core philosophy is to **"remove the human expert from the loop"**, addressing the most significant bottleneck in the creation and application of machine learning potentials: the reliance on expert intuition and manual intervention. Traditional methods for simulating materials at the atomic level, such as Density Functional Theory (DFT) and Ab Initio Molecular Dynamics (AIMD), are incredibly powerful but suffer from two major drawbacks: they require deep, specialised knowledge to operate correctly, and they are computationally expensive, limiting the time and length scales they can explore. The process of generating high-quality training data for MLIPs—deciding which atomic configurations to calculate at specific temperatures and pressures—is currently more of an art than a science, depending heavily on the tacit knowledge of experienced researchers.

MLIP-AutoPipe systematically dismantles this bottleneck by introducing a fully automated, self-correcting pipeline. It guides the entire workflow from initial structure generation to active learning and large-scale simulation. The system is designed to be accessible to a broader range of scientists and engineers, requiring only minimal input, such as the material's composition. From this starting point, the pipeline autonomously generates a bespoke, high-accuracy MLIP that rivals the precision of first-principles calculations. This automation empowers users to focus on analysing complex phenomena like phase transformations, reaction dynamics, and defect behaviour, rather than getting bogged down in the complex process of potential generation.

The pipeline's key innovation lies in its intelligent combination of physics-based heuristics and machine learning-driven uncertainty quantification. Instead of relying on computationally expensive AIMD simulations for initial data generation, MLIP-AutoPipe employs a suite of sophisticated, physics-aware techniques (e.g., Special Quasirandom Structures, Normal Mode Sampling, Ab Initio Random Structure Searching) to create a diverse and physically meaningful set of initial atomic configurations. This is followed by a high-throughput exploration phase using pre-trained, universal foundation models (like MACE or M3GNet) to rapidly scan vast regions of the material's phase space without performing a single DFT calculation. This 'DIRECT' sampling approach ensures that precious DFT resources are focused exclusively on structures that provide the most new information, maximising the efficiency of the learning process. An automated labelling engine, built around Quantum Espresso, handles the complexities of DFT calculations, from selecting pseudopotentials to optimising convergence parameters, ensuring robust and reproducible results. The subsequent training engine employs a 'Delta Learning' strategy, learning the residual between a robust baseline potential and the true DFT energies, which ensures physically correct behaviour even in sparse data regions. Finally, an 'on-the-fly' active learning loop continuously monitors simulations, detects when the model encounters novel atomic environments, and automatically triggers a retraining cycle to progressively improve the potential's accuracy and reliability. This creates a virtuous cycle of autonomous improvement, leading to a highly robust and transferable potential capable of exploring phenomena over timescales (nanoseconds to microseconds) that are simply inaccessible to traditional methods.

## 2. System Design Objectives

The primary objective of the MLIP-AutoPipe system is to democratise the creation of high-fidelity interatomic potentials. This overarching goal is supported by a series of specific, measurable design objectives that guide the system's architecture and implementation.

**1. Maximise Automation, Minimise User Intervention:** The system is designed around the principle of "zero-touch" operation. The user should only need to provide the most basic information (e.g., chemical composition) via a minimal configuration file (`input.yaml`). All subsequent decisions—from determining the bond type and selecting the appropriate structure generation algorithm, to setting DFT parameters and choosing a surrogate model—must be made autonomously by the system's heuristic engine. This objective directly addresses the goal of removing the human expert from the loop, making the technology accessible to non-specialists. Success will be measured by the system's ability to generate a valid potential for a wide range of materials without requiring any adjustments to the auto-generated full configuration file.

**2. Computational Efficiency and Resource Optimisation:** The pipeline must be significantly more computationally efficient than traditional AIMD-based data generation workflows. This is achieved through a multi-pronged strategy: avoiding expensive AIMD for initial sampling, using fast surrogate models for exploration, and applying active learning to select only the most informative data points for DFT labelling. The objective is to reduce the total DFT calculation cost by at least an order of magnitude compared to a brute-force approach while achieving the same level of potential accuracy. Performance will be benchmarked by tracking the number of DFT single-point calculations required to reach a target accuracy for a set of standard materials systems.

**3. Robustness and Reproducibility:** Every step of the pipeline must be fully automated, deterministic, and traceable. The 'Two-Tier Configuration' strategy is central to this objective. The system-generated `exec_config_dump.yaml` file serves as an immutable record of every parameter used in a given run, from the DFT cutoff energy to the random seed used in structure generation. This ensures that any result can be perfectly reproduced. Furthermore, the system must include robust error-handling and self-correction logic, such as automatically adjusting DFT mixing parameters if a calculation fails to converge. The success of this objective will be validated by ensuring that identical `input.yaml` files produce statistically identical MLIPs and that the pipeline can recover from common, non-critical errors without user intervention.

**4. Modularity and Extensibility:** The system's architecture must be modular, allowing for the easy integration of new algorithms, simulation engines, and machine learning models as they become available. Each component (Structure Generator, Explorer, Labelling Engine, etc.) is designed as a loosely coupled module with well-defined interfaces. This allows, for example, a new universal potential to be added to the Explorer module by simply implementing a compatible wrapper. This design principle ensures the long-term viability and relevance of the project, preventing technological lock-in. The objective will be considered met if a developer can add a new structure generation method or a new MLIP framework with only localised code changes.

**5. Performance and Scalability:** To handle the large datasets and computationally intensive tasks involved, the system must be designed for high performance. This involves leveraging modern, high-speed tooling (`uv` for package management) and aggressive code optimisation. Critical numerical routines, particularly in the Explorer & Sampler module, will be just-in-time (JIT) compiled using Numba to achieve C/C++ level performance. The system should also leverage available hardware, automatically utilising GPUs for neural network inference where possible. Scalability will be assessed by the system's ability to efficiently process increasingly large atomic systems and generate massive MD trajectories (millions of frames) without becoming a bottleneck.

## 3. System Architecture

The MLIP-AutoPipe system is architected as a modular, five-stage pipeline orchestrated by a central workflow controller. This design promotes separation of concerns, maintainability, and extensibility. Data flows sequentially through the modules, with feedback loops for active learning, and all intermediate results and metadata are persistently stored in a database (e.g., ASE DB) to ensure traceability.

```mermaid
graph TD
    subgraph User Interaction
        A[User provides input.yaml]
    end

    subgraph Workflow Orchestrator
        B[Config Expander / Heuristic Engine]
        C[ASE Database for State & Provenance]
    end

    subgraph Core Pipeline Modules
        D[Module A: Structure Generator]
        E[Module B: Explorer & Sampler]
        F[Module C: Labelling Engine]
        G[Module D: Training Engine]
        H[Module E: Simulation Engine]
    end

    subgraph Active Learning Loop
        I{Uncertainty > Threshold?}
    end

    A --> B
    B -- Generates --> exec_config_dump.yaml
    B -- Initializes --> C

    exec_config_dump.yaml -- Drives --> D
    D -- Initial Structures --> C
    C -- Feeds Structures --> E
    E -- Uses Universal Potential --> E
    E -- Samples Informative Structures --> C
    C -- Feeds Structures for Labelling --> F
    F -- Uses Quantum Espresso --> F
    F -- DFT Labels (Energy/Force/Stress) --> C
    C -- Provides Training Data --> G
    G -- Trains MLIP --> C
    C -- Provides Trained MLIP --> H
    H -- Runs MD/kMC Simulation --> H
    H -- Monitors Uncertainty --> I
    I -- Yes --> |Extract Structure| C
    I -- No --> |Continue Simulation| H
```

**Module Descriptions:**

1.  **Workflow Orchestrator & Config Expander:** This is the brain of the system. It begins by consuming the user's minimal `input.yaml`. The **Config Expander**, a physics-based heuristic engine, analyses the input, determines key properties like bond type and estimated melting point, and makes intelligent decisions to populate a complete `exec_config_dump.yaml`. This full configuration file dictates the behaviour of all downstream modules, ensuring reproducibility. The orchestrator manages the flow of data between modules, interacts with the central database, and controls the main execution loop.

2.  **Module A: Structure Generator:** This module is responsible for creating the initial seed data without resorting to expensive DFT calculations. Based on the bond type determined by the orchestrator, it selects the most appropriate algorithm. For alloys, it generates Special Quasirandom Structures (SQS). For molecules, it uses Normal Mode Sampling (NMS) to explore vibrational modes. For ionic crystals, it employs an Ab Initio Random Structure Searching (AIRSS) approach. For covalent systems, it uses "Deep Rattling" or simulated melt-quench protocols with a surrogate model. This diversity ensures the initial training set covers a wide range of local atomic environments.

3.  **Module B: Explorer & Sampler:** This module performs a vast, low-cost exploration of the system's phase space. It takes the initial structures and uses a pre-trained, universal foundation model (e.g., MACE-MP, M3GNet) to run large-scale molecular dynamics simulations. This generates millions of candidate structures. The key task is then to select a small, diverse, and informative subset for expensive DFT labelling. To do this, it calculates structural descriptors (like SOAP) for all candidates, uses dimensionality reduction techniques (PCA/UMAP) to map the conformational space, and then applies stratified sampling to select a representative set of structures, avoiding redundancy and bias. Critical parts of this module are JIT-compiled with Numba for maximum performance.

4.  **Module C: Labelling Engine:** This module is a robust wrapper around a DFT engine, specifically Quantum Espresso. It receives a batch of structures from the sampler and performs single-point calculations to obtain high-fidelity energy, force, and stress labels. Its primary role is automation; it handles everything from selecting the correct pseudopotentials and cutoff energies (based on a standard protocol like SSSP), to setting k-point density and automatically managing SCF convergence parameters. It includes error recovery logic to retry failed calculations with adjusted settings. All inputs, outputs, and metadata are logged to the database for provenance.

5.  **Module D: Training Engine:** This module takes the DFT-labelled data and trains the Machine Learning Interatomic Potential. It implements a **Delta Learning** strategy. Instead of learning the absolute DFT energy, it trains the model to predict the *difference* between the DFT energy and the energy from a simpler, physics-based reference potential (e.g., ZBL for core repulsion, LJ for van der Waals). This approach ensures the final MLIP behaves correctly in regions with sparse data, respecting fundamental physical constraints. The engine is designed to be compatible with modern MLIP frameworks like ACE or MACE.

6.  **Module E: Simulation Engine & Active Learning Loop:** This is the final stage where the trained MLIP is put to use. The engine, likely built on LAMMPS, runs large-scale simulations (MD or kMC) to explore long-timescale phenomena. Crucially, it incorporates an **On-the-fly (OTF)** uncertainty monitoring system. During the simulation, it constantly evaluates the model's confidence in its predictions. If the uncertainty for a given atomic configuration exceeds a predefined threshold, it indicates the model is in an unexplored region of phase space. The simulation is paused, the high-uncertainty structure is extracted, and it is sent back to the Labelling Engine (Module C) to acquire a DFT label. The new data point is then used to retrain and refine the MLIP in Module D. This self-correcting loop allows the potential to autonomously improve its accuracy and expand its domain of applicability.

## 4. Design Architecture

The software design of MLIP-AutoPipe emphasizes modularity, configurability, and performance. The system is designed as a Python package managed by `pyproject.toml` and the `uv` toolchain for rapid and reproducible environment setup.

**File Structure:**
```
mlip_autopipe/
├── pyproject.toml       # Project metadata and dependencies
├── src/
│   └── mlip_pipe/
│       ├── __init__.py
│       ├── main.py          # CLI entry point
│       ├── orchestrator.py  # Main workflow control
│       ├── config/
│       │   └── expander.py  # Heuristic engine for config generation
│       ├── modules/
│       │   ├── __init__.py
│       │   ├── a_structure_generator.py
│       │   ├── b_explorer_sampler.py
│       │   ├── c_labelling_engine.py
│       │   ├── d_training_engine.py
│       │   └── e_simulation_engine.py
│       ├── utils/
│       │   ├── ase_db.py    # ASE Database interface
│       │   ├── dft_utils.py # Quantum Espresso wrappers
│       │   └── performance.py # Numba-optimized functions
│       └── data_models.py   # Pydantic models for data structures
└── tests/
    └── ...              # Unit and integration tests
```

**Key Class/Function Definitions:**

*   `main.py`: Implements the command-line interface using a library like `typer` or `click`. The main command `uv run mlip-pipe input.yaml` will trigger the orchestration process.
*   `orchestrator.Orchestrator`: The central class that manages the pipeline. It will have methods like `run_pipeline()`, which executes the full workflow, and `_execute_cycle()`, which runs a single active learning iteration. It holds the state of the pipeline and interacts with the ASE database.
*   `config.expander.ConfigExpander`: Responsible for the two-tier configuration strategy. Its primary method, `expand(minimal_config)`, will take the user's `input.yaml`, apply physical heuristics, and return a fully specified configuration object.
*   `modules.a_structure_generator.StructureGenerator`: A factory class that, based on the configuration, returns a specific generator instance (e.g., `SQSGenerator`, `NMSGenerator`). Each instance will have a `generate()` method that returns a list of ASE Atoms objects.
*   `modules.b_explorer_sampler.Explorer`: This class runs the high-throughput exploration using a universal potential. It will contain methods for running MD simulations (`run_md()`) and for sampling (`sample_structures()`). The descriptor calculation and clustering logic will be offloaded to optimized functions in `utils.performance`.
*   `modules.c_labelling_engine.QuantumEspressoRunner`: This class provides a high-level API for running DFT calculations. It will have a method `run_calculation(atoms)` that takes an ASE Atoms object, generates the appropriate QE input file, executes `pw.x`, parses the output, and returns the labelled Atoms object.
*   `modules.d_training_engine.Trainer`: This class manages the training of the MLIP. Its `train(dataset)` method will take a dataset of labelled structures, fit the selected MLIP model (e.g., ACE), and save the resulting potential file. It will also handle the logic for Delta Learning.
*   `modules.e_simulation_engine.SimulationEngine`: This class runs production simulations with the trained MLIP. It will have a method `run_otf_md(potential)` that executes the on-the-fly active learning loop, monitoring uncertainty and yielding high-uncertainty structures for retraining.

**Data Models:**
Pydantic models will be used to ensure data integrity and provide clear schema for configuration and state.

*   `MinimalConfig(BaseModel)`: Defines the schema for `input.yaml`, with fields for `elements`, `composition`, and `simulation_goals`.
*   `FullConfig(BaseModel)`: A comprehensive model that defines all possible parameters for the entire pipeline, from DFT settings to MLIP hyperparameters. The `ConfigExpander`'s job is to transform a `MinimalConfig` into a `FullConfig`.
*   `PipelineRun(BaseModel)`: Represents the state of a single execution, including paths to artifacts, database identifiers, and cycle information.

This architecture ensures a clean separation of concerns. The `modules` contain the scientific logic, the `orchestrator` handles the workflow, `config` manages setup, and `utils` provides shared, low-level functionality. This makes the system easier to test, maintain, and extend.

## 5. Implementation Plan

The project will be developed over five distinct, sequential cycles. Each cycle delivers a functional, self-contained subset of the total system, allowing for iterative development and testing.

**Cycle 1: The Core Engine (Foundation)**
This foundational cycle focuses on establishing the project's structure and building the absolute minimum viable product: a pipeline that can take a set of structures, label them with DFT, and train a potential.
*   **Features:**
    *   Set up the project structure with `pyproject.toml` and `uv`.
    *   Implement the core `Orchestrator` class to manage a linear workflow.
    *   Develop **Module C (Labelling Engine)**: Create a robust wrapper for Quantum Espresso that can automatically generate input files from ASE Atoms objects, execute `pw.x`, and parse the output for energies and forces. This includes implementing the SSSP protocol for automated parameter selection.
    *   Develop **Module D (Training Engine)**: Implement the training logic for a single, modern MLIP framework (e.g., MACE). This will include the Delta Learning strategy, where it learns the residual from a baseline ZBL potential.
    *   Implement the basic ASE database utility for storing labelled structures.
    *   **Goal:** At the end of this cycle, a developer will be able to manually provide a set of CIF files, and the pipeline will automatically compute their DFT labels and train a simple MLIP.

**Cycle 2: Automated Configuration and Structure Generation**
This cycle removes the need for manual input by introducing the automated configuration and initial structure generation modules.
*   **Features:**
    *   Develop the **Config Expander (Heuristic Engine)**: This is the core of the two-tier configuration strategy. It will parse the `input.yaml`, automatically determine bond type (alloy, molecular, etc.), and generate the `exec_config_dump.yaml` with sensible defaults for DFT and simulation parameters.
    *   Implement **Module A (Structure Generator)**: Based on the bond type detected by the Config Expander, this module will automatically generate a diverse set of initial structures. This includes implementing SQS for alloys, NMS for molecules, and AIRSS-like methods for ionic crystals.
    *   Integrate Module A with the Orchestrator, so the pipeline now starts from `input.yaml` and autonomously creates its own initial dataset.
    *   **Goal:** A user can provide a simple `input.yaml` with only the composition, and the system will auto-generate an initial dataset and train a preliminary MLIP without any further intervention.

**Cycle 3: High-Throughput Exploration and Optimisation**
This cycle focuses on dramatically improving the efficiency of data generation by implementing the surrogate-based exploration and sampling module.
*   **Features:**
    *   Implement **Module B (Explorer & Sampler)**:
        *   Integrate a pre-trained universal potential (like MACE-MP) to run fast MD simulations.
        *   Implement the DIRECT sampling workflow: generate a massive trajectory, compute structural descriptors (e.g., SOAP), perform dimensionality reduction (UMAP), and use stratified sampling to select an information-rich, diverse subset of structures.
    *   **Performance Optimisation:** Profile the descriptor calculation and sampling code and rewrite critical, bottleneck functions in Numba for JIT compilation, ensuring high throughput.
    *   Integrate Module B into the orchestrator. The workflow is now: Generate initial structures -> Explore with surrogate -> Sample best candidates -> Label with DFT -> Train MLIP.
    *   **Goal:** The pipeline's efficiency is significantly enhanced. It can now explore vast conformational spaces at low cost, leading to better-quality MLIPs with fewer expensive DFT calculations compared to the random generation in Cycle 2.

**Cycle 4: The Active Learning Loop**
This cycle closes the loop, transforming the linear pipeline into a self-improving, autonomous system.
*   **Features:**
    *   Implement **Module E (Simulation Engine)**: Integrate a simulation engine like LAMMPS.
    *   Develop the **On-the-fly (OTF) uncertainty monitoring system**. This involves calculating an extrapolation grade or other uncertainty metric during an MD simulation run with the trained MLIP.
    *   Implement the core active learning logic in the Orchestrator: When uncertainty exceeds a threshold, the simulation is paused, the structure is extracted (using a periodic embedding approach), and it is passed back to Module C for labelling.
    *   The Orchestrator will then trigger retraining (Module D) with the augmented dataset.
    *   Implement advanced kMC and saddle point search methods for exploring rare events, also under the control of the uncertainty monitor.
    *   **Goal:** The system is now fully autonomous. It can start from scratch, train an initial potential, and then iteratively and automatically refine it by intelligently exploring new regions of phase space during simulation, converging towards a highly accurate and robust potential.

**Cycle 5: User Interface and Finalisation**
The final cycle focuses on usability, documentation, and packaging.
*   **Features:**
    *   Develop a user-friendly command-line interface (CLI) with clear commands, help messages, and progress indicators.
    *   Implement comprehensive logging and reporting features, allowing users to easily track the progress of a run and diagnose issues.
    *   Write detailed user documentation, tutorials, and examples.
    *   Package the project for distribution via PyPI using `uv`.
    *   Perform final system-wide testing and benchmarking to validate performance and accuracy claims.
    *   **Goal:** The MLIP-AutoPipe is a polished, well-documented, and easy-to-use tool ready for distribution to the materials science community.

## 6. Test Strategy

A rigorous, multi-layered testing strategy is essential to ensure the correctness, robustness, and performance of the MLIP-AutoPipe system. Testing will be integrated throughout the development process, with a focus on automation.

**Cycle 1: Core Engine Testing**
*   **Unit Testing:**
    *   Mock the Quantum Espresso `pw.x` executable. Test the `QuantumEspressoRunner`'s ability to correctly generate input files for different scenarios (e.g., magnetic vs. non-magnetic systems).
    *   Verify that the output parser correctly extracts energy, forces, and stresses from sample QE output files.
    *   Test the `Trainer` class with a fixed, pre-computed dataset. Verify that it correctly loads the data, trains the model, and that the resulting potential can be saved and loaded.
    *   Test the Delta Learning component by ensuring it correctly computes the residual against a known reference potential.
*   **Integration Testing:**
    *   Create a small, self-contained test with a real (but fast) DFT calculation on a simple system (e.g., a silicon dimer). The test will run the minimal pipeline: take an ASE Atoms object, run a real QE calculation, and verify that the label is correctly stored in the test database.

**Cycle 2: Configuration and Generation Testing**
*   **Unit Testing:**
    *   Test the `ConfigExpander` extensively. Provide various `input.yaml` examples (alloy, molecule, etc.) and assert that the generated `FullConfig` contains the correct, physically sensible parameters (e.g., `nspin=2` for iron, correct SQS parameters for a binary alloy).
    *   Test each structure generator individually. For SQS, verify that the generated structures have the correct composition and low correlation functions. For NMS, verify that the displacements correspond to vibrational modes.
*   **Integration Testing:**
    *   Run the pipeline from a minimal `input.yaml` up to the point of DFT calculation. Verify that the orchestrator correctly interprets the expanded config, calls the right structure generator, and prepares the structures for labelling.

**Cycle 3: Explorer and Sampler Testing**
*   **Unit Testing:**
    *   Test the descriptor calculation functions (e.g., SOAP) on known structures and compare the output against reference implementations.
    *   Test the Numba-optimised functions by comparing their output with pure Python versions to ensure correctness.
    *   Mock the universal potential. Test the sampler's logic by providing it with a pre-computed trajectory and verifying that its stratified sampling selects a diverse set of structures based on the mock descriptors.
*   **Performance Testing:**
    *   Benchmark the Numba-optimised functions. Create benchmarks to measure the speed of descriptor calculation and clustering on large trajectories (e.g., 1 million frames) to ensure they meet performance targets.

**Cycle 4: Active Learning Loop Testing**
*   **Unit Testing:**
    *   Mock the `SimulationEngine`. Create a mock MD run where the uncertainty metric is manually controlled. Test that the `Orchestrator` correctly detects when the threshold is exceeded, pauses the simulation, and extracts the correct structure.
    *   Test the periodic embedding extraction logic to ensure it correctly extracts a sub-cell with buffer regions for DFT recalculation.
*   **Integration Testing:**
    *   This is the most critical integration test. It will involve a full, end-to-end run on a simple, well-understood system. The test will start from `input.yaml`, train an initial (deliberately poor) potential, and then run a short OTF-MD simulation. The test will assert that at least one new structure is identified due to high uncertainty and that a retraining cycle is successfully triggered. This validates the entire feedback loop.

**Cycle 5: UI and System Testing**
*   **CLI Testing:**
    *   Use a framework like `pytest-click` to test the command-line interface. Verify that all commands, options, and arguments work as expected and that appropriate error messages are shown for invalid input.
*   **End-to-End (E2E) "Golden" Tests:**
    *   Create a small number of "golden" test cases for different material types (e.g., a simple alloy, a water molecule). These tests will run the entire pipeline from `input.yaml` to a converged MLIP. The final trained potential will be compared against a known, "golden" potential file to ensure bit-for-bit reproducibility. These tests ensure that changes in one part of the system do not unexpectedly degrade the overall quality of the results.
*   **Documentation Testing:**
    *   Ensure all code examples in the documentation are automatically run and verified as part of the CI/CD pipeline.

**General Test Practices:**
*   **Continuous Integration (CI):** All tests will be run automatically on every commit to the main branch using a CI service like GitHub Actions.
*   **Test Coverage:** Maintain a high level of test coverage (e.g., >90%) for the entire codebase, monitored using tools like `pytest-cov`.
*   **Dependency Management:** The use of `uv` and `pyproject.toml` ensures that the testing environment is identical to the development and production environments, eliminating "works on my machine" issues.