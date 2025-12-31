# Cycle 05 Specification: User Interface, Finalisation, and Documentation

## 1. Summary

Cycle 05 is the final and crucial phase of the MLIP-AutoPipe project, focusing on transforming the powerful, automated backend into a polished, user-friendly, and robust scientific software package. While the previous cycles have built a technologically sophisticated engine capable of autonomous potential generation and refinement, this cycle is dedicated to the user experience, overall system reliability, and the comprehensive documentation necessary for the project's adoption, usage, and future development. The primary goal is to ensure that the system is not just functional but also accessible, intuitive, and trustworthy for its target audience of computational materials scientists, who may be experts in their domain but not necessarily in software engineering or machine learning. This cycle is about building the bridge between the complex internal logic and the end user.

The first major component of this cycle is the development of a clean, powerful, and intuitive Command-Line Interface (CLI). This will be the main, and initially only, entry point for users. It will be built using the `click` library to provide a structured, self-documenting, and user-friendly experience. The CLI will be designed to make running complex, multi-stage workflows simple, with clear commands, arguments, and options. It will also incorporate robust validation for user inputs (like checking for the existence of config files) to provide immediate, helpful feedback and prevent frustrating errors deep into a long run.

The second focus is on providing informative user feedback during execution. Long-running scientific workflows can often feel like a frustrating "black box." This cycle will address that by implementing a comprehensive, structured logging system and integrating rich progress indicators for iterative tasks. Users will be kept informed of the pipeline's status at every stage, from DFT calculations to MLIP training, making the process transparent, debuggable, and engaging. This is not merely a cosmetic feature; it is essential for building user trust in the autonomous decisions the system is making.

Finally, this cycle will culminate in the creation of comprehensive documentation and a suite of rigorous end-to-end benchmark tests. The internal code will be thoroughly documented with docstrings to aid future maintenance and extension. More importantly, extensive user-facing documentation, including a top-level `README.md`, detailed tutorials, and example use cases, will be created to lower the barrier to entry. The benchmark tests will serve as the ultimate validation of the entire pipeline, running it on well-understood materials to confirm that the generated potentials are not only produced successfully but are also scientifically sound. This provides the final stamp of approval and ensures the reliability of the software as a whole.

## 2. System Architecture

The system architecture remains largely unchanged in this cycle, as the focus is on the user-facing layer and overall system hardening rather than adding new core computational modules. The primary architectural addition is the formalisation of the Command-Line Interface (CLI) as the single, well-defined entry point for the entire system, ensuring a clean separation between the user interaction layer and the backend workflow engine.

The architectural layers can be visualized as follows:
1.  **User Interaction Layer:** The user interacts exclusively with the `mlip-pipe` command-line tool. This is the public API of the application.
2.  **CLI Module (`cli.py`):** This module acts as the "front door" or the controller in a model-view-controller (MVC) paradigm. It is responsible for parsing all user commands, options, and arguments using the `click` library. Its primary role is to validate the user's input at the earliest possible stage (e.g., checking that the config file path exists) and then to instantiate and invoke the `WorkflowOrchestrator` with the correct, validated parameters. It also takes responsibility for configuring system-wide concerns, most notably the logging system. Based on user flags like `-v` or `--verbose`, it will set the appropriate logging level (e.g., INFO, DEBUG) for the entire application.
3.  **Workflow Orchestration Layer (`orchestrator.py`):** The `Orchestrator` and the core modules (A-E) function as before, representing the core business logic of the application. However, a significant architectural refinement in this cycle is the replacement of all `print` statements with structured logging calls. Instead of printing directly to the console, modules will emit log records through a standard logging interface (like Python's built-in `logging` module). These log records will contain not just the message but also metadata such as the severity level (INFO, WARNING, ERROR) and the module of origin.
4.  **Presentation Layer:** The CLI module, having configured the logging system, determines how these log records are presented to the user. For console output, it will set up a handler that formats the log records into human-readable messages. This design ensures a clean separation between the user interface logic (in the CLI) and the core scientific workflow logic (in the orchestrator and modules). The core modules don't know *how* their messages will be displayed, only that they need to report their status. This makes the backend more modular and easier to test, and allows for future extensions, such as adding a file-based logger or integrating with a GUI, without changing any of the core scientific code. The CLI is a thin, user-friendly layer on top of the powerful engine built in previous cycles.

This formalized, layered architecture is a hallmark of mature, well-designed applications and is crucial for the long-term maintainability and extensibility of the project.

## 3. Design Architecture

The design for Cycle 05 focuses on the implementation details of the CLI, the logging framework, the presentation of progress, and the structure of the project's documentation.

**Key Classes and Modules:**

*   **`cli.py`:** This file will be the heart of the user interaction layer.
    *   It will be structured using decorators from the `click` library to create a clean, declarative command structure.
    *   `@click.group()`: A main command group `mlip-pipe` will be defined to serve as the root for all commands.
    *   `@mlip_pipe.command()`: A primary command, `run`, will be the main entry point for executing the pipeline.
    - ` @run.argument('config_file', type=click.Path(exists=True, dir_okay=False))`: The command will take the path to the configuration file as a mandatory argument. `click`'s built-in `Path` type will be used to automatically handle the validation that the file exists and is not a directory, providing immediate, clear feedback to the user.
    *   `@run.option('--verbose', '-v', is_flag=True, help='Enable verbose logging output for debugging.')`: An option to control the logging level, allowing users to see more detailed information when troubleshooting.
    *   `@run.option('--resume', is_flag=True, help='Resume a previously failed run from the last completed step.')`: A potential advanced feature to allow the orchestrator to check the database and intelligently pick up where it left off, avoiding re-computation.

*   **Logging Configuration (`utils/logging_utils.py`):**
    *   A new utility file will be created to centralize the configuration of the application's logger.
    *   A function `setup_logger(level: str = 'INFO')` will be defined. It will get the root logger, remove any default handlers, and add a custom-formatted handler.
    *   The format will be designed for readability, including a timestamp, the log level, and the message (e.g., `[2023-10-27 10:30:00] [INFO] Starting DFT labelling for 50 structures.`).
    *   The CLI's `run` command will call this `setup_logger` function at the very beginning, passing 'DEBUG' if the `--verbose` flag is present, and 'INFO' otherwise.

*   **Progress Indicators:**
    *   To provide a richer, more dynamic user experience for long-running tasks, the `rich` library will be chosen over `tqdm` due to its more extensive formatting capabilities and better integration with logging.
    *   The `rich.progress` module will be used to display progress bars. These will be implemented in the key loops of the application:
        *   `LabellingEngine`: A progress bar will be wrapped around the loop that iterates through the list of structures to be calculated, showing `[5/20]`.
        *   `ExplorerSampler`: A progress bar will show the progress of the MD simulation steps.
        *   `Orchestrator`: A top-level progress bar will show the overall progress through the active learning generations, e.g., `[Generation 2/5]`.

*   **Documentation Structure:**
    *   `/README.md`: The front page of the project. It will contain a concise project summary, a list of key features, clear installation instructions using `uv`, and a "Quick Start" guide with a minimal, copy-pasteable example to get a new user running their first calculation in minutes.
    *   `/docs/`: A new top-level directory for all detailed user documentation.
    *   `/docs/tutorial.md`: A detailed, step-by-step guide to running a full workflow on an example system (e.g., Silicon). This will explain the output of each stage and how to interpret the results.
    *   `/docs/configuration.md`: A comprehensive reference guide for all the parameters in the `input.yaml` file. Each parameter will be documented with its type, default value, and a clear explanation of what it controls.
    *   `/examples/`: A directory containing several well-commented example `input.yaml` files for different material types (e.g., an alloy, a covalent solid, a molecule), which users can use as templates for their own projects.

## 4. Implementation Approach

The implementation will be a final sweep through the codebase to add polish, user-facing features, and documentation, transforming the project from a developer's tool into a user's product.

1.  **Implement the CLI:**
    *   The current entry point of the application (if it's a simple `if __name__ == "__main__":` block) will be completely refactored into the `click` structure in `cli.py`.
    *   The `run` command, its required `config_file` argument, and the options (`--verbose`, `--resume`) will be implemented as designed using `click` decorators.
    *   The `pyproject.toml` file will be configured with a `[project.scripts]` entry point. This will ensure that when the user installs the package (`uv pip install .`), a command-line script named `mlip-pipe` is automatically created and added to their path, making the command available system-wide in the active virtual environment.

2.  **Integrate Logging and Progress Bars:**
    *   The `setup_logger` function will be implemented in `utils/logging_utils.py`.
    *   A methodical pass will be made through the entire codebase (`Orchestrator` and all modules A-E). All existing `print()` statements will be located and replaced with appropriate `logger.info()`, `logger.warning()`, or `logger.error()` calls. This will provide structured, controllable, and informative output.
    *   In the key iterative loops identified in the design, the code will be wrapped with `rich.progress` contexts to provide real-time, dynamic feedback to the user during long waits. The `rich` library's ability to handle logging without interfering with progress bars will be leveraged.

3.  **Write Documentation:**
    *   **Code Documentation:** A full pass on all files will be performed. Every public class, method, and function will be reviewed to ensure it has a clear, well-formatted docstring explaining its purpose, arguments, and return values. This is crucial for long-term maintainability.
    *   **User Documentation:** The `docs/` directory will be created, and the user guide, a detailed tutorial, and the configuration reference will be written in Markdown. These documents will be written from the perspective of a new user and will avoid internal jargon where possible.
    *   **Example Configurations:** The `examples/` directory will be created, and several well-commented minimal `input.yaml` files will be added to provide users with ready-made templates.

4.  **Perform Benchmark Testing:**
    *   2-3 well-understood materials will be selected for benchmarking (e.g., Silicon, Copper, FePt). These materials have well-known properties that can be used for validation.
    *   The entire, final pipeline will be run for these materials, starting from a minimal config. This will be a "real" run, involving actual DFT calculations, and may take several hours on a compute cluster.
    *   The results will be carefully analyzed. The primary goal is not necessarily to achieve state-of-the-art scientific accuracy, but to verify that the pipeline completes successfully from end-to-end and produces a physically reasonable potential. This will involve writing small post-processing scripts to calculate basic material properties (like the lattice constant or bulk modulus) with the generated potential and comparing them to known values. This acts as the final sanity check for the entire integrated system.

## 5. Test Strategy

The testing for Cycle 05 focuses on the user experience and the end-to-end scientific validity of the pipeline. It shifts from testing mocked components to testing the real, final application.

**Unit Testing Approach (Min 300 words):**

While the focus of this cycle is on higher-level testing, some unit tests for the new UI components are still essential.

*   **CLI Testing:** The `click.testing.CliRunner` provides a powerful way to test the command-line interface in isolation, without actually running the full, time-consuming pipeline.
    *   A test will be written to invoke `mlip-pipe run` with a path to a valid, existing config file. The test will mock the `Orchestrator` class and assert that its `__init__` and `run_full_pipeline` methods are called, confirming that the CLI correctly dispatches to the backend.
    *   Another test will invoke `mlip-pipe run --config non_existent_file.yaml`. Since we use `type=click.Path(exists=True)`, we don't need to test our own code, but rather confirm that `click`'s built-in error handling is active and provides a clear "File not found" message to the user.
    *   We will test the help text by invoking `mlip-pipe run --help` and asserting that the output contains the descriptions for all our defined options and arguments.
    *   The `--verbose` flag will be tested by running a command with it and inspecting the configured logging level. We will mock our `setup_logger` function and assert that it is called with `level='DEBUG'`.

**End-to-End (E2E) / Benchmark Testing (Min 300 words):**

This is the most important part of the test strategy for this final cycle. These are not mocked tests; they are full runs of the software designed to validate its real-world performance and scientific correctness. These tests are the final acceptance criteria for the project.

*   **Benchmark 1: Covalent Solid (Silicon):**
    *   **Execution:** The full pipeline will be executed, starting from a minimal configuration file: `system: {elements: ["Si"]}`. This will be run on a machine with Quantum Espresso and all other dependencies installed.
    *   **Verification:**
        1.  The primary assertion is that the pipeline must complete the entire active learning workflow without any crashes or unhandled exceptions.
        2.  A final set of MLIP model files (e.g., in `gen_5/`) must be generated.
        3.  **Scientific Sanity Check:** A post-processing script will be written that uses the `ase` library to load the generated potential. The script will use this potential to calculate the equilibrium lattice constant and bulk modulus of a bulk Silicon crystal. The test will assert that the calculated values are within a reasonable physical range (e.g., the lattice constant should be within +/- 10% of the experimental value of ~5.43 Å). This confirms the potential is not physically nonsensical.
*   **Benchmark 2: Metallic Alloy (FePt):**
    *   **Execution:** The full pipeline will be run again, this time starting with a minimal config for FePt (`system: {elements: ["Fe", "Pt"]}`).
    *   **Verification:**
        1.  The pipeline must complete successfully.
        2.  **Scientific Sanity Check:** A second post-processing script will be written. This script will construct two different atomic structures of FePt: the ordered L1_0 phase and a random solid solution (disordered) phase. It will use the generated potential to calculate the total energy of both structures. The test will assert that the energy of the L1_0 phase is lower than the energy of the disordered phase, as this is a fundamental, well-known property of this alloy. This validates the potential's ability to capture basic chemical ordering.

These benchmark tests serve as the final, holistic validation that the MLIP-AutoPipe project has successfully achieved its goal of creating a reliable, automated, and scientifically sound workflow.
