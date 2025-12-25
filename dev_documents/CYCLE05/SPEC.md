# Cycle 05 Specification: User Interface and Finalisation

**Version:** 1.0.0
**Status:** Final
**Cycle Goal:** To polish the MLIP-AutoPipe into a distributable, user-friendly tool by developing a clean command-line interface (CLI), comprehensive documentation, and robust packaging.

## 1. Summary

Cycle 05 is the final phase of development, focusing on usability, accessibility, and professional polish. While the preceding cycles have built a powerful and autonomous engine, this cycle ensures that the engine is controllable, understandable, and easily deployable by the target audience of computational materials scientists. The primary goal is to move beyond a collection of developer-run scripts and create a polished, cohesive software package. This involves three main pillars of work: creating a user-friendly Command-Line Interface (CLI), writing comprehensive documentation, and packaging the entire project for easy distribution and installation.

The first major task is to develop a formal CLI using a modern framework like `Typer` or `Click`. This will provide a single, consistent entry point for all of the pipeline's functions. The CLI will feature clear commands (e.g., `mlip-pipe run`, `mlip-pipe status`), intuitive options, and helpful, automatically generated help messages. Crucially, it will include rich console output, such as progress bars for long-running tasks, status indicators, and well-formatted summaries of results. This moves the user experience from watching raw log files to interacting with a professional piece of software.

The second pillar is documentation. We will create a comprehensive user guide that explains not just *how* to use the software, but also the key concepts behind it. This will include tutorials with step-by-step examples for common use cases (e.g., generating a potential for an alloy, a molecule), a detailed API reference for developers who may wish to extend the tool, and a clear explanation of the `input.yaml` configuration file.

Finally, we will finalize the project's packaging for distribution via the Python Package Index (PyPI). This involves ensuring the `pyproject.toml` file is complete with all metadata, dependencies are correctly specified, and the package can be reliably built. The goal is to make installation as simple as `pip install mlip-autopipe` or `uv pip install mlip-autopipe`, allowing users to get started with the tool in minutes. This cycle will culminate in a series of end-to-end "golden" tests to ensure the final, packaged application is robust, reproducible, and ready for its first official release.

## 2. System Architecture

The architecture for Cycle 05 primarily involves adding a new presentation layer (the CLI) on top of the existing backend and formalizing the project's structure for distribution.

**Component Breakdown:**

*   **Command-Line Interface (`main.py`):** This will be the main entry point for the application.
    *   **Framework:** A library like `Typer` will be used to build a structured CLI application.
    *   **Commands:**
        *   `mlip-pipe run [INPUT_YAML]`: The primary command to execute the full pipeline. It will instantiate and run the `Orchestrator`.
        *   `mlip-pipe status [RUN_ID]`: A command to inspect the state of a completed or ongoing run, reading from the database and state files.
        *   `mlip-pipe package-info`: A command to provide information about the package and its dependencies.
    *   **User Experience:** The CLI will use a library like `rich` to provide an enhanced console experience. This includes:
        *   **Progress Bars:** Displayed for DFT calculations, MD simulations, and training epochs.
        *   **Styled Output:** Using colors and formatting to clearly distinguish between informational messages, warnings, and errors.
        *   **Summary Tables:** Displaying key results in a clean, tabular format.

*   **Packaging (`pyproject.toml`):** The `pyproject.toml` will be finalized to make the project installable.
    *   **Entry Point:** An entry point will be defined, e.g., `[project.scripts] mlip-pipe = "mlip_pipe.main:app"`, which creates the `mlip-pipe` executable upon installation.
    *   **Dependencies:** All dependencies, including those for external tools that might need to be compiled (like LAMMPS, if bundled), will be clearly specified. Optional dependencies for different MLIP frameworks can be defined.
    *   **Metadata:** All required package metadata (author, license, description, etc.) will be completed for uploading to PyPI.

*   **Documentation (`docs/`):** A new top-level `docs/` directory will be created.
    *   **Generator:** A static site generator like Sphinx or MkDocs will be used.
    *   **Content:**
        *   `index.md`: Project overview.
        *   `installation.md`: Clear, simple installation instructions.
        *   `tutorial.md`: A step-by-step guide for a new user.
        *   `configuration.md`: A detailed reference for the `input.yaml` file.
        *   `api/`: Auto-generated API documentation for the source code.

The existing backend (Orchestrator, Modules A-E) will remain largely unchanged, but the `Orchestrator` will be modified to accept a callback function for reporting progress, allowing the CLI to be decoupled from the core logic.

## 3. Design Architecture

The design focuses on the separation of concerns between the core logic and the user interface.

**Key Classes and APIs:**

*   **`mlip_pipe.main.app`**
    *   This will be the `Typer` application object.
    *   `@app.command()`
        `run(input_file: Path)`: The function that implements the `run` command. It will be responsible for:
        1.  Parsing the command-line arguments.
        2.  Creating a `Rich` console object.
        3.  Creating a progress reporting callback function.
        4.  Instantiating the `Orchestrator`.
        5.  Passing the callback to the `Orchestrator`.
        6.  Calling the `Orchestrator`'s main execution method.
        7.  Handling any exceptions and printing user-friendly error messages to the console.

*   **`mlip_pipe.orchestrator.Orchestrator`**
    *   `__init__(self, config, progress_callback: Callable = None)`: The constructor will be updated to accept an optional callback function.
    *   Inside its long-running loops (e.g., iterating over structures for DFT labelling), the `Orchestrator` will call this callback to report progress, e.g., `self.progress_callback({"step": "DFT Labelling", "progress": i+1, "total": n})`. This allows the CLI to update a progress bar without the core logic needing to know anything about the console.

*   **`mlip_pipe.ui.progress.RichProgressReporter`**
    *   A new helper class that encapsulates the logic for displaying progress using the `rich` library. The `run` command function will instantiate this class and pass its `update` method as the callback to the `Orchestrator`.

## 4. Implementation Approach

1.  **CLI Scaffolding:**
    *   Choose a CLI framework (`Typer` is a good choice for its simplicity and features).
    *   Set up the basic `main.py` with the `Typer` app object and the main `run` command.
    *   Define the entry point in `pyproject.toml` and test the installation locally using `uv pip install -e .`. Verify that the `mlip-pipe` command becomes available in the shell.

2.  **Progress Reporting Integration:**
    *   Modify the `Orchestrator`'s constructor and internal methods to accept and use the progress callback as designed. This is a small but important change that decouples the backend from the UI.
    *   Implement the `RichProgressReporter` class. This class will manage the `rich.progress.Progress` object, defining columns for description, percentage, and ETA. Its `update` method will parse the dictionary from the callback and update the appropriate progress bar.

3.  **Enhance CLI Output:**
    *   Integrate the `RichProgressReporter` into the `run` command function.
    *   Add styled print statements (`rich.print`) for key events, such as "[green]Pipeline completed successfully![/green]".
    *   Implement robust exception handling. A top-level `try...except` block in the `run` command will catch any exceptions from the backend, log the full traceback to a file for debugging, and print a simple, helpful error message to the user.

4.  **Documentation:**
    *   Set up the chosen documentation generator (e.g., `mkdocs`).
    *   Write the main content pages: Installation, Tutorial, Configuration Reference. The tutorial should be a complete, runnable example.
    *   Configure the tool to auto-generate API documentation from the code's docstrings. Ensure all public classes and methods have clear, well-formatted docstrings.

5.  **Packaging and Finalisation:**
    *   Thoroughly review and complete all sections of `pyproject.toml`.
    *   Perform a clean build of the package (`uv build`).
    *   Test the installation of the built wheel in a clean, fresh virtual environment to ensure all dependencies are correctly specified and the entry point script works.

6.  **"Golden" End-to-End Tests:**
    *   Create a final set of tests that run the full pipeline via the CLI command itself, using `subprocess.run(['mlip-pipe', 'run', ...])`.
    *   These tests will use a fixed `input.yaml` and a fixed random seed.
    *   The test will assert that the command completes with exit code 0.
    *   Most importantly, it will assert that the final trained potential file is bit-for-bit identical to a "golden" reference file stored in the repository. This provides the ultimate guarantee of reproducibility.

## 5. Test Strategy

Testing for Cycle 05 focuses on the user-facing aspects of the application and the overall package integrity.

**Unit Testing Approach (Min 300 words):**
*   **CLI Tests:** We will use a framework like `pytest-click` (which works with Typer) to test the CLI in isolation. We will not run the full pipeline in these tests.
    *   We will mock the `Orchestrator` class.
    *   **Test Command Invocation:** We will invoke the `run` command with a path to a test `input.yaml`. We will then assert that the `Orchestrator` was instantiated and that its `run_full_pipeline` method was called exactly once.
    *   **Test Argument Parsing:** We will test that file paths are correctly passed from the command line to the orchestrator.
    *   **Test Error Handling:** We will configure the mocked `Orchestrator` to raise an exception. We will then run the `run` command and capture its output, asserting that a user-friendly error message was printed to the console and that the exit code was non-zero.
    *   **Test Progress Callback:** We can use a mock callback function to assert that the `Orchestrator` is called with the progress reporter, and we can even simulate the `Orchestrator` calling the callback to ensure the UI layer would respond.

*   **Documentation Tests:** The code examples in the documentation (especially in the tutorial) will be written as `doctest`s. This means the documentation generator or a testing plugin can automatically run the code in the documentation and verify that its output matches what is written. This ensures the documentation never becomes outdated or contains incorrect examples.

**Integration Testing Approach (Min 300 words):**
The primary integration tests for this cycle are the "golden" tests, which provide the highest level of confidence in the final, packaged application.

*   **`test_golden_run_alloy`:**
    1.  **Setup:** The test will have a directory containing a specific `input.yaml` for an alloy (e.g., SiGe) and a "golden" reference potential file that was generated from a previous, trusted run with the same input and a fixed random seed.
    2.  **Execution:** The test will use `subprocess.run` to execute the packaged CLI command: `mlip-pipe run path/to/sige_input.yaml --seed 12345`.
    3.  **Assertions:**
        *   Assert that the command completes with an exit code of 0.
        *   Assert that a new potential file is created in the output directory.
        *   Compare the newly generated potential file with the "golden" reference file. The test will perform a binary comparison (e.g., comparing the SHA256 hashes of the files). The hashes must be identical. This proves that the entire pipeline, from parsing input to the final floating-point operations of the training, is perfectly reproducible.

*   **Installation Test:** A separate test, likely run only in the CI/CD pipeline, will create a completely empty virtual environment, install the application from the built wheel using `uv pip install`, and then run the `mlip-pipe --help` command. This verifies that the installation process is sound and that the entry point script is correctly installed and executable.