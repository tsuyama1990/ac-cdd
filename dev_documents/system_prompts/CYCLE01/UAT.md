# User Acceptance Testing (UAT): Cycle 1

This document outlines the User Acceptance Testing scenarios for the initial release of the MLIP-AutoPipe command-line tool. The goal of these tests is to verify that the core pipeline is functional, robust, and produces the expected outputs from a user's perspective. These tests are designed to be run by a user to confirm that the software meets their basic requirements for dataset generation.

A Jupyter Notebook, `CYCLE01_UAT.ipynb`, will be provided to guide the user through these tests interactively. The notebook will contain cells to help set up the necessary configuration files, run the CLI command, and then programmatically inspect the output database to verify the results, providing a clear pass/fail assessment for each scenario. This interactive approach is designed to not only test the software but also to serve as a practical tutorial, giving users hands-on experience and building their confidence in the tool's capabilities from the very beginning.

## 1. Test Scenarios

| Scenario ID | Priority | Description                                                                 |
| :---------- | :------- | :-------------------------------------------------------------------------- |
| UAT-C1-001  | High     | Verify a successful end-to-end pipeline run for a simple binary alloy.      |
| UAT-C1-002  | High     | Verify the tool handles invalid configuration with clear error messages.    |
| UAT-C1-003  | Medium   | Verify the output database contains the correct number of sampled structures. |
| UAT-C1-004  | Medium   | Verify that pipeline components respect the key configuration parameters.   |

---

### **Scenario UAT-C1-001: Successful End-to-End Pipeline Run**

*   **Priority:** High
*   **Description:** This is the most fundamental and critical test for the application, representing the primary "happy path." Its purpose is to confirm that a user can, with a valid and minimal configuration, execute the entire data generation pipeline from start to finish without any errors. This test is a comprehensive validation of the integration between all four core components: Generation, Exploration, Sampling, and Storage. A successful run demonstrates that the data flows correctly between each stage, that file I/O operations are handled properly, and that the final output is a well-formed, usable database. The user experience for this core task should feel seamless and reliable. The accompanying Jupyter Notebook will provide a pre-written, valid YAML configuration for a simple system, like a Copper-Gold (CuAu) alloy. The user will execute a single cell that runs the `mlip-autopipec` command-line tool. The notebook will then automatically check for the existence of the expected output files (`initial_structures.xyz`, `trajectory.xyz`, `results.db`). Finally, it will use the ASE library to connect to the `results.db` file, read a few entries, and confirm that it contains valid atomic structure data. This provides the user with immediate, tangible proof that the software has successfully completed its core mission, building a strong foundation of trust in its capabilities. This scenario is not just a test; it's the user's first successful interaction, making its clarity and success paramount.
*   **Success Criteria:**
    *   The CLI command executes without any Python tracebacks, crashes, or logged errors, exiting cleanly with a status code of 0.
    *   The command produces all the expected output files in the specified working directory: `initial_structures.xyz`, `trajectory.xyz`, and `results.db`.
    *   The final `results.db` is a valid ASE database file. This can be verified by successfully connecting to it using `ase.db.connect()`. The database must contain at least one table and should not be an empty or corrupted file.

---

### **Scenario UAT-C1-002: Invalid Configuration Handling**

*   **Priority:** High
*   **Description:** The robustness and user-friendliness of a command-line tool are often best measured by how it behaves when given incorrect input. This test scenario is designed to verify that the application's configuration validation, powered by Pydantic, is functioning correctly and provides clear, actionable feedback to the user. A tool that fails with a cryptic error message can be incredibly frustrating. This test ensures MLIP-AutoPipe guides the user towards correcting their mistakes. The UAT notebook will present the user with a series of deliberately flawed YAML configuration files. Examples will include common mistakes: a `composition` dictionary whose values do not sum to 1.0, a required field (like `elements`) being completely omitted, a parameter with an incorrect data type (e.g., `temperature_k: "hot"` instead of a number), or an unknown parameter being added to the configuration, which should be caught by Pydantic's `extra='forbid'` setting. For each of these invalid files, the user will execute the CLI command. The expected outcome is not a successful run, but a controlled failure. The tool must exit gracefully with a non-zero status code and, most importantly, print a human-readable error message that pinpoints the exact location and nature of the problem in the configuration file. This immediate, precise feedback is essential for a positive user experience.
*   **Success Criteria:**
    *   For each invalid configuration file, the CLI command must exit with a non-zero status code, which is the standard convention for indicating an error in shell environments.
    *   A clear, informative error message must be printed to the standard error stream. The message should be specific, for example: "Validation Error: `system.composition` - values must sum to 1.0" or "Validation Error: field `exploration.temperature_k` - expected a number but received a string."
    *   The application must not create any partial output files. The working directory should be clean, with no `.xyz` or `.db` files generated from the failed run.

---

### **Scenario UAT-C1-003: Verification of Sample Count in Output Database**

*   **Priority:** Medium
*   **Description:** This test focuses on verifying that the Sampling stage of the pipeline correctly adheres to the user's specified parameters. When a user requests a specific number of samples for their final dataset, they need to be absolutely certain that the output database contains precisely that number. This scenario builds confidence in the tool's reliability and precision. The UAT Jupyter notebook will instruct the user to set up a valid configuration file and to specify a non-default number for the `num_samples` parameter within the `sampling` section (e.g., 75). After the user executes the pipeline command, the notebook will provide a code cell that uses the ASE database API to connect to the resulting `results.db` file. This script will perform a query to count the total number of rows in the database. The notebook will then display this count and compare it directly to the `num_samples` value that the user set in the configuration. A clear "Pass" or "Fail" message will be displayed based on whether these two numbers match exactly. This provides an unambiguous and automated verification that the sampling component is functioning as specified, ensuring the user has full control over the size of their final dataset. This is important for reproducibility and for managing dataset sizes for machine learning experiments.
*   **Success Criteria:**
    *   The pipeline must complete successfully without any errors.
    *   A valid `results.db` file must be created.
    *   When queried, the number of rows in the `results.db` file must exactly match the integer value provided for the `num_samples` key in the YAML configuration file used for the run. There should be no off-by-one errors or discrepancies.

---

### **Scenario UAT-C1-004: Component Configuration Adherence**

*   **Priority:** Medium
*   **Description:** This scenario expands on the principle of the previous test to verify that other key components are also correctly interpreting and acting upon the user's configuration settings. A trustworthy tool must be configurable and transparent in its operations. This test gives the user confidence that the parameters they set are having a real effect on the pipeline's behaviour. The UAT notebook will guide the user through a two-part verification process. In the first part, the user will set the `num_initial_structures` parameter in the `generation` section of their configuration file to a specific value (e.g., 5). After running the pipeline, a script will read the intermediate `initial_structures.xyz` file and count the number of atomic configurations it contains, asserting that it matches the user's setting. In the second part, the user will set the `num_steps` parameter in the `exploration` section (e.g., 250). After the run, another script will read the `trajectory.xyz` file, which contains all the frames from the MD simulation, and will assert that the number of frames is equal to `num_steps`. These checks on intermediate files provide valuable insight into the pipeline's internal workings and confirm that the Generation and Exploration stages are being controlled correctly by the configuration.
*   **Success Criteria:**
    *   The number of distinct structures contained within the `initial_structures.xyz` file must be exactly equal to the `num_initial_structures` parameter from the config file.
    *   The number of frames (atomic configurations) within the `trajectory.xyz` file must be exactly equal to the `num_steps` parameter from the config file.

---

## 2. Behavior Definitions

The following section defines the expected behavior for each test scenario in the Gherkin syntax, which follows a Given-When-Then structure. This provides a clear, unambiguous, and non-technical description of the system's expected behavior from a user's perspective. It serves as a direct link between the software's functionality and the user acceptance criteria, forming a shared understanding of what "correct" means for each feature. These definitions are not just for testing; they document the intended user experience. For example, the definition for a successful run explicitly lists all the files the user should expect to see, setting a clear expectation. Similarly, the definition for invalid configuration handling specifies that the error message must be informative, making user-friendliness a formal requirement of the system. The Jupyter Notebook provided for UAT will be structured to mirror these definitions, with sections for setting the "Given" preconditions, executing the "When" action, and then programmatically verifying the "Then" outcomes. This tight coupling between this document and the interactive test environment ensures that the UAT process is both rigorous and easy to follow.

### **UAT-C1-001: Successful End-to-End Pipeline Run**

```gherkin
GIVEN a valid configuration file named "config.yaml" is present in the current directory
  AND this file specifies a binary alloy system (e.g., CuAu)
  AND all necessary command-line tools and dependencies are installed
WHEN the user executes the command "mlip-autopipec --config config.yaml" in their terminal
THEN the command should execute without printing any error messages or tracebacks
  AND the command should finish and exit with a status code of 0, indicating success
  AND a file named "initial_structures.xyz", containing the generated seed structures, should be created in the current directory
  AND a file named "trajectory.xyz", containing the frames from the molecular dynamics simulation, should be created
  AND a final database file named "results.db" should be created
  AND the "results.db" file should be a valid, non-empty SQLite file that can be opened by the ASE database library
```

### **UAT-C1-002: Invalid Configuration Handling**

```gherkin
GIVEN a configuration file named "invalid_config.yaml" is present
  AND this file contains a specific, known error (e.g., the composition values sum to 0.9 instead of 1.0)
WHEN the user executes the command "mlip-autopipec --config invalid_config.yaml"
THEN the command should fail quickly, without attempting to run the full pipeline
  AND the command should exit with a non-zero status code, indicating an error occurred
  AND a clear error message should be printed to the console
  AND this message must identify the part of the configuration that is invalid (e.g., "system.composition")
  AND no output files like "initial_structures.xyz", "trajectory.xyz", or "results.db" should be created
```

### **UAT-C1-003: Verification of Sample Count in Output Database**

```gherkin
GIVEN a valid configuration file "config.yaml" is present
  AND in this file, the "sampling.num_samples" parameter is set to a specific integer, for example, 50
WHEN the user successfully executes the pipeline using the command "mlip-autopipec --config config.yaml"
THEN a final database file named "results.db" should be created
  AND a script connecting to this database
  SHOULD find that the total number of rows in the main table is exactly 50
```

### **UAT-C1-004: Component Configuration Adherence**

```gherkin
GIVEN a valid configuration file "config.yaml" is present
  AND in this file, "generation.num_initial_structures" is set to 5
  AND in this file, "exploration.num_steps" is set to 100
WHEN the user successfully executes the pipeline using this configuration
THEN an intermediate file named "initial_structures.xyz" should be created
  AND this file should contain exactly 5 atomic structures
  AND an intermediate file named "trajectory.xyz" should be created
  AND this file should contain exactly 100 atomic simulation frames
```