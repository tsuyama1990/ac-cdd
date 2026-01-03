# Specification: Cycle 2 - Advanced Features and Web UI

## 1. Summary

This specification details the second development cycle for the MLIP-AutoPipe project. Building upon the foundational command-line tool established in Cycle 1, this cycle focuses on implementing the advanced, high-value features that distinguish this framework as a state-of-the-art solution for MLIP dataset generation. The primary goals are to significantly enhance the diversity and quality of the generated datasets and to improve the overall usability of the tool by introducing a graphical user interface. This cycle moves beyond simple automation and injects sophisticated scientific algorithms and user-centric design into the core product. The features developed in this cycle are what will provide the key competitive advantages and drive adoption within the research community.

The key technical advancements in this cycle are twofold, targeting both the scientific rigor of the exploration phase and the intelligence of the data selection process. First, the **Exploration** engine, which was a basic MD simulator in Cycle 1, will be upgraded to a sophisticated hybrid Molecular Dynamics/Monte Carlo (MD/MC) engine. This is a critical enhancement that allows the simulation to explore the material's configuration space more effectively than with plain MD. By introducing Monte Carlo moves like atomic swaps at regular intervals, the engine can overcome energy barriers that would typically trap a standard MD simulation, leading to a much broader and more comprehensive exploration of possible atomic arrangements. This is especially crucial for modelling alloys and disordered systems where chemical ordering is a key variable. This upgraded engine will also incorporate "auto ensemble switching," a feature that intelligently applies the correct thermodynamic conditions (NPT vs. NVT) for different system types, such as bulk materials versus surfaces, preventing common simulation artifacts and improving physical accuracy.

Second, the **Sampling** module will be upgraded from a simplistic random selection algorithm to an intelligent, diversity-driven approach using Farthest Point Sampling (FPS). This represents a major leap in the quality of the final dataset. Instead of picking structures at random, FPS uses mathematical fingerprints called structural descriptors to select a set of atomic configurations that are maximally different from one another. This ensures the final training dataset is not redundant and covers the widest possible range of atomic environments, which is essential for training robust and generalizable MLIPs. Finally, to make all these powerful new features accessible to a broader audience, this cycle includes the development of a **Web User Interface (UI)**. This graphical interface will provide users with an intuitive, interactive way to configure and launch pipeline runs, monitor their progress in real-time, and visualise the atomic structures being generated. This will significantly lower the barrier to entry for new users and provide a more powerful and engaging experience for experts.

## 2. System Architecture

The architecture in Cycle 2 expands significantly upon the existing structure from Cycle 1. It involves modifying and upgrading key components to add advanced functionality and introducing an entirely new package for the web-based user interface. The focus is on seamless integration of these new features while maintaining the modular and testable design established previously.

**File Structure (ASCII Tree):**

The files and directories to be created or significantly modified in this cycle are marked in **bold**. The core structure from Cycle 1 is retained, but several files will be heavily modified, and a new `web_ui` directory will be added.

```
src/
└── mlip_autopipec/
    ├── __init__.py
    ├── __main__.py
    ├── cli/
    │   ├── __init__.py
    │   └── main.py
    ├── common/
    │   ├── __init__.py
    │   └── **pydantic_models.py**   # Will be extended with new configuration options for MC and FPS.
    ├── generators/
    │   ├── __init__.py
    │   ├── base.py
    │   └── alloy.py
    ├── explorers/
    │   ├── __init__.py
    │   └── **md_engine.py**         # Will be significantly upgraded with hybrid MD/MC and auto-ensemble logic.
    ├── samplers/
    │   ├── __init__.py
    │   ├── base.py
    │   ├── random_sampler.py
    │   └── **fps.py**               # A new file implementing the Farthest Point Sampling algorithm.
    ├── storage/
    │   ├── __init__.py
    │   └── database_manager.py
    ├── pipeline/
    │   ├── __init__.py
    │   └── orchestrator.py
    ├── **factories.py**             # Will be updated to recognize and construct the new FPS sampler.
    ├── interfaces.py
    └── **web_ui/**                  # A new package for the web application.
        ├── **__init__.py**
        ├── **app.py**               # The main application file (e.g., using Streamlit or FastAPI).
        └── **components.py**        # Reusable UI components (e.g., configuration forms, visualizers).
```

**Code Blueprints:**

*   `explorers/md_engine.py`: This file will undergo a major refactoring. The `MDEngine` class will be upgraded to support a hybrid MD/MC loop. This will involve modifying the main `run` method to include a check at a specified frequency (e.g., every 100 MD steps) to decide whether to perform an MC move. New private methods, such as `_perform_swap_move`, will be added to implement the Monte Carlo logic. This method will randomly select two atoms of different species and attempt to swap their positions, accepting or rejecting the move based on a standard Metropolis criterion. Furthermore, the engine will gain the logic for auto ensemble switching. A new method, `_detect_vacuum`, will be implemented. This method will likely work by creating a 3D grid over the simulation cell and checking for large contiguous regions of grid points that are far from any atom, which would indicate a vacuum slab. The `run` method will call this at the beginning of a simulation to automatically select the appropriate ASE dynamics ensemble (NVT for slab systems, NPT for bulk systems) to prevent unphysical simulation artifacts.

*   `samplers/fps.py`: This new file will house the `FarthestPointSampler` class, which will be a concrete implementation of the `ISampler` interface. This class will have a dependency on an external library capable of calculating structural descriptors, such as `dscribe` for the SOAP (Smooth Overlap of Atomic Positions) method. Its `sample` method will be algorithmically complex. It will first need to read the entire trajectory from the explorer and compute the descriptor vector for each and every frame, storing these vectors in a large NumPy array. It will then implement the iterative FPS algorithm. This involves first picking a random structure to initialize the sampled set. Then, in a loop, it will calculate the distance of all remaining structures to the current set and select the one that is "farthest away" (i.e., has the maximum minimum distance to any point already in the set). This structure is added to the set, and the process repeats until the desired number of samples is reached.

*   `common/pydantic_models.py`: The Pydantic configuration schemas will be extended to control the new features. The `ExplorationConfig` model will be updated to include new fields such as `mc_enabled: bool`, `swap_frequency: int`, and `mc_move_types: List[str]`. These will have default values to ensure backward compatibility with Cycle 1 configs. Similarly, the `SamplingConfig` model will have its `method` enum updated to include a new member, `'fps'`. A new `FPSConfig` model will be added to hold parameters specific to the FPS algorithm, such as the type of descriptor to use (`descriptor_type: str`) and any parameters for the descriptor itself (e.g., `soap_nmax`, `soap_lmax`). This new model will be an optional field within the main `SamplingConfig`.

*   `web_ui/app.py`: This will be the main entry point for the new web application. We will use Streamlit for its rapid development capabilities. This file will contain the Python code that lays out the UI components: various widgets for setting all the pipeline configuration parameters (e.g., sliders for temperature, dropdowns for elements, checkboxes for boolean flags like `mc_enabled`), a main "Run Pipeline" button to start the process, and a display area for showing progress updates and visualizing the final atomic structures (e.g., using a component that integrates the `py3Dmol` library). The application will be designed to construct the exact same Pydantic `FullConfig` object that the CLI uses. It will then call the `PipelineOrchestrator` in a separate background process or thread to run the simulation without blocking the UI's event loop.

*   `web_ui/components.py`: To keep the main `app.py` file clean and organized, reusable UI elements will be encapsulated into functions within this file. For example, a function like `create_system_config_form(defaults)` could be responsible for rendering all the Streamlit widgets for the `SystemConfig` section of the form and returning the corresponding Pydantic object. This modular approach will make the UI code much easier to manage and debug.

## 3. Design Architecture

The design for Cycle 2 is focused on two primary goals: integrating more complex scientific algorithms in a robust way, and providing a user-friendly graphical interface that abstracts away the underlying complexity. All this must be done while maintaining the modularity and testability of the architecture established in Cycle 1.

**Pydantic-Based Schema Design:**

The existing Pydantic schema is the foundation for this cycle's new features. The design principle is to extend the schema by adding new, optional configuration sections, which is a non-breaking change that ensures backward compatibility with configurations from Cycle 1.

*   **`ExplorationConfig` Extension**:
    *   New Fields: The model will be extended with `enable_mc` (a `bool` that defaults to `False`), `mc_swap_probability` (a `float` between 0.0 and 1.0), and `mc_auto_ensemble` (a `bool` that defaults to `True`).
    *   Producers: These values will be set either by a user in their YAML file or through new widgets (e.g., checkboxes, sliders) in the Web UI form.
    *   Consumers: The primary consumer is the `MDEngine`, which will use these values to conditionally enable and control the hybrid MD/MC simulation logic.
    *   Design: The use of default values is critical here. If a user provides a Cycle 1 configuration file that lacks these new keys, the model will still validate successfully and the new features will simply be disabled, ensuring a smooth upgrade path.

*   **`SamplingConfig` Extension**:
    *   `method` Enum: The `method` field, which was an enum in Cycle 1, will be updated to `Enum('random', 'fps')`.
    *   `fps_settings` (Optional[`FPSConfig`]): A new field will be added to hold FPS-specific settings. This field will be optional.
    *   `FPSConfig` Model: A completely new Pydantic model will be created. It will contain fields like `descriptor_type` (e.g., an `Enum` with values 'soap', 'acsf')), and `descriptor_params` (a `Dict` to hold arbitrary parameters for the chosen descriptor, like `nmax` and `lmax` for SOAP).
    *   Design: This nested, optional structure is a key design choice. It ensures that FPS-specific parameters are only provided and validated when FPS is the selected sampling method. The factory function in `factories.py` will be updated to inspect the `config.sampling.method` field and, if it is 'fps', it will instantiate and return a `FarthestPointSampler`, passing the `fps_settings` to its constructor.

*   **Web UI and Configuration**:
    *   The Web UI will become a primary producer of the `FullConfig` object during interactive sessions. The UI components (sliders, text boxes, etc.) will be directly and explicitly mapped to the fields in the Pydantic models.
    *   When a user clicks the "Run" button in the UI, the application will gather the current state of all its input widgets into a dictionary. This dictionary will then be parsed by the `FullConfig.model_validate()` method. This is a critical design choice that reuses the exact same validation logic as the CLI, ensuring consistency and preventing logic duplication. The core pipeline logic is completely agnostic to whether its configuration originated from a human-written YAML file or a graphical user interface.

**Component Interaction and Extensibility:**

*   `MDEngine`: The refactored engine will have a main simulation loop. Inside this loop, after a configurable number of MD steps, it will check the `enable_mc` flag. If true, it will attempt an MC move by calling a private helper method like `_attempt_swap`. This design keeps the MD and MC logic cleanly separated but allows them to work together within the same simulation run.
*   `FarthestPointSampler`: This new component will be designed to be as decoupled as possible. Its public `sample` method will require only a path to a trajectory file and the relevant sampling parameters. This high degree of encapsulation makes it highly reusable and much easier to write focused unit tests for its complex algorithm.
*   `Web UI and PipelineOrchestrator`: The UI, defined in `web_ui/app.py`, will import and use the `PipelineOrchestrator` from the core `mlip_autopipec` package, treating the core application as a library. To avoid freezing the UI during a potentially long-running simulation, the call to `orchestrator.run()` must be executed asynchronously. The recommended approach for this is to use Python's `multiprocessing` module to launch the entire run in a completely separate process. The UI can then monitor the progress of this background process by periodically checking for the existence of output files or by reading a status from a simple log file that the orchestrator updates.

## 4. Implementation Approach

The implementation of Cycle 2 will be more complex than Cycle 1 and will be tackled in three parallel streams: upgrading the explorer, building the new sampler, and developing the web UI from scratch.

1.  **Extend Configuration**: As in Cycle 1, the first step is to update the source of truth: the Pydantic models in `common/pydantic_models.py`. The new fields and models required for the advanced features will be added first. This includes adding the `mc_enabled` flag to `ExplorationConfig` and adding the `fps` option to the `SamplingConfig` method enum, along with the new `FPSConfig` model. This "contract-first" approach ensures that the requirements for the new functionality are clearly and programmatically defined before implementation begins.

2.  **Upgrade the Exploration Engine**:
    *   The `MDEngine`'s main `run` method will be refactored. The existing loop over MD steps will be preserved, but a conditional block will be added inside it (`if step % swap_frequency == 0:`).
    *   Inside this block, the logic for performing MC moves will be called. A new private method, `_perform_swap_move`, will be implemented. This method will need to select two atoms of different species, calculate the potential energy change of the proposed swap, and accept or reject the move based on the Metropolis criterion.
    *   Separately, the `_detect_vacuum` function will be implemented. A robust approach would be to create a 3D voxel grid over the simulation cell and check for large, contiguous regions of empty voxels.
    *   This detection logic will be integrated at the start of the `run` method to automatically select the appropriate ASE dynamics ensemble (`NVT` or `NPT`) for the simulation.

3.  **Implement the Farthest Point Sampler**:
    *   A new file, `samplers/fps.py`, will be created, containing the `FarthestPointSampler` class.
    *   A new dependency on a descriptor calculation library, such as `dscribe`, will be added to the project's `pyproject.toml`.
    *   The `sample` method will be the core of this component. It will first need a loop to read the entire trajectory and compute the descriptor vector (e.g., SOAP vector) for each frame, storing these high-dimensional vectors in a large NumPy array.
    *   The core FPS algorithm will then be implemented. This is an iterative process that maintains a set of selected indices. At each step, it must efficiently calculate the distance of all remaining points to the currently selected set and find the point with the maximum "minimum distance." This point is then added to the set, and the process repeats.

4.  **Develop the Web UI**:
    *   The basic application structure will be set up in `web_ui/app.py` using Streamlit. The file will start with a title and a description.
    *   The UI components will be created in `web_ui/components.py` as reusable functions. These functions will generate the Streamlit widgets (sliders, number inputs, dropdowns) needed to configure the pipeline, directly mirroring the structure of the Pydantic config models.
    *   The "Run Pipeline" button will be implemented in `app.py`. The on-click handler for this button will be the most complex part of the UI. It will need to gather the state from all the UI widgets, construct the `FullConfig` Pydantic object, and then use the `multiprocessing` library to launch the `PipelineOrchestrator.run()` method in a completely separate process to prevent blocking.
    *   A progress display will be added to the UI. A simple but effective method is to have the orchestrator write log messages to a file, and the Streamlit app can periodically read and display the contents of this file in a text area.
    *   Finally, a 3D molecule viewer component will be integrated using a library like `py3Dmol` to display a sample result after the pipeline completes.

5.  **Update Factories and CLI**: The `create_sampler` function in `factories.py` will be updated to handle the new `'fps'` method. This will involve adding a new condition that checks for this value in the config and, if found, returns an instance of the `FarthestPointSampler`. This ensures that both the CLI and the Web UI can seamlessly make use of the new, advanced sampler.

## 5. Test Strategy

The testing for Cycle 2 must cover the new complex algorithms and the interactive web UI.

**Unit Testing Approach (Min 300 words):**

The unit tests for Cycle 2 will focus on the new, algorithmically complex components and the backend logic of the web UI.

*   **`FarthestPointSampler`**: This component requires rigorous testing. We will create a deterministic test case with a small, known set of 2D vectors. We will run the FPS algorithm on this set and assert that it returns the expected indices in the correct order. This validates the core logic of the sampler independently of any real atomic data. We will also test edge cases, such as requesting more samples than there are data points.

*   **`MDEngine`**: The new logic in the `MDEngine` will be unit tested using mocks. To test the hybrid MD/MC functionality, we will mock the underlying ASE dynamics and assert that the `_perform_swap_move` method is called the correct number of times based on the configuration. To test the `_detect_vacuum` method, we will create several `Atoms` objects manually—some representing bulk crystals and others representing slabs with vacuum layers—and assert that the method correctly classifies each one.

*   **Web UI Backend**: We can write unit tests for the logic that connects the UI to the pipeline. For example, we can test the function that gathers data from the UI widgets and creates the `FullConfig` object. We will simulate widget states (e.g., a dictionary of values) and assert that the function produces a correctly structured and validated Pydantic object. This ensures the UI is correctly communicating with the core application logic.

**Integration Testing Approach (Min 300 words):**

Integration tests will ensure that the new features work correctly within the full pipeline and that the Web UI functions as a complete application.

*   **Advanced CLI End-to-End Test**: A new end-to-end test for the CLI will be created. This test will use a configuration file that specifically enables the hybrid MD/MC engine and the Farthest Point Sampler. The test will run the full pipeline. While it is difficult to assert the "correctness" of the stochastic output, we can perform important checks. The test will verify that the pipeline runs to completion without errors. It will also inspect the output database to confirm that the number of samples is correct. We can also add logging within the `MDEngine` and check the logs to verify that the MC swap code paths were actually executed during the run.

*   **Web UI End-to-End Test**: This is the most critical integration test for Cycle 2. We will use a browser automation framework like Playwright. The test script will perform the following actions:
    1.  Launch the Streamlit web application as a separate process.
    2.  Use Playwright to open a browser and navigate to the application's URL.
    3.  Programmatically interact with the UI widgets: select elements from a dropdown, move a temperature slider, type into a text box for the number of steps.
    4.  Click the "Run Pipeline" button.
    5.  The script will then wait and poll the UI for an indicator that the run is complete (e.g., the appearance of a "Done!" message or a rendered molecule).
    6.  Finally, the test will check the file system to assert that the expected output database was created.
    This comprehensive test validates the entire user workflow, from graphical interaction in the browser to the final output of the scientific pipeline.