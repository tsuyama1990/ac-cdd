# Specification: MLIP Structure Generator - CYCLE02

## 1. Summary

This document provides the detailed technical specification for the second development cycle (CYCLE02) of the MLIP Structure Generator. Building upon the robust, command-line-driven core established in CYCLE01, this cycle focuses on significantly expanding the system's capabilities, scientific reach, and user accessibility. The primary objectives are to introduce advanced and more physically realistic simulation techniques, support a wider and more complex range of material systems, implement a more intelligent "smart" sampling algorithm to improve dataset quality, and develop a web-based graphical user interface (GUI) to make the tool accessible to a much wider audience of scientists and students. By the end of this cycle, the generator will evolve from a powerful but expert-focused tool into a comprehensive and user-friendly platform that can tackle a much broader set of problems in materials science research, accelerating discovery and innovation.

The key enhancements in this cycle begin within the Exploration stage. The MD engine will be significantly upgraded to support **hybrid Molecular Dynamics / Monte Carlo (MD/MC)** simulations. This powerful technique is essential for overcoming the sampling limitations of pure MD. This includes the implementation of Monte Carlo "swap moves," which are essential for efficiently sampling the vast combinatorial configuration space of multi-component alloys, a task at which pure MD is notoriously inefficient. We will also implement "vacancy hop" moves to simulate atomic diffusion, a key process in material degradation and evolution. To support these more aggressive and often high-temperature simulations, we will integrate crucial safety and automation features. This includes mixing the MLIP with a classical ZBL potential to prevent unrealistic atomic fusion at short distances, a common failure mode in high-energy simulations. A "Charge Safety" mechanism will also be developed to forbid invalid MC moves in ionic systems that would violate the fundamental law of charge neutrality. Furthermore, an "Auto Ensemble Switching" feature will be introduced, which intelligently detects the system's dimensionality (e.g., bulk vs. surface) and automatically applies the correct thermodynamic ensemble (NPT vs. NVT), simplifying configuration for the user and preventing common, subtle simulation artifacts.

The structure generation capabilities will also be significantly extended beyond the simple alloys and covalent crystals of CYCLE01. We will develop generators for scientifically important and structurally complex systems, including **ionic crystals** (with automated charge neutrality enforcement, a critical physical constraint), **material interfaces** (heterostructures), and **surface adsorption** systems, which are crucial for applications in electronics and catalysis. A knowledge-based generator that can propose plausible initial structures from just a chemical formula by leveraging crystallographic databases will also be implemented, lowering the barrier to entry for new users.

To improve the quality and efficiency of the final dataset, this cycle will see the implementation of a sophisticated **Farthest Point Sampling (FPS)** algorithm, replacing the simple random sampling method from the first cycle. By using SOAP (Smooth Overlap of Atomic Positions) descriptors to map high-dimensional atomic structures into a lower-dimensional feature space, FPS intelligently selects a subset of configurations that are maximally diverse. This ensures the resulting dataset is rich in information and free of redundant structures, which in turn leads to a more efficient and robust training process for the MLIP.

Finally, to dramatically improve usability and accessibility, a **web-based GUI** will be developed. This interface will provide users with an intuitive, interactive way to define their material system, configure complex simulation parameters using clear widgets and menus, launch and monitor jobs in the background, and visualise the resulting atomic structures in 3D directly in their browser. This will lower the barrier to entry significantly, making the powerful features of the generator accessible to researchers and students who are not experts in command-line tools or complex configuration files.

## 2. System Architecture

CYCLE02 introduces several new modules and significantly modifies existing ones to accommodate the advanced features. The overall four-stage pipeline structure (Generate, Explore, Sample, Store) remains the same, providing a stable architectural backbone. However, the components within each stage will become much more sophisticated, and a new top-level package for the web application will be added. The modular design established in CYCLE01 is critical to allowing these extensive changes without destabilizing the entire system.

**File Structure for CYCLE02:**
The file structure will be expanded from CYCLE01. New or significantly modified files for this cycle are marked in **bold**. This clearly shows the addition of new generators, a new sampler, new simulation logic, and the entire web package.

```
nnp-structure-generator/
├── configs/
│   ├── system/
│   │   ├── alloy.yaml
│   │   ├── covalent.yaml
│   │   ├── **ionic.yaml**         # New config for ionic systems
│   │   └── **interface.yaml**     # New config for interface systems
│   └── exploration/
│       ├── default.yaml
│       └── **hybrid_mc.yaml**     # New config for hybrid MD/MC runs
├── src/
│   └── nnp_gen/
│       ├── generators/
│       │   ├── base.py
│       │   ├── alloy.py
│       │   ├── covalent.py
│       │   ├── **ionic.py**         # Generator for ionic compounds
│       │   ├── **interface.py**     # Generator for material interfaces
│       │   ├── **adsorption.py**    # Generator for surface adsorption
│       │   └── **knowledge.py**     # Knowledge-based generator
│       ├── explorers/
│       │   ├── md_engine.py       # Will be significantly modified for MC, etc.
│       │   └── **mc_moves.py**      # New module for all MC move logic
│       ├── samplers/
│       │   ├── base.py
│       │   ├── random.py
│       │   └── **fps.py**           # Farthest Point Sampler implementation
│       ├── storage/
│       │   └── db_writer.py
│       ├── pipeline/
│       │   └── runner.py
│       ├── common/
│       │   ├── physics.py         # Will be modified for vacuum detection
│       │   └── **schemas.py**       # Will be significantly modified for new features
│       ├── utils/
│       │   └── **descriptors.py**   # New utility for calculating SOAP descriptors
│       └── **web/**               # New package for the entire Web UI
│           ├── **__init__.py**
│           ├── **app.py**         # Main Flask/Streamlit application logic
│           └── **templates/**       # Directory for HTML templates for the UI
├── main.py
├── **main_gui.py**                 # The new entry point for launching the Web UI
└── pyproject.toml                # Will be updated with new dependencies (dscribe, flask, etc.)
```

**Component Breakdown:**
This section details the design of the new and modified components, providing a blueprint for their implementation.

*   **`explorers/md_engine.py` -> `MDEngine`**: This class, central to CYCLE01, will be heavily modified to incorporate the advanced simulation logic.
    *   The main simulation loop will be refactored to be able to intersperse MD steps with attempted Monte Carlo moves, the frequency of which will be controlled by user configuration. It will call functions from the new `mc_moves.py` module to execute these.
    *   The `_get_calculator` method will be enhanced to implement potential mixing. Based on a configuration flag, it will return either the pure MLIP calculator or a hybrid calculator that combines the MLIP with the ZBL potential for accurate close-range repulsion.
    *   A new method, `_determine_ensemble`, will be added. This method will be called at the start of a run. It will invoke the `detect_vacuum` function from `common/physics.py` to check for the presence of a vacuum layer and automatically select either the NPT or NVT ensemble, overriding the user's setting if `"auto"` is selected.

*   **`explorers/mc_moves.py`**: This new, self-contained module will encapsulate all the logic for the various Monte Carlo moves. This separation of concerns makes the logic highly testable.
    *   `swap_move(atoms, elements_to_swap)`: A function that attempts to swap two randomly chosen atoms of different specified types, accepting or rejecting the move based on the Metropolis criterion.
    *   `charge_safe_swap(...)`: A critical wrapper function that will be used for ionic systems. It will check the assigned oxidation states of the atoms being swapped and will immediately reject any move that would violate local or global charge neutrality, preventing physically impossible states.

*   **`generators/ionic.py`, `interface.py`, etc.**: These new generator classes will implement the logic for creating their respective complex structures. The `IonicGenerator` is particularly notable as it must include sophisticated logic to ensure the initial structure it creates is perfectly charge-neutral based on the provided oxidation states of the elements. The `InterfaceGenerator` will use ASE's interface-building utilities to join two different crystal slabs.

*   **`common/physics.py`**: This module will be enhanced with the `detect_vacuum` function. This function will implement a robust, grid-based algorithm that discretises the simulation cell, checking the distance from each grid point to the nearest atom. If a contiguous region of grid points is found to be far from any atom (indicating a vacuum layer), the function will return `True`, otherwise `False`.

*   **`samplers/fps.py` -> `FarthestPointSampler`**: This new class will implement the "smart" sampling algorithm, inheriting from `BaseSampler`.
    *   It will have a dependency on a new utility module, `utils/descriptors.py`, which will be responsible for calculating the SOAP descriptors for each structure in a trajectory. This module will use a well-established third-party library like `dscribe`.
    *   The main `sample()` method will orchestrate the process: first, it will call the descriptor utility to compute the SOAP vectors for all candidate structures. Then, it will iteratively build the final dataset by first selecting a random structure, and then repeatedly adding the one structure from the remaining pool that is geometrically "farthest" (in the L2-norm sense of the descriptor vectors) from all previously selected structures.

*   **`main_gui.py` and `web/app.py`**: These files will form the core of the new web interface. We will use a lightweight but powerful framework like Streamlit or Flask for this purpose.
    *   `app.py` will define the UI layout, including pages, tabs, and interactive widgets for setting all the key configuration parameters (e.g., dropdowns for elements, sliders for temperature, file upload for structures).
    *   It will have a "Run" button that, when clicked, will construct the complete Hydra configuration object from the current state of the UI widgets and launch the `PipelineRunner` in a separate, non-blocking background process. This is critical to prevent the UI from freezing during long calculations.
    *   It will include a status area to provide real-time feedback on the job's progress (e.g., "Generating," "Exploring step 5000/10000," "Sampling...") and an integrated 3D molecule viewer (e.g., using `py3Dmol`) to display generated structures.

## 3. Design Architecture

The design in CYCLE02 focuses on extending the Pydantic-based configuration schema to accommodate the new, more complex configurations while ensuring full backward compatibility with configurations from CYCLE01. The architecture promotes the clean separation of complex scientific logic (like descriptor calculation and MC move acceptance) from the main application flow, making the code easier to maintain, test, and reason about.

**Extended Pydantic-based Configuration Schemas:**
The existing schemas from CYCLE01 will be carefully updated to support the new options. Union types and discriminated unions, powerful features of Pydantic, will be used extensively to manage the complexity and ensure that the configuration remains strongly typed and self-documenting.

```python
# In src/nnp_gen/common/schemas.py

from pydantic import BaseModel, Field, conlist
from typing import List, Dict, Literal, Optional, Union

# ... (Existing schemas from CYCLE01, such as BaseGeneratorConfig) ...

# --- NEW GENERATOR SCHEMAS ---
class IonicGeneratorConfig(BaseGeneratorConfig):
    name: Literal["ionic"] = "ionic"
    elements: Dict[str, int] = Field(..., description="Dict of elements to their oxidation states, e.g., {'Na': 1, 'Cl': -1}")
    # ... other params for ionic crystal generation

class InterfaceGeneratorConfig(BaseGeneratorConfig):
    # ... detailed schema for building material interfaces
    name: Literal["interface"] = "interface"

# --- UPDATED EXPLORATION SCHEMA ---
class MCMovesConfig(BaseModel):
    swap_probability: float = Field(0.1, ge=0, le=1, description="Probability of attempting a swap move each step.")
    vacancy_hop_probability: float = Field(0.0, ge=0, le=1)

class MDConfig(BaseModel):
    # ... (existing fields from CYCLE01) ...
    ensemble: Literal["NVT", "NPT", "auto"] = Field("auto", description="Set to 'auto' to enable automatic ensemble detection for surfaces.")
    use_zbl_mixing: bool = Field(True, description="Whether to mix in ZBL potential for close-range repulsion.")
    mc_moves: Optional[MCMovesConfig] = None

# --- UPDATED SAMPLING SCHEMA ---
class RandomSamplerConfig(BaseModel):
    method: Literal["random"] = "random"

class FPSSamplingConfig(BaseModel):
    method: Literal["fps"] = "fps"
    # ... other FPS specific params like descriptor type

class MainSamplingConfig(BaseModel):
    # Use a discriminated union for the method, ensuring only one sampler's config is present
    sampler: Union[RandomSamplerConfig, FPSSamplingConfig] = Field(..., discriminator='method')
    n_samples: int = Field(100, gt=0)

# --- UPDATED MAIN SCHEMA ---
class MainConfig(BaseModel):
    generator: Union[AlloyGeneratorConfig, CovalentGeneratorConfig, IonicGeneratorConfig, InterfaceGeneratorConfig] = Field(..., discriminator='name')
    exploration: MDConfig
    sampling: MainSamplingConfig
    # ...
```

**Consumers and Producers:**
*   **Producers:** The `MDEngine` remains the primary data producer, but now its output trajectory is much richer, having been influenced by stochastic MC moves. The new generator classes are also significant producers of more complex initial `Atoms` objects. A key new intermediate producer is the `SOAPDescriptorCalculator` in `utils/descriptors.py`; it consumes `Atoms` objects and produces numerical descriptor vectors.
*   **Consumers:** The `FarthestPointSampler` is a key new consumer. It is unique in that it consumes two distinct types of data: the `Atoms` objects from the trajectory and the descriptor vectors from the utility module. It uses both to produce the final curated list of structures. The Web UI is a new high-level consumer of the final database file, reading it to visualise structures for the user.

**Key Invariants and Constraints:**
*   **Charge Neutrality:** For any structure generated by the `IonicGenerator`, the sum of the oxidation states of all atoms must be exactly zero. This invariant will be programmatically enforced within the generator and will be a key assertion in its unit tests.
*   **MC Move Validity:** The `charge_safe_swap` function must ensure that any proposed atom swap in an ionic system does not result in a violation of charge neutrality. This is a hard constraint that must never be violated.
*   **Descriptor Consistency:** The dimensionality and parameters (e.g., cutoff radius) of the SOAP descriptor vectors must be consistent for all structures within a single sampling run. The `FarthestPointSampler` will be responsible for enforcing this.

## 4. Implementation Approach

The implementation for CYCLE02 will be carefully staged to tackle the most significant architectural changes first, followed by the discrete feature additions. This ensures a stable base for building the more complex functionalities. A test-driven development (TDD) approach will be used for critical new logic, especially for the physics and mathematics-heavy parts like the MC moves and FPS algorithm.

1.  **Refactor Configuration:** The first and most critical step is to update the Pydantic schemas in `common/schemas.py` and create corresponding new YAML configuration files. This includes the significant architectural change of refactoring the sampling configuration to use a discriminated union. This change must be made carefully to maintain backward compatibility with CYCLE01 configurations.

2.  **Implement Physics Utilities:** Develop the `detect_vacuum` function in `common/physics.py`. This is a prerequisite for the auto-ensemble switching feature. It is a pure function with no side effects and can be developed and unit-tested in isolation early in the cycle.

3.  **Enhance MD Engine:**
    *   Modify the `MDEngine` to incorporate the `detect_vacuum` logic and implement the automatic switching between NVT and NPT ensembles based on the `ensemble: "auto"` setting.
    *   Integrate the ZBL potential mixing. This will involve modifying the `_get_calculator` method to use a hybrid calculator, likely using ASE's `Combo` calculator or a similar utility.
    *   Implement the framework for adding MC moves. The main run loop will be modified to call a (currently empty) MC move function at regular intervals, based on the `mc_moves` configuration.

4.  **Implement MC Moves:** Develop the `mc_moves.py` module in its entirety. Implement the basic `swap_move` and the crucial `charge_safe_swap` wrapper. Write extensive and rigorous unit tests for this logic, as its physical correctness is paramount to the scientific validity of the tool's output.

5.  **Develop Advanced Generators:** Implement the new generator classes one by one, starting with `IonicGenerator` due to its dependency on the charge safety logic. Each generator will be developed in its own file and will be accompanied by its own dedicated set of unit tests.

6.  **Implement FPS Sampler:** This is another major, self-contained task.
    *   First, implement the `utils/descriptors.py` module to compute the SOAP descriptors. This will require adding a new dependency, `dscribe`, to the `pyproject.toml` file and writing a wrapper to simplify its use within our pipeline.
    *   Once the descriptor calculation is working and tested, implement the `FarthestPointSampler` class in `samplers/fps.py`, including the core mathematical logic for finding the "farthest" point in each iteration.

7.  **Develop Web Interface:** This will be the final major implementation step of the cycle.
    *   Set up the basic Streamlit or Flask application in `web/app.py` and create the new entry point `main_gui.py`.
    *   Build the UI components for configuration, using widgets to represent the fields in our Pydantic schemas. This ensures consistency between the CLI and GUI.
    *   Implement the logic to launch the pipeline in a background process. This is critical to ensure the UI remains responsive. A simple `subprocess.Popen` will be used initially, with the possibility of upgrading to a more advanced task queue like Celery in the future if needed.
    *   Integrate a JavaScript-based molecule viewer like `py3Dmol` to display structures from the final database directly in the browser.

## 5. Test Strategy

Testing in CYCLE02 will be significantly more extensive than in the first cycle, covering the new complex physics, the mathematical correctness of the sampling algorithm, and the usability and responsiveness of the new web interface. The testing pyramid (unit, integration, system/E2E) will be strictly adhered to.

**Unit Testing Approach (Min 300 words):**
Unit tests will form the base of our quality assurance. They will be fast, isolated, and comprehensive.
*   **Advanced Generators:** The `IonicGenerator` will be tested to assert that every single structure it generates is perfectly charge-neutral. The `InterfaceGenerator` will have tests to verify that the two slabs are correctly oriented, that the interface is properly formed, and that the vacuum layer has the correct thickness.
*   **MC Moves:** The `swap_move` function will be tested on a simple binary `Atoms` object, and we will assert that after the move, the positions of two different atoms have been correctly exchanged. The `charge_safe_swap` wrapper is critical and will be tested with an ionic `Atoms` object; we will test both a valid swap (e.g., a Na+ ion for another Na+ ion) which should be allowed, and an invalid swap (e.g., a Na+ ion for a Cl- ion) which must always be rejected.
*   **Physics Utilities:** The `detect_vacuum` function is critical for automation and will be tested with multiple scenarios: a bulk crystal (should return `False`), a slab with a vacuum layer on the z-axis (should return `True`), and a single isolated molecule in a large box (should also return `True`).
*   **FPS Sampler:** The mathematical logic of the FPS sampler will be unit-tested in isolation from the complex SOAP descriptors. We will create a small, known set of 2D vectors (representing simplified descriptors) and assert that the sampler selects them in the correct, maximally-distant order. This verifies the core algorithm's correctness.
*   **Descriptor Calculation:** The `utils/descriptors.py` module will be tested to ensure it produces descriptor vectors of the correct shape and `dtype` and that the calculation runs without errors for a simple `Atoms` object. We will also test its error handling for invalid inputs.

**Integration Testing Approach (Min 300 words):**
Integration tests will ensure that the newly developed components work correctly with the existing pipeline from CYCLE01.
*   **Hybrid MD/MC Pipeline:** A full end-to-end integration test will be run for a binary alloy using the new hybrid MD/MC exploration mode. After the run, we will load the resulting trajectory and programmatically check that atom swaps have actually occurred by tracking the indices of specific elements over time. This provides definitive proof that the MC moves are being correctly integrated into the MD simulation loop.
*   **Auto-Ensemble Switching:** A key integration test will be to run the pipeline on a surface slab system with the `ensemble` configuration parameter set to `auto`. We will need to capture the log output from the application (e.g., by redirecting stdout) and assert that the log contains a specific, unambiguous message indicating that a vacuum was detected and that the NVT ensemble was chosen. This verifies the correct integration of the `detect_vacuum` utility into the `MDEngine`.
*   **FPS vs. Random Sampling:** We will run two parallel integration tests on the same simple system for the same number of steps. One will use the `random` sampler, and the other will use the new `fps` sampler. While we cannot assert the scientific "quality" of the data in a simple test, we can perform a quantitative check: we will calculate the average pairwise distance between the SOAP descriptors of the final sampled structures. We would expect and assert that the average distance for the FPS-sampled set is significantly larger than for the randomly-sampled set, providing a strong quantitative check that the FPS algorithm is working as intended.
*   **Web UI Backend Test:** We will write a test that uses a library like `requests` or a test client provided by Flask/Streamlit to post a valid JSON configuration to a specific endpoint in the backend. This test will bypass the browser UI and directly test the backend logic that launches the pipeline, asserting that a background process is started successfully and that we can poll a status endpoint to see its progress.
