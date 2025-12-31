# Cycle 05 User Acceptance Testing (UAT)

This document outlines the User Acceptance Testing scenarios for Cycle 05 of the MLIP-AutoPipe project. This final cycle focuses on the user experience, including the command-line interface (CLI), user feedback, documentation, and the overall scientific validity of the end-to-end workflow. These UATs are designed to be performed by a representative end-user and are the final quality gate before the software is considered ready for release. They validate not just that the software works, but that it is usable, helpful, and trustworthy.

## 1. Test Scenarios

| Scenario ID | Scenario Name                                      | Priority |
| :---------- | :------------------------------------------------- | :------- |
| UAT-C05-01  | Intuitive Command-Line Interface Operation         | High     |
| UAT-C05-02  | Informative Feedback During a Long Run             | High     |
| UAT-C05-03  | End-to-End Scientific Benchmark (Silicon)          | High     |
| UAT-C05-04  | Clear and Usable Documentation                     | Medium   |

---

### **Scenario UAT-C05-01: Intuitive Command-Line Interface Operation**

**Description (Min 300 words):**
This scenario tests the usability and robustness of the final command-line interface (CLI), which is the primary point of interaction for the user. A user, representing the target audience of a computational materials scientist (who may not be a software expert), should be able to interact with the program effectively with minimal guidance. The test will involve providing the user with a set of common tasks and observing their ability to complete them using only the CLI itself and its built-in help. For example, the user should be able to easily figure out how to start a new pipeline run, how to specify the required configuration file, and how to get help on available commands and options by running commands like `mlip-pipe --help` and `mlip-pipe run --help`.

The test will also critically evaluate the CLI's error handling. The user will be asked to intentionally make common mistakes, such as providing a path to a non-existent configuration file, providing a path to a directory instead of a file, or creating a config file with a syntax error (e.g., malformed YAML). The expectation is that the CLI will not crash with an obscure, multi-page Python traceback. Instead, it should provide a clear, concise, and user-friendly error message that helps the user immediately understand what went wrong and how to fix it. For instance, `Error: Configuration file not found at path '...'` is a good message; a generic `FileNotFoundError` is not. This scenario is passed if a user can successfully start a run, understand how to use the main options like `--verbose`, and receive helpful, actionable feedback when they make a mistake, all without needing to consult the source code. It validates that the CLI is an effective and robust front-end for the powerful backend engine.

---

### **Scenario UAT-C05-02: Informative Feedback During a Long Run**

**Description (Min 300 words):**
This scenario focuses on the user experience during the pipeline's execution, which can often take minutes or hours. A key objective of this cycle is to make the automated process transparent and to provide the user with a clear understanding of what the system is doing and how much progress has been made at any given time. This test will verify the effectiveness of the structured logging and dynamic progress indicators. The user will initiate a full pipeline run on a moderately complex system that is expected to take at least 10-15 minutes to complete a few active learning generations.

During the run, the user will monitor the console output. The expectation is to see a clear, continuous stream of log messages indicating the current stage of the workflow (e.g., "INFO: Starting structure generation using SQS...", "INFO: Starting MACE exploration for 5 seed structures...", "INFO: Labelling structure 5 of 20..."). For long, iterative tasks, such as the DFT labelling of multiple structures or the steps in an MD simulation, the user should see a persistent progress bar (e.g., from the `rich` library) that shows the percentage completion, the iteration rate (e.g., steps/sec), and an estimated time remaining. If a recoverable error occurs, such as a single DFT calculation failing to converge, it should be clearly logged as a `WARNING`-level message, but it should not halt the overall progress bar or the execution of the rest of the batch. This test is successful if the user feels informed and confident about the system's status throughout the run, transforming the experience from an opaque "black box" into a transparent, observable process that they can trust.

---

## 2. Behavior Definitions

**Scenario: UAT-C05-01 - Intuitive Command-Line Interface Operation**

```gherkin
GIVEN a user has successfully installed the MLIP-AutoPipe package in a clean virtual environment.
WHEN the user opens a new terminal and types `mlip-pipe --help`.
THEN the terminal should display a well-formatted help message showing the main command, 'run'.
AND the help message for 'run' should clearly indicate that it requires a 'CONFIG_FILE' argument and describe what it is.

GIVEN the user has a valid 'input.yaml' file in their current directory.
WHEN the user executes `mlip-pipe run input.yaml`.
THEN the pipeline should start successfully and begin logging its progress.

GIVEN the user tries to execute `mlip-pipe run non_existent.yaml`.
THEN the command should fail immediately before any computation starts.
AND a clear error message should be printed to the console: "Error: Invalid value for 'CONFIG_FILE': Path 'non_existent.yaml' does not exist."

GIVEN the user provides a valid config file but includes the '--verbose' flag: `mlip-pipe run input.yaml --verbose`.
THEN the pipeline should start successfully.
AND the log messages printed to the console should be more detailed, including messages with the `[DEBUG]` level prefix.
```

---

**Scenario: UAT-C05-02 - Informative Feedback During a Long Run**

```gherkin
GIVEN a user has started a full pipeline run that involves labelling 50 structures.
WHEN the `LabellingEngine` begins its work.
THEN a rich progress bar should appear on the console.
AND the progress bar should have a descriptive title like "Labelling Structures".
AND it should display a dynamic count, such as "[5/50]", a percentage, and an estimated time remaining.
AND as each DFT calculation completes, the progress bar should update in real-time.

GIVEN the run enters the active learning phase, configured to run for 10,000 MD steps per generation.
WHEN the `SimulationEngine` starts a simulation.
THEN a new, persistent progress bar should appear for the MD simulation.
AND it should display the current step, the total steps, and the simulation rate (steps/sec).
AND informative log messages, such as "INFO: Starting MD simulation for generation 1 of 5", should be printed cleanly above the progress bar without disrupting it.
```

---

**Scenario: UAT-C05-03 - End-to-End Scientific Benchmark (Silicon)**

```gherkin
GIVEN a user has created a minimal 'input.yaml' file for Silicon containing only:
  """
  system:
    elements: ["Si"]
  """
WHEN the user runs the entire pipeline from start to finish with the command `mlip-pipe run input.yaml`.
THEN the pipeline must complete successfully after several active learning generations without any unhandled errors or crashes.
AND a final MLIP model file, for the last generation, must be generated and saved (e.g., `gen_5/model_ace_0.ace`).
AND the user then runs a separate, provided post-processing script to analyze the final potential.
AND this script calculates the equilibrium lattice constant of a silicon diamond structure using the generated potential.
THEN the calculated lattice constant must fall within a physically reasonable range of 5.2 to 5.7 Angstroms (the known experimental value is ~5.43 A), indicating the potential is not nonsensical.
```

---

**Scenario: UAT-C05-04 - Clear and Usable Documentation**

```gherkin
GIVEN a new user, unfamiliar with the project, wants to learn how to use the software.
WHEN the user opens the main `README.md` file in the project's root directory.
THEN the user should find clear, concise instructions on how to set up a virtual environment and install the package using `uv`.
AND the README should contain a "Quick Start" section with a minimal working example `input.yaml` that the user can copy, and the exact command to run it.

GIVEN the user wants to understand a specific, advanced configuration parameter, like `uncertainty_threshold`.
WHEN the user navigates to the `docs/configuration.md` file.
THEN the user should be able to easily find a section for 'active_learning'.
AND within that section, there should be a clearly marked entry for `uncertainty_threshold`.
AND this entry should explain what the parameter does, what its data type is, and list the possible valid values (e.g., a specific float or the string "dynamic_95percentile").
```
