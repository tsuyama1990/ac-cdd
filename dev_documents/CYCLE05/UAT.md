# Cycle 05 User Acceptance Testing (UAT)

**Version:** 1.0.0
**Status:** Final
**Cycle Goal:** To verify that the final application is user-friendly, well-documented, and can be easily installed and run by a typical user.

## 1. Test Scenarios

This final UAT focuses on the overall user experience. The scenarios are designed from the perspective of a new user interacting with the packaged application for the first time. They validate the CLI, the clarity of the output, the documentation, and the installation process.

| Scenario ID | Priority | Summary                                                                                         |
| :---------- | :------- | :---------------------------------------------------------------------------------------------- |
| UAT-C05-01  | **High** | Verify that the `mlip-pipe run` command successfully executes the full pipeline and displays clear progress. |
| UAT-C05-02  | **High** | Ensure the application can be easily installed in a clean environment using `uv pip install`.     |
| UAT-C05-03  | **Medium** | Validate that the CLI provides helpful error messages for invalid user input.                 |
| UAT-C05-04  | **Medium** | Confirm that a user can follow the tutorial in the documentation to get a successful result.    |

---

### **Scenario UAT-C05-01: Successful End-to-End Run via CLI**

*   **Description:** This scenario represents the primary "happy path" for a user. It tests the main `run` command of the CLI, ensuring that it correctly initiates the pipeline and provides informative feedback to the user throughout the process.
*   **Success Criteria:**
    *   A user executes `mlip-pipe run path/to/input.yaml` in their terminal.
    *   The command must start without errors.
    *   The console must display clear status messages indicating the current stage of the pipeline (e.g., "Generating initial structures...", "Running surrogate MD...", "Performing DFT labelling...").
    *   For long-running stages like DFT labelling and MD simulations, a progress bar must be displayed, showing the percentage of completion and an estimated time remaining.
    *   Upon successful completion, a clear, color-coded success message (e.g., in green) should be printed to the console.
    *   The final potential file must be created in the expected output location.

---

### **Scenario UAT-C05-02: Installation from Package**

*   **Description:** A user's first experience with the software is installing it. This scenario validates that the packaging is correctly configured and that the installation process is simple and reliable using standard Python tooling.
*   **Success Criteria:**
    *   A user creates a new, empty Python virtual environment (`uv venv`).
    *   The user runs `uv pip install mlip-autopipe` (assuming the package is hosted on PyPI, or pointing to the built wheel file).
    *   The installation must complete successfully without any dependency conflicts or compilation errors.
    *   After installation, the user must be able to run `mlip-pipe --help`.
    *   The help command must execute successfully and display a well-formatted help message listing the available commands and options.

---

### **Scenario UAT-C05-03: User Input Error Handling**

*   **Description:** This scenario tests the user-friendliness of the CLI when given bad input. The system should not crash with an intimidating stack trace but should provide a helpful message that guides the user to fix the problem.
*   **Success Criteria:**
    *   **Case 1 (File Not Found):** The user runs `mlip-pipe run path/to/nonexistent/file.yaml`. The application must not crash. It should print a clear error message like "Error: Input file not found at 'path/to/nonexistent/file.yaml'" and exit gracefully.
    *   **Case 2 (Invalid Command):** The user runs `mlip-pipe foobar`. The CLI framework should automatically catch this and display a message like "Error: No such command 'foobar'." along with a list of valid commands.
    *   The application must exit with a non-zero status code in all error cases.

---

### **Scenario UAT-C05-04: Documentation Tutorial**

*   **Description:** This scenario validates the quality and correctness of the user documentation. A non-expert user should be able to follow the main tutorial and successfully run the pipeline to completion, demonstrating that the documentation is fit for purpose.
*   **Success Criteria:**
    *   A user navigates to the hosted documentation website (or opens the local HTML files).
    *   The user follows the steps in the "Installation" guide and successfully installs the application.
    *   The user then follows the "Tutorial" section. This includes copying the example `input.yaml` provided in the documentation.
    *   The user runs the `mlip-pipe run` command as instructed in the tutorial.
    *   The pipeline must execute and complete successfully, producing the same or very similar results to those described in the tutorial.
    *   The user must be able to complete the tutorial without encountering any undocumented errors or steps.

## 2. Behavior Definitions

### **GIVEN/WHEN/THEN Definitions**

**Scenario: UAT-C05-01**
*   **GIVEN** a valid `input.yaml` file.
*   **AND** the `mlip-autopipe` package is installed.
*   **WHEN** the user runs `mlip-pipe run input.yaml` in the terminal.
*   **THEN** the console should display a message indicating that the pipeline has started.
*   **AND** a progress bar should appear during the DFT calculation phase.
*   **AND** after several minutes, the process should complete.
*   **AND** a message like "[SUCCESS] MLIP trained and saved to output/potential.pt" should be displayed.

**Scenario: UAT-C05-02**
*   **GIVEN** a user has created and activated a new Python virtual environment with `uv`.
*   **WHEN** the user runs `uv pip install /path/to/mlip_autopipe-*.whl`.
*   **THEN** the command should complete with no errors.
*   **AND** running the command `mlip-pipe --version` should print the correct version number.

**Scenario: UAT-C05-03**
*   **GIVEN** the `mlip-autopipe` package is installed.
*   **WHEN** the user runs `mlip-pipe run file_does_not_exist.yaml`.
*   **THEN** the program must exit immediately.
*   **AND** a colored error message should be printed to the console stating that the input file could not be found.
*   **AND** the exit code of the shell process must be 1 (or non-zero).

**Scenario: UAT-C05-04**
*   **GIVEN** a user has access to the project's documentation.
*   **WHEN** the user follows the installation and tutorial instructions exactly as written.
*   **THEN** they should be able to successfully install the software.
*   **AND** they should be able to successfully run the example project.
*   **AND** the output they see on their screen should match the example output shown in the documentation.