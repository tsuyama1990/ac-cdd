# User Acceptance Testing (UAT): MLIP Structure Generator - CYCLE01

This document outlines the User Acceptance Testing (UAT) plan for the first development cycle of the MLIP Structure Generator. The primary goal of this UAT is to provide a clear, user-friendly, and hands-on guide to verify that the core functionalities delivered in this cycle meet the project's objectives. We have intentionally designed these tests not just as rote checks, but as interactive tutorials that guide a new user through the most common workflows. To this end, we highly recommend using a Jupyter Notebook to execute these test scenarios. This environment allows you to run the command-line instructions, immediately inspect the output files, and even visualise the generated atomic structures in 3D, providing a much richer and more intuitive learning experience than a simple command-line interface. This approach turns the process of acceptance testing into a practical exploration of the tool's capabilities, empowering the user to understand both what the tool does and how to use it effectively for their own research. Each scenario is designed to build confidence and familiarity with the software's core features.

## 1. Test Scenarios

Here we present a series of test scenarios designed to validate the key features of the application as delivered in CYCLE01. Each scenario includes a unique ID for tracking purposes, a priority level to indicate its importance, and a detailed, tutorial-style description of the steps to follow and the expected outcomes.

### **Scenario ID: UAT-C01-01**
**Priority: High**
**Title: Generate a Training Dataset for a Binary Alloy (Copper-Gold)**

**Description (Min 300 words):**
This is the primary "happy path" scenario and is designed to serve as the main tutorial for any new user of the software. Its purpose is to verify the entire end-to-end pipeline for a common and well-understood materials science use case: generating a training dataset for a binary alloy. We will use the Copper-Gold (CuAu) system as our example, as it is a classic case study. The user will begin by creating a simple YAML configuration file that defines the elements ('Cu', 'Au'), their composition (50% of each), the desired crystal structure ('fcc'), and the parameters for a short molecular dynamics simulation (e.g., temperature, number of steps). They will then execute the main application from the command line, using a simple command like `python main.py --config-path configs --config-name alloy_config`, pointing the tool to their newly created configuration. The test is considered successful if the application runs to completion without any errors or crashes, and produces a valid, non-empty ASE database file at the path specified in the configuration.

This single scenario implicitly tests several of the most critical components of the system in concert. It first validates the `AlloyGenerator`'s ability to create a physically plausible starting structure with the correct chemical composition and lattice. It then thoroughly tests the `MDEngine`'s capacity to take this initial structure and run a stable Molecular Dynamics simulation at a specified temperature, exploring nearby configurations. It also confirms that the parallel processing mechanism is functioning correctly, as the exploration will be distributed across available CPU cores, which the user could verify by observing their system's CPU usage during the run. Finally, it verifies that the `RandomSampler` correctly selects the specified number of structures from the simulation trajectory and that the `DBWriter` successfully saves these structures and their associated metadata into the final database file. A user following this tutorial will not only confirm that the system works as advertised but will also learn the fundamental workflow of using the software: defining a material system, running the pipeline, and obtaining the final, ready-to-use dataset. For an enhanced experience in a Jupyter Notebook, the user can add a final cell to open the generated `cu_au_dataset.db` file using ASE's library and visualise one of the atomic structures, providing tangible, visual proof of success.

### **Scenario ID: UAT-C01-02**
**Priority: High**
**Title: Generate a Training Dataset for a Covalent Material (Silicon)**

**Description (Min 300 words):**
This scenario is designed to verify that the system is not limited to a single class of materials and demonstrates the modularity of the generator framework. It tests the pipeline's flexibility by targeting a covalent material, specifically Silicon in the diamond crystal structure. This is another critical use case, as many of the most technologically important semiconductor materials fall into this category. The process for the user is very similar to the first scenario, but it involves creating and using a different configuration file, thereby demonstrating the power and flexibility of the Hydra-based configuration system. The user will create a second configuration file, this time specifying the `covalent` generator, the element 'Si', and the 'diamond' crystal structure. They can also specify a different set of simulation parameters, perhaps a higher temperature, to explore the stability of the silicon crystal.

Successfully completing this test provides a high degree of confidence in the system's robustness and generality. It confirms that the `CovalentGenerator` is working correctly and that it can produce a valid initial structure for a non-alloy material with strong, directional bonds. It also further validates that the downstream components of the pipeline—the MD engine, the sampler, and the database writer—are robust enough to handle different types of inputs and potential energy landscapes. For example, the bonding characteristics and atomic coordination of Silicon are very different from those of a metallic alloy, so this test provides confidence in the general applicability of the simulation engine. From a user's perspective, this scenario is a crucial lesson in how to adapt the configuration file to model different kinds of materials, highlighting the ease with which the system can be targeted at new scientific problems. In a Jupyter Notebook environment, the user could directly compare the final structures from this test with those from the alloy test, for example by plotting the radial distribution function for each, visually observing the distinct crystallographic signatures of a face-centred cubic alloy versus a diamond-like covalent solid. This reinforces their understanding of the software's capabilities and the physics it is simulating.

### **Scenario ID: UAT-C01-03**
**Priority: Medium**
**Title: Verify Graceful Failure with an Invalid User Configuration**

**Description (Min 300 words):**
A robust and user-friendly system should not only work correctly with valid input but also fail gracefully and informatively when given incorrect or physically implausible input. This scenario tests the system's input validation and error-handling capabilities, which are crucial for a good user experience. The user will be instructed to create a deliberately flawed configuration file. For instance, they could define an alloy with a lattice constant so small that the atoms in the initial structure will physically overlap, a common and easy mistake for a novice user to make. Another possible invalid configuration would be to define an alloy composition where the fractions do not sum to 1.0. The goal of this test is not to produce a dataset but to verify that the application identifies the error at the earliest possible stage, provides a clear and understandable error message to the user, and terminates cleanly without crashing or producing a corrupted or empty output file.

This test is crucial for building user trust and for teaching the user the constraints of the system. A system that crashes with a cryptic traceback is frustrating and difficult for a non-expert to debug. By running this scenario, we verify that the validation logic implemented in the Pydantic schemas and the `BaseGenerator` (specifically, the `overlap_check`) is correctly integrated into the pipeline and is triggered before any expensive computations are started. We also confirm that the application's exit codes are meaningful (i.e., it returns a non-zero exit code on failure), which is important for users who may wish to incorporate the tool into larger automated shell scripts. For the user, this tutorial is an important lesson in what constitutes a valid configuration. By seeing a clear error message like "PydanticValidationError: Alloy composition must sum to 1.0" or "PhysicsViolationError: Atoms are too close," they learn about the physical and logical constraints the system enforces. In a Jupyter Notebook, the user can execute the command in a cell and inspect the captured standard error stream, seeing the exact, helpful error message that the application produces, which is a valuable diagnostic lesson.

## 2. Behavior Definitions

The following are Gherkin-style (GIVEN/WHEN/THEN) definitions that describe the expected behavior of the system in precise, unambiguous terms for each of the test scenarios. This format is designed to be easily understood by all stakeholders, including developers, testers, and end-users. It connects the user's actions directly to the system's expected responses and outcomes, forming a clear and verifiable set of requirements for the successful completion of the cycle.

---

**Scenario: UAT-C01-01 - Generate a Training Dataset for a Binary Alloy (Copper-Gold)**

*   **GIVEN** I have a working and correct installation of the MLIP Structure Generator software.
*   **AND** I have created a valid YAML configuration file named `cuau_config.yaml` in my `configs/system` directory.
*   **AND** the configuration file specifies the use of the `alloy` generator.
*   **AND** the generator is configured for the elements `Cu` and `Au` with a `composition` of `{"Cu": 0.5, "Au": 0.5}`.
*   **AND** the configuration file specifies a short Molecular Dynamics exploration run at a `temperature_K` of 300.
*   **AND** the configuration file specifies the use of the `random` sampler to select exactly 10 structures.
*   **AND** the configuration specifies the final output database path as `cu_au_dataset.db`.
*   **WHEN** I execute the generator from my command line with the command: `python main.py system=cuau_config`.
*   **THEN** the application should start up, correctly parse the configuration, and begin the pipeline execution without raising any immediate errors.
*   **AND** the process should run to completion, showing progress for the exploration and sampling stages.
*   **AND** the process should complete successfully and exit with a status code of 0.
*   **AND** a new file named `cu_au_dataset.db` should be created in the current working directory.
*   **AND** the created database file should be a valid, non-empty ASE SQLite database.
*   **AND** when inspected, the database should be shown to contain exactly 10 atomic structures.

---

**Scenario: UAT-C01-02 - Generate a Training Dataset for a Covalent Material (Silicon)**

*   **GIVEN** I have a working and correct installation of the MLIP Structure Generator software.
*   **AND** I have created a valid YAML configuration file named `si_config.yaml` in my `configs/system` directory.
*   **AND** the configuration file specifies the use of the `covalent` generator.
*   **AND** the generator is configured for the element `Si` and the `diamond` crystal structure.
*   **AND** the configuration file specifies a short Molecular Dynamics exploration run at a `temperature_K` of 500.
*   **AND** the configuration file specifies the final output database path as `si_dataset.db`.
*   **WHEN** I execute the generator from my command line with the command: `python main.py system=si_config`.
*   **THEN** the application should start, run the full pipeline to completion.
*   **AND** the process should exit cleanly with a status code of 0, indicating success.
*   **AND** a new file named `si_dataset.db` should be created in the current working directory.
*   **AND** the database file should be a valid ASE database that can be read by standard materials science tools.
*   **AND** the database should contain the number of structures that were specified in the default sampling configuration.

---

**Scenario: UAT-C01-03 - Verify Graceful Failure with an Invalid User Configuration**

*   **GIVEN** I have a working and correct installation of the MLIP Structure Generator software.
*   **AND** I have created a deliberately invalid YAML configuration file named `invalid_config.yaml`.
*   **AND** the configuration file specifies an `alloy` generator with a `lattice_constant` so small that atoms will certainly overlap (e.g., 1.0 Angstrom).
*   **WHEN** I execute the generator from my command line with the command: `python main.py system=invalid_config`.
*   **THEN** the application should start but should terminate prematurely, before beginning the computationally expensive exploration stage.
*   **AND** the application must print a clear, human-readable error message to the console or log.
*   **AND** the error message should explicitly state the nature of the physical violation, for example, "PhysicsViolationError: Initial structure has overlapping atoms."
*   **AND** the process should exit with a non-zero status code, indicating that a failure has occurred.
*   **AND** no output database file with the specified name should be created.
